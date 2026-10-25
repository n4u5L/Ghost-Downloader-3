from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from bkit import ui

from app.services.update_service import UpdateState
from app.ui.components.message_box import MessageBoxBase
from app.i18n import tr
from app.ui.icons import buildIconButton
from app.ui.layout import row, text
from app.ui.theme import schemeColor, statusColor

if TYPE_CHECKING:
    from app.models.pack import FeaturePack
    from app.services.update_service import UpdateInfo, UpdateService

# (符号, statusColor() 的状态)；下载中没有状态，用主色
STATUSES = {
    UpdateState.AVAILABLE: ("↑", "warning"),
    UpdateState.DOWNLOADING: ("↓", None),
    UpdateState.READY: ("✓", "success"),
    UpdateState.FAILED: ("✗", "error"),
}


def T(text: str) -> str:
    return tr("PackInfoDialog", text)


def toStatusLabel(state: UpdateState) -> ui.Text:
    symbol, status = STATUSES[state]
    return ui.Text(symbol, color=schemeColor("primary") if status is None else statusColor(status))


class PackRow(ui.Node):
    def __init__(self, pack: FeaturePack, onRetry: Callable[[], object]) -> None:
        super().__init__()
        self.statusSlot = ui.Box()
        self.statusSlot.append_child(toStatusLabel(UpdateState.READY))
        self.retryBox, _ = buildIconButton("sync", T("重试"), onRetry)
        self.retrySlot = ui.Box()
        box = ui.Box()
        box.set_padding(4)
        box.append_child(row(text(type(pack).__name__), text(f"v{pack.manifest.version}"), self.statusSlot,
                             self.retrySlot, spacing=8, flex=0))
        self.append_child(box)

    def update(self, info: UpdateInfo) -> None:
        if info.state not in STATUSES:
            return
        self.statusSlot.remove_child(0)
        self.statusSlot.append_child(toStatusLabel(info.state))
        isFailed = info.state == UpdateState.FAILED
        if isFailed and not self.retrySlot.children:
            self.retrySlot.append_child(self.retryBox)
        elif not isFailed and self.retrySlot.children:
            self.retrySlot.remove_child(0)


class PackInfoDialog(MessageBoxBase):

    def __init__(self, packs: list[FeaturePack], updateService: UpdateService, host: ui.Node) -> None:
        super().__init__(host)
        self._updateService = updateService
        self._rows: dict[str, PackRow] = {}
        self._initWidget(packs)
        self._bind()

    def _initWidget(self, packs: list[FeaturePack]) -> None:
        self.dialog.set_title(T("功能包"))
        self.yesButton.text = T("关闭")
        self.buttonLayout.remove_child(self.buttonLayout.children.index(self.cancelButton))
        for pack in packs:
            if pack.manifest is None:
                continue
            manifestName = pack.manifest.name
            packRow = PackRow(pack, lambda n=manifestName: self._updateService.download(n))
            self._rows[manifestName] = packRow
            self.viewLayout.append_child(packRow)

    def _bind(self) -> None:
        self._updateService.changed.connect(self._onUpdateChanged)

    def _onUpdateChanged(self, info: UpdateInfo) -> None:
        packRow = self._rows.get(info.targetId)
        if packRow is not None:
            packRow.update(info)
