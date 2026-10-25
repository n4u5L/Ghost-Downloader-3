"""应用更新的下载进度，对应 Qt 界面的 ProgressToast：一条不自动关闭的消息条，底部是进度条。"""
from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from bkit import ui

from app.services.update_service import UpdateState
from app.ui.components.info_bar import InfoBarArea, InfoBarIcon
from app.ui.i18n import toLocalizedError, tr
from app.ui.icons import buildIcon, loadIcon
from app.ui.layout import column, row, text
from app.ui.theme import isDark

if TYPE_CHECKING:
    from app.services.update_service import UpdateInfo

# 进度条要和卡片同宽，卡片定宽，不像普通消息条那样随内容伸缩
WIDTH = 420
COLORS = {
    UpdateState.DOWNLOADING: (0xFF9D5D00, 0xFFFCE100),
    UpdateState.READY: (0xFF0F7B0F, 0xFF6CCB5F),
    UpdateState.FAILED: (0xFFC42B1C, 0xFFFF99A4),
}
ICONS = {
    UpdateState.DOWNLOADING: InfoBarIcon.WARNING,
    UpdateState.READY: InfoBarIcon.SUCCESS,
    UpdateState.FAILED: InfoBarIcon.ERROR,
}


def T(text: str) -> str:
    return tr("ProgressToast", text)


class ProgressToast(ui.Node):

    def __init__(self, area: InfoBarArea, onRetry: Callable[[], object], onRestart: Callable[[], object]) -> None:
        super().__init__()
        self._area = area
        self._isDismissed = False
        self._state: UpdateState | None = None
        self._initWidget(onRetry, onRestart)
        self._initLayout()

    def _initWidget(self, onRetry: Callable[[], object], onRestart: Callable[[], object]) -> None:
        self.iconSlot = ui.Box()
        self.titleLabel = text(fontWeight=600)
        self.contentLabel = text(maxLines=4)
        self.progressBar = ui.LinearProgressIndicator()
        self.progressBar.set_size(WIDTH, 3)
        self.progressBar.set_colors(track=0)
        self.retryBox = ui.IconButton(loadIcon("sync"), onRetry)
        self.restartBox = ui.IconButton(loadIcon("power_settings_new"), onRestart)
        self.buttonSlot = ui.Box()
        self.closeButton = ui.IconButton(ui.MaterialIcon.CLOSE, self._onUserClose)

    def _initLayout(self) -> None:
        # 与 InfoBar 一样水平排列，进度条贴着底边
        card = ui.Card(ui.CardStyle.ELEVATED)
        card.set_padding(16, 6, 8, 0)
        card.append_child(column(
            row(self.iconSlot, self.titleLabel, self.contentLabel, ui.Spacer(), self.buttonSlot, self.closeButton,
                spacing=12, flex=3),
            self.progressBar,
            spacing=2,
        ))
        box = ui.Box()
        box.set_size(WIDTH, None)
        box.append_child(card)
        self.append_child(box)

    def setInfo(self, info: UpdateInfo) -> None:
        if info.state == UpdateState.DOWNLOADING:
            if self._isDismissed:
                return
            self.titleLabel.text = T("正在下载更新")
            self.contentLabel.text = f"{info.latestVersion} ({info.progress:.0f}%)"
            self.progressBar.progress = info.progress / 100
            self._setButton(None)
        elif info.state == UpdateState.READY:
            self._isDismissed = False
            self.titleLabel.text = T("更新已就绪")
            self.contentLabel.text = T("重启后生效")
            self.progressBar.progress = 1
            self._setButton(self.restartBox)
        elif info.state == UpdateState.FAILED:
            self._isDismissed = False
            self.titleLabel.text = T("下载更新失败")
            self.contentLabel.text = toLocalizedError(info.error) if info.error is not None else T("未知错误")
            self.progressBar.progress = 1
            self._setButton(self.retryBox)
        else:
            return
        self._setState(info.state)
        if self.parent is None:
            self._area.node.append_child(self)

    def _setState(self, state: UpdateState) -> None:
        if state == self._state:
            return
        self._state = state
        light, dark = COLORS[state]
        self.progressBar.set_colors(indicator=dark if isDark() else light)
        iconName, color = ICONS[state].value
        if self.iconSlot.children:
            self.iconSlot.remove_child(0)
        self.iconSlot.append_child(buildIcon(iconName, tint=color))

    def _setButton(self, button: ui.Node | None) -> None:
        if self.buttonSlot.children:
            self.buttonSlot.remove_child(0)
        if button is not None:
            self.buttonSlot.append_child(button)

    def close(self) -> None:
        if self.parent is not None:
            self._area.node.remove_child(self._area.node.children.index(self))

    def _onUserClose(self) -> None:
        # 用户关掉后下载进度不再弹出，就绪或失败时才再出现
        self._isDismissed = True
        self.close()
