from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QHBoxLayout
from qfluentwidgets import (
    CaptionLabel, FluentIcon, MessageBoxBase,
    SubtitleLabel, TeachingTip, TeachingTipTailPosition,
    TransparentToolButton,
)

from app.url_template import expandTemplate
from app.view.components.editors import AutoSizingEdit


class BatchUrlDialog(MessageBoxBase):

    def __init__(self, parent=None):
        super().__init__(parent)
        self._urls: list[str] = []
        self._expandTimer = QTimer(self, singleShot=True)

        self.titleLabel = SubtitleLabel(self.tr("批量添加"), self)
        self.helpButton = TransparentToolButton(FluentIcon.QUESTION, self)
        self.titleRow = QHBoxLayout()
        self.templateEdit = AutoSizingEdit(self, minimumVisibleLines=2, maximumVisibleLines=3)
        self.previewEdit = AutoSizingEdit(self, minimumVisibleLines=3, maximumVisibleLines=12)
        self.countLabel = CaptionLabel("", self)

        self._initWidget()
        self._initLayout()
        self._bind()

    def _initWidget(self) -> None:
        self.widget.setFixedWidth(600)
        self.templateEdit.setPlaceholderText(
            self.tr("http://example.com/img/[001-100].jpg\n"
                     "http://example.com/{mp4,mkv}/video")
        )
        self.previewEdit.setReadOnly(True)
        self.previewEdit.setPlaceholderText(self.tr("输入模板后在此预览"))
        self.countLabel.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.countLabel.setTextColor("grey", "grey")
        self.countLabel.hide()
        self.yesButton.setEnabled(False)

    def _initLayout(self) -> None:
        self.titleRow.addWidget(self.titleLabel)
        self.titleRow.addWidget(self.helpButton)
        self.titleRow.addStretch(1)
        self.titleRow.setContentsMargins(0, 0, 0, 0)

        self.viewLayout.addLayout(self.titleRow)
        self.viewLayout.addWidget(self.templateEdit)
        self.viewLayout.addWidget(self.previewEdit)
        self.viewLayout.addWidget(self.countLabel)
        self.viewLayout.setSpacing(8)
        self.viewLayout.setContentsMargins(24, 24, 24, 8)

    def _bind(self) -> None:
        self._expandTimer.setInterval(300)
        self._expandTimer.timeout.connect(self._onExpandNeeded)
        self.templateEdit.textChanged.connect(self._expandTimer.start)
        self.helpButton.clicked.connect(self._onHelpClicked)

    def urls(self) -> list[str]:
        return list(self._urls)

    def _onHelpClicked(self) -> None:
        TeachingTip.create(
            self.helpButton,
            self.tr("语法说明"),
            self.tr(
                "[1-100] → 1, 2, 3, …, 100\n"
                "[001-050] → 001, 002, …, 050 (自动补零)\n"
                "[1-10:2] → 1, 3, 5, 7, 9 (步长)\n"
                "[a-z] → a, b, …, z (字母范围)\n"
                "{mp4,mkv,avi} → mp4, mkv, avi (枚举)"
            ),
            tailPosition=TeachingTipTailPosition.BOTTOM,
            isClosable=True,
            duration=-1,
            parent=self,
        )

    def _onExpandNeeded(self) -> None:
        template = self.templateEdit.toPlainText().strip()
        if not template:
            self._urls = []
            self.previewEdit.clear()
            self.countLabel.hide()
            self.yesButton.setEnabled(False)
            return

        self._urls = expandTemplate(template)
        count = len(self._urls)
        self.yesButton.setEnabled(count > 0)

        if count == 0:
            self.previewEdit.clear()
            self.countLabel.hide()
        else:
            lines = self._urls[:10]
            if count > 10:
                lines.append("⋯")
                lines.append(self._urls[-1])
            self.previewEdit.setPlainText("\n".join(lines))
            self.countLabel.setText(self.tr("共 {} 个链接").format(count))
            self.countLabel.show()
