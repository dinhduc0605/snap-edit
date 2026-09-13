"""Interactive scrolling capture session for Windows."""
import os
import time
import ctypes
from ctypes import wintypes
from tempfile import NamedTemporaryFile

import mss
import numpy as np
from PIL import Image
from pynput.keyboard import Key, Listener
from PyQt6.QtCore import QObject, QRect, Qt, QThread, pyqtSignal
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import (
    QApplication, QFrame, QLabel, QVBoxLayout,
)

from capture.region import RegionSelector
from capture.scroll_native import ScrollTarget, release_cursor_clip
from capture.scroll_stitch import StitchError, StripStore, difference, gray, match_vertical
from theme import BORDER, SURFACE, TEXT_PRIMARY, TEXT_SECONDARY
from ui_scaling import WindowScaler, screen_scale


class ScrollRegionSelector(RegionSelector):
    """Select a global screen rectangle without taking the final still frame."""

    region_selected = pyqtSignal(QRect)

    def mouseReleaseEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton or not self._selecting:
            return
        self._selecting = False
        self._current = event.pos()
        self._selection_rect = QRect(self._origin, self._current).normalized()
        if self._selection_rect.width() < 40 or self._selection_rect.height() < 80:
            self._selection_rect = QRect()
            self.update()
            return
        top_left = self.mapToGlobal(self._selection_rect.topLeft())
        selected = QRect(top_left, self._selection_rect.size())
        self.hide()
        self.region_selected.emit(selected)
        self.close()


class ScrollCaptureWorker(QThread):
    progress = pyqtSignal(int, int)
    completed = pyqtSignal(str, str)
    failed = pyqtSignal(str)
    cancelled = pyqtSignal()

    def __init__(self, rect: QRect, parent=None):
        super().__init__(parent)
        self.rect = QRect(rect)
        self._discard = False
        self._stop_requested = False
        self._output_path = None

    def finish(self):
        self._stop_requested = True
        self.requestInterruption()

    def cancel(self):
        self._discard = True
        self._stop_requested = True
        self.requestInterruption()

    def _grab(self, sct):
        shot = sct.grab({
            "left": self.rect.x(), "top": self.rect.y(),
            "width": self.rect.width(), "height": self.rect.height(),
        })
        bgra = np.asarray(shot)
        return np.ascontiguousarray(bgra[:, :, [2, 1, 0]])

    def _settled_frame(self, sct, before):
        previous = before
        stable = 0
        deadline = time.monotonic() + 1.8
        while (time.monotonic() < deadline and not self._stop_requested
               and not self.isInterruptionRequested()):
            time.sleep(0.075)
            current = self._grab(sct)
            if difference(gray(previous), gray(current)) < 2:
                stable += 1
                if stable >= 2:
                    return current
            else:
                stable = 0
            previous = current
        return previous

    @staticmethod
    def _write_result(store):
        image = store.assemble()
        tmp = NamedTemporaryFile(prefix="snapedit-scroll-result-", suffix=".png", delete=False)
        path = tmp.name
        tmp.close()
        try:
            image.save(path, format="PNG")
        except Exception:
            try:
                os.unlink(path)
            except OSError:
                pass
            raise
        finally:
            image.close()
        return path

    def run(self):
        store = None
        target = None
        warning = ""
        previous = None
        margins = None
        try:
            if self._discard:
                self.cancelled.emit()
                return
            target = ScrollTarget(self.rect)
            target.activate()
            time.sleep(0.25)
            target.validate()
            store = StripStore(self.rect.width())
            with mss.mss() as sct:
                previous = self._grab(sct)
                initialized = False
                unchanged = 0
                frames = 1
                self.progress.emit(frames, previous.shape[0])

                while not self._stop_requested and not self.isInterruptionRequested():
                    target.scroll(2)
                    current = self._settled_frame(sct, previous)
                    if self._stop_requested or self.isInterruptionRequested():
                        break
                    match = match_vertical(previous, current, margins)
                    if match.shift == 0:
                        unchanged += 1
                        if unchanged >= 2:
                            break
                        previous = current
                        continue
                    unchanged = 0
                    if margins is None:
                        margins = (match.top, match.bottom)
                    top, bottom = margins
                    content_end = len(previous) - bottom
                    if not initialized:
                        store.append(previous[:content_end])
                        initialized = True
                    store.append(current[content_end-match.shift:content_end])
                    previous = current
                    frames += 1
                    self.progress.emit(frames, store.height + bottom)

                if self._discard:
                    self.cancelled.emit()
                    return
                if not initialized:
                    store.append(previous)
                elif margins and margins[1]:
                    store.append(previous[len(previous)-margins[1]:])
                self._output_path = self._write_result(store)
                if self._discard:
                    os.unlink(self._output_path)
                    self._output_path = None
                    self.cancelled.emit()
                    return
                self.completed.emit(self._output_path, warning)
                self._output_path = None
        except (StitchError, RuntimeError, OSError) as exc:
            if self._discard:
                self.cancelled.emit()
                return
            warning = str(exc)
            if store is not None and previous is not None:
                try:
                    if not store.height:
                        store.append(previous)
                    self._output_path = self._write_result(store)
                    self.completed.emit(self._output_path, warning)
                    self._output_path = None
                    return
                except Exception:
                    pass
            self.failed.emit(warning)
        except Exception as exc:
            self.failed.emit(f"Scroll capture failed: {exc}")
        finally:
            if target is not None:
                try:
                    target.restore_cursor()
                except Exception:
                    pass
            if store is not None:
                store.close()
            if self._output_path:
                try:
                    os.unlink(self._output_path)
                except OSError:
                    pass


class ScrollControl(QFrame):
    finish_requested = pyqtSignal()
    cancel_requested = pyqtSignal()

    def __init__(self, rect: QRect):
        super().__init__(None, Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint
                         | Qt.WindowType.WindowStaysOnTopHint
                         | Qt.WindowType.WindowDoesNotAcceptFocus)
        self._capture_rect = QRect(rect)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setObjectName("scrollControl")
        self.setStyleSheet(f"""
            QFrame#scrollControl {{ background: {SURFACE}; border: 1px solid {BORDER}; border-radius: 8px; }}
            QLabel {{ color: {TEXT_SECONDARY}; border: none; }}
            QLabel#title {{ color: {TEXT_PRIMARY}; font-weight: 600; }}
        """)
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 10, 12, 10)
        root.setSpacing(7)
        title = QLabel("Scroll capture")
        title.setObjectName("title")
        root.addWidget(title)
        self.status = QLabel("Starting…")
        root.addWidget(self.status)
        self.pointer_hint = QLabel("Pointer is locked while scrolling")
        root.addWidget(self.pointer_hint)
        self.hint = QLabel("Press Enter to finish · Esc to cancel")
        root.addWidget(self.hint)
        self._scaler = WindowScaler(self, resize_window=False)
        self._listener = None

    def show_near_selection(self):
        screen = QApplication.screenAt(self._capture_rect.center()) or QApplication.primaryScreen()
        self._scaler.apply(screen_scale(screen), resize=False)
        self.adjustSize()
        area = screen.availableGeometry()
        x = min(max(self._capture_rect.left(), area.left()+8), area.right()-self.width()-8)
        above = self._capture_rect.top() - self.height() - 10
        below = self._capture_rect.bottom() + 10
        y = above if above >= area.top()+8 else below
        y = min(max(y, area.top()+8), area.bottom()-self.height()-8)
        self.move(x, y)
        self.show()
        self._exclude_from_capture()
        self._listener = Listener(on_press=self._on_key)
        self._listener.daemon = True
        self._listener.start()

    def _exclude_from_capture(self):
        try:
            api = ctypes.WinDLL("user32", use_last_error=True)
            api.SetWindowDisplayAffinity.argtypes = [wintypes.HWND, wintypes.DWORD]
            api.SetWindowDisplayAffinity.restype = wintypes.BOOL
            api.SetWindowDisplayAffinity(wintypes.HWND(int(self.winId())), 0x11)
        except Exception:
            pass

    def _on_key(self, key):
        if key == Key.esc:
            self.cancel_requested.emit()
            return False
        if key == Key.enter:
            self.finish_requested.emit()
            return False
        return None

    def set_progress(self, frames, height):
        self.status.setText(f"{frames} frames · {height:,} px")

    def closeEvent(self, event):
        if self._listener is not None:
            self._listener.stop()
            self._listener = None
        self._scaler.dispose()
        super().closeEvent(event)


class ScrollCaptureSession(QObject):
    capture_ready = pyqtSignal(QPixmap)
    message = pyqtSignal(str)
    finished = pyqtSignal()

    def __init__(self, rect: QRect, parent=None):
        super().__init__(parent)
        self.control = ScrollControl(rect)
        self.worker = ScrollCaptureWorker(rect, self)
        self.control.finish_requested.connect(self.finish)
        self.control.cancel_requested.connect(self.cancel)
        self.worker.progress.connect(self.control.set_progress)
        self.worker.completed.connect(self._completed)
        self.worker.failed.connect(self._failed)
        self.worker.cancelled.connect(self._cancelled)
        self.worker.finished.connect(self._thread_finished)

    def start(self):
        self.control.show_near_selection()
        self.worker.start()

    def finish(self):
        self.worker.finish()
        release_cursor_clip()

    def cancel(self):
        self.worker.cancel()
        release_cursor_clip()

    def _completed(self, path, warning):
        pixmap = QPixmap(path)
        try:
            os.unlink(path)
        except OSError:
            pass
        if warning:
            self.message.emit(warning)
        if pixmap.isNull():
            self.message.emit("Could not create the scrolling screenshot.")
        else:
            self.capture_ready.emit(pixmap)

    def _failed(self, message):
        self.message.emit(message)

    def _cancelled(self):
        pass

    def _thread_finished(self):
        self.control.close()
        self.control.deleteLater()
        self.finished.emit()

    def wait(self, milliseconds=3000):
        return self.worker.wait(milliseconds)

    def dispose(self):
        self.cancel()
        if self.worker.isRunning():
            self.worker.wait(5000)
        if self.worker.isRunning():
            self.worker.terminate()
            self.worker.wait(1000)
        release_cursor_clip()
        self.control.close()
