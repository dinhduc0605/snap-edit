"""Gallery dialog for recent captures and images in the save directory."""

from pathlib import Path

from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QIcon, QImageReader, QPixmap
from PyQt6.QtWidgets import (
    QDialog, QFrame, QLabel, QListView, QListWidget, QListWidgetItem,
    QVBoxLayout,
)

from theme import (
    ACCENT, BASE, BORDER, CONTROL_RADIUS, HOVER, SURFACE, SURFACE_ALT,
    TEXT_MUTED, TEXT_PRIMARY, TEXT_SECONDARY, TYPE_BODY_PT, TYPE_CAPTION_PT,
    TYPE_TITLE_PT,
)
from ui_scaling import WindowScaler


_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp", ".webp"}
_THUMBNAIL_SIZE = QSize(148, 96)


_STYLESHEET = f"""
QDialog {{
    background: {BASE};
    color: {TEXT_PRIMARY};
    font-family: 'Segoe UI Variable', 'Segoe UI';
    font-size: {TYPE_BODY_PT}pt;
}}
QLabel#galleryTitle {{
    color: {TEXT_PRIMARY};
    font-size: {TYPE_TITLE_PT}pt;
    font-weight: 600;
}}
QLabel#gallerySubtitle, QLabel#emptyHint {{
    color: {TEXT_MUTED};
    font-size: {TYPE_CAPTION_PT}pt;
}}
QLabel#sectionTitle {{
    color: {TEXT_SECONDARY};
    font-size: {TYPE_BODY_PT}pt;
    font-weight: 600;
}}
QFrame#sectionCard {{
    background: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: 8px;
}}
QListWidget {{
    background: transparent;
    color: {TEXT_PRIMARY};
    border: none;
    outline: none;
}}
QListWidget::item {{
    background: {SURFACE_ALT};
    border: 1px solid transparent;
    border-radius: {CONTROL_RADIUS}px;
    padding: 6px;
    margin: 3px;
}}
QListWidget::item:hover {{
    background: {HOVER};
    border-color: {BORDER};
}}
QListWidget::item:selected {{
    background: {HOVER};
    border-color: {ACCENT};
}}
QScrollBar:vertical, QScrollBar:horizontal {{
    background: transparent;
    width: 10px;
    height: 10px;
}}
QScrollBar::handle:vertical, QScrollBar::handle:horizontal {{
    background: {BORDER};
    border-radius: 5px;
    min-width: 28px;
    min-height: 28px;
}}
QScrollBar::add-line, QScrollBar::sub-line {{
    width: 0px;
    height: 0px;
}}
QScrollBar::add-page, QScrollBar::sub-page {{
    background: transparent;
}}
"""


class GalleryDialog(QDialog):
    """Show recent captures and saved images as selectable thumbnails."""

    def __init__(self, recent_screenshots, save_directory: str, parent=None):
        super().__init__(parent)
        self._recent_screenshots = list(recent_screenshots[:5])
        self._save_directory = Path(save_directory)
        self._selected_pixmap = QPixmap()
        self._disposed = False

        self.setWindowTitle("SnapEdit — Gallery")
        self.setMinimumSize(760, 560)
        self.resize(920, 680)
        self.setStyleSheet(_STYLESHEET)

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 18, 20, 20)
        root.setSpacing(12)

        title = QLabel("Gallery")
        title.setObjectName("galleryTitle")
        root.addWidget(title)
        subtitle = QLabel("Choose an image to open it in the editor")
        subtitle.setObjectName("gallerySubtitle")
        root.addWidget(subtitle)

        recent_card, self._recent_list = self._create_section(
            "Recent screenshots", fixed_height=188
        )
        root.addWidget(recent_card)

        saved_card, self._saved_list = self._create_section("Saved images")
        saved_card.setToolTip(str(self._save_directory))
        root.addWidget(saved_card, 1)

        self._recent_list.itemClicked.connect(self._select_item)
        self._saved_list.itemClicked.connect(self._select_item)
        self._ui_scaler = WindowScaler(self)
        self._thumbnail_size = _THUMBNAIL_SIZE * self._ui_scaler.scale
        self._populate_recent()
        self._populate_saved()
        self._ui_scaler.scale_changed.connect(self._refresh_thumbnails)

    def dispose(self):
        """Called after the caller has copied the selected result."""
        if self._disposed:
            return
        self._disposed = True
        self._ui_scaler.dispose()
        self._selected_pixmap = QPixmap()
        self._recent_screenshots.clear()
        self._recent_list.clear()
        self._saved_list.clear()

    def _refresh_thumbnails(self, scale):
        if self._disposed:
            return
        self._thumbnail_size = _THUMBNAIL_SIZE * scale
        # Re-render at the actual monitor DPI, not a permanent 4x allocation.
        self._recent_list.clear()
        self._populate_recent()
        for index in range(self._saved_list.count()):
            item = self._saved_list.item(index)
            path = item.data(Qt.ItemDataRole.UserRole + 1)
            if path:
                item.setIcon(QIcon(self._read_pixmap(Path(path), self._thumbnail_size)))

    @property
    def selected_pixmap(self) -> QPixmap:
        return self._selected_pixmap

    def _create_section(self, title_text: str, fixed_height=None):
        card = QFrame()
        card.setObjectName("sectionCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(12, 10, 12, 12)
        layout.setSpacing(6)

        title = QLabel(title_text)
        title.setObjectName("sectionTitle")
        title.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(title)

        image_list = QListWidget()
        image_list.setViewMode(QListView.ViewMode.IconMode)
        image_list.setResizeMode(QListView.ResizeMode.Adjust)
        image_list.setMovement(QListView.Movement.Static)
        image_list.setIconSize(_THUMBNAIL_SIZE)
        image_list.setGridSize(QSize(176, 132))
        image_list.setSpacing(2)
        image_list.setWordWrap(False)
        if fixed_height is not None:
            card.setFixedHeight(fixed_height)
            image_list.setFlow(QListView.Flow.LeftToRight)
            image_list.setWrapping(False)
            image_list.setHorizontalScrollBarPolicy(
                Qt.ScrollBarPolicy.ScrollBarAsNeeded
            )
        layout.addWidget(image_list, 1)
        return card, image_list

    def _populate_recent(self):
        if not self._recent_screenshots:
            self._add_empty_item(self._recent_list, "No screenshots captured yet")
            return
        for index, pixmap in enumerate(self._recent_screenshots):
            thumbnail = pixmap.scaled(
                self._thumbnail_size,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            item = QListWidgetItem(
                QIcon(thumbnail),
                f"Recent {index + 1}  ·  {pixmap.width()}×{pixmap.height()}",
            )
            item.setData(Qt.ItemDataRole.UserRole, "recent")
            item.setData(Qt.ItemDataRole.UserRole + 1, index)
            item.setToolTip(f"Recent screenshot {index + 1}")
            self._recent_list.addItem(item)

    def _populate_saved(self):
        try:
            paths = sorted(
                (
                    path for path in self._save_directory.iterdir()
                    if path.is_file() and path.suffix.lower() in _IMAGE_EXTENSIONS
                ),
                key=lambda path: path.stat().st_mtime,
                reverse=True,
            )
        except (FileNotFoundError, PermissionError, OSError):
            paths = []

        if not paths:
            self._add_empty_item(self._saved_list, "No saved images in this folder")
            return

        for path in paths:
            thumbnail = self._read_pixmap(path, self._thumbnail_size)
            if thumbnail.isNull():
                continue
            item = QListWidgetItem(QIcon(thumbnail), path.name)
            item.setData(Qt.ItemDataRole.UserRole, "saved")
            item.setData(Qt.ItemDataRole.UserRole + 1, str(path))
            item.setToolTip(str(path))
            self._saved_list.addItem(item)

        if self._saved_list.count() == 0:
            self._add_empty_item(self._saved_list, "No readable images in this folder")

    @staticmethod
    def _add_empty_item(image_list: QListWidget, text: str):
        item = QListWidgetItem(text)
        item.setFlags(Qt.ItemFlag.NoItemFlags)
        item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        image_list.addItem(item)

    @staticmethod
    def _read_pixmap(path: Path, maximum_size=None) -> QPixmap:
        reader = QImageReader(str(path))
        reader.setAutoTransform(True)
        if maximum_size is not None:
            source_size = reader.size()
            if source_size.isValid():
                source_size.scale(
                    maximum_size, Qt.AspectRatioMode.KeepAspectRatio
                )
                reader.setScaledSize(source_size)
        image = reader.read()
        return QPixmap.fromImage(image) if not image.isNull() else QPixmap()

    def _select_item(self, item: QListWidgetItem):
        source = item.data(Qt.ItemDataRole.UserRole)
        payload = item.data(Qt.ItemDataRole.UserRole + 1)
        if source == "recent" and isinstance(payload, int):
            if 0 <= payload < len(self._recent_screenshots):
                self._selected_pixmap = QPixmap(self._recent_screenshots[payload])
        elif source == "saved" and payload:
            self._selected_pixmap = self._read_pixmap(Path(payload))

        if not self._selected_pixmap.isNull():
            self.accept()
