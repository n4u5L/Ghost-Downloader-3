from __future__ import annotations

from bkit import ui

from app.header_text import parseHeaders, toHeadersText
from app.ui.components.message_box import MessageBoxBase
from app.i18n import tr
from app.ui.theme import statusColor

WIDTH = 500


def T(text: str) -> str:
    return tr("HeadersPresetEditDialog", text)


class HeadersPresetEditDialog(MessageBoxBase):
    """编辑标头预设。Qt 界面的表格与文本两种视图只保留文本：每行 name: value，也可直接粘贴 cURL 命令。"""

    def __init__(self, host: ui.Node, *, preset: dict) -> None:
        super().__init__(host)
        self._initWidget(preset)
        self._initLayout()

    def _initWidget(self, preset: dict) -> None:
        self.dialog.platform_default_width = WIDTH
        self.yesButton.text = T("确定")
        self.cancelButton.text = T("取消")
        self.nameEdit = ui.OutlinedTextField(ui.TextFieldState(preset["name"]))
        self.nameEdit.set_placeholder(T("预设名称"))
        self.nameEdit.set_line_limits(single_line=True)
        self.headersEdit = ui.OutlinedTextField(ui.TextFieldState(toHeadersText(list(preset["headers"].items()))))
        self.headersEdit.set_line_limits(min_lines=6, max_lines=16)
        self.warningLabel = ui.Text("", color=statusColor("error"))

    def _initLayout(self) -> None:
        for node in (self.nameEdit, self.headersEdit, self.warningLabel):
            self.viewLayout.append_child(node)

    def close(self, isAccepted: bool) -> None:
        if isAccepted and not self.nameEdit.state.text.strip():
            self.warningLabel.text = f"{T('请输入预设名称')}：{T('预设名称不能为空')}"
            return
        super().close(isAccepted)

    def preset(self) -> dict:
        return {
            "name": self.nameEdit.state.text.strip() or T("未命名预设"),
            # 与 HeadersEditor.headers() 一致：名称转小写，丢掉空值
            "headers": {name.strip().lower(): value.strip()
                        for name, value in parseHeaders(self.headersEdit.state.text)
                        if name.strip() and value.strip()},
        }
