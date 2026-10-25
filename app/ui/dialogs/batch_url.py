from __future__ import annotations

from bkit import ui

from app.ui.components.menu import openTeachingTip
from app.ui.components.message_box import MessageBoxBase
from app.i18n import tr
from app.ui.icons import buildIconButton
from app.ui.layout import row, text
from app.ui.loop import SingleShotTimer, UiLoop
from app.url_template import expandTemplate

WIDTH = 600
EXPAND_INTERVAL = 0.3
PREVIEW_COUNT = 10


def T(text: str) -> str:
    return tr("BatchUrlDialog", text)


class BatchUrlDialog(MessageBoxBase):

    def __init__(self, host: ui.Node, uiLoop: UiLoop) -> None:
        super().__init__(host)
        self._urls: list[str] = []
        self._tip: ui.DropdownMenu | None = None
        self._expandTimer = SingleShotTimer(uiLoop.post, EXPAND_INTERVAL, self._onExpandNeeded)
        self._initWidget()
        self._initLayout()
        self._bind()

    def _initWidget(self) -> None:
        self.dialog.platform_default_width = WIDTH
        self.helpBox, self.helpButton = buildIconButton("help", T("语法说明"), self._onHelpClicked)
        self.templateEdit = ui.OutlinedTextField()
        self.templateEdit.set_placeholder(T("http://example.com/img/[001-100].jpg\n"
                                            "http://example.com/{mp4,mkv}/video"))
        self.templateEdit.set_line_limits(min_lines=2, max_lines=3)
        self.previewEdit = ui.OutlinedTextField()
        self.previewEdit.read_only = True
        self.previewEdit.set_placeholder(T("输入模板后在此预览"))
        self.previewEdit.set_line_limits(min_lines=3, max_lines=12)
        self.countLabel = text()
        self.yesButton.enabled = False

    def _initLayout(self) -> None:
        self.viewLayout.append_child(row(text(T("批量添加"), fontSize=20, fontWeight=600), self.helpBox, spacing=4))
        self.viewLayout.append_child(self.templateEdit)
        self.viewLayout.append_child(self.previewEdit)
        self.viewLayout.append_child(row(ui.Spacer(), self.countLabel, flex=0))

    def _bind(self) -> None:
        self.templateEdit.on_value_change = self._expandTimer.start

    def _onHelpClicked(self) -> None:
        self._tip = openTeachingTip(self.helpButton, T("语法说明"), T(
            "[1-100] → 1, 2, 3, …, 100\n"
            "[001-050] → 001, 002, …, 050 (自动补零)\n"
            "[1-10:2] → 1, 3, 5, 7, 9 (步长)\n"
            "[a-z] → a, b, …, z (字母范围)\n"
            "{mp4,mkv,avi} → mp4, mkv, avi (枚举)"
        ))

    def urls(self) -> list[str]:
        return list(self._urls)

    def _onExpandNeeded(self) -> None:
        template = self.templateEdit.state.text.strip()
        self._urls = expandTemplate(template) if template else []
        count = len(self._urls)
        self.yesButton.enabled = count > 0
        if count == 0:
            self.previewEdit.state.text = ""
            self.countLabel.text = ""
            return
        lines = self._urls[:PREVIEW_COUNT]
        if count > PREVIEW_COUNT:
            lines += ["⋯", self._urls[-1]]
        self.previewEdit.state.text = "\n".join(lines)
        self.countLabel.text = T("共 {} 个链接").format(count)
