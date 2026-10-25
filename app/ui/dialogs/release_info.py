"""新版本详情：更新说明和可下载的文件。bkit 没有 Markdown 渲染，更新说明按原文显示。"""
from __future__ import annotations

from typing import TYPE_CHECKING

from bkit import ui

from app.config.constants import DONATE_URL
from app.format import toReadableSize
from app.platform.shell import openUrl
from app.ui.components.message_box import MessageBoxBase
from app.ui.components.setting_cards import fixedWidth
from app.i18n import tr
from app.ui.icons import buildIconButton
from app.ui.layout import column, row, text
from app.ui.theme import statusColor
from app.update import bestAsset

if TYPE_CHECKING:
    from app.sources import Release, ReleaseAsset

WIDTH = 640
ASSET_NAME_WIDTH = 340
ASSET_SIZE_WIDTH = 100
ASSET_COUNT_WIDTH = 80


def T(text: str) -> str:
    return tr("ReleaseInfoDialog", text)


class ReleaseInfoDialog(MessageBoxBase):

    def __init__(self, release: Release, host: ui.Node) -> None:
        super().__init__(host)
        self._release = release
        self._selected: ReleaseAsset | None = bestAsset(release)
        self._rows: list[tuple[ui.Button, ReleaseAsset]] = []
        self._initWidget()
        self._initLayout()

    def _initWidget(self) -> None:
        release = self._release
        self.dialog.platform_default_width = WIDTH
        self.yesButton.text = T("下载")
        self.versionLabel = text(release.version, fontSize=20, fontWeight=600)
        self.dateLabel = text(release.publishedAt[:10] if release.publishedAt else "", fontSize=12)
        self.prereleaseLabel = ui.Text(T("⚠️ 预发布版本") if release.prerelease else "", color=statusColor("warning"))
        self.detailBox, _ = buildIconButton("link", T("打开发布页"), lambda: openUrl(release.pageUrl),
                                            ui.IconButtonVariant.FILLED)
        self.sponsorBox, _ = buildIconButton("favorite", T("赞助作者"), lambda: openUrl(DONATE_URL),
                                             ui.IconButtonVariant.OUTLINED)
        self.descriptionEdit = ui.Text(release.body or T("暂无更新说明"))

    def _initLayout(self) -> None:
        self.viewLayout.append_child(row(self.versionLabel, self.dateLabel, self.prereleaseLabel, ui.Spacer(),
                                         self.detailBox, self.sponsorBox, spacing=6, flex=3))
        self.viewLayout.append_child(self.descriptionEdit)
        if not self._release.assets:
            return
        # 对应 assetView 表格：表头一行，每个文件一行，点一行选中它
        table = column(self._buildAssetRow(T("文件名"), T("大小"), T("下载次数")), spacing=2)
        for asset in self._release.assets:
            button = ui.Button([self._buildAssetRow(asset.name, toReadableSize(asset.size), str(asset.downloadCount))],
                               lambda a=asset: self._setSelected(a), ui.ButtonStyle.TEXT)
            button.set_content_padding(0)
            self._rows.append((button, asset))
            table.append_child(button)
        card = ui.Card(ui.CardStyle.OUTLINED)
        card.set_padding(8, 4)
        card.append_child(table)
        self.viewLayout.append_child(card)
        self._refreshRows()

    def _buildAssetRow(self, name: str, size: str, count: str) -> ui.Node:
        cells = [(name, ASSET_NAME_WIDTH), (size, ASSET_SIZE_WIDTH), (count, ASSET_COUNT_WIDTH)]
        box = ui.Box()
        box.set_padding(8, 6)
        box.append_child(row(*(fixedWidth(text(value), width) for value, width in cells), spacing=8))
        return box

    def selectedAsset(self) -> ReleaseAsset | None:
        return self._selected

    def close(self, isAccepted: bool) -> None:
        if isAccepted and self._selected is None:
            return
        super().close(isAccepted)

    def _setSelected(self, asset: ReleaseAsset) -> None:
        self._selected = asset
        self._refreshRows()

    def _refreshRows(self) -> None:
        for button, asset in self._rows:
            button.set_style(ui.ButtonStyle.FILLED_TONAL if asset is self._selected else ui.ButtonStyle.TEXT)
            button.set_content_padding(0)
