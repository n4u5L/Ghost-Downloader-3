from __future__ import annotations

from typing import TYPE_CHECKING

from bkit import ui

from app.config.cfg import cfg
from app.signal import Signal
from app.ui.icons import loadIcon
from app.ui.layout import ClickArea, column, row, text

if TYPE_CHECKING:
    from app.ui.components.setting_cards import SettingCard


def isSearchMatch(card: SettingCard, value: str) -> bool:
    return value in card.title.lower() or value in card.content.lower()


class SettingCardGroup(ui.Node):
    """设置页的一组卡片，对应 CollapsibleSettingCardGroup：一张卡片里是标题行和各设置行，
    点标题行折叠或展开，展开状态存于 cfg.expandedSettingGroups；鼠标悬停时标题行显示上移、下移按钮，
    顺序由设置页保存到 cfg.settingGroupOrder。

    key 对应 Qt 界面的 objectName。
    """

    moveRequested = Signal(object, int)

    def __init__(self, title: str, key: str) -> None:
        super().__init__()
        self.key = key
        self._cards: list[SettingCard] = []
        self._cardBuilders = []
        self._isCollapsed = key not in cfg.expandedSettingGroups.value
        self._initWidget(title)
        self._initLayout()

    def _initWidget(self, title: str) -> None:
        self.pointer_input = True
        self.titleLabel = text(title, fontWeight=600)
        self.moveUpButton = ui.IconButton(loadIcon("keyboard_arrow_up"), lambda: self.moveRequested.emit(self, -1))
        self.moveDownButton = ui.IconButton(loadIcon("keyboard_arrow_down"), lambda: self.moveRequested.emit(self, 1))
        self.moveSlot = ui.Row()
        self.expandButton = ui.IconButton(loadIcon(self._expandIcon()), self._onExpandClicked)
        self.cardLayout = column()
        self.separator = ui.HorizontalDivider()

    def _initLayout(self) -> None:
        header = ui.Box()
        header.set_padding(16, 4, 8, 4)
        header.append_child(row(self.titleLabel, ui.Spacer(), self.moveSlot, self.expandButton, spacing=4, flex=1))
        self.vBoxLayout = column(ClickArea(header, self._onExpandClicked))
        if not self._isCollapsed:
            self.vBoxLayout.append_child(self.separator)
            self.vBoxLayout.append_child(self.cardLayout)
        card = ui.Card(ui.CardStyle.FILLED)
        card.append_child(self.vBoxLayout)
        self.append_child(card)

    def addSettingCard(self, card: SettingCard) -> None:
        self._cards.append(card)
        self.cardLayout.append_child(card)

    def addSettingCards(self, cards: list[SettingCard]) -> None:
        for card in cards:
            self.addSettingCard(card)

    def setCardsBuilder(self, build) -> None:
        self._cardBuilders.append(build)
        if not self._isCollapsed:
            self._loadCards()

    def addSettingCardFactory(self, build) -> None:
        self.setCardsBuilder(lambda: self.addSettingCard(build()))

    def _loadCards(self) -> None:
        builders, self._cardBuilders = self._cardBuilders, []
        for build in builders:
            build()

    def setSearchText(self, value: str) -> bool:
        """只留匹配的设置行；有匹配时展开。返回这一组是否该显示。"""
        value = value.strip().lower()
        if value or not self._isCollapsed:
            self._loadCards()
        matched = [card for card in self._cards if not value or isSearchMatch(card, value)]
        if list(self.cardLayout.children) != matched:
            while self.cardLayout.children:
                self.cardLayout.remove_child(0)
            for card in matched:
                self.cardLayout.append_child(card)
        isExpand = (bool(value) and bool(matched)) or self.key in cfg.expandedSettingGroups.value
        self._setCollapsed(not isExpand)
        return bool(matched) or not value

    def setMoveEnabled(self, canMoveUp: bool, canMoveDown: bool) -> None:
        self.moveUpButton.enabled = canMoveUp
        self.moveDownButton.enabled = canMoveDown

    def on_pointer_event(self, event: ui.PointerEvent, pass_: ui.PointerEventPass,
                         bounds: tuple[float, float], /) -> None:
        if pass_ != ui.PointerEventPass.INITIAL:
            return
        if event.type == ui.PointerEventType.ENTER and not self.moveSlot.children:
            self.moveSlot.append_child(self.moveUpButton)
            self.moveSlot.append_child(self.moveDownButton)
        elif event.type == ui.PointerEventType.EXIT:
            while self.moveSlot.children:
                self.moveSlot.remove_child(0)

    def _expandIcon(self) -> str:
        return "keyboard_arrow_down" if self._isCollapsed else "keyboard_arrow_up"

    def _onExpandClicked(self) -> None:
        self._setCollapsed(not self._isCollapsed)
        keys = [key for key in cfg.expandedSettingGroups.value if key != self.key]
        if not self._isCollapsed:
            keys.append(self.key)
        cfg.set(cfg.expandedSettingGroups, keys)

    def _setCollapsed(self, isCollapsed: bool) -> None:
        if not isCollapsed:
            self._loadCards()
        if isCollapsed == self._isCollapsed:
            return
        self._isCollapsed = isCollapsed
        if isCollapsed:
            self.vBoxLayout.remove_child(self.vBoxLayout.children.index(self.cardLayout))
            self.vBoxLayout.remove_child(self.vBoxLayout.children.index(self.separator))
        else:
            self.vBoxLayout.append_child(self.separator)
            self.vBoxLayout.append_child(self.cardLayout)
        self.expandButton.icon = loadIcon(self._expandIcon())
