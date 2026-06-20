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
from PIL import Image

from PyQt6.QtCore import Qt, pyqtSignal, QRect, QPoint
from PyQt6.QtGui import (
    QPixmap, QImage, QPainter, QColor, QCursor, QPen, QFont
)
from PyQt6.QtWidgets import QWidget, QApplication


def pil_to_qpixmap(pil_image: Image.Image) -> QPixmap:
    """Convert a PIL Image to a QPixmap.

    Args:
        pil_image: The source PIL Image to convert.

    Returns:
        A QPixmap containing the image data.
    """
    if pil_image.mode != 'RGBA':
        pil_image = pil_image.convert('RGBA')
    data = pil_image.tobytes('raw', 'RGBA')
    qimage = QImage(
        data,
        pil_image.width,
        pil_image.height,
        QImage.Format.Format_RGBA8888
    )
    return QPixmap.fromImage(qimage)


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

        # Configure window flags for frameless, always-on-top overlay
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
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
        self.show()
        self.activateWindow()
        self.raise_()

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

    # ── Qt Event Handlers ──────────────────────────────────────────────

    def paintEvent(self, event):
        """Paint the dim overlay and highlight the selection region."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Draw the dim overlay across the entire widget
        painter.fillRect(self.rect(), self._OVERLAY_COLOR)

        if self._selecting and self._selection_rect.isValid():
            rect = self._selection_rect

            # Clear the selected region (punch a hole through the overlay)
            painter.setCompositionMode(
                QPainter.CompositionMode.CompositionMode_Clear
            )
            painter.fillRect(rect, Qt.GlobalColor.transparent)

            # Switch back to normal composition for the border
            painter.setCompositionMode(
                QPainter.CompositionMode.CompositionMode_SourceOver
            )

            # Draw selection border
            pen = QPen(self._BORDER_COLOR, 2, Qt.PenStyle.SolidLine)
            painter.setPen(pen)
            painter.drawRect(rect)

            # Draw dimension label near the bottom-right of the selection
            self._draw_dimension_label(painter, rect)

        painter.end()

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
        metrics = painter.fontMetrics()

        text_width = metrics.horizontalAdvance(label_text)
        text_height = metrics.height()
        padding = 6

        # Label dimensions
        label_w = text_width + padding * 2
        label_h = text_height + padding * 2

        # Position: below and to the right of the selection bottom-right
        label_x = rect.right() - label_w
        label_y = rect.bottom() + 6

        # If label goes off-screen, move it above the selection
        if label_y + label_h > self.height():
            label_y = rect.top() - label_h - 6
        if label_x < 0:
            label_x = rect.left()

        # Draw label background
        label_rect = QRect(label_x, label_y, label_w, label_h)
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
            self.repaint()

    def mouseMoveEvent(self, event):
        """Handle mouse move to update the selection rectangle."""
        if self._selecting:
            self._current = event.pos()
            self._selection_rect = QRect(
                self._origin, self._current
            ).normalized()
            self.repaint()

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

                pil_image = Image.frombytes(
                    'RGB',
                    (screenshot.width, screenshot.height),
                    screenshot.rgb
                )

                return pil_to_qpixmap(pil_image)

        except Exception as e:
            print(f"[SnapEdit] Region capture failed: {e}")
            return None
