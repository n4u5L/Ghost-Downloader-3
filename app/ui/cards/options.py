from app.ui.cards.draft_cards import DraftCard
from app.ui.layout import column


class OptionsDraftCard(DraftCard):
    def __init__(self, task, categoryService, probeConflict, cards):
        self.optionCards = cards
        super().__init__(task, categoryService, probeConflict)
        self.preferredHeight = 48 + sum(getattr(card, "preferredHeight", 64) for card in cards)
        if cards:
            body = self.remove_child(0)
            self.append_child(column(body, *cards, spacing=4))

    def applyOptions(self) -> bool:
        return all([card.apply() for card in self.optionCards])

    def overrides(self):
        values = {}
        for card in self.optionCards:
            if hasattr(card, "overrides"):
                values.update(card.overrides())
        return values

    def dispose(self):
        for card in self.optionCards:
            if hasattr(card, "dispose"):
                card.dispose()
        self.optionCards.clear()
        super().dispose()
