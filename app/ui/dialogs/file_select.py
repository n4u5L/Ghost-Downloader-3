"""选择多文件任务要下载的文件。Qt 界面的树控件改为按层级缩进的列表，文件夹全部展开。

各功能包的专用选择对话框（种子、哔哩哔哩分 P）依赖 Qt；bkit 界面对所有多文件任务都用这一个。
"""
from __future__ import annotations

import weakref
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from bkit import ui

from app.format import toReadableSize
from app.ui.components.category_settings import toCategoryName
from app.ui.components.menu import buildMenu, buildMenuAction
from app.ui.components.message_box import MessageBoxBase
from app.ui.i18n import tr
from app.ui.icons import CATEGORY_FALLBACK_ICON, buildIcon, loadIcon, toCategoryIcon
from app.ui.layout import column, row, text

if TYPE_CHECKING:
    from app.models.task import Task
    from app.services.category_service import CategoryService

WIDTH = 720
ROW_HEIGHT = 40
MAX_VISIBLE_ROWS = 10
INDENT = 20
ERROR_COLOR = 0xFFB3261E


def T(text: str) -> str:
    return tr("FileSelectDialog", text)


@dataclass
class FileRow:
    depth: int
    name: str
    icon: str
    size: str
    fileIndexes: list[int] = field(default_factory=list)
    isFolder: bool = False


class FileRowView(ui.Node):
    def __init__(self, fileRow: FileRow, dialog: FileSelectDialog) -> None:
        super().__init__()
        self._fileRow = fileRow
        self._dialog = dialog
        self.checkBox = ui.Checkbox(False, self._onCheckedChange)
        box = ui.Box()
        box.set_size(None, ROW_HEIGHT)
        box.set_padding(8 + fileRow.depth * INDENT, 0, 16, 0)
        box.append_child(row(self.checkBox, buildIcon(fileRow.icon, 20), text(fileRow.name), text(fileRow.size),
                             spacing=8, flex=2))
        self.append_child(box)
        self.refresh()

    def refresh(self) -> None:
        self.checkBox.state = self._dialog.toCheckState(self._fileRow.fileIndexes)

    def _onCheckedChange(self, checked: bool) -> None:
        self._dialog.setChecked(self._fileRow.fileIndexes, checked)


class FileSelectDialog(MessageBoxBase):

    def __init__(self, task: Task, categoryService: CategoryService, host: ui.Node) -> None:
        super().__init__(host)
        self._task = task
        self._categoryService = categoryService
        self._files = list(task.files or [])
        self._selected = {f.index for f in self._files if f.selected}
        self._rows = self._buildRows()
        self._liveRows: weakref.WeakValueDictionary[int, FileRowView] = weakref.WeakValueDictionary()
        self._menu: ui.DropdownMenu | None = None
        self._initWidget()
        self._initLayout()
        self._refreshSummary()

    def _initWidget(self) -> None:
        self.dialog.set_title(T("选择下载文件"))
        self.dialog.platform_default_width = WIDTH
        self.yesButton.text = T("应用")
        self.cancelButton.text = T("取消")
        self.summaryLabel = text()
        self.warningLabel = ui.Text("", color=ERROR_COLOR)
        self.treeView = ui.LazyColumn()
        self.treeView.set_item_provider(len(self._rows), self._createRow)
        self.selectAllButton = ui.Button(T("全选"), lambda: self._setSelected(set(self._allIndexes())),
                                         ui.ButtonStyle.FILLED)
        self.clearButton = ui.Button(T("全不选"), lambda: self._setSelected(set()), ui.ButtonStyle.OUTLINED)
        self.invertButton = ui.Button(T("反选"), self._invertSelection, ui.ButtonStyle.OUTLINED)
        # 对应 DropDownPushButton
        self.selectByTypeButton = ui.Button([ui.Text(T("按类型选择")), buildIcon("keyboard_arrow_down", 16)],
                                            self._onSelectByTypeClicked, ui.ButtonStyle.OUTLINED)
        self.selectByTypeButton.enabled = bool(self._typeCounts())

    def _initLayout(self) -> None:
        treeBox = ui.Box()
        treeBox.set_size(None, min(len(self._rows), MAX_VISIBLE_ROWS) * ROW_HEIGHT)
        treeBox.append_child(self.treeView)
        header = ui.Box()
        header.set_padding(8 + INDENT + 48, 6, 16, 6)
        header.append_child(row(text(T("文件"), fontWeight=600), text(T("大小"), fontWeight=600), flex=0))
        card = ui.Card(ui.CardStyle.OUTLINED)
        card.append_child(column(header, ui.HorizontalDivider(), treeBox))
        actions = row(self.selectAllButton, self.clearButton, self.invertButton, self.selectByTypeButton, spacing=8)
        for node in (self.summaryLabel, card, actions, self.warningLabel):
            self.viewLayout.append_child(node)

    def selectedIndexes(self) -> set[int]:
        return set(self._selected)

    def close(self, isAccepted: bool) -> None:
        if isAccepted and not self._selected:
            self.warningLabel.text = f"{T('至少选择一个文件')}：{T('当前没有任何文件被勾选')}"
            return
        super().close(isAccepted)

    def toCheckState(self, fileIndexes: list[int]) -> ui.ToggleableState:
        count = sum(1 for index in fileIndexes if index in self._selected)
        if count == 0:
            return ui.ToggleableState.OFF
        return ui.ToggleableState.ON if count == len(fileIndexes) else ui.ToggleableState.INDETERMINATE

    def setChecked(self, fileIndexes: list[int], checked: bool) -> None:
        selected = set(self._selected)
        if checked:
            selected.update(fileIndexes)
        else:
            selected.difference_update(fileIndexes)
        self._setSelected(selected)

    def _buildRows(self) -> list[FileRow]:
        """按显示路径建出树，再按先序展开为行；文件夹行收集其下所有文件的下标。"""
        rows: list[FileRow] = []
        folders: dict[tuple[str, ...], FileRow] = {}
        for file in self._files:
            parts = self._task.toDisplayPath(file).split("/")
            for depth in range(len(parts) - 1):
                key = tuple(parts[:depth + 1])
                folder = folders.get(key)
                if folder is None:
                    folder = folders[key] = FileRow(depth, parts[depth], "folder", "", isFolder=True)
                    rows.append(folder)
                folder.fileIndexes.append(file.index)
            categoryId = self._categoryService.matchByName(parts[-1])
            category = self._categoryService.categoryById(categoryId) if categoryId else None
            icon = toCategoryIcon(category.icon) if category is not None else "draft"
            rows.append(FileRow(len(parts) - 1, parts[-1], icon, toReadableSize(file.size), [file.index]))
        return rows

    def _createRow(self, index: int) -> ui.Node:
        view = FileRowView(self._rows[index], self)
        self._liveRows[index] = view
        return view

    def _allIndexes(self) -> list[int]:
        return [f.index for f in self._files]

    def _setSelected(self, selected: set[int]) -> None:
        self._selected = selected
        self.warningLabel.text = ""
        for view in self._liveRows.values():
            view.refresh()
        self._refreshSummary()

    def _invertSelection(self) -> None:
        self._setSelected({index for index in self._allIndexes() if index not in self._selected})

    def _typeCounts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for file in self._files:
            categoryId = self._categoryService.matchByName(file.relativePath)
            counts[categoryId] = counts.get(categoryId, 0) + 1
        return counts

    def _onSelectByTypeClicked(self) -> None:
        menu = buildMenu(self.selectByTypeButton)
        # 与 Qt 界面一致，「其他」排在各分类之后
        for categoryId, count in sorted(self._typeCounts().items(), key=lambda item: not item[0]):
            if categoryId:
                category = self._categoryService.categoryById(categoryId)
                if category is None:
                    continue
                name, icon = toCategoryName(category), toCategoryIcon(category.icon)
            else:
                name, icon = T("其他"), CATEGORY_FALLBACK_ICON
            item = menu.add_item(T("仅选{0} ({1})").format(name, count),
                                 buildMenuAction(menu, lambda c=categoryId: self._selectCategory(c)))
            item.set_leading_icon(loadIcon(icon))
        self._menu = menu
        menu.expanded = True

    def _selectCategory(self, categoryId: str) -> None:
        self._setSelected({f.index for f in self._files
                           if self._categoryService.matchByName(f.relativePath) == categoryId})

    def _refreshSummary(self) -> None:
        size = sum(f.size for f in self._files if f.index in self._selected)
        self.summaryLabel.text = T("已选择 {0}/{1} 个文件，共 {2}").format(
            len(self._selected), len(self._files), toReadableSize(size))
