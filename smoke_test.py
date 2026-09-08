"""Verify the actual packaged Qt libraries/plugins with hidden widgets.

No user config, hotkeys, desktop capture, clipboard, or tray is touched.
"""
import json
from pathlib import Path
import sys
import time
import traceback


def run(report_path):
    report = {"ok": False, "frozen": bool(getattr(sys, "frozen", False)),
              "stage": "import Qt/application"}
    try:
        import main
        from PyQt6 import QtCore
        from PyQt6.QtCore import QEvent, QPointF
        from PyQt6.QtGui import QColor, QFont, QPainter, QPixmap
        from PyQt6.QtWidgets import QApplication
        from copy import deepcopy
        from capture.region import RegionSelector
        from editor.editor_window import EditorWindow
        from editor.gallery_dialog import GalleryDialog
        from settings.config import Config, DEFAULT_CONFIG
        from ui_scaling import prepare_ui_fonts
        from ocr.worker import OcrWorker

        report.update(qt=QtCore.qVersion(), pyqt=QtCore.PYQT_VERSION_STR,
                      qtcore_path=QtCore.__file__, main_path=main.__file__)
        if report["frozen"]:
            bundle = Path(sys._MEIPASS).resolve()
            assert Path(QtCore.__file__).resolve().is_relative_to(bundle)
            assert Path(main.__file__).resolve().is_relative_to(bundle)

        report["stage"] = "initialize platform plugin/fonts"
        app = QApplication([])
        app.setStyle("Fusion")
        app.setFont(QFont("Segoe UI Variable", 10))
        app.setQuitOnLastWindowClosed(False)
        prepare_ui_fonts()
        if report["frozen"]:
            from winrt.windows.media.ocr import OcrEngine
            report["ocr_languages"] = [
                language.language_tag
                for language in OcrEngine.available_recognizer_languages
            ]
        controller = main.SnapEditApp.__new__(main.SnapEditApp)
        controller._app = app
        controller._apply_dark_palette()
        assert not controller._create_tray_icon().isNull()

        report["stage"] = "render editor and annotations"
        config = Config.__new__(Config)
        config._data = deepcopy(DEFAULT_CONFIG)
        config._data["save_directory"] = str(Path(report_path).with_suffix(".no-images"))
        screenshot = QPixmap(640, 360)
        screenshot.fill(QColor("#274060"))
        painter = QPainter(screenshot)
        painter.setPen(QColor("white"))
        painter.setFont(QFont("Segoe UI", 32))
        painter.drawText(24, 64, "SnapEdit OCR 123")
        painter.end()
        ocr_worker = OcrWorker(screenshot)
        ocr_text = []
        ocr_errors = []
        ocr_worker.text_ready.connect(ocr_text.append)
        ocr_worker.failed.connect(ocr_errors.append)
        ocr_worker.start()
        deadline = time.monotonic() + 15
        while ocr_worker.isRunning() and time.monotonic() < deadline:
            app.processEvents()
            time.sleep(0.01)
        if ocr_worker.isRunning():
            ocr_worker.terminate()
            ocr_worker.wait(1000)
            raise RuntimeError("Frozen OCR smoke test timed out.")
        app.processEvents()
        if ocr_errors:
            raise RuntimeError(f"Frozen OCR smoke test failed: {ocr_errors[0]}")
        report["ocr_text"] = ocr_text[0] if ocr_text else ""
        if "napEdit" not in report["ocr_text"] or "OCR" not in report["ocr_text"]:
            raise RuntimeError(f"Frozen OCR returned unexpected text: {report['ocr_text']!r}")
        editor = EditorWindow(screenshot, config)
        editor.ensurePolished()
        editor._canvas._add_text(QPointF(30, 30))
        editor._canvas._add_bubble(QPointF(100, 100))
        assert not editor.grab().isNull()
        assert editor._canvas.export_to_pixmap().size() == screenshot.size()
        selector = RegionSelector()
        assert selector._label_metrics.height() > 0
        gallery = GalleryDialog([screenshot], config.save_directory, editor)
        assert not gallery.grab().isNull()
        gallery.dispose()
        gallery.deleteLater()
        selector.close()
        selector.deleteLater()
        editor.close()
        app.processEvents()
        app.sendPostedEvents(None, QEvent.Type.DeferredDelete)

        if sys.platform == "win32":
            import ctypes
            from ctypes import wintypes
            kernel = ctypes.WinDLL("kernel32", use_last_error=True)
            kernel.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
            kernel.GetModuleHandleW.restype = wintypes.HMODULE
            kernel.GetModuleFileNameW.argtypes = [wintypes.HMODULE, wintypes.LPWSTR, wintypes.DWORD]
            module = kernel.GetModuleHandleW("icuuc.dll")
            if module:
                path = ctypes.create_unicode_buffer(32768)
                kernel.GetModuleFileNameW(module, path, len(path))
                report["icu_path"] = path.value

        report.update(ok=True, stage="complete", platform=app.platformName())
    except Exception:
        report["error"] = traceback.format_exc()
    Path(report_path).write_text(json.dumps(report, indent=2), encoding="utf-8")
    return 0 if report["ok"] else 1
