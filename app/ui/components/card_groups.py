from __future__ import annotations

from typing import TYPE_CHECKING

from bkit import ui

from app.format import toReadableSize
from app.i18n import tr
from app.ui.layout import column, row, text
from app.ui.theme import statusColor

if TYPE_CHECKING:
    from app.ui.components.option_cards import OptionCard


class TitledCardGroup(ui.Node):
    """带标题的一组卡片，外框为描边卡片。"""

    def __init__(self) -> None:
        super().__init__()
        self.headerLabel = text(fontSize=15, fontWeight=600)
        self.headerLayout = row(self.headerLabel, spacing=8, flex=0)
        self.scrollLayout = column()
        self._initLayout()

    def _initLayout(self) -> None:
        header = ui.Box()
        header.set_padding(16, 8)
        header.append_child(self.headerLayout)
        self.vBoxLayout = column(header, self._buildBody())
        card = ui.Card(ui.CardStyle.OUTLINED)
        card.append_child(self.vBoxLayout)
        self.append_child(card)

    def _buildBody(self) -> ui.Node:
        return self.scrollLayout

    def setTitle(self, title: str) -> None:
        self.headerLabel.text = title

    def addCard(self, card: ui.Node) -> None:
        self.scrollLayout.append_child(card)


class DraftCardGroup(TitledCardGroup):
    """解析结果；超过 MAX_VISIBLE 行时在组内滚动。"""

    CARD_HEIGHT = 48
    MAX_VISIBLE = 5

    def __init__(self) -> None:
        super().__init__()
        self._cardByUrl: dict[str, ui.Node] = {}
        self._ratioLabel = text()
        self._ratioLabel.set_color(statusColor("warning"))
        self._sizeLabel = text()
        self.headerLayout.append_child(self._ratioLabel)
        self.headerLayout.append_child(self._sizeLabel)
        self.setTitle(tr("DraftCardGroup", "解析结果"))
        self._refreshHeight()

    def _buildBody(self) -> ui.Node:
        scroll = ui.ScrollContainer()
        scroll.append_child(self.scrollLayout)
        self.listBox = ui.Box()
        self.listBox.append_child(scroll)
        return self.listBox

    def updateStats(self, successCount: int, failCount: int, totalSize: int) -> None:
        totalCount = successCount + failCount
        self._ratioLabel.text = f"{successCount}/{totalCount}" if failCount > 0 else ""
        if totalCount and totalSize > 0:
            self._sizeLabel.text = toReadableSize(totalSize)
        elif successCount > 0:
            self._sizeLabel.text = tr("DraftCardGroup", "{0} 个任务").format(successCount)
        else:
            self._sizeLabel.text = ""

    def addCard(self, url: str, card: ui.Node) -> None:
        old = self._cardByUrl.pop(url, None)
        if old is not None:
            self.scrollLayout.remove_child(self.scrollLayout.children.index(old))
        self._cardByUrl[url] = card
        self.scrollLayout.append_child(card)
        self._refreshHeight()

    def setUrls(self, urls: list[str]) -> None:
        keep = set(urls)
        for url in [u for u in self._cardByUrl if u not in keep]:
            card = self._cardByUrl.pop(url)
            self.scrollLayout.remove_child(self.scrollLayout.children.index(card))
        ordered = [self._cardByUrl[u] for u in urls if u in self._cardByUrl]
        if list(self.scrollLayout.children) != ordered:
            while self.scrollLayout.children:
                self.scrollLayout.remove_child(0)
            for card in ordered:
                self.scrollLayout.append_child(card)
        self._refreshHeight()

    def clear(self) -> None:
        while self.scrollLayout.children:
            self.scrollLayout.remove_child(0)
        self._cardByUrl.clear()
        self._refreshHeight()

    def _refreshHeight(self) -> None:
        self.listBox.set_size(None, min(len(self._cardByUrl), self.MAX_VISIBLE) * self.CARD_HEIGHT)


class OptionCardGroup(TitledCardGroup):
    def __init__(self) -> None:
        super().__init__()
        self._cards: list[OptionCard] = []
        self.setTitle(tr("OptionCardGroup", "下载设置"))

    def addCard(self, card: OptionCard) -> None:
        self._cards.append(card)
        super().addCard(card)

    def options(self) -> dict:
        result = {}
        for card in self._cards:
            result.update(card.options())
        return result

    def reset(self) -> None:
        for card in self._cards:
            card.reset()
