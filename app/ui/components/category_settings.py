from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from bkit import ui

from app.signal import Signal
from app.ui.components.menu import buildMenuAction
from app.ui.components.setting_cards import CollapsibleSettingCard
from app.i18n import tr
from app.ui.icons import CATEGORY_FALLBACK_ICON, buildButton, buildIcon, buildIconButton, loadIcon, toCategoryIcon
from app.ui.layout import column, row, text
from app.ui.loop import UiLoop

if TYPE_CHECKING:
    from app.services.category_service import Category, CategoryService


def toCategoryName(category: Category) -> str:
    return tr("Categories", category.name)


def addCategoryItems(menu: ui.DropdownMenu, categories: list[Category], firstText: str,
                     onPicked: Callable[[str], object], *, firstIcon: str = CATEGORY_FALLBACK_ICON,
                     selectedId: str | None = None) -> None:
    """firstText 对应空分类 id：移动菜单里是「未分类」，筛选菜单里是「全部分类」，其后是分隔线和各分类。

    firstIcon 沿用 Qt 界面各处的图标；selectedId 不为 None 时各项带单选标记，对应 CheckableMenu 的 RADIO 指示。
    """
    entries = [("", firstText, firstIcon)]
    entries += [(c.categoryId, toCategoryName(c), toCategoryIcon(c.icon)) for c in categories]
    for index, (categoryId, name, icon) in enumerate(entries):
        onClick = buildMenuAction(menu, lambda c=categoryId: onPicked(c))
        if selectedId is None:
            item = menu.add_item(name, onClick)
        else:
            item = menu.add_selectable_item(name, categoryId == selectedId, onClick)
        item.set_leading_icon(loadIcon(icon))
        if index == 0:
            menu.add_divider()


class CategoryRowWidget(ui.Node):
    editRequested = Signal(str)
    removeRequested = Signal(str)

    def __init__(self, category: Category) -> None:
        super().__init__()
        self._categoryId = category.categoryId
        editBox, _ = buildIconButton("edit", tr("CategoryRowWidget", "编辑"),
                                     lambda: self.editRequested.emit(self._categoryId), ui.IconButtonVariant.OUTLINED)
        removeBox, _ = buildIconButton("delete", tr("CategoryRowWidget", "删除"),
                                       lambda: self.removeRequested.emit(self._categoryId),
                                       ui.IconButtonVariant.OUTLINED)
        self.append_child(row(buildIcon(toCategoryIcon(category.icon), 16),
                              text(toCategoryName(category), fontWeight=600), ui.Spacer(),
                              text(self._toSummary(category)), editBox, removeBox, spacing=12, flex=2))

    def _toSummary(self, category: Category) -> str:
        count = len(category.extensions)
        if count == 0:
            return tr("CategoryRowWidget", "无扩展名")
        head = ", ".join(category.extensions[:4])
        if count > 4:
            return tr("CategoryRowWidget", "{0} 等 {1} 项").format(head, count)
        return head


class CategoryRulesCard(CollapsibleSettingCard):
    """分类列表与增删改，对应 Qt 界面的 CategoryRulesCard；改动交给 CategoryService 保存。"""

    def __init__(self, categoryService: CategoryService, uiLoop: UiLoop) -> None:
        super().__init__("label", tr("CategoryRulesCard", "下载分类规则"),
                         tr("CategoryRulesCard", "根据扩展名自动归类，可为分类指定下载文件夹"))
        self._categoryService = categoryService
        self._uiLoop = uiLoop
        self._dialog = None
        self.rowLayout = column(spacing=8)
        self.resetButton = buildButton("sync", tr("CategoryRulesCard", "恢复默认"), categoryService.reset)
        self.addButton = buildButton("add", tr("CategoryRulesCard", "添加分类"), self._onAddClicked)
        self.addGroupWidget(column(self.rowLayout, row(ui.Spacer(), self.resetButton, self.addButton, spacing=8,
                                                       flex=0), spacing=8))
        categoryService.categoriesChanged.connect(self._reload)
        self._reload()

    def _reload(self) -> None:
        while self.rowLayout.children:
            self.rowLayout.remove_child(0)
        categories = self._categoryService.categories()
        for category in categories:
            categoryRow = CategoryRowWidget(category)
            categoryRow.editRequested.connect(self._onEditClicked)
            categoryRow.removeRequested.connect(self._onRemoveClicked)
            self.rowLayout.append_child(categoryRow)
        self.setContent(tr("CategoryRulesCard", "已配置 {0} 个分类").format(len(categories)))

    def _onRemoveClicked(self, categoryId: str) -> None:
        # 删除会重建各行，被点的按钮也在其中：等这次点击处理完再删
        self._uiLoop.post(lambda: self._categoryService.removeCategory(categoryId))

    def _onAddClicked(self) -> None:
        from app.ui.dialogs.category_edit import CategoryEditDialog
        dialog = CategoryEditDialog(self, self._uiLoop)
        dialog.accepted.connect(lambda: self._categoryService.addCategory(dialog.category()))
        dialog.open()
        self._dialog = dialog

    def _onEditClicked(self, categoryId: str) -> None:
        category = self._categoryService.categoryById(categoryId)
        if category is None:
            return
        from app.ui.dialogs.category_edit import CategoryEditDialog
        dialog = CategoryEditDialog(self, self._uiLoop, category=category)
        dialog.accepted.connect(lambda: self._categoryService.updateCategory(dialog.category()))
        dialog.open()
        self._dialog = dialog
