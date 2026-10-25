from __future__ import annotations

import itertools
import weakref
from collections.abc import Callable
from enum import IntEnum
from typing import TYPE_CHECKING

from bkit import ui

from app.config.cfg import cfg
from app.format import toReadableSize
from app.models.task import TaskStatus
from app.platform.filesystem import isExisting
from app.ui.cards.task_cards import TaskCard
from app.ui.components.category_settings import addCategoryItems
from app.ui.components.info_bar import InfoBarArea, InfoBarIcon
from app.ui.components.menu import buildMenu, buildMenuAction, openMenuAt
from app.ui.components.message_box import MessageBox
from app.ui.dialogs.plan_task import PlanTaskDialog
from app.ui.dialogs.task_drawer import TaskDrawer
from app.ui.i18n import toLocalizedError, tr
from app.ui.icons import buildButton, buildIcon, buildIconButton, loadIcon
from app.ui.layout import SecondaryClickArea, Slot, checkBox, column, overlay, row, text
from app.ui.loop import SingleShotTimer, Timer, UiLoop

if TYPE_CHECKING:
    from app.models.task import Task, TaskError
    from app.services.category_service import CategoryService
    from app.services.plan import Plan
    from app.services.speed_meter import SpeedMeter
    from app.services.task_service import TaskService

KB = 1024
TICK_INTERVAL = 1.0
RATE_LIMIT_DELAY = 0.5


def T(text: str) -> str:
    return tr("TaskPage", text)


class FilterMode(IntEnum):
    ALL = 0
    ACTIVE = 1
    COMPLETED = 2


FILTER_TO_STATUSES = {
    FilterMode.ACTIVE: {TaskStatus.RUNNING, TaskStatus.WAITING, TaskStatus.PAUSED},
    FilterMode.COMPLETED: {TaskStatus.COMPLETED, TaskStatus.FAILED},
}


class SortField(IntEnum):
    CREATED_AT = 0
    NAME = 1
    SIZE = 2
    COMPLETED_AT = 3
    QUEUE_POSITION = 4


SORT_ITEMS = [
    (SortField.CREATED_AT, "calendar_clock", "按添加时间"),
    (SortField.COMPLETED_AT, "history", "按完成时间"),
    (SortField.NAME, "text_fields", "按名称排序"),
    (SortField.SIZE, "library_books", "按大小排序"),
    (SortField.QUEUE_POSITION, "receipt_long", "按队列顺序"),
]
# 筛选分段与 Qt 界面一样只有图标：全部、活动、完成
FILTER_ICONS = ["home", "download", "check"]
COMMAND_ICON_SIZE = 18
EMPTY_ICON_SIZE = 64


def buildDropDownButton(icon: str, onClick: Callable[[], object]) -> ui.Button:
    """图标加下拉箭头的按钮，对应 qfluentwidgets 的 DropDownToolButton。"""
    button = ui.Button([buildIcon(icon, 20), buildIcon("keyboard_arrow_down", 16)], onClick, ui.ButtonStyle.OUTLINED)
    button.set_content_padding(12, 8, 8, 8)
    return button


def buildCommandButton(icon: str, label: str) -> ui.Button:
    """图标在上、文字在下的按钮，对应 CommandBarView 的 ToolButtonTextUnderIcon。"""
    button = ui.Button([column(buildIcon(icon, COMMAND_ICON_SIZE), text(label, fontSize=12), spacing=4,
                               isCrossFilled=False)], None, ui.ButtonStyle.TEXT)
    button.set_content_padding(8, 6)
    return button


class EmptyStatusWidget(ui.Node):
    """没有内容时居中的卡片：大图标下一行说明，对应 Qt 界面的 EmptyStatusWidget。"""

    def __init__(self, icon: str, value: str) -> None:
        super().__init__()
        self.label = text(value, fontSize=12)
        card = ui.Card(ui.CardStyle.FILLED)
        card.set_padding(16, 20)
        card.set_min_size(200, 0)
        card.set_content_alignment(ui.Alignment.CENTER, ui.Alignment.CENTER)
        card.append_child(column(buildIcon(icon, EMPTY_ICON_SIZE), self.label, spacing=10, isCrossFilled=False))
        box = ui.Box()
        box.set_content_alignment(ui.Alignment.CENTER, ui.Alignment.CENTER)
        box.append_child(card)
        self.append_child(Slot(box))

    def setText(self, value: str) -> None:
        self.label.text = value


class TaskCommandBarView(ui.Node):
    """选择模式下浮在列表底部的命令栏，图标在上、文字在下，与 Qt 界面一致。"""

    def __init__(self) -> None:
        super().__init__()
        self.actions: dict[str, ui.Button] = {}
        self._initWidget()
        self._initLayout()

    def _initWidget(self) -> None:
        def C(text: str) -> str:
            return tr("TaskCommandBarView", text)

        for name, icon, label in (
            ("moveToFront", "arrow_upward", C("移到最前")), ("redownload", "update", C("重新下载")),
            ("delete", "delete", C("删除")), ("copyUrl", "content_copy", C("复制链接")),
            ("moveCategory", "label", C("移动到分类")), ("selectAll", "select", C("全选")),
            ("selectMissing", "remove", C("选择缺失")), ("invertSelect", "content_cut", C("反选")),
            ("cancel", "select", C("取消全选")),
        ):
            self.actions[name] = buildCommandButton(icon, label)
        self.moveCategorySlot = ui.Box()
        self.moveCategorySlot.append_child(self.actions["moveCategory"])

    def _initLayout(self) -> None:
        actions = self.actions
        divider = ui.VerticalDivider()
        divider.set_length(32)
        bar = ui.Row(spacing=2, cross_alignment=ui.Alignment.CENTER)
        for node in (actions["moveToFront"], actions["redownload"], actions["delete"], actions["copyUrl"],
                     self.moveCategorySlot, divider, actions["selectAll"], actions["selectMissing"],
                     actions["invertSelect"], actions["cancel"]):
            bar.append_child(node)
        card = ui.Card(ui.CardStyle.ELEVATED)
        card.set_padding(8, 4)
        card.append_child(bar)
        box = ui.Box()
        box.set_padding(0, 0, 0, 20)
        box.append_child(card)
        self.append_child(box)

    def setCategoryVisible(self, isVisible: bool) -> None:
        if isVisible and not self.moveCategorySlot.children:
            self.moveCategorySlot.append_child(self.actions["moveCategory"])
        elif not isVisible and self.moveCategorySlot.children:
            self.moveCategorySlot.remove_child(0)


class TaskPage(ui.Node):
    def __init__(self, taskService: TaskService, categoryService: CategoryService, speedMeter: SpeedMeter,
                 plan: Plan, copyUrls: Callable[[list[str]], None], infoBars: InfoBarArea,
                 uiLoop: UiLoop) -> None:
        super().__init__()
        self._taskService = taskService
        self._copyUrls = copyUrls
        self._categoryService = categoryService
        self._speedMeter = speedMeter
        self._plan = plan
        self._infoBars = infoBars
        self._uiLoop = uiLoop
        self._filterMode = FilterMode.ALL
        self._categoryFilter = ""
        self._searchText = ""
        self._sortField = SortField.CREATED_AT
        self._sortAscending = False
        self._isSelectionMode = False
        self._selectionAnchor: str | None = None
        self._selectedIds: set[str] = set()
        self._tasks: list[Task] = []
        self._displayOrder: list[str] = []
        # LazyColumn 要求稳定的 64 位整数 key
        self._keys: dict[str, int] = {}
        self._nextKey = itertools.count(1)
        self._liveCards: weakref.WeakValueDictionary[str, TaskCard] = weakref.WeakValueDictionary()
        self._isRefreshPosted = False
        self._tickTimer: Timer | None = None
        self._menu: ui.DropdownMenu | None = None
        self._deleteBox: MessageBox | None = None
        self._planDialog: PlanTaskDialog | None = None
        self._drawer: TaskDrawer | None = None
        self._initWidget()
        self._initLayout()
        self._bind()
        self._refreshList()

    def _initWidget(self) -> None:
        self.filterSegment = ui.SegmentedButtonRow(on_select=self._onFilterSelected)
        for icon in FILTER_ICONS:
            self.filterSegment.add_button(buildIcon(icon, 18)).set_icon(None)
        self.filterSegment.selected_index = FilterMode.ALL
        self.startAllButton = buildButton("play_arrow", T("全部开始"), self.startAll)
        self.pauseAllButton = buildButton("pause", T("全部暂停"), self.pauseAll)
        self.selectBox, _ = buildIconButton("select", T("选择任务"),
                                            lambda: self.setSelectionMode(not self._isSelectionMode),
                                            ui.IconButtonVariant.OUTLINED)
        self.planButton = ui.IconToggleButton(loadIcon("calendar_clock"), False, self._onPlanButtonClicked,
                                              ui.IconButtonVariant.OUTLINED)
        self.planBox = ui.TooltipBox(self.planButton)
        self.planBox.set_plain_tooltip(T("计划任务"))
        self.rateLimitButton = ui.IconToggleButton(loadIcon("speed"), cfg.isSpeedLimitEnabled.value,
                                                   self._onRateLimitToggled, ui.IconButtonVariant.OUTLINED)
        rateLimitBox = ui.TooltipBox(self.rateLimitButton)
        rateLimitBox.set_plain_tooltip(T("限速（右键修改）"))
        self.rateLimitArea = SecondaryClickArea(rateLimitBox, self._onRateLimitMenuRequested)
        self.speedBadge = text()
        self.sortButton = buildDropDownButton("space_dashboard", self._onSortClicked)
        self.categoryFilterButton = buildDropDownButton("label", self._onCategoryFilterClicked)
        self.categoryFilterBox = ui.TooltipBox(self.categoryFilterButton)
        self.categoryFilterBox.set_plain_tooltip(T("按分类筛选"))
        self.categoryFilterSlot = ui.Box()
        self._refreshCategoryFilterButton()

        self.emptyStatusWidget = EmptyStatusWidget("emoji_symbols", T("暂无下载任务"))

        self.list = ui.LazyColumn()
        self.list.set_content_padding(12, 0, 12, 12)
        self.list.set_vertical_arrangement(ui.Arrangement.spaced_by(8))
        self.list.set_item_provider(0, self._createCard, key=self._keyAt)
        self.listSlot = Slot(self.list)

        self.commandView = TaskCommandBarView()
        self.commandView.setCategoryVisible(bool(cfg.isCategoryEnabled.value))
        self.commandSlot = ui.Box()
        self._onSpeedLimitChanged()

    def _initLayout(self) -> None:
        toolBar = row(
            self.filterSegment, self.startAllButton, self.pauseAllButton, self.selectBox, self.planBox,
            self.rateLimitArea, ui.Spacer(4, 0), buildIcon("speed", 20), self.speedBadge, ui.Spacer(),
            self.sortButton, self.categoryFilterSlot,
            spacing=6, flex=10,
        )
        toolBarBox = ui.Box()
        toolBarBox.set_padding(16, 10)
        toolBarBox.append_child(toolBar)
        content = column(toolBarBox, self.listSlot, flex=1)
        self.append_child(overlay(content, self.commandSlot, ui.Alignment.CENTER, ui.Alignment.END))

    def _bind(self) -> None:
        service = self._taskService
        service.taskAdded.connect(self._onTaskChanged)
        service.taskRemoved.connect(self._onTaskRemoved)
        service.taskStarted.connect(self._onTaskChanged)
        service.taskPaused.connect(self._onTaskChanged)
        service.taskCompleted.connect(self._onTaskChanged)
        service.taskFailed.connect(self._onTaskChanged)
        service.seedingStarted.connect(self._onTaskChanged)
        service.seedingStopped.connect(self._onTaskChanged)
        service.checksumStarted.connect(self._onTaskChanged)
        service.checksumCompleted.connect(self._onChecksumCompleted)
        service.checksumStopped.connect(self._onChecksumStopped)
        service.queueChanged.connect(self._onQueueChanged)
        service.fileDisappeared.connect(self._onTaskChanged)
        service.overwriteFailed.connect(self._onOverwriteFailed)
        self._speedMeter.speedChanged.connect(self._onSpeedChanged)
        cfg.isSpeedLimitEnabled.valueChanged.connect(self._onSpeedLimitChanged)
        cfg.speedLimitation.valueChanged.connect(self._onSpeedLimitChanged)
        cfg.isCategoryEnabled.valueChanged.connect(self._onCategoryEnabledChanged)
        self._categoryService.categoriesChanged.connect(self._onCategoriesChanged)

        actions = self.commandView.actions
        actions["moveToFront"].on_click = self._onMoveToFrontSelected
        actions["redownload"].on_click = self._onRedownloadSelected
        actions["delete"].on_click = self._onDeleteSelected
        actions["copyUrl"].on_click = self._onCopyUrlSelected
        actions["moveCategory"].on_click = self._onMoveCategorySelected
        actions["selectAll"].on_click = self.selectAll
        actions["selectMissing"].on_click = self.selectMissing
        actions["invertSelect"].on_click = self.invertSelection
        actions["cancel"].on_click = lambda: self.setSelectionMode(False)

    # ── 对外的操作 ──

    def setFilterMode(self, mode: FilterMode) -> None:
        self._filterMode = mode
        self.filterSegment.selected_index = mode
        self._refreshList()

    def setCategoryFilter(self, categoryId: str) -> None:
        self._categoryFilter = categoryId
        self._refreshList()

    def setSortField(self, field: SortField) -> None:
        self._sortField = field
        self._refreshList()

    def setSortOrder(self, ascending: bool) -> None:
        self._sortAscending = ascending
        self._refreshList()

    @property
    def searchPlaceholder(self) -> str:
        return T("搜索任务")

    def setSearchText(self, text: str) -> None:
        if text != self._searchText:
            self._searchText = text
            self._refreshList()

    def startAll(self) -> None:
        self._taskService.startAll()

    def pauseAll(self) -> None:
        self._taskService.pauseAll()

    def selectAll(self) -> None:
        self._selectedIds.update(self._displayOrder)
        self._refreshChecked()

    def invertSelection(self) -> None:
        self._selectedIds ^= set(self._displayOrder)
        self._refreshChecked()

    def selectMissing(self) -> None:
        self._selectedIds = {
            taskId for taskId in self._displayOrder
            if (task := self._taskService.taskById(taskId)) and task.hasOutputFile and not isExisting(task.outputPath)
        }
        self._refreshChecked()

    def setSelectionMode(self, enter: bool) -> None:
        if self._isSelectionMode == enter:
            return
        self._isSelectionMode = enter
        self._selectionAnchor = None
        if not enter:
            self._selectedIds.clear()
        for card in self._liveCards.values():
            card.setSelectionMode(enter)
        if enter:
            self.commandSlot.append_child(self.commandView)
        else:
            self.commandSlot.remove_child(0)

    @property
    def isSelectionMode(self) -> bool:
        return self._isSelectionMode

    def _refreshChecked(self) -> None:
        for taskId, card in self._liveCards.items():
            card.setChecked(taskId in self._selectedIds)

    def _onCardSelectionChanged(self, taskId: str, checked: bool, extend: bool) -> None:
        if not self._isSelectionMode:
            self.setSelectionMode(True)

        if extend and self._selectionAnchor:
            try:
                anchorIndex = self._displayOrder.index(self._selectionAnchor)
                currentIndex = self._displayOrder.index(taskId)
            except ValueError:
                return
            first, last = min(anchorIndex, currentIndex), max(anchorIndex, currentIndex)
            self._selectedIds = set(self._displayOrder[first:last + 1])
            self._refreshChecked()
        else:
            if checked:
                self._selectedIds.add(taskId)
                self._selectionAnchor = taskId
            else:
                self._selectedIds.discard(taskId)
                if taskId == self._selectionAnchor:
                    self._selectionAnchor = None
            card = self._liveCards.get(taskId)
            if card is not None:
                card.setChecked(checked)

        if not self._selectedIds:
            self.setSelectionMode(False)

    def on_key_event(self, event: ui.KeyEvent, /) -> bool:
        if event.type != ui.KeyEventType.DOWN:
            return False
        if event.key == ui.Key.A and event.modifiers & ui.KeyboardModifiers.CTRL and self._displayOrder:
            self.setSelectionMode(True)
            self.selectAll()
            return True
        if event.key == ui.Key.DELETE and self._isSelectionMode:
            self._onDeleteSelected()
            return True
        return False

    # ── 工具栏 ──

    def _onFilterSelected(self, index: int) -> None:
        self.setFilterMode(FilterMode(index))

    def _onSpeedChanged(self, speed: int = 0) -> None:
        value = f"{toReadableSize(speed)}/s"
        if cfg.isSpeedLimitEnabled.value:
            value += f" / {toReadableSize(cfg.speedLimitation.value)}/s"
        self.speedBadge.text = value

    def _onSpeedLimitChanged(self, *_args) -> None:
        self.rateLimitButton.checked = cfg.isSpeedLimitEnabled.value
        self._onSpeedChanged(self._speedMeter.currentSpeed)

    def _onPlanButtonClicked(self, checked: bool) -> None:
        if not checked:
            self._plan.clear()
            return
        dialog = PlanTaskDialog(self, self._uiLoop)

        def onAccepted() -> None:
            self._plan.set(dialog.selectedAction(), dialog.selectedFilePath(),
                           onCleared=lambda: setattr(self.planButton, "checked", False))
            self.planButton.checked = True

        dialog.accepted.connect(onAccepted)
        dialog.open()
        self._planDialog = dialog

    def _onRateLimitToggled(self, checked: bool) -> None:
        cfg.set(cfg.isSpeedLimitEnabled, checked)

    def _onRateLimitMenuRequested(self, x: float, y: float) -> None:
        # 对应 Flyout 里的 SpinBox：输入停顿后保存并打开限速
        low, high = cfg.speedLimitation.range
        edit = ui.OutlinedTextField(ui.TextFieldState(str(cfg.speedLimitation.value // KB)))
        edit.set_line_limits(single_line=True)
        edit.set_keyboard_options(keyboard_type=ui.KeyboardType.NUMBER)
        edit.set_trailing_content(text("KB/s"))

        def save() -> None:
            saveTimer.stop()
            value = edit.state.text.strip()
            edit.is_error = not value.isdigit() or not low <= int(value) * KB <= high
            if not edit.is_error:
                cfg.set(cfg.speedLimitation, int(value) * KB)
                cfg.set(cfg.isSpeedLimitEnabled, True)

        saveTimer = SingleShotTimer(self._uiLoop.post, RATE_LIMIT_DELAY, save)
        edit.on_value_change = saveTimer.start
        edit.on_keyboard_action = save
        # 对应 FlyoutView：标题下面一个输入框
        box = ui.Box()
        box.set_padding(16, 8)
        box.append_child(column(text(T("下载限速"), fontWeight=600), edit, spacing=8))
        menu = buildMenu(self.rateLimitArea)
        menu.append_content(box)
        self._menu = menu
        openMenuAt(menu, self.rateLimitArea, x, y)

    def _onSortClicked(self) -> None:
        menu = buildMenu(self.sortButton)
        for field, icon, label in SORT_ITEMS:
            item = menu.add_selectable_item(T(label), field == self._sortField,
                                            buildMenuAction(menu, lambda f=field: self.setSortField(f)))
            item.set_leading_icon(loadIcon(icon))
        menu.add_divider()
        for ascending, icon, label in ((True, "arrow_upward", "顺序"), (False, "arrow_downward", "倒序")):
            item = menu.add_selectable_item(T(label), ascending == self._sortAscending,
                                            buildMenuAction(menu, lambda a=ascending: self.setSortOrder(a)))
            item.set_leading_icon(loadIcon(icon))
        self._menu = menu
        menu.expanded = True

    def _onCategoryFilterClicked(self) -> None:
        menu = buildMenu(self.categoryFilterButton)
        addCategoryItems(menu, self._categoryService.categories(), T("全部分类"), self.setCategoryFilter,
                         firstIcon="filter_alt", selectedId=self._categoryFilter)
        self._menu = menu
        menu.expanded = True

    def _refreshCategoryFilterButton(self) -> None:
        isVisible = bool(cfg.isCategoryEnabled.value)
        if isVisible and not self.categoryFilterSlot.children:
            self.categoryFilterSlot.append_child(self.categoryFilterBox)
        elif not isVisible and self.categoryFilterSlot.children:
            self.categoryFilterSlot.remove_child(0)

    def _onCategoryEnabledChanged(self, *_args) -> None:
        self._refreshCategoryFilterButton()
        self.commandView.setCategoryVisible(bool(cfg.isCategoryEnabled.value))
        # 卡片名称前的分类图标随之显示或隐藏
        for card in self._liveCards.values():
            card.refresh(force=True)

    def _onCategoriesChanged(self) -> None:
        validIds = {"", *(c.categoryId for c in self._categoryService.categories())}
        if self._categoryFilter not in validIds:
            self.setCategoryFilter("")
        for card in self._liveCards.values():
            card.refresh(force=True)

    # ── 命令栏 ──

    def _selectedTasks(self) -> list[Task]:
        return [task for taskId in self._displayOrder
                if taskId in self._selectedIds and (task := self._taskService.taskById(taskId))]

    def _onMoveToFrontSelected(self) -> None:
        self._taskService.moveToFront([taskId for taskId in self._displayOrder if taskId in self._selectedIds])
        self.setSelectionMode(False)

    def _onRedownloadSelected(self) -> None:
        for task in self._selectedTasks():
            self._taskService.redownload(task)
        self.setSelectionMode(False)

    def _onCopyUrlSelected(self) -> None:
        self._copyUrls([task.url for task in self._selectedTasks()])

    def _onDeleteSelected(self) -> None:
        box = MessageBox(T("删除任务"), T("确定要删除选中的下载任务吗？"), self)
        deleteFilesRow, deleteFiles = checkBox(T("同时删除已下载的文件"), cfg.shouldDeleteFilesOnRemove.value)
        box.viewLayout.append_child(deleteFilesRow)

        def onAccepted() -> None:
            cfg.set(cfg.shouldDeleteFilesOnRemove, deleteFiles.checked)
            for task in self._selectedTasks():
                self._taskService.delete(task, deleteFiles.checked)
            self.setSelectionMode(False)

        box.accepted.connect(onAccepted)
        box.open()
        self._deleteBox = box

    def _onMoveCategorySelected(self) -> None:
        targets = self._selectedTasks()
        if not targets:
            return

        def moveTo(categoryId: str) -> None:
            for task in targets:
                self._taskService.setCategory(task, categoryId)
            self.setSelectionMode(False)
            self._refreshList()

        menu = buildMenu(self.commandView.actions["moveCategory"])
        addCategoryItems(menu, self._categoryService.categories(), T("未分类"), moveTo, firstIcon="more_horiz")
        self._menu = menu
        menu.expanded = True

    # ── 列表 ──

    def _keyAt(self, index: int) -> int:
        taskId = self._tasks[index].taskId
        key = self._keys.get(taskId)
        if key is None:
            key = self._keys[taskId] = next(self._nextKey)
        return key

    def _createCard(self, index: int) -> ui.Node:
        task = self._tasks[index]
        taskId = task.taskId
        card = TaskCard(task, self._taskService, self._categoryService, self._copyUrls, self._openDrawer)
        card.setSelectionMode(self._isSelectionMode)
        card.setChecked(taskId in self._selectedIds)
        card.selectionChanged.connect(
            lambda checked, extend: self._onCardSelectionChanged(taskId, checked, extend))
        self._liveCards[taskId] = card
        return card

    def _postRefreshList(self) -> None:
        # 恢复已保存任务时 taskAdded 会连发上百次，合并成一次重建
        if not self._isRefreshPosted:
            self._isRefreshPosted = True
            self._uiLoop.post(self._refreshList)

    def _refreshList(self) -> None:
        self._isRefreshPosted = False
        tasks = self._taskService.tasks
        statuses = FILTER_TO_STATUSES.get(self._filterMode)
        if statuses is not None:
            tasks = [t for t in tasks if t.status in statuses]
        if self._categoryFilter:
            tasks = [t for t in tasks if t.category == self._categoryFilter]
        if self._searchText:
            lower = self._searchText.lower()
            tasks = [t for t in tasks if lower in t.name.lower() or lower in t.url.lower()]

        if self._sortField == SortField.QUEUE_POSITION:
            waitingIndex = {taskId: i for i, taskId in enumerate(self._taskService.waitingOrder())}
            running = [t for t in tasks if t.status == TaskStatus.RUNNING]
            waiting = sorted((t for t in tasks if t.status != TaskStatus.RUNNING and t.taskId in waitingIndex),
                             key=lambda t: waitingIndex[t.taskId])
            rest = sorted((t for t in tasks if t.status != TaskStatus.RUNNING and t.taskId not in waitingIndex),
                          key=lambda t: t.createdAt, reverse=True)
            tasks = rest + waiting + running if self._sortAscending else running + waiting + rest
        elif self._sortField == SortField.NAME:
            tasks.sort(key=lambda t: t.name.lower(), reverse=not self._sortAscending)
        elif self._sortField == SortField.SIZE:
            tasks.sort(key=lambda t: t.fileSize, reverse=not self._sortAscending)
        elif self._sortField == SortField.COMPLETED_AT:
            descending = not self._sortAscending
            completed = sorted((t for t in tasks if t.completedAt), key=lambda t: t.completedAt, reverse=descending)
            pending = sorted((t for t in tasks if not t.completedAt), key=lambda t: t.createdAt, reverse=descending)
            tasks = pending + completed if descending else completed + pending
        else:
            tasks.sort(key=lambda t: t.createdAt, reverse=not self._sortAscending)

        self._tasks = tasks
        self._displayOrder = [t.taskId for t in tasks]
        self.list.notify_data_set_changed(len(tasks))
        if tasks:
            if self.list.parent is None:
                self.listSlot.setChild(self.list)
        else:
            self.emptyStatusWidget.setText(self._emptyText())
            if self.emptyStatusWidget.parent is None:
                self.listSlot.setChild(self.emptyStatusWidget)
        self._refreshTicking()

    def _emptyText(self) -> str:
        if not self._taskService.tasks:
            return T("暂无下载任务")
        if self._searchText and (self._filterMode != FilterMode.ALL or self._categoryFilter):
            return T("没有匹配筛选条件的任务")
        if self._searchText:
            return T("没有匹配的任务")
        if self._categoryFilter:
            return T("该分类下暂无任务")
        if self._filterMode == FilterMode.ACTIVE:
            return T("暂无活动任务")
        if self._filterMode == FilterMode.COMPLETED:
            return T("暂无完成任务")
        return T("暂无下载任务")

    def _onTaskChanged(self, task: Task) -> None:
        card = self._liveCards.get(task.taskId)
        if card is not None:
            card.refresh(force=True)
        self._postRefreshList()

    def _onTaskRemoved(self, taskId: str) -> None:
        self._keys.pop(taskId, None)
        self._liveCards.pop(taskId, None)
        self._selectedIds.discard(taskId)
        if self._selectionAnchor == taskId:
            self._selectionAnchor = None
        self._postRefreshList()

    def _onQueueChanged(self) -> None:
        if self._sortField == SortField.QUEUE_POSITION:
            self._postRefreshList()

    def _onChecksumCompleted(self, task: Task, _algorithm: str) -> None:
        self._onTaskChanged(task)
        # 与 Qt 界面一样，算完校验值后打开详情方便比对；页面不在显示或已有详情时不打扰
        if self.is_attached and (self._drawer is None or not self._drawer.isOpen):
            self._openDrawer(task)

    def _openDrawer(self, task: Task) -> None:
        self._drawer = TaskDrawer(task, self._taskService, self._categoryService, self, self._uiLoop)
        self._drawer.open()

    def _onChecksumStopped(self, task: Task, error: TaskError | None) -> None:
        self._onTaskChanged(task)
        if error is not None:
            self._infoBars.add(T("校验失败"), toLocalizedError(error), icon=InfoBarIcon.ERROR)

    def _onOverwriteFailed(self, task: Task) -> None:
        self._infoBars.add(T("无法移到回收站"), T("旧文件已保留，新文件另存为 {0}").format(task.name),
                           icon=InfoBarIcon.WARNING)

    # ── 每秒刷新运行中的卡片 ──

    def _refreshTicking(self) -> None:
        isTicking = any(t.status == TaskStatus.RUNNING or t.isSeeding for t in self._taskService.tasks)
        if isTicking and self._tickTimer is None:
            self._tickTimer = self._uiLoop.post(self._onTick, TICK_INTERVAL)
        elif not isTicking and self._tickTimer is not None:
            self._tickTimer.cancel()
            self._tickTimer = None

    def _onTick(self) -> None:
        self._tickTimer = self._uiLoop.post(self._onTick, TICK_INTERVAL)
        for info in self.list.state.layout_info.visible_items_info:
            card = self.list.item_node_at(info.index)
            if isinstance(card, TaskCard):
                card.refresh()
