"""Per-monitor UI sizing while capture coordinates remain physical pixels.

SnapEdit deliberately keeps Qt's coordinate scaling disabled for its spanning
capture overlays. Scale widget chrome independently; never scale image buffers
or QGraphicsScene coordinates. Sizes are always derived from the original
values, so moving repeatedly between monitors cannot accumulate rounding error.
"""
import os
from pathlib import Path
import re
import weakref

from PyQt6 import sip
from PyQt6.QtCore import QEvent, QObject, QSize, QTimer, Qt, pyqtSignal
from PyQt6.QtGui import QCursor, QFont, QFontDatabase, QImage, QPainter
from PyQt6.QtWidgets import (
    QAbstractButton, QApplication, QFormLayout, QGridLayout, QLayout,
    QListView, QWidget,
)

_DIMENSION = re.compile(r"(-?\d+(?:\.\d+)?)(px|pt)\b")
_MAX_WIDGET_SIZE = 16777215


def screen_scale(screen=None) -> float:
    """Effective Windows scale, not DPI inferred from screen inches."""
    app = QApplication.instance()
    screen = screen or (app.primaryScreen() if app else None)
    if screen is None:
        return 1.0
    # With native Qt scaling enabled elsewhere, don't scale the chrome twice.
    dpi_scale = screen.logicalDotsPerInch() / 96.0
    return max(1.0, min(4.0, dpi_scale))


def screen_at_cursor():
    return QApplication.screenAt(QCursor.pos()) or QApplication.primaryScreen()


def scaled_stylesheet(source: str, scale: float) -> str:
    """Resolve point sizes at 96 DPI, then scale once to physical pixels."""
    def replace(match):
        value = float(match.group(1))
        if match.group(2) == "pt":
            value *= 96.0 / 72.0
        return f"{round(value * scale)}px"
    return _DIMENSION.sub(replace, source)


def pixel_font(font: QFont, scale: float) -> QFont:
    result = QFont(font)
    size = font.pixelSize()
    if size < 0:
        size = max(1.0, font.pointSizeF()) * 96.0 / 72.0
    result.setPixelSize(max(1, round(size * scale)))
    return result


def prepare_ui_fonts():
    """Load our known fonts and shape them before capture hotkeys are enabled.

    Windows font discovery can take seconds on the first QFontMetrics call.
    Loading just the fonts we use avoids putting that work in mouseMoveEvent.
    No font is copied to the project or redistributed.
    """
    app = QApplication.instance()
    if app is None or app.property("snapeditFontsReady"):
        return
    fonts_dir = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"
    for name in ("SegUIVar.ttf", "segoeui.ttf", "segoeuib.ttf"):
        path = fonts_dir / name
        if path.is_file():
            QFontDatabase.addApplicationFont(str(path))
    image = QImage(256, 64, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(0)
    painter = QPainter(image)
    for family in ("Segoe UI", "Segoe UI Variable"):
        for weight in (QFont.Weight.Normal, QFont.Weight.DemiBold, QFont.Weight.Bold):
            painter.setFont(pixel_font(QFont(family, 11, weight), 1.0))
            painter.drawText(0, 32, "SnapEdit 0123456789 × px")
    painter.end()
    app.setProperty("snapeditFontsReady", True)


class WindowScaler(QObject):
    """Scale the existing layout, including embedded icons and custom QSS.

    Install after constructing a window's controls. This changes dimensions,
    not layout structure. It can also scale a child panel (timed capture).
    """
    scale_changed = pyqtSignal(float)

    def __init__(self, widget: QWidget, *, resize_window=True):
        super().__init__(widget)
        # The window owns us; never retain it (or child wrappers) in return.
        # A Python reference cycle can otherwise keep multi-MB pixmaps alive
        # long after the native window has been deleted.
        self._widget_ref = weakref.ref(widget)
        self.scale = 1.0
        self._applied = False
        self._disposed = False
        self._refresh_timer = QTimer(self)
        self._refresh_timer.setSingleShot(True)
        self._refresh_timer.timeout.connect(self.refresh)
        self._handle = None
        self._screen = None
        self._widgets = []
        self._layouts = []
        if widget.isWindow():
            target = widget.parentWidget().screen() if widget.parentWidget() else screen_at_cursor()
            if target is not None:
                widget.setScreen(target)
            # A popup must not multiply its parent's already-scaled font.
            if not widget.testAttribute(Qt.WidgetAttribute.WA_SetFont):
                widget.setFont(QApplication.font())
        for child in [widget, *widget.findChildren(QWidget)]:
            record = {
                "widget": weakref.ref(child), "minimum": child.minimumSize(),
                "maximum": child.maximumSize(), "font": QFont(child.font()),
                "source": child.styleSheet(), "rendered": child.styleSheet(),
            }
            if isinstance(child, (QAbstractButton, QListView)):
                record["icon"] = child.iconSize()
            if isinstance(child, QListView):
                record["grid"] = child.gridSize()
                record["spacing"] = child.spacing()
            self._widgets.append(record)
        for layout in widget.findChildren(QLayout):
            margins = layout.contentsMargins()
            record = {
                "layout": weakref.ref(layout),
                "margins": (margins.left(), margins.top(), margins.right(), margins.bottom()),
                "spacing": layout.spacing(),
            }
            if isinstance(layout, (QGridLayout, QFormLayout)):
                record["horizontal"] = layout.horizontalSpacing()
                record["vertical"] = layout.verticalSpacing()
            self._layouts.append(record)
        # Child panels in a spanning overlay follow the selection's monitor,
        # not the overlay window's primary QScreen. Their owner applies scale.
        if widget.isWindow():
            widget.installEventFilter(self)
        widget.destroyed.connect(self.dispose)
        # Editor has already sized itself to 80% of the physical display.
        # Other windows use design-size dimensions and need initial resizing.
        self.apply(screen_scale(widget.screen()), resize=resize_window)

    @property
    def widget(self):
        return self._widget_ref()

    def dispose(self, *_):
        """Cancel queued work and disconnect external screen signals once."""
        if self._disposed:
            return
        self._disposed = True
        if not sip.isdeleted(self._refresh_timer):
            self._refresh_timer.stop()
        for obj, signal in ((self._handle, "screenChanged"),
                            (self._screen, "logicalDotsPerInchChanged")):
            if obj is not None and not sip.isdeleted(obj):
                try:
                    getattr(obj, signal).disconnect(self.schedule_refresh)
                except (RuntimeError, TypeError):
                    pass
        widget = self.widget
        if widget is not None and not sip.isdeleted(widget):
            widget.removeEventFilter(self)
        self._handle = self._screen = None
        self._widgets.clear()
        self._layouts.clear()

    def eventFilter(self, watched, event):
        if watched is self.widget and event.type() in (
            QEvent.Type.Show, QEvent.Type.Move, QEvent.Type.WinIdChange,
        ):
            self.schedule_refresh()
        return False

    def schedule_refresh(self, *_):
        if not self._disposed and not self._refresh_timer.isActive():
            self._refresh_timer.start(0)

    def refresh(self):
        widget = self.widget
        if self._disposed or widget is None or sip.isdeleted(widget):
            return
        handle = widget.window().windowHandle()
        if handle is not None and handle is not self._handle:
            if self._handle is not None and not sip.isdeleted(self._handle):
                try:
                    self._handle.screenChanged.disconnect(self.schedule_refresh)
                except (RuntimeError, TypeError):
                    pass
            self._handle = handle
            handle.screenChanged.connect(self.schedule_refresh)
        screen = widget.screen()
        if screen is not self._screen:
            if self._screen is not None:
                try:
                    self._screen.logicalDotsPerInchChanged.disconnect(self.schedule_refresh)
                except (RuntimeError, TypeError):
                    pass
            self._screen = screen
            if screen is not None:
                screen.logicalDotsPerInchChanged.connect(self.schedule_refresh)
        self.apply(screen_scale(screen))

    def apply(self, scale: float, *, resize=True):
        widget = self.widget
        if self._disposed or widget is None or sip.isdeleted(widget):
            return
        scale = max(1.0, min(4.0, float(scale)))
        if self._applied and abs(self.scale - scale) < 0.001:
            return
        old_scale = self.scale
        old_size = widget.size()
        self.scale = scale
        self._applied = True
        for record in self._widgets:
            child = record["widget"]()
            if child is None or sip.isdeleted(child):
                continue
            child.setProperty("uiScale", scale)
            child.setFont(pixel_font(record["font"], scale))
            child.setMinimumSize(record["minimum"] * scale)
            maximum = record["maximum"]
            child.setMaximumSize(QSize(*[
                round(value * scale) if value < _MAX_WIDGET_SIZE else value
                for value in (maximum.width(), maximum.height())
            ]))
            # Color swatches and property popups may change their own QSS.
            # Preserve those new colors on the next monitor transition.
            current = child.styleSheet()
            if current != record["rendered"]:
                record["source"] = current
            styled = scaled_stylesheet(record["source"], scale)
            if current != styled:
                child.setStyleSheet(styled)
            record["rendered"] = styled
            if "icon" in record:
                child.setIconSize(record["icon"] * scale)
            if "grid" in record and record["grid"].isValid():
                child.setGridSize(record["grid"] * scale)
                child.setSpacing(round(record["spacing"] * scale))
        for record in self._layouts:
            layout = record["layout"]()
            if layout is None or sip.isdeleted(layout):
                continue
            layout.setContentsMargins(*[round(value * scale) for value in record["margins"]])
            if record["spacing"] >= 0:
                layout.setSpacing(round(record["spacing"] * scale))
            if "horizontal" in record:
                if record["horizontal"] >= 0:
                    layout.setHorizontalSpacing(round(record["horizontal"] * scale))
                if record["vertical"] >= 0:
                    layout.setVerticalSpacing(round(record["vertical"] * scale))
        if resize and widget.isWindow() and not (
            widget.isMaximized() or widget.isFullScreen()
        ):
            new_size = old_size * (scale / old_scale)
            screen = widget.screen()
            if screen is not None:
                new_size = new_size.boundedTo(screen.availableGeometry().size())
            widget.resize(new_size)
        self.scale_changed.emit(scale)
