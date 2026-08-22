"""
Region capture module for SnapEdit.

Provides an interactive fullscreen overlay that lets the user click and drag
to select a rectangular screen region. The selected region is captured using
`mss` and emitted as a QPixmap signal.

Features:
    - Frameless, translucent overlay covering all monitors
    - Crosshair cursor for precise selection
    - Dim overlay with the selected region highlighted (clear)
    - Live dimension label (WxH) displayed near the cursor
    - Escape key cancels the selection
    - Multi-monitor support via combined virtual desktop geometry

Classes:
    RegionSelector: The interactive overlay widget.
"""
import mss

from PyQt6.QtCore import Qt, pyqtSignal, QRect, QPoint, QEventLoop
from PyQt6.QtGui import (
    QPixmap, QImage, QPainter, QColor, QCursor, QPen, QFont,
    QFontMetrics, QRegion
)
from PyQt6.QtWidgets import QWidget, QApplication


class RegionSelector(QWidget):
    """Fullscreen overlay for interactive rectangular region selection.

    The user clicks and drags to define a capture region. The overlay dims
    the entire screen except for the selected rectangle, which remains clear.
    Upon mouse release, the selected region is captured using `mss` and
    emitted via the `region_captured` signal.

    Signals:
        region_captured(QPixmap): Emitted with the captured region image.
        selection_cancelled(): Emitted when the user presses Escape.

    Usage:
        selector = RegionSelector()
        selector.region_captured.connect(handle_capture)
        selector.start()
    """

    region_captured = pyqtSignal(QPixmap)
    selection_cancelled = pyqtSignal()

    # Overlay dim color (semi-transparent black)
    _OVERLAY_COLOR = QColor(0, 0, 0, 120)
    # Selection border color
    _BORDER_COLOR = QColor(0, 174, 255, 220)
    # Dimension label colors
    _LABEL_BG_COLOR = QColor(0, 0, 0, 180)
    _LABEL_TEXT_COLOR = QColor(255, 255, 255, 230)

    def __init__(self, parent=None):
        """Initialize the RegionSelector overlay.

        Args:
            parent: Optional parent widget.
        """
        super().__init__(parent)

        # Selection state
        self._origin = QPoint()        # Where the mouse press started
        self._current = QPoint()       # Current mouse position
        self._selecting = False        # Whether a drag is in progress
        self._selection_rect = QRect() # The normalized selection rectangle
        self._desktop_pixmap = QPixmap()
        self._dimmed_pixmap = QPixmap()
        self._first_drag_frame = False

        # Configure window flags for frameless, always-on-top overlay
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        # This widget paints a cached desktop image, so it can stay opaque and
        # avoid expensive full-screen translucent composition while dragging.
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent)
        self.setCursor(QCursor(Qt.CursorShape.CrossCursor))
        self.setMouseTracking(True)

    def start(self):
        """Show the overlay covering all screens and begin selection mode.

        Calculates the combined bounding box of all screens and positions
        the overlay to span the entire virtual desktop.
        """
        # Calculate the combined geometry of all screens
        virtual_geometry = self._get_virtual_geometry()
        self.setGeometry(virtual_geometry)
        self._cache_desktop(virtual_geometry)
        self.show()
        self.activateWindow()
        self.raise_()
        # Ensure the native window and its first full backing-store frame are
        # ready before a fast first drag can request partial repaints.
        QApplication.processEvents(
            QEventLoop.ProcessEventsFlag.ExcludeUserInputEvents
        )

    def _get_virtual_geometry(self) -> QRect:
        """Calculate the bounding rectangle spanning all screens.

        Returns:
            QRect covering the combined virtual desktop area.
        """
        app = QApplication.instance()
        screens = app.screens()

        if not screens:
            # Fallback to primary screen
            primary = app.primaryScreen()
            return primary.geometry() if primary else QRect(0, 0, 1920, 1080)

        # Union all screen geometries
        combined = screens[0].geometry()
        for screen in screens[1:]:
            combined = combined.united(screen.geometry())

        return combined

    def _cache_desktop(self, geometry: QRect):
        """Capture and pre-dim the desktop once before showing the overlay."""
        try:
            with mss.mss() as sct:
                screenshot = sct.grab({
                    'left': geometry.x(),
                    'top': geometry.y(),
                    'width': geometry.width(),
                    'height': geometry.height(),
                })
                image = QImage(
                    screenshot.bgra,
                    screenshot.width,
                    screenshot.height,
                    screenshot.width * 4,
                    # MSS exposes BGRA bytes. On Windows, ARGB32's native
                    # little-endian byte order is BGRA in memory.
                    QImage.Format.Format_ARGB32,
                ).copy()

            self._desktop_pixmap = QPixmap.fromImage(image)
            self._dimmed_pixmap = self._desktop_pixmap.copy()
            painter = QPainter(self._dimmed_pixmap)
            painter.fillRect(self._dimmed_pixmap.rect(), self._OVERLAY_COLOR)
            painter.end()
        except Exception as exc:
            # Keep a functional (plain dim) selector if preview capture fails.
            print(f"[SnapEdit] Desktop preview failed: {exc}")
            self._desktop_pixmap = QPixmap()
            self._dimmed_pixmap = QPixmap()

    # ── Qt Event Handlers ──────────────────────────────────────────────

    def paintEvent(self, event):
        """Paint the dim overlay and highlight the selection region."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Qt clips these draws to event.region(), so pointer movement copies
        # only pixels whose selected/unselected state actually changed.
        dirty_rect = event.rect()
        if not self._dimmed_pixmap.isNull():
            painter.drawPixmap(dirty_rect, self._dimmed_pixmap, dirty_rect)
        else:
            painter.fillRect(dirty_rect, self._OVERLAY_COLOR)

        if self._selecting and self._selection_rect.isValid():
            rect = self._selection_rect

            # Restore cached, undimmed pixels instead of asking the desktop
            # compositor to process a translucent full-screen window.
            if not self._desktop_pixmap.isNull():
                painter.drawPixmap(rect, self._desktop_pixmap, rect)

            # Draw selection border
            pen = QPen(self._BORDER_COLOR, 2, Qt.PenStyle.SolidLine)
            painter.setPen(pen)
            painter.drawRect(rect)

            # Draw dimension label near the bottom-right of the selection
            self._draw_dimension_label(painter, rect)

        painter.end()

    def _dimension_label_rect(self, rect: QRect) -> QRect:
        """Return the pixels occupied by the live dimension label."""
        font = QFont("Segoe UI", 11, QFont.Weight.Bold)
        metrics = QFontMetrics(font, self)
        label_text = f"{rect.width()} × {rect.height()}"
        padding = 6
        text_w = max(
            metrics.horizontalAdvance(label_text),
            metrics.boundingRect(label_text).width(),
        )
        label_w = text_w + padding * 2
        label_h = metrics.height() + padding * 2
        gap = 6

        # Align to the selection's right edge, then clamp to both horizontal
        # edges of the overlay.
        max_x = max(0, self.width() - label_w)
        label_x = max(0, min(rect.right() - label_w + 1, max_x))

        below_y = rect.bottom() + gap + 1
        above_y = rect.top() - label_h - gap
        max_y = max(0, self.height() - label_h)

        if below_y <= max_y:
            label_y = below_y
        elif above_y >= 0:
            label_y = above_y
        else:
            # A tall selection may leave no room outside. Put the label just
            # inside its bottom edge and keep it fully within the overlay.
            inside_y = rect.bottom() - label_h - gap + 1
            label_y = max(0, min(inside_y, max_y))

        return QRect(label_x, label_y, label_w, label_h)

    def _draw_dimension_label(self, painter: QPainter, rect: QRect):
        """Draw a WxH dimension label near the selection rectangle.

        The label is positioned just below the bottom-right corner of the
        selection. If there isn't enough room below, it's placed above.

        Args:
            painter: The active QPainter.
            rect: The current selection rectangle.
        """
        width = rect.width()
        height = rect.height()
        label_text = f"{width} × {height}"

        # Configure font
        font = QFont("Segoe UI", 11, QFont.Weight.Bold)
        painter.setFont(font)

        # Draw label background
        label_rect = self._dimension_label_rect(rect)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(self._LABEL_BG_COLOR)
        painter.drawRoundedRect(label_rect, 4, 4)

        # Draw label text
        painter.setPen(self._LABEL_TEXT_COLOR)
        painter.drawText(
            label_rect,
            Qt.AlignmentFlag.AlignCenter,
            label_text
        )

    def mousePressEvent(self, event):
        """Handle mouse press to begin region selection."""
        if event.button() == Qt.MouseButton.LeftButton:
            self._origin = event.pos()
            self._current = event.pos()
            self._selecting = True
            self._selection_rect = QRect()
            self._first_drag_frame = True
            self.update()

    def mouseMoveEvent(self, event):
        """Handle mouse move to update the selection rectangle."""
        if self._selecting:
            old_rect = self._selection_rect
            self._current = event.pos()
            new_rect = QRect(
                self._origin, self._current
            ).normalized()
            self._selection_rect = new_rect
            if self._first_drag_frame and new_rect.isValid():
                self._first_drag_frame = False
                # Paint only the thin border and label synchronously so the
                # first visual feedback is immediate even for a 4K region.
                outer = QRegion(new_rect.adjusted(-3, -3, 3, 3))
                inner = QRegion(new_rect.adjusted(3, 3, -3, -3))
                first_visual = outer.subtracted(inner).united(
                    QRegion(
                        self._dimension_label_rect(new_rect).adjusted(
                            -2, -2, 2, 2
                        )
                    )
                )
                self.repaint(first_visual)
                # Restore the undimmed selection interior asynchronously.
                self.update(QRegion(new_rect).united(first_visual))
            else:
                self._update_selection_delta(old_rect, new_rect)

    def _update_selection_delta(self, old_rect: QRect, new_rect: QRect):
        """Repaint only changed fill, border, and label pixels."""
        dirty = QRegion(old_rect).xored(QRegion(new_rect))

        for rect in (old_rect, new_rect):
            if not rect.isValid():
                continue
            outer = QRegion(rect.adjusted(-3, -3, 3, 3))
            inner = QRegion(rect.adjusted(3, 3, -3, -3))
            dirty = dirty.united(outer.subtracted(inner))
            label_dirty = self._dimension_label_rect(rect).adjusted(-2, -2, 2, 2)
            dirty = dirty.united(QRegion(label_dirty))

        self.update(dirty)

    def mouseReleaseEvent(self, event):
        """Handle mouse release to finalize and capture the selected region."""
        if event.button() == Qt.MouseButton.LeftButton and self._selecting:
            self._selecting = False
            self._current = event.pos()
            self._selection_rect = QRect(
                self._origin, self._current
            ).normalized()

            # Minimum selection size to avoid accidental clicks
            if (self._selection_rect.width() < 5
                    or self._selection_rect.height() < 5):
                self.update()
                return

            # Hide the overlay before capturing to avoid capturing it
            self.hide()
            QApplication.processEvents()

            # Capture the selected region
            pixmap = self._capture_region(self._selection_rect)
            if pixmap and not pixmap.isNull():
                self.region_captured.emit(pixmap)

            self.close()

    def keyPressEvent(self, event):
        """Handle key press — Escape cancels the selection."""
        if event.key() == Qt.Key.Key_Escape:
            self._selecting = False
            self.selection_cancelled.emit()
            self.close()
        else:
            super().keyPressEvent(event)

    # ── Capture Logic ──────────────────────────────────────────────────

    def _capture_region(self, rect: QRect) -> QPixmap:
        """Capture a screen region defined by the widget-local rectangle.

        Converts widget coordinates to absolute screen coordinates and
        uses `mss` to grab the pixels.

        Args:
            rect: The selection rectangle in widget coordinates.

        Returns:
            A QPixmap of the captured region, or None on failure.
        """
        try:
            # Convert widget coordinates to global screen coordinates
            top_left = self.mapToGlobal(rect.topLeft())
            abs_x = top_left.x()
            abs_y = top_left.y()
            abs_w = rect.width()
            abs_h = rect.height()

            with mss.mss() as sct:
                region = {
                    'left': abs_x,
                    'top': abs_y,
                    'width': abs_w,
                    'height': abs_h
                }
                screenshot = sct.grab(region)

                image = QImage(
                    screenshot.bgra,
                    screenshot.width,
                    screenshot.height,
                    screenshot.width * 4,
                    QImage.Format.Format_ARGB32,
                ).copy()
                return QPixmap.fromImage(image)

        except Exception as e:
            print(f"[SnapEdit] Region capture failed: {e}")
            return None
