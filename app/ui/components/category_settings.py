from __future__ import annotations

from typing import TYPE_CHECKING

from bkit import ui

from app.signal import Signal
from app.ui.components.categories import toCategoryName
from app.ui.components.setting_cards import CollapsibleSettingCard
from app.i18n import tr
from app.ui.icons import buildButton, buildIcon, buildIconButton, toCategoryIcon
from app.ui.layout import column, row, text
from app.ui.loop import UiLoop

if TYPE_CHECKING:
    from app.services.category_service import Category, CategoryService


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
