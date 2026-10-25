from __future__ import annotations

import re

from bkit import ui

from app.ui.components.menu import buildMenu, openTeachingTip
from app.ui.components.message_box import MessageBoxBase
from app.ui.components.option_cards import addProfileItems, toProfileLabel
from app.i18n import tr
from app.ui.icons import buildIconButton
from app.ui.layout import row, text
from app.ui.theme import statusColor

WIDTH = 480
HOST_SEPARATOR = re.compile(r"[\s,，;；]+")


def T(text: str) -> str:
    return tr("PresetEditDialog", text)


class PresetEditDialog(MessageBoxBase):
    """添加或编辑身份预设。Qt 界面的 TokenLineEdit 改为一个输入框，Host 以空格或逗号分隔。"""

    def __init__(self, host: ui.Node, *, preset: dict | None = None) -> None:
        super().__init__(host)
        self._preset = preset
        self._profileValue = preset.get("clientProfile", "") if preset else ""
        self._menu: ui.DropdownMenu | None = None
        self._initWidget()
        self._initLayout()
        self._populate()

    def _initWidget(self) -> None:
        self.dialog.set_title(T("编辑身份预设") if self._preset else T("添加身份预设"))
        self.dialog.platform_default_width = WIDTH
        self.yesButton.text = T("确定")
        self.cancelButton.text = T("取消")
        self.nameEdit = ui.OutlinedTextField()
        self.nameEdit.set_placeholder(T("预设名称"))
        self.nameEdit.set_line_limits(single_line=True)
        self.hostsEdit = ui.OutlinedTextField()
        self.hostsEdit.set_line_limits(single_line=True)
        self.hostsHelpBox, self.hostsHelpButton = buildIconButton("help", T("Host 匹配规则"), self._onHostsHelpClicked)
        self.profileButton = ui.Button("", self._onProfileClicked, ui.ButtonStyle.OUTLINED)
        self.uaEdit = ui.OutlinedTextField()
        self.uaEdit.set_placeholder(T("留空则跟随 TLS 指纹自动生成"))
        self.uaEdit.set_line_limits(single_line=True)
        self.warningLabel = ui.Text("", color=statusColor("error"))

    def _initLayout(self) -> None:
        for label, node in ((T("名称"), self.nameEdit), (T("匹配 Host"), self.hostsEdit),
                            (T("TLS 指纹"), self.profileButton), (T("User-Agent"), self.uaEdit)):
            self.viewLayout.append_child(row(text(label), self.hostsHelpBox, spacing=4)
                                         if node is self.hostsEdit else text(label))
            self.viewLayout.append_child(node)
        self.viewLayout.append_child(self.warningLabel)

    def _populate(self) -> None:
        self._refreshProfileLabel()
        if self._preset is None:
            return
        self.nameEdit.state.text = self._preset.get("name", "")
        self.hostsEdit.state.text = " ".join(self._preset.get("hosts", []))
        self.uaEdit.state.text = self._preset.get("userAgent", "")

    def _onHostsHelpClicked(self) -> None:
        self._menu = openTeachingTip(self.hostsHelpButton, T("Host 匹配规则"), T(
            "输入域名后按回车添加，支持两种格式：\n\n"
            "精确匹配: pcs.baidu.com\n"
            "通配符: *.pcs.baidu.com（匹配所有子域名）"
        ))

    def _onProfileClicked(self) -> None:
        menu = buildMenu(self.profileButton)
        addProfileItems(menu, self._onProfilePick, includeAuto=False)
        self._menu = menu
        menu.expanded = True

    def _onProfilePick(self, value: str) -> None:
        self._profileValue = value
        self._refreshProfileLabel()

    def _refreshProfileLabel(self) -> None:
        self.profileButton.text = toProfileLabel(self._profileValue) if self._profileValue else T("跟随全局默认")

    def _hosts(self) -> list[str]:
        return [host for host in HOST_SEPARATOR.split(self.hostsEdit.state.text) if host]

    def close(self, isAccepted: bool) -> None:
        if isAccepted and not self._hosts():
            self.warningLabel.text = f"{T('请添加匹配 Host')}：{T('预设需要至少一个 Host 才能匹配请求')}"
            return
        super().close(isAccepted)

    def preset(self) -> dict:
        return {
            "name": self.nameEdit.state.text.strip() or T("未命名预设"),
            "clientProfile": self._profileValue,
            "userAgent": self.uaEdit.state.text.strip(),
            "hosts": self._hosts(),
            "isEnabled": self._preset.get("isEnabled", True) if self._preset is not None else True,
        }
