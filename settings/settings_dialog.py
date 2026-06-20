"""
Settings dialog for SnapEdit.
Provides a modern dark-themed dialog with tabs for Hotkeys, Storage, and Drawing Defaults.
"""
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QKeySequence, QFont, QIcon
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QSpinBox, QComboBox, QCheckBox, QTabWidget,
    QWidget, QFileDialog, QKeySequenceEdit,
    QGroupBox, QFormLayout, QColorDialog,
)

from settings.config import Config


# ── Dark‑theme colour tokens ────────────────────────────────────────
_BG       = "#1E1E2E"
_CARD     = "#2A2A3C"
_ACCENT   = "#7C5CFC"
_TEXT     = "#E0E0E0"
_INPUT_BG = "#363650"
_BORDER   = "#3A3A52"
_HOVER    = "#8E72FF"
_PRESSED  = "#6A48E0"

# ── Global stylesheet applied to the dialog ─────────────────────────
_STYLESHEET = f"""
/* ─── Dialog ─────────────────────────────── */
QDialog {{
    background: {_BG};
    color: {_TEXT};
    font-family: 'Segoe UI', sans-serif;
    font-size: 13px;
}}

/* ─── Tab widget ─────────────────────────── */
QTabWidget::pane {{
    border: 1px solid {_BORDER};
    border-radius: 8px;
    background: {_CARD};
    top: -1px;
}}
QTabBar::tab {{
    background: {_BG};
    color: {_TEXT};
    padding: 8px 20px;
    margin-right: 2px;
    border-top-left-radius: 8px;
    border-top-right-radius: 8px;
    border: 1px solid {_BORDER};
    border-bottom: none;
    min-width: 100px;
}}
QTabBar::tab:selected {{
    background: {_CARD};
    color: {_ACCENT};
    font-weight: bold;
    border-bottom: 2px solid {_ACCENT};
}}
QTabBar::tab:hover:!selected {{
    background: {_INPUT_BG};
}}

/* ─── Group boxes ────────────────────────── */
QGroupBox {{
    background: {_CARD};
    border: 1px solid {_BORDER};
    border-radius: 8px;
    margin-top: 14px;
    padding: 16px 12px 12px 12px;
    font-weight: bold;
    color: {_TEXT};
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    subcontrol-position: top left;
    padding: 0 6px;
    color: {_ACCENT};
}}

/* ─── Labels ─────────────────────────────── */
QLabel {{
    color: {_TEXT};
    font-size: 13px;
}}

/* ─── Input fields ───────────────────────── */
QLineEdit, QSpinBox, QComboBox, QKeySequenceEdit {{
    background: {_INPUT_BG};
    color: {_TEXT};
    border: 1px solid {_BORDER};
    border-radius: 6px;
    padding: 6px 10px;
    min-height: 28px;
    selection-background-color: {_ACCENT};
}}
QLineEdit:focus, QSpinBox:focus, QComboBox:focus, QKeySequenceEdit:focus {{
    border: 1px solid {_ACCENT};
}}
QComboBox::drop-down {{
    border: none;
    width: 28px;
}}
QComboBox QAbstractItemView {{
    background: {_INPUT_BG};
    color: {_TEXT};
    border: 1px solid {_ACCENT};
    selection-background-color: {_ACCENT};
    outline: 0px;
}}
QSpinBox::up-button, QSpinBox::down-button {{
    background: {_CARD};
    border: none;
    width: 20px;
}}
QSpinBox::up-arrow {{
    image: none;
    border-left: 5px solid transparent;
    border-right: 5px solid transparent;
    border-bottom: 5px solid {_TEXT};
    width: 0; height: 0;
}}
QSpinBox::down-arrow {{
    image: none;
    border-left: 5px solid transparent;
    border-right: 5px solid transparent;
    border-top: 5px solid {_TEXT};
    width: 0; height: 0;
}}

/* ─── Checkboxes ─────────────────────────── */
QCheckBox {{
    color: {_TEXT};
    spacing: 8px;
}}
QCheckBox::indicator {{
    width: 18px;
    height: 18px;
    border: 2px solid {_BORDER};
    border-radius: 4px;
    background: {_INPUT_BG};
}}
QCheckBox::indicator:checked {{
    background: {_ACCENT};
    border-color: {_ACCENT};
}}

/* ─── Buttons ────────────────────────────── */
QPushButton {{
    background: {_INPUT_BG};
    color: {_TEXT};
    border: 1px solid {_BORDER};
    border-radius: 6px;
    padding: 7px 18px;
    font-size: 13px;
    min-height: 28px;
}}
QPushButton:hover {{
    background: {_HOVER};
    border-color: {_HOVER};
    color: #FFFFFF;
}}
QPushButton:pressed {{
    background: {_PRESSED};
}}
QPushButton#btnSave {{
    background: {_ACCENT};
    border-color: {_ACCENT};
    color: #FFFFFF;
    font-weight: bold;
}}
QPushButton#btnSave:hover {{
    background: {_HOVER};
}}

/* ─── Dialog button box ──────────────────── */
QDialogButtonBox QPushButton {{
    min-width: 90px;
}}

/* ─── Scroll area (if ever used) ─────────── */
QScrollBar:vertical {{
    background: {_BG};
    width: 8px;
    border-radius: 4px;
}}
QScrollBar::handle:vertical {{
    background: {_BORDER};
    border-radius: 4px;
    min-height: 30px;
}}
"""


class _ColorButton(QPushButton):
    """A small push‑button that displays and lets the user pick a colour."""

    def __init__(self, initial_color: str = "#FF3B30", parent=None):
        super().__init__(parent)
        self._color = QColor(initial_color)
        self.setFixedSize(40, 30)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._update_swatch()
        self.clicked.connect(self._pick_color)

    # ── public API ───────────────────────────────────────────────────
    @property
    def color(self) -> str:
        """Return the currently selected colour as a hex string."""
        return self._color.name()

    @color.setter
    def color(self, hex_color: str):
        self._color = QColor(hex_color)
        self._update_swatch()

    # ── internals ────────────────────────────────────────────────────
    def _update_swatch(self):
        self.setStyleSheet(
            f"background: {self._color.name()};"
            f"border: 2px solid {_BORDER};"
            f"border-radius: 6px;"
        )

    def _pick_color(self):
        chosen = QColorDialog.getColor(
            self._color, self, "Pick Color",
            QColorDialog.ColorDialogOption.ShowAlphaChannel,
        )
        if chosen.isValid():
            self._color = chosen
            self._update_swatch()


class SettingsDialog(QDialog):
    """Application settings dialog with a modern dark‑themed UI."""

    def __init__(self, config: Config, parent=None):
        super().__init__(parent)
        self._config = config

        self.setWindowTitle("SnapEdit – Settings")
        self.setMinimumSize(520, 480)
        self.resize(560, 520)
        self.setStyleSheet(_STYLESHEET)

        # ── main layout ─────────────────────────────────────────────
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 18, 18, 14)
        root.setSpacing(12)

        # Title label
        title = QLabel("⚙  Settings")
        title.setFont(QFont("Segoe UI", 17, QFont.Weight.Bold))
        title.setStyleSheet(f"color: {_ACCENT}; margin-bottom: 2px;")
        root.addWidget(title)

        # Tab widget
        self._tabs = QTabWidget()
        root.addWidget(self._tabs, 1)

        self._build_hotkeys_tab()
        self._build_storage_tab()
        self._build_drawing_tab()

        # ── bottom buttons ───────────────────────────────────────────
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)

        self._btn_reset = QPushButton("Reset to Defaults")
        self._btn_reset.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_layout.addWidget(self._btn_reset)

        btn_layout.addStretch()

        self._btn_cancel = QPushButton("Cancel")
        self._btn_cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_layout.addWidget(self._btn_cancel)

        self._btn_save = QPushButton("Save")
        self._btn_save.setObjectName("btnSave")
        self._btn_save.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_layout.addWidget(self._btn_save)

        root.addLayout(btn_layout)

        # ── connections ──────────────────────────────────────────────
        self._btn_save.clicked.connect(self._on_save)
        self._btn_cancel.clicked.connect(self.reject)
        self._btn_reset.clicked.connect(self._on_reset)

        # Load current values into the widgets
        self._load_from_config()

    # ────────────────────────────────────────────────────────────────
    #  Tab builders
    # ────────────────────────────────────────────────────────────────
    def _build_hotkeys_tab(self):
        """Build the Hotkeys settings tab."""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(12, 16, 12, 12)
        layout.setSpacing(14)

        group = QGroupBox("Global Hotkeys")
        form = QFormLayout(group)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        form.setHorizontalSpacing(16)
        form.setVerticalSpacing(14)

        self._hk_fullscreen = QKeySequenceEdit()
        self._hk_region = QKeySequenceEdit()

        form.addRow(QLabel("Capture Fullscreen"), self._hk_fullscreen)
        form.addRow(QLabel("Capture Region"), self._hk_region)

        layout.addWidget(group)
        layout.addStretch()
        self._tabs.addTab(tab, "🔑  Hotkeys")

    def _build_storage_tab(self):
        """Build the Storage settings tab."""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(12, 16, 12, 12)
        layout.setSpacing(14)

        group = QGroupBox("Storage")
        form = QFormLayout(group)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        form.setHorizontalSpacing(16)
        form.setVerticalSpacing(14)

        # Save directory row
        dir_row = QHBoxLayout()
        self._save_dir_edit = QLineEdit()
        self._save_dir_edit.setReadOnly(True)
        self._save_dir_edit.setPlaceholderText("Select save directory…")
        dir_row.addWidget(self._save_dir_edit, 1)
        self._btn_browse = QPushButton("Browse…")
        self._btn_browse.setFixedWidth(72)
        self._btn_browse.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_browse.clicked.connect(self._browse_directory)
        dir_row.addWidget(self._btn_browse)
        dir_widget = QWidget()
        dir_widget.setLayout(dir_row)
        form.addRow(QLabel("Save Directory"), dir_widget)

        # Default format
        self._format_combo = QComboBox()
        self._format_combo.addItems(["PNG", "JPG", "BMP"])
        form.addRow(QLabel("Default Format"), self._format_combo)

        # Auto‑copy clipboard
        self._auto_copy_cb = QCheckBox("Auto-copy to clipboard after capture")
        form.addRow("", self._auto_copy_cb)

        layout.addWidget(group)
        layout.addStretch()
        self._tabs.addTab(tab, "💾  Storage")

    def _build_drawing_tab(self):
        """Build the Drawing Defaults tab."""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(12, 16, 12, 12)
        layout.setSpacing(14)

        group = QGroupBox("Drawing Defaults")
        form = QFormLayout(group)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        form.setHorizontalSpacing(16)
        form.setVerticalSpacing(14)

        # Stroke colour
        self._stroke_color_btn = _ColorButton()
        form.addRow(QLabel("Default Color"), self._stroke_color_btn)

        # Stroke width
        self._stroke_width_spin = QSpinBox()
        self._stroke_width_spin.setRange(1, 20)
        self._stroke_width_spin.setSuffix(" px")
        form.addRow(QLabel("Stroke Width"), self._stroke_width_spin)

        # Bubble colour
        self._bubble_color_btn = _ColorButton()
        form.addRow(QLabel("Bubble Color"), self._bubble_color_btn)

        layout.addWidget(group)
        layout.addStretch()
        self._tabs.addTab(tab, "🎨  Drawing")

    # ────────────────────────────────────────────────────────────────
    #  Config <‑> Widget synchronisation
    # ────────────────────────────────────────────────────────────────
    def _load_from_config(self):
        """Populate all widgets from the current Config values."""
        hotkeys = self._config.hotkeys

        self._hk_fullscreen.setKeySequence(
            QKeySequence.fromString(self._format_hotkey_display(hotkeys.get("fullscreen", "")))
        )
        self._hk_region.setKeySequence(
            QKeySequence.fromString(self._format_hotkey_display(hotkeys.get("region", "")))
        )

        self._save_dir_edit.setText(self._config.save_directory)

        fmt = self._config.default_format.upper()
        idx = self._format_combo.findText(fmt)
        if idx >= 0:
            self._format_combo.setCurrentIndex(idx)

        self._auto_copy_cb.setChecked(
            self._config.get("auto_copy_clipboard", False)
        )

        self._stroke_color_btn.color = self._config.stroke_color
        self._stroke_width_spin.setValue(self._config.stroke_width)
        self._bubble_color_btn.color = self._config.bubble_color

    @staticmethod
    def _format_hotkey_display(hotkey_str: str) -> str:
        """Convert a stored hotkey like 'ctrl+shift+f' into the
        QKeySequence‑friendly format 'Ctrl+Shift+F'."""
        if not hotkey_str:
            return ""
        parts = [p.strip().capitalize() for p in hotkey_str.split("+")]
        return "+".join(parts)

    @staticmethod
    def _format_hotkey_store(key_seq: QKeySequence) -> str:
        """Convert a QKeySequence back to the storage format 'ctrl+shift+f'."""
        text = key_seq.toString()
        if not text:
            return ""
        return text.lower().replace(" ", "")

    # ────────────────────────────────────────────────────────────────
    #  Slots
    # ────────────────────────────────────────────────────────────────
    def _browse_directory(self):
        """Open a native directory picker."""
        path = QFileDialog.getExistingDirectory(
            self, "Select save directory", self._save_dir_edit.text()
        )
        if path:
            self._save_dir_edit.setText(path)

    def _on_save(self):
        """Persist all widget values into Config and close."""
        # Hotkeys
        self._config.set(
            "hotkeys.fullscreen",
            self._format_hotkey_store(self._hk_fullscreen.keySequence()),
        )
        self._config.set(
            "hotkeys.region",
            self._format_hotkey_store(self._hk_region.keySequence()),
        )

        # Storage
        self._config.set("save_directory", self._save_dir_edit.text())
        self._config.set("default_format", self._format_combo.currentText().lower())
        self._config.set("auto_copy_clipboard", self._auto_copy_cb.isChecked())

        # Drawing defaults
        self._config.set("stroke_color", self._stroke_color_btn.color)
        self._config.set("stroke_width", self._stroke_width_spin.value())
        self._config.set("bubble_color", self._bubble_color_btn.color)

        self._config.save()
        self.accept()

    def _on_reset(self):
        """Reset config to factory defaults and reload the UI."""
        self._config.reset_to_defaults()
        self._load_from_config()
