from __future__ import annotations

from bkit import ui

from app.i18n import tr
from app.ui.components.menu import buildMenuAction
from app.ui.icons import CATEGORY_FALLBACK_ICON, loadIcon, toCategoryIcon


def toCategoryName(category) -> str:
    return tr("Categories", category.name)


def addCategoryItems(menu: ui.DropdownMenu, categories, firstText, onPicked, *,
                     firstIcon=CATEGORY_FALLBACK_ICON, selectedId=None) -> None:
    entries = [("", firstText, firstIcon)]
    entries += [(category.categoryId, toCategoryName(category), toCategoryIcon(category.icon))
                for category in categories]
    for index, (categoryId, name, icon) in enumerate(entries):
        onClick = buildMenuAction(menu, lambda categoryId=categoryId: onPicked(categoryId))
        if selectedId is None:
            item = menu.add_item(name, onClick)
        else:
            item = menu.add_selectable_item(name, categoryId == selectedId, onClick)
        item.set_leading_icon(loadIcon(icon))
        if index == 0:
            menu.add_divider()
