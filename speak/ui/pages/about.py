"""About page: version, sponsor links, and open-source notices."""
from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QHBoxLayout, QPushButton, QVBoxLayout, QWidget

from ... import config, platform_utils, updates
from ..controls import Page, make_card, make_label


def _open_url(url: str):
    QDesktopServices.openUrl(QUrl(url))


class AboutPage(Page):
    def __init__(self, logo: QWidget):
        super().__init__()
        head = QHBoxLayout()
        head.setSpacing(14)
        head.addWidget(logo, 0, Qt.AlignVCenter)
        names = QVBoxLayout()
        names.setSpacing(2)
        names.addWidget(make_label("Speak", "title"))
        names.addWidget(make_label(updates.display(), "muted"))
        head.addLayout(names, 1)
        self.layout_.addLayout(head)
        self.layout_.addWidget(make_label("Talk anywhere and Speak types it for you. Private, offline and free.",
                                          "muted"))
        self.layout_.addSpacing(6)

        self.layout_.addWidget(make_label("Support Speak", "section"))
        card, rows = make_card()
        rows.setContentsMargins(18, 16, 18, 16)
        rows.setSpacing(12)
        rows.addWidget(make_label("Speak is free, with no ads, no account and no paid tier. "
                                  "If it saves you time, sponsoring keeps it going and growing."))
        buttons = QHBoxLayout()
        buttons.setSpacing(10)
        sponsor = QPushButton("♥  Sponsor on GitHub", objectName="primary", cursor=Qt.PointingHandCursor)
        sponsor.clicked.connect(lambda: _open_url(config.SPONSOR_URL))
        coffee = QPushButton("Buy me a coffee", cursor=Qt.PointingHandCursor)
        coffee.clicked.connect(lambda: _open_url(config.COFFEE_URL))
        buttons.addWidget(sponsor)
        buttons.addWidget(coffee)
        buttons.addStretch(1)
        rows.addLayout(buttons)
        rows.addWidget(make_label("GitHub takes no fee from sponsorships, monthly or one-off. "
                                  "Or buy a one-off coffee with a card, no account needed.", "hint"))
        self.layout_.addWidget(card)
        self.layout_.addSpacing(6)

        self.layout_.addWidget(make_label("Open source", "section"))
        links = make_label('Speak is built on open-source software and open models.<br>'
                           '<a href="source">Source code</a> &nbsp;·&nbsp; <a href="notices">Open-source notices</a>'
                           ' &nbsp;·&nbsp; <a href="issues">Report a problem</a>', "muted")
        links.setTextFormat(Qt.RichText)
        links.linkActivated.connect(self._open_link)
        self.layout_.addWidget(links)
        self.layout_.addStretch(1)

    def _open_link(self, link: str):
        notices = platform_utils.notices_file()
        if link == "notices" and notices.is_file():
            platform_utils.open_path(notices)
            return
        _open_url(config.REPO_URL + {"source": "", "issues": "/issues",
                                     "notices": "/blob/main/docs/licensing-and-privacy.md"}[link])
