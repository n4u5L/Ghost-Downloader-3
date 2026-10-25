"""浮在窗口右下角的消息条，对应 qfluentwidgets 的 InfoBar（水平排列，InfoBarPosition.BOTTOM_RIGHT）。"""
from __future__ import annotations

from enum import Enum

from bkit import ui

from app.ui.icons import buildIcon
from app.ui.layout import row, text
from app.ui.loop import UiLoop
from app.ui.theme import statusColor

MAX_CONTENT_LINES = 6


class InfoBarIcon(Enum):
    """(图标名, statusColor() 的状态)；没有状态的图标跟随内容色。"""
    INFO = ("info", None)
    CLOUD = ("cloud", None)
    SUCCESS = ("check_circle", "success")
    WARNING = ("error", "warning")
    ERROR = ("error", "error")

    @property
    def iconName(self) -> str:
        return self.value[0]

    @property
    def tint(self) -> int | None:
        status = self.value[1]
        return None if status is None else statusColor(status)


class InfoBar(ui.Node):
    """一行里依次是图标、标题、内容、addWidget() 加的控件和关闭按钮。"""

    def __init__(self, area: InfoBarArea, icon: InfoBarIcon, title: str, content: str) -> None:
        super().__init__()
        self._area = area
        self._isClosed = False
        self._initWidget(icon, title, content)

    def _initWidget(self, icon: InfoBarIcon, title: str, content: str) -> None:
        self.iconWidget = buildIcon(icon.iconName, tint=icon.tint)
        self.titleLabel = text(title, fontWeight=600)
        self.contentLabel = text(content, maxLines=MAX_CONTENT_LINES)
        self.closeButton = ui.IconButton(ui.MaterialIcon.CLOSE, self.close)
        self.hBoxLayout = row(self.iconWidget, self.titleLabel, spacing=12)
        if content:
            self.hBoxLayout.append_child(self.contentLabel)
        self.hBoxLayout.append_child(self.closeButton)
        card = ui.Card(ui.CardStyle.ELEVATED)
        card.set_padding(16, 6, 8, 6)
        card.append_child(self.hBoxLayout)
        self.append_child(card)

    def addWidget(self, node: ui.Node) -> None:
        self.hBoxLayout.insert_child(len(self.hBoxLayout.children) - 1, node)

    def close(self) -> None:
        if self._isClosed:
            return
        self._isClosed = True
        self._area.remove(self)


class InfoBarArea:
    """消息条从下往上叠放；duration 秒后自动关闭，None 时一直显示到用户关闭。"""

    def __init__(self, uiLoop: UiLoop) -> None:
        self._uiLoop = uiLoop
        self.node = ui.Column(spacing=8)
        self.node.set_cross_alignment(ui.Alignment.END)

    def add(self, title: str, content: str = "", *, icon: InfoBarIcon = InfoBarIcon.INFO,
            duration: float | None = 5.0) -> InfoBar:
        bar = InfoBar(self, icon, title, content)
        self.node.append_child(bar)
        if duration is not None:
            self._uiLoop.post(bar.close, duration)
        return bar

    def remove(self, bar: InfoBar) -> None:
        self.node.remove_child(self.node.children.index(bar))
