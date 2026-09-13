"""
Settings dialog for SnapEdit.
Provides a modern dark-themed dialog with tabs for General, Hotkeys, and Storage.
"""
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QKeySequence
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QComboBox, QCheckBox,
    QWidget, QFileDialog, QKeySequenceEdit,
    QGroupBox, QFormLayout, QListWidget,
    QStackedWidget, QFrame, QMessageBox, QScrollArea,
)
from settings.config import Config
from theme import (
    ACCENT, ACCENT_HOVER, ACCENT_PRESSED, BASE, BORDER,
    BORDER_SUBTLE, CONTROL_RADIUS, HOVER, OVERLAY_RADIUS, PRESSED,
    SURFACE, SURFACE_ALT, TEXT_MUTED, TEXT_PRIMARY, TEXT_SECONDARY,
    TYPE_BODY_PT, TYPE_CAPTION_PT, TYPE_DISPLAY_PT, TYPE_TITLE_PT,
)
from windows_integration import (
    is_startup_enabled, set_startup_enabled, startup_is_supported,
)


_STYLESHEET = f"""
QDialog {{
    background: {BASE};
    color: {TEXT_PRIMARY};
    font-family: 'Segoe UI Variable', 'Segoe UI';
    font-size: {TYPE_BODY_PT}pt;
}}
QFrame#settingsHeader {{
    background: {BASE};
    border-bottom: 1px solid {BORDER_SUBTLE};
}}
QFrame#settingsFooter {{
    background: {BASE};
    border-top: 1px solid {BORDER_SUBTLE};
}}
QScrollArea#settingsPageScroll {{
    background: transparent;
    border: none;
}}
QStackedWidget#settingsPages {{
    background: transparent;
}}
QLabel#settingsTitle {{
    color: {TEXT_PRIMARY};
    font-size: {TYPE_DISPLAY_PT}pt;
    font-weight: 600;
}}
QLabel#settingsSubtitle, QLabel#pageDescription {{
    color: {TEXT_MUTED};
    font-size: {TYPE_CAPTION_PT}pt;
}}
QLabel#pageTitle {{
    color: {TEXT_PRIMARY};
    font-size: {TYPE_TITLE_PT}pt;
    font-weight: 600;
}}
QListWidget {{
    background: transparent;
    border: none;
    outline: none;
    color: {TEXT_SECONDARY};
    padding: 4px;
}}
QListWidget::item {{
    border-radius: {CONTROL_RADIUS}px;
    padding: 8px 12px;
    margin: 1px 0;
}}
QListWidget::item:hover {{
    background: {HOVER};
}}
QListWidget::item:selected {{
    background: {SURFACE_ALT};
    color: {TEXT_PRIMARY};
    border-left: 2px solid {ACCENT};
}}
QGroupBox {{
    background: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: {OVERLAY_RADIUS}px;
    margin-top: 18px;
    padding: 16px;
    color: {TEXT_PRIMARY};
    font-weight: 600;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 12px;
    padding: 0 6px;
    color: {TEXT_PRIMARY};
}}
QLabel {{
    color: {TEXT_SECONDARY};
    font-size: {TYPE_BODY_PT}pt;
}}
QLineEdit, QSpinBox, QComboBox, QKeySequenceEdit {{
    background: {SURFACE_ALT};
    color: {TEXT_PRIMARY};
    border: 1px solid {BORDER};
    border-radius: {CONTROL_RADIUS}px;
    padding: 6px 10px;
    min-height: 30px;
    selection-background-color: {ACCENT};
    selection-color: {BASE};
}}
QLineEdit:focus, QSpinBox:focus, QComboBox:focus, QKeySequenceEdit:focus {{
    border-color: {ACCENT};
}}
QComboBox::drop-down {{ border: none; width: 28px; }}
QComboBox QAbstractItemView {{
    background: {SURFACE_ALT};
    color: {TEXT_PRIMARY};
    border: 1px solid {BORDER};
    selection-background-color: {HOVER};
    outline: none;
}}
QSpinBox::up-button, QSpinBox::down-button {{
    background: {SURFACE};
    border: none;
    width: 24px;
}}
QSpinBox::up-button {{ border-top-right-radius: {CONTROL_RADIUS}px; }}
QSpinBox::down-button {{ border-bottom-right-radius: {CONTROL_RADIUS}px; }}
QSpinBox::up-button:hover, QSpinBox::down-button:hover {{
    background: {HOVER};
}}
QSpinBox::up-arrow, QSpinBox::down-arrow {{
    image: none;
    width: 0px;
    height: 0px;
    border: none;
}}
QCheckBox {{
    color: {TEXT_PRIMARY};
    spacing: 8px;
}}
QCheckBox::indicator {{
    width: 16px;
    height: 16px;
    border: 1px solid {BORDER};
    border-radius: 3px;
    background: {SURFACE_ALT};
}}
QCheckBox::indicator:checked {{
    background: {ACCENT};
    border-color: {ACCENT};
}}
QPushButton {{
    background: {SURFACE_ALT};
    color: {TEXT_PRIMARY};
    border: 1px solid {BORDER};
    border-radius: {CONTROL_RADIUS}px;
    padding: 6px 14px;
    font-size: {TYPE_BODY_PT}pt;
    min-height: 30px;
}}
QPushButton:hover {{
    background: {HOVER};
}}
QPushButton:pressed {{
    background: {PRESSED};
}}
QPushButton:focus, QListWidget:focus, QLineEdit:focus, QSpinBox:focus,
QComboBox:focus, QKeySequenceEdit:focus {{
    outline: none;
    border-color: {ACCENT};
}}
QPushButton#btnSave {{
    background: {ACCENT};
    border-color: {ACCENT};
    color: {BASE};
    font-weight: 600;
}}
QPushButton#btnSave:hover {{
    background: {ACCENT_HOVER};
    border-color: {ACCENT_HOVER};
}}
QPushButton#btnSave:pressed {{
    background: {ACCENT_PRESSED};
    border-color: {ACCENT_PRESSED};
}}
QScrollBar:vertical {{
    background: {BASE};
    width: 8px;
    border-radius: 4px;
}}
QScrollBar::handle:vertical {{
    background: {BORDER};
    border-radius: 4px;
    min-height: 30px;
}}
"""


class SettingsDialog(QDialog):
    """Application settings dialog using a Fluent left-nav silhouette."""

    def __init__(self, config: Config, parent=None):
        super().__init__(parent)
        self._config = config

        self.setWindowTitle("SnapEdit - Settings")
        self.setMinimumSize(720, 560)
        self.resize(860, 640)
        self.setStyleSheet(_STYLESHEET)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        header = QFrame()
        header.setObjectName("settingsHeader")
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(20, 12, 20, 12)
        header_layout.setSpacing(2)
        title = QLabel("Settings")
        title.setObjectName("settingsTitle")
        subtitle = QLabel(
            "Customize startup, capture, and storage behavior"
        )
        subtitle.setObjectName("settingsSubtitle")
        header_layout.addWidget(title)
        header_layout.addWidget(subtitle)
        root.addWidget(header)

        body = QWidget()
        body_layout = QHBoxLayout(body)
        body_layout.setContentsMargins(12, 12, 12, 12)
        body_layout.setSpacing(12)

        self._nav = QListWidget()
        self._nav.setMinimumWidth(168)
        self._nav.setMaximumWidth(192)
        self._nav.setSpacing(0)
        self._nav.addItems(["General", "Hotkeys", "Storage"])
        self._nav.setAccessibleName("Settings sections")
        body_layout.addWidget(self._nav)

        self._stack = QStackedWidget()
        self._stack.setObjectName("settingsPages")
        self._page_scroll = QScrollArea()
        self._page_scroll.setObjectName("settingsPageScroll")
        self._page_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._page_scroll.setWidgetResizable(True)
        self._page_scroll.setWidget(self._stack)
        body_layout.addWidget(self._page_scroll, 1)
        root.addWidget(body, 1)

        self._build_general_tab()
        self._build_hotkeys_tab()
        self._build_storage_tab()
        self._nav.currentRowChanged.connect(self._stack.setCurrentIndex)
        self._nav.setCurrentRow(0)

        footer = QFrame()
        footer.setObjectName("settingsFooter")
        btn_layout = QHBoxLayout(footer)
        btn_layout.setContentsMargins(12, 8, 12, 8)
        btn_layout.setSpacing(8)

        self._btn_reset = QPushButton("Reset defaults")
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

        root.addWidget(footer)

        # ── connections ──────────────────────────────────────────────
        self._btn_save.clicked.connect(self._on_save)
        self._btn_cancel.clicked.connect(self.reject)
        self._btn_reset.clicked.connect(self._on_reset)

        # Load current values into the widgets
        self._load_from_config()
        from ui_scaling import WindowScaler
        self._ui_scaler = WindowScaler(self)

    # ────────────────────────────────────────────────────────────────
    #  Page builders
    # ────────────────────────────────────────────────────────────────
    @staticmethod
    def _add_page_header(layout: QVBoxLayout, title: str, description: str):
        title_label = QLabel(title)
        title_label.setObjectName("pageTitle")
        description_label = QLabel(description)
        description_label.setObjectName("pageDescription")
        description_label.setWordWrap(True)
        layout.addWidget(title_label)
        layout.addWidget(description_label)

    def _build_hotkeys_tab(self):
        """Build the Hotkeys settings page."""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(8, 4, 8, 8)
        layout.setSpacing(8)
        self._add_page_header(
            layout,
            "Hotkeys",
            "Choose shortcuts that work while SnapEdit is running in the tray.",
        )

        group = QGroupBox("Capture shortcuts")
        form = QFormLayout(group)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
        form.setHorizontalSpacing(24)
        form.setVerticalSpacing(12)

        self._hk_fullscreen = QKeySequenceEdit()
        self._hk_region = QKeySequenceEdit()
        self._hk_timed_region = QKeySequenceEdit()
        self._hk_ocr = QKeySequenceEdit()
        self._hk_scroll = QKeySequenceEdit()

        form.addRow(QLabel("Full screen"), self._hk_fullscreen)
        form.addRow(QLabel("Region"), self._hk_region)
        form.addRow(QLabel("Timed region"), self._hk_timed_region)
        form.addRow(QLabel("Copy text from screen"), self._hk_ocr)
        form.addRow(QLabel("Scrolling capture"), self._hk_scroll)

        layout.addWidget(group)
        layout.addStretch()
        self._stack.addWidget(tab)

    def _build_general_tab(self):
        """Build application-level Windows settings."""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(8, 4, 8, 8)
        layout.setSpacing(8)
        self._add_page_header(
            layout,
            "General",
            "Control how SnapEdit starts and behaves on Windows.",
        )

        group = QGroupBox("Startup")
        group_layout = QVBoxLayout(group)
        group_layout.setContentsMargins(20, 18, 20, 18)
        group_layout.setSpacing(6)

        self._startup_cb = QCheckBox("Start SnapEdit when Windows starts")
        self._startup_cb.setMinimumHeight(32)
        self._startup_cb.setAccessibleName("Start SnapEdit when Windows starts")
        group_layout.addWidget(self._startup_cb)

        description = QLabel(
            "SnapEdit will start in the system tray after you sign in."
        )
        description.setObjectName("pageDescription")
        description.setWordWrap(True)
        group_layout.addWidget(description)

        if not startup_is_supported():
            self._startup_cb.setEnabled(False)
            self._startup_cb.setToolTip("This option is only available on Windows")

        layout.addWidget(group)

        ocr_group = QGroupBox("Text OCR")
        ocr_layout = QVBoxLayout(ocr_group)
        ocr_layout.setContentsMargins(20, 18, 20, 18)
        ocr_layout.setSpacing(6)

        ocr_form = QFormLayout()
        ocr_form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
        ocr_form.setHorizontalSpacing(24)
        ocr_form.setVerticalSpacing(8)
        self._ocr_language_combo = QComboBox()
        self._ocr_language_combo.addItem("Auto (installed languages)", "auto")
        self._ocr_language_combo.addItem("Japanese", "ja")
        self._ocr_language_combo.addItem("English", "en")
        self._ocr_language_combo.setAccessibleName("Text OCR recognition language")
        ocr_form.addRow(QLabel("Recognition language"), self._ocr_language_combo)
        ocr_layout.addLayout(ocr_form)

        ocr_description = QLabel(
            "Japanese mode tries a few lightweight image variants to preserve "
            "small kana and stroke details. It can take slightly longer."
        )
        ocr_description.setObjectName("pageDescription")
        ocr_description.setWordWrap(True)
        ocr_layout.addWidget(ocr_description)
        layout.addWidget(ocr_group)
        layout.addStretch()
        self._stack.addWidget(tab)

    def _build_storage_tab(self):
        """Build the Storage settings page."""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(8, 4, 8, 8)
        layout.setSpacing(8)
        self._add_page_header(
            layout,
            "Storage",
            "Control where captures are saved and what happens after capture.",
        )

        group = QGroupBox("Save options")
        form = QFormLayout(group)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
        form.setHorizontalSpacing(24)
        form.setVerticalSpacing(12)

        # Save directory row
        dir_row = QHBoxLayout()
        dir_row.setContentsMargins(0, 0, 0, 0)
        dir_row.setSpacing(8)
        self._save_dir_edit = QLineEdit()
        self._save_dir_edit.setReadOnly(True)
        self._save_dir_edit.setPlaceholderText("Select a save folder")
        dir_row.addWidget(self._save_dir_edit, 1)
        self._btn_browse = QPushButton("Browse")
        self._btn_browse.setMinimumWidth(104)
        self._btn_browse.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_browse.clicked.connect(self._browse_directory)
        dir_row.addWidget(self._btn_browse)
        dir_widget = QWidget()
        dir_widget.setLayout(dir_row)
        form.addRow(QLabel("Save folder"), dir_widget)

        # Default format
        self._format_combo = QComboBox()
        self._format_combo.addItems(["PNG", "JPG", "BMP"])
        form.addRow(QLabel("Default format"), self._format_combo)

        # Auto‑copy clipboard
        self._auto_copy_cb = QCheckBox("Auto-copy to clipboard after capture")
        self._auto_copy_cb.setMinimumHeight(32)
        form.addRow(self._auto_copy_cb)

        layout.addWidget(group)
        layout.addStretch()
        self._stack.addWidget(tab)

    # ────────────────────────────────────────────────────────────────
    #  Config <‑> Widget synchronisation
    # ────────────────────────────────────────────────────────────────
    def _load_from_config(self):
        """Populate all widgets from the current Config values."""
        hotkeys = self._config.hotkeys

        self._startup_cb.setChecked(is_startup_enabled())

        self._hk_fullscreen.setKeySequence(
            QKeySequence.fromString(self._format_hotkey_display(hotkeys.get("fullscreen", "")))
        )
        self._hk_region.setKeySequence(
            QKeySequence.fromString(self._format_hotkey_display(hotkeys.get("region", "")))
        )
        self._hk_timed_region.setKeySequence(
            QKeySequence.fromString(
                self._format_hotkey_display(hotkeys.get("timed_region", ""))
            )
        )
        self._hk_ocr.setKeySequence(
            QKeySequence.fromString(self._format_hotkey_display(hotkeys.get("ocr", "")))
        )
        self._hk_scroll.setKeySequence(
            QKeySequence.fromString(self._format_hotkey_display(hotkeys.get("scroll", "")))
        )

        self._save_dir_edit.setText(self._config.save_directory)

        fmt = self._config.default_format.upper()
        idx = self._format_combo.findText(fmt)
        if idx >= 0:
            self._format_combo.setCurrentIndex(idx)

        self._auto_copy_cb.setChecked(
            self._config.get("auto_copy_clipboard", False)
        )

        language = str(self._config.get("ocr.language", "auto")).casefold()
        if language.startswith("ja"):
            language = "ja"
        elif language.startswith("en"):
            language = "en"
        idx = self._ocr_language_combo.findData(language)
        self._ocr_language_combo.setCurrentIndex(idx if idx >= 0 else 0)

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
        try:
            set_startup_enabled(self._startup_cb.isChecked())
        except OSError as exc:
            QMessageBox.critical(
                self,
                "Could not update startup setting",
                f"SnapEdit could not update the Windows startup entry.\n\n{exc}",
            )
            return
        self._config.set(
            "start_with_windows", self._startup_cb.isChecked()
        )

        # Hotkeys
        self._config.set(
            "hotkeys.fullscreen",
            self._format_hotkey_store(self._hk_fullscreen.keySequence()),
        )
        self._config.set(
            "hotkeys.region",
            self._format_hotkey_store(self._hk_region.keySequence()),
        )
        self._config.set(
            "hotkeys.timed_region",
            self._format_hotkey_store(self._hk_timed_region.keySequence()),
        )
        self._config.set(
            "hotkeys.ocr",
            self._format_hotkey_store(self._hk_ocr.keySequence()),
        )
        self._config.set(
            "hotkeys.scroll",
            self._format_hotkey_store(self._hk_scroll.keySequence()),
        )

        # Storage
        self._config.set("save_directory", self._save_dir_edit.text())
        self._config.set("default_format", self._format_combo.currentText().lower())
        self._config.set("auto_copy_clipboard", self._auto_copy_cb.isChecked())
        self._config.set("ocr.language", self._ocr_language_combo.currentData())

        self._config.save()
        self.accept()

    def _on_reset(self):
        """Reset config to factory defaults and reload the UI."""
        self._config.reset_to_defaults()
        self._load_from_config()
        self._startup_cb.setChecked(False)
