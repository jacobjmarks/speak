"""First-run setup page, shown instead of the app until every OS permission is granted (macOS)."""
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout

from ... import permissions
from ..controls import Page, make_card, make_label


class SetupPage(Page):
    """Shown instead of the app until every OS permission in `permissions.REQUIRED` is granted."""

    allow_clicked = Signal(str)
    settings_clicked = Signal(str)
    restart_clicked = Signal()

    def __init__(self):
        super().__init__()
        self.layout_.setContentsMargins(48, 36, 48, 28)
        self.layout_.addStretch(1)
        self.layout_.addWidget(make_label("Set up Speak", "title"))
        self.layout_.addWidget(make_label(
            "Speak needs three permissions from macOS. Click Allow on each and approve it; this page updates as you go.",
            "muted"))
        self.layout_.addSpacing(6)
        self._rows = {}
        for permission in permissions.REQUIRED:
            card, layout = make_card()
            layout.setContentsMargins(18, 14, 18, 14)
            row = QHBoxLayout()
            row.setSpacing(12)
            mark = QLabel("○")
            mark.setFixedWidth(22)
            text = QVBoxLayout()
            text.setSpacing(2)
            title = QLabel(permission.title)
            title.setStyleSheet("font-weight: 600;")
            text.addWidget(title)
            text.addWidget(make_label(permission.why, "hint"))
            allow = QPushButton("Allow", objectName="primary", cursor=Qt.PointingHandCursor)
            allow.clicked.connect(lambda _=False, pid=permission.id: self.allow_clicked.emit(pid))
            settings = QPushButton("Open Settings", objectName="ghost", cursor=Qt.PointingHandCursor)
            settings.clicked.connect(lambda _=False, pid=permission.id: self.settings_clicked.emit(pid))
            row.addWidget(mark)
            row.addLayout(text, 1)
            row.addWidget(settings)
            row.addWidget(allow)
            layout.addLayout(row)
            self.layout_.addWidget(card)
            self._rows[permission.id] = (mark, allow, settings)
        self.layout_.addSpacing(6)
        footer = QHBoxLayout()
        footer.addWidget(make_label("If a permission shows as allowed in Settings but stays unchecked here, "
                                    "restart Speak.", "hint"), 1)
        restart = QPushButton("Restart Speak", objectName="ghost", cursor=Qt.PointingHandCursor)
        restart.clicked.connect(self.restart_clicked)
        footer.addWidget(restart)
        self.layout_.addLayout(footer)
        self.layout_.addStretch(2)

    def set_status(self, granted: dict, palette) -> None:
        for pid, (mark, allow, settings) in self._rows.items():
            ok = granted.get(pid, False)
            mark.setText("✓" if ok else "○")
            mark.setStyleSheet(f"color: {palette.success if ok else palette.muted}; font-size: 14pt; font-weight: 700;")
            allow.setVisible(not ok)
            settings.setVisible(not ok)
