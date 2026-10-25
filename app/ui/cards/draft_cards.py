from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING

from bkit import ui

from app.config.cfg import cfg
from app.format import toReadableSize
from app.signal import Signal
from app.ui.cards.task_cards import isMultiFile, toFileIcon
from app.ui.components.card_groups import DraftCardGroup
from app.ui.components.category_settings import addCategoryItems, toCategoryName
from app.ui.components.menu import buildMenu
from app.ui.dialogs.file_select import FileSelectDialog
from app.ui.i18n import tr
from app.ui.icons import CATEGORY_FALLBACK_ICON, buildIcon, buildIconButton, loadIcon, toCategoryIcon
from app.ui.layout import column, row, text
from app.ui.theme import contentColor

if TYPE_CHECKING:
    from app.models.task import Task
    from app.services.category_service import CategoryService

ICON_SIZE = 16


def T(text: str) -> str:
    return tr("DraftCard", text)


class DraftCard(ui.Node):
    """解析结果的一行：文件图标、可直接改的文件名、同名提示、大小和分类按钮。"""

    categoryPicked = Signal(str)

    def __init__(self, task: Task, categoryService: CategoryService,
                 probeConflict: Callable[[Task], Path | None]) -> None:
        super().__init__()
        self._task = task
        self._categoryService = categoryService
        self._probeConflict = probeConflict
        self._menu: ui.DropdownMenu | None = None
        self._fileSelectDialog: FileSelectDialog | None = None
        self._initWidget()
        self._initLayout()
        self._bind()
        self._refreshCategoryButton()
        self._refreshConflictIcon()

    @property
    def task(self) -> Task:
        return self._task

    def _initWidget(self) -> None:
        self.iconLabel = buildIcon(toFileIcon(self._task, self._categoryService), ICON_SIZE)
        # 对应 EditableLabel：文件名就是输入框，改完回车或换焦点即生效
        self.nameEdit = ui.BasicTextField(ui.TextFieldState(self._task.name))
        self.nameEdit.set_line_limits(single_line=True)
        self.nameEdit.set_text_color(contentColor())
        self.nameEdit.set_cursor_color(contentColor())
        self.sizeLabel = text(self._summaryText())
        self.conflictIcon = ui.TooltipBox(buildIcon("info", ICON_SIZE))
        self.conflictIcon.set_plain_tooltip(T("下载目录中已有同名文件，下载时按设置处理"))
        self.conflictSlot = ui.Box()
        self.categoryButton = ui.IconButton(loadIcon(CATEGORY_FALLBACK_ICON), self._onCategoryClicked)
        self.categoryBox = ui.TooltipBox(self.categoryButton)
        self.categorySlot = ui.Box()
        # 对应 MultiFileDraftCard 的「选择文件」按钮
        self.selectFilesSlot = ui.Box()
        if isMultiFile(self._task):
            selectFilesBox, _ = buildIconButton("library_books", tr("MultiFileDraftCard", "选择文件"),
                                                self._onSelectFilesClicked)
            self.selectFilesSlot.append_child(selectFilesBox)

    def _initLayout(self) -> None:
        box = ui.Box()
        box.set_size(None, DraftCardGroup.CARD_HEIGHT)
        box.set_padding(16, 0, 8, 0)
        box.append_child(row(self.iconLabel, self.nameEdit, self.conflictSlot, self.sizeLabel,
                             self.categorySlot, self.selectFilesSlot, spacing=12, flex=1))
        self.append_child(column(ui.HorizontalDivider(), box))

    def _bind(self) -> None:
        self.nameEdit.on_value_change = self._onNameEdited
        cfg.isCategoryEnabled.valueChanged.connect(self._refreshCategoryButton)

    def _summaryText(self) -> str:
        task = self._task
        size = toReadableSize(task.fileSize) if task.fileSize > 1 else "--"
        if not isMultiFile(task):
            return size
        selected = sum(1 for f in task.files if f.selected)
        return tr("MultiFileDraftCard", "{0}/{1} 个文件 · {2}").format(selected, len(task.files), size)

    def _onSelectFilesClicked(self) -> None:
        dialog = FileSelectDialog(self._task, self._categoryService, self)

        def onAccepted() -> None:
            self._task.setSelection(dialog.selectedIndexes())
            self.sizeLabel.text = self._summaryText()

        dialog.accepted.connect(onAccepted)
        dialog.open()
        self._fileSelectDialog = dialog

    def _onNameEdited(self) -> None:
        name = self.nameEdit.state.text.strip()
        if not name or name == self._task.name:
            return
        self._task.setName(name)
        self.iconLabel.icon = loadIcon(toFileIcon(self._task, self._categoryService))
        self._refreshConflictIcon()

    def _refreshConflictIcon(self) -> None:
        isConflicted = self._probeConflict(self._task) is not None
        if isConflicted and not self.conflictSlot.children:
            self.conflictSlot.append_child(self.conflictIcon)
        elif not isConflicted and self.conflictSlot.children:
            self.conflictSlot.remove_child(0)

    def _refreshCategoryButton(self, *_args) -> None:
        if not cfg.isCategoryEnabled.value:
            if self.categorySlot.children:
                self.categorySlot.remove_child(0)
            return
        category = self._categoryService.categoryById(self._task.category)
        if category is not None:
            self.categoryButton.icon = loadIcon(toCategoryIcon(category.icon))
            self.categoryBox.set_plain_tooltip(toCategoryName(category))
        else:
            self.categoryButton.icon = loadIcon(CATEGORY_FALLBACK_ICON)
            self.categoryBox.set_plain_tooltip(T("未分类"))
        if not self.categorySlot.children:
            self.categorySlot.append_child(self.categoryBox)

    def _onCategoryClicked(self) -> None:
        menu = buildMenu(self.categoryButton)
        addCategoryItems(menu, self._categoryService.categories(), T("未分类"), self._onCategoryPicked)
        self._menu = menu
        menu.expanded = True

    def _onCategoryPicked(self, categoryId: str) -> None:
        self._task.category = categoryId
        self._refreshCategoryButton()
        self._refreshConflictIcon()
        self.categoryPicked.emit(categoryId)
