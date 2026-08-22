"""Timed region selection with an input-transparent countdown overlay."""

from PyQt6.QtCore import Qt, QRect, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QPainter, QPen
from PyQt6.QtWidgets import (
    QApplication, QComboBox, QFrame, QHBoxLayout, QLabel, QPushButton,
)
from pynput.keyboard import Key, Listener

from capture.region import RegionSelector
from theme import (
    ACCENT, ACCENT_HOVER, BASE, BORDER, CONTROL_RADIUS, HOVER, SURFACE,
    SURFACE_ALT, TEXT_PRIMARY, TEXT_SECONDARY, TYPE_BODY_PT,
)


_OPTIONS_STYLE = f"""
QFrame#timedOptions {{
    background: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: 8px;
}}
QLabel {{
    color: {TEXT_SECONDARY};
    border: none;
    font-family: 'Segoe UI Variable', 'Segoe UI';
    font-size: {TYPE_BODY_PT}pt;
}}
QComboBox {{
    background: {SURFACE_ALT};
    color: {TEXT_PRIMARY};
    border: 1px solid {BORDER};
    border-radius: {CONTROL_RADIUS}px;
    padding: 6px 26px 6px 9px;
    min-height: 28px;
    min-width: 88px;
    font-size: {TYPE_BODY_PT}pt;
}}
QComboBox::drop-down {{ border: none; width: 26px; }}
QComboBox QAbstractItemView {{
    background: {SURFACE_ALT};
    color: {TEXT_PRIMARY};
    border: 1px solid {BORDER};
    selection-background-color: {HOVER};
}}
QPushButton {{
    background: {SURFACE_ALT};
    color: {TEXT_PRIMARY};
    border: 1px solid {BORDER};
    border-radius: {CONTROL_RADIUS}px;
    padding: 6px 14px;
    min-height: 28px;
    font-size: {TYPE_BODY_PT}pt;
}}
QPushButton:hover {{ background: {HOVER}; }}
QPushButton#captureButton {{
    background: {ACCENT};
    border-color: {ACCENT};
    color: {BASE};
    font-weight: 600;
}}
QPushButton#captureButton:hover {{ background: {ACCENT_HOVER}; }}
"""


class TimedRegionSelector(RegionSelector):
    """Select a region, then capture it after a click-through countdown."""

    _COUNTDOWN_BG = QColor(20, 20, 20, 210)
    countdown_cancel_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, False)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

        self._phase = "selecting"
        self._remaining_seconds = 0
        self._countdown_timer = QTimer(self)
        self._countdown_timer.setInterval(1000)
        self._countdown_timer.timeout.connect(self._countdown_tick)
        self._escape_listener = None
        self.countdown_cancel_requested.connect(self._cancel_countdown)

        self._options = QFrame(self)
        self._options.setObjectName("timedOptions")
        self._options.setStyleSheet(_OPTIONS_STYLE)
        options_font = QFont("Segoe UI Variable")
        options_font.setPointSize(TYPE_BODY_PT)
        self._options.setFont(options_font)
        options_layout = QHBoxLayout(self._options)
        options_layout.setContentsMargins(12, 10, 12, 10)
        options_layout.setSpacing(8)

        self._delay_label = QLabel("Delay")
        options_layout.addWidget(self._delay_label)
        self._delay_combo = QComboBox()
        for seconds in (3, 5, 10):
            self._delay_combo.addItem(f"{seconds} s", seconds)
        options_layout.addWidget(self._delay_combo)

        self._capture_button = QPushButton("Capture")
        self._capture_button.setObjectName("captureButton")
        self._capture_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._capture_button.clicked.connect(self._start_countdown)
        options_layout.addWidget(self._capture_button)

        self._cancel_button = QPushButton("Cancel")
        self._cancel_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._cancel_button.clicked.connect(self._cancel)
        options_layout.addWidget(self._cancel_button)
        self._options.hide()

    def start(self):
        """Show a live translucent selector across the virtual desktop."""
        self.setGeometry(self._get_virtual_geometry())
        self.show()
        self.activateWindow()
        self.raise_()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Clear the backing store first so the countdown phase reveals the
        # live desktop rather than retaining pixels from the dim selector.
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
        painter.fillRect(event.rect(), Qt.GlobalColor.transparent)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)

        rect = self._selection_rect
        if self._phase in ("selecting", "options"):
            painter.fillRect(event.rect(), self._OVERLAY_COLOR)
            if rect.isValid():
                painter.setCompositionMode(
                    QPainter.CompositionMode.CompositionMode_Clear
                )
                painter.fillRect(rect, Qt.GlobalColor.transparent)
                painter.setCompositionMode(
                    QPainter.CompositionMode.CompositionMode_SourceOver
                )
                self._draw_selection_border(painter, rect)
                self._draw_dimension_label(painter, rect)
        elif self._phase == "countdown" and rect.isValid():
            self._draw_selection_border(painter, rect)
            self._draw_countdown(painter, rect)

        painter.end()

    def _draw_selection_border(self, painter: QPainter, rect: QRect):
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(self._BORDER_COLOR, 2, Qt.PenStyle.SolidLine))
        painter.drawRect(rect)

    def _draw_countdown(self, painter: QPainter, rect: QRect):
        diameter = 88
        center = rect.center()
        badge = QRect(
            center.x() - diameter // 2,
            center.y() - diameter // 2,
            diameter,
            diameter,
        )
        painter.setPen(QPen(QColor(255, 255, 255, 90), 1))
        painter.setBrush(self._COUNTDOWN_BG)
        painter.drawEllipse(badge)
        painter.setPen(QColor(255, 255, 255))
        painter.setFont(QFont("Segoe UI Variable", 30, QFont.Weight.DemiBold))
        painter.drawText(
            badge, Qt.AlignmentFlag.AlignCenter, str(self._remaining_seconds)
        )

    def mousePressEvent(self, event):
        if self._phase == "countdown":
            event.ignore()
            return
        if event.button() == Qt.MouseButton.LeftButton:
            self._options.hide()
            self._phase = "selecting"
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        if (
            event.button() != Qt.MouseButton.LeftButton
            or not self._selecting
            or self._phase == "countdown"
        ):
            return

        self._selecting = False
        self._current = event.pos()
        self._selection_rect = QRect(self._origin, self._current).normalized()
        if (
            self._selection_rect.width() < 5
            or self._selection_rect.height() < 5
        ):
            self._selection_rect = QRect()
            self.update()
            return

        self._phase = "options"
        self._position_options()
        self._options.show()
        self._options.raise_()
        self.update()

    def _position_options(self):
        # Polish before measuring so the QSS font and padding are included.
        # Resizing from the layout hint prevents text clipping at different
        # Windows DPI/font settings.
        self._options.ensurePolished()
        longest_delay = max(
            self._delay_combo.itemText(index)
            for index in range(self._delay_combo.count())
        )
        self._delay_combo.setMinimumWidth(
            max(
                136,
                self._delay_combo.fontMetrics().horizontalAdvance(longest_delay) + 72,
            )
        )
        self._delay_label.setMinimumWidth(
            self._delay_label.fontMetrics().horizontalAdvance(
                self._delay_label.text()
            ) + 16
        )
        for button in (self._capture_button, self._cancel_button):
            button.setMinimumWidth(
                max(
                    112,
                    button.fontMetrics().horizontalAdvance(button.text()) + 56,
                )
            )
        size = self._options.layout().sizeHint()
        self._options.resize(size)
        rect = self._selection_rect
        gap = 10
        x = rect.right() - size.width() + 1
        below_y = rect.bottom() + gap + 1
        above_y = rect.top() - size.height() - gap
        y = below_y if below_y + size.height() <= self.height() else above_y
        x = max(8, min(x, self.width() - size.width() - 8))
        y = max(8, min(y, self.height() - size.height() - 8))
        self._options.move(x, y)

    def _start_countdown(self):
        self._remaining_seconds = int(self._delay_combo.currentData())
        self._phase = "countdown"
        self._options.hide()
        self.unsetCursor()

        # Recreate the native window as output-only. Mouse and keyboard input
        # then reaches the application beneath this always-on-top overlay.
        self.setWindowFlag(Qt.WindowType.WindowTransparentForInput, True)
        self.show()
        self.raise_()
        self.update()
        self._start_escape_listener()
        self._countdown_timer.start()

    def _start_escape_listener(self):
        """Listen for Escape while the click-through overlay has no focus."""
        self._stop_escape_listener()
        self._escape_listener = Listener(on_press=self._on_global_key_press)
        self._escape_listener.daemon = True
        self._escape_listener.start()

    def _on_global_key_press(self, key):
        if key == Key.esc:
            self.countdown_cancel_requested.emit()
            return False
        return None

    def _stop_escape_listener(self):
        if self._escape_listener is not None:
            self._escape_listener.stop()
            self._escape_listener = None

    def _cancel_countdown(self):
        if self._phase != "countdown":
            return
        self._countdown_timer.stop()
        self._stop_escape_listener()
        self.selection_cancelled.emit()
        self.close()

    def _countdown_tick(self):
        self._remaining_seconds -= 1
        if self._remaining_seconds <= 0:
            self._countdown_timer.stop()
            self._stop_escape_listener()
            self.hide()
            QApplication.processEvents()
            pixmap = self._capture_region(self._selection_rect)
            if pixmap and not pixmap.isNull():
                self.region_captured.emit(pixmap)
            self.close()
            return
        self.update()

    def _cancel(self):
        self.selection_cancelled.emit()
        self.close()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            if self._phase == "countdown":
                self._cancel_countdown()
            else:
                self._cancel()
            return
        super().keyPressEvent(event)

    def closeEvent(self, event):
        self._countdown_timer.stop()
        self._stop_escape_listener()
        super().closeEvent(event)
