from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import TYPE_CHECKING

from bkit import ui

from app.checksum import ALGORITHMS, COMMON_ALGORITHMS
from app.config.cfg import cfg
from app.format import toReadableSize, toReadableTime
from app.models.task import SpecialFileSize, TaskStatus
from app.platform.filesystem import isExisting, isFolder
from app.platform.shell import openFile, revealInFolder
from app.signal import Signal
from app.ui.components.category_settings import addCategoryItems
from app.ui.components.menu import buildMenu, buildMenuAction, openMenuAt
from app.ui.components.message_box import MessageBox
from app.ui.dialogs.file_select import FileSelectDialog
from app.ui.i18n import toLocalizedError, tr
from app.ui.icons import buildIcon, buildIconButton, loadIcon, toCategoryIcon
from app.ui.layout import Slot, checkBox, column, isClick, row, text
from app.ui.theme import colorOf

if TYPE_CHECKING:
    from app.models.task import Task
    from app.services.category_service import CategoryService
    from app.services.task_service import TaskService

ERROR_COLOR = 0xFFB3261E
WARNING_COLOR = 0xFFC8A050
ROW_HEIGHT = 60
FILE_ICON_BOX = 48
FILE_ICON_SIZE = 40
INFO_ICON_SIZE = 16
# 进度条宽度由所在行撑满到卡片宽，这里只给一个足够大的上限
PROGRESS_WIDTH = 4096
PROGRESS_HEIGHT = 4
DOUBLE_CLICK_INTERVAL = 400


def T(text: str) -> str:
    return tr("TaskCard", text)


def toEtaText(task: Task, speed: int, received: int) -> str:
    if task.fileSize > 0 and speed > 0:
        return toReadableTime(int((task.fileSize - received) / speed))
    return "--"


def toSizeText(task: Task, received: int) -> str | None:
    if task.status == TaskStatus.COMPLETED:
        return toReadableSize(task.fileSize) if task.fileSize > 0 else None
    if task.fileSize > 0:
        return f"{toReadableSize(received)}/{toReadableSize(task.fileSize)}"
    return f"{toReadableSize(received)}/--"


def isDeterminate(task: Task) -> bool:
    return task.fileSize not in {SpecialFileSize.UNKNOWN, SpecialFileSize.NOT_SUPPORTED}


def isMultiFile(task: Task) -> bool:
    return bool(task.files) and len(task.files) > 1


def canOpenFile(task: Task) -> bool:
    return task.status == TaskStatus.COMPLETED and (not task.hasOutputFile or isExisting(task.outputPath))


def toFileIcon(task: Task, categoryService: CategoryService) -> str:
    # 分类关闭时 task.category 为空，仍按文件名匹配，让图标表示文件类型
    if isMultiFile(task):
        return "folder"
    category = categoryService.categoryById(task.category or categoryService.categoryOf(task))
    return toCategoryIcon(category.icon) if category is not None else "draft"


class InfoLabel(ui.Node):
    """小图标加一行文字，对应 Qt 界面的 IconBodyLabel；文字为 None 时由卡片隐藏。"""

    def __init__(self, icon: str) -> None:
        super().__init__()
        self._value: str | None = None
        self._color: int | None = None
        self.textLabel = text()
        self.hBoxLayout = row(buildIcon(icon, INFO_ICON_SIZE), self.textLabel, spacing=4)
        self.append_child(self.hBoxLayout)

    @property
    def isVisible(self) -> bool:
        return self._value is not None

    def setText(self, value: str | None) -> None:
        self._value = value
        if value is not None and value != self.textLabel.text:
            self.textLabel.text = value

    def setTextColor(self, color: int | None) -> None:
        # Text 只能设定颜色、不能恢复为主题的内容色，所以换成新节点
        if color == self._color:
            return
        self._color = color
        label = text(self.textLabel.text)
        if color is not None:
            label.set_color(color)
        self.hBoxLayout.remove_child(1)
        self.hBoxLayout.insert_child(1, label)
        self.textLabel = label


class TaskCard(ui.Node):
    """任务列表的一行。LazyColumn 按需创建，滚出视口即丢弃。

    点击卡片空白处选中任务，Shift 点击连选，双击打开文件，右键打开菜单，与 Qt 界面一致。
    """

    selectionChanged = Signal(bool, bool)

    def __init__(self, task: Task, taskService: TaskService, categoryService: CategoryService,
                 copyUrls: Callable[[list[str]], None], openDrawer: Callable[[Task], None]) -> None:
        super().__init__()
        self._task = task
        self._taskService = taskService
        self._categoryService = categoryService
        self._copyUrls = copyUrls
        self._openDrawer = openDrawer
        self._isSelectionMode = False
        self._isChecked = False
        self._lastStatus: TaskStatus | None = None
        self._progressKind = ""
        self._fileIcon = ""
        self._categoryIcon = ""
        self._pressedButtons = 0
        self._pressPosition = (0.0, 0.0)
        self._lastClickTime: int | None = None
        self._menu: ui.DropdownMenu | None = None
        self._deleteBox: MessageBox | None = None
        self._fileSelectDialog: FileSelectDialog | None = None
        self._initWidget()
        self._initLayout()
        self.refresh(force=True)

    @property
    def task(self) -> Task:
        return self._task

    def _initWidget(self) -> None:
        self.pointer_input = True
        self.card = ui.Card(ui.CardStyle.FILLED)
        self.card.set_size(None, ROW_HEIGHT)
        # 进度条贴着卡片底边，对应 Qt 界面在 resizeEvent 里把它放到底部
        self.card.set_content_alignment(ui.Alignment.START, ui.Alignment.END)
        self.checkBox = ui.Checkbox(False, self._onCheckBoxChanged)
        self.checkBoxSlot = ui.Box()
        self.iconLabel = buildIcon("draft", FILE_ICON_SIZE)
        self.categoryIconSlot = ui.Box()
        self.nameLabel = text(self._task.name, fontWeight=600)
        self.speedLabel = InfoLabel("speed")
        self.etaLabel = InfoLabel("timer")
        self.sizeLabel = InfoLabel("library_books")
        self.statusLabel = InfoLabel("info")
        self.infoLayout = ui.Row(spacing=12, cross_alignment=ui.Alignment.CENTER)
        self.toggleBox, self.toggleButton = buildIconButton(
            "play_arrow", T("暂停/继续"), self._onToggleClicked, ui.IconButtonVariant.FILLED)
        self.selectFilesBox, _ = buildIconButton("library_books", T("选择文件"), self._onSelectFilesClicked,
                                                 ui.IconButtonVariant.OUTLINED)
        self.checksumBox, self.checksumButton = buildIconButton("fingerprint", T("计算校验值"), self._onChecksumClicked,
                                                               ui.IconButtonVariant.OUTLINED)
        # 多文件任务显示「选择文件」，单文件任务显示「计算校验值」，与 Qt 界面一样二者只出现其一
        self.fileActionSlot = ui.Box()
        self.openFileBox, self.openFileButton = buildIconButton(
            "link", T("打开文件"), lambda: openFile(self._task.outputPath), ui.IconButtonVariant.OUTLINED)
        self.openFolderBox, _ = buildIconButton(
            "folder", T("打开文件夹"), lambda: revealInFolder(self._task.outputPath), ui.IconButtonVariant.OUTLINED)
        self.deleteBox = ui.TooltipBox(ui.IconButton(ui.MaterialIcon.CLOSE, self._onDeleteClicked))
        self.deleteBox.set_plain_tooltip(T("删除"))
        self.progressSlot = ui.Box()
        self.progressSlot.set_padding(4, 0, 4, 0)
        self.progressBar: ui.LinearProgressIndicator | None = None

    def _initLayout(self) -> None:
        content = column(row(self.categoryIconSlot, self.nameLabel, spacing=4, flex=1), self.infoLayout, spacing=4)
        iconBox = ui.Box()
        iconBox.set_size(FILE_ICON_BOX, FILE_ICON_BOX)
        iconBox.set_content_alignment(ui.Alignment.CENTER, ui.Alignment.CENTER)
        iconBox.append_child(self.iconLabel)
        inner = ui.Box()
        inner.set_padding(12, 0)
        inner.append_child(Slot(row(
            self.checkBoxSlot, iconBox, content, self.toggleBox, self.fileActionSlot,
            self.openFileBox, self.openFolderBox, self.deleteBox,
            spacing=8, flex=2,
        )))
        self.card.append_child(inner)
        self.card.append_child(self.progressSlot)
        self.append_child(self.card)

    def refresh(self, force: bool = False) -> None:
        task = self._task
        checksumProgress = self._taskService.checksumProgress(task)
        if (not force and self._lastStatus == task.status and task.status != TaskStatus.RUNNING
                and not task.isSeeding and checksumProgress is None):
            return
        progress, speed, received = task.currentSnapshot()
        self._refreshIcon(task)
        self._refreshCategoryIcon(task)
        self._refreshInfo(task, speed, received)
        self._refreshProgress(task, progress)
        self._refreshButtons(task, checksumProgress)
        self._lastStatus = task.status

    def _refreshIcon(self, task: Task) -> None:
        # 任务名在探测后才确定，图标随之更新
        name = toFileIcon(task, self._categoryService)
        if name != self._fileIcon:
            self._fileIcon = name
            self.iconLabel.icon = loadIcon(name)

    def _refreshCategoryIcon(self, task: Task) -> None:
        category = (self._categoryService.categoryById(task.category)
                    if cfg.isCategoryEnabled.value and task.category else None)
        icon = toCategoryIcon(category.icon) if category is not None else ""
        if icon == self._categoryIcon:
            return
        self._categoryIcon = icon
        if self.categoryIconSlot.children:
            self.categoryIconSlot.remove_child(0)
        if icon:
            self.categoryIconSlot.append_child(buildIcon(icon, INFO_ICON_SIZE))

    def _refreshInfo(self, task: Task, speed: int, received: int) -> None:
        isRunning = task.status == TaskStatus.RUNNING
        self.speedLabel.setText(f"{toReadableSize(speed)}/s" if isRunning else None)
        self.etaLabel.setText(toEtaText(task, speed, received) if isRunning else None)
        self.sizeLabel.setText(toSizeText(task, received))

        status: str | None = None
        color: int | None = None
        isFileMissing = False
        if task.status == TaskStatus.COMPLETED:
            self.nameLabel.text = task.name
            isFileMissing = task.hasOutputFile and not isExisting(task.outputPath)
            if isFileMissing:
                status, color = T("文件不存在"), WARNING_COLOR
            elif task.completedAt:
                status = T("完成于 {}").format(datetime.fromtimestamp(task.completedAt).strftime("%Y-%m-%d %H:%M:%S"))
            else:
                status = T("任务已经完成")
        elif task.status == TaskStatus.FAILED:
            error = task.lastError
            status = toLocalizedError(error) if error else T("下载过程中发生错误，请稍后重试")
        elif task.status == TaskStatus.PAUSED:
            status = T("任务已经暂停")
        elif task.status == TaskStatus.WAITING:
            status = T("任务正在等待")
        # 对应 MultiFileTaskCard：等待和完成时以选中文件数代替状态
        if isMultiFile(task) and not isFileMissing and task.status in {TaskStatus.WAITING, TaskStatus.COMPLETED}:
            selected = sum(1 for f in task.files if f.selected)
            status = tr("MultiFileTaskCard", "{0}/{1} 个文件").format(selected, len(task.files))
        self.statusLabel.setTextColor(color)
        self.statusLabel.setText(status)
        self._refreshInfoLayout()

    def _setStatus(self, value: str) -> None:
        self.statusLabel.setTextColor(None)
        self.statusLabel.setText(value)
        self._refreshInfoLayout()

    def _refreshInfoLayout(self) -> None:
        # 没有内容的标签不占位置，对应 Qt 界面的 label.hide()
        visible = [label for label in (self.speedLabel, self.etaLabel, self.sizeLabel, self.statusLabel)
                   if label.isVisible]
        if list(self.infoLayout.children) == visible:
            return
        while self.infoLayout.children:
            self.infoLayout.remove_child(0)
        for label in visible:
            self.infoLayout.append_child(label)

    def _refreshProgress(self, task: Task, progress: float) -> None:
        if task.status == TaskStatus.COMPLETED:
            kind = ""
        elif task.status == TaskStatus.FAILED:
            kind = "error"
        elif isDeterminate(task):
            kind = "determinate"
        else:
            # 不定进度条挂上去就一直动画，只在运行时显示
            kind = "indeterminate" if task.status == TaskStatus.RUNNING else ""

        if kind != self._progressKind:
            if self.progressSlot.children:
                self.progressSlot.remove_child(0)
            self.progressBar = None
            if kind:
                self.progressBar = ui.LinearProgressIndicator(indeterminate=kind == "indeterminate")
                self.progressBar.set_size(PROGRESS_WIDTH, PROGRESS_HEIGHT)
                # 与 Qt 界面一样不画轨道，只画已完成的部分
                self.progressBar.set_colors(track=0)
                if kind == "error":
                    self.progressBar.set_colors(indicator=ERROR_COLOR, track=0)
                self.progressSlot.append_child(row(self.progressBar, flex=0))
            self._progressKind = kind
        if self.progressBar is not None and kind != "indeterminate":
            self.progressBar.progress = progress / 100

    def _refreshButtons(self, task: Task, checksumProgress: int | None) -> None:
        if task.status == TaskStatus.RUNNING:
            icon, isEnabled = "pause", task.canPause
        elif task.status == TaskStatus.COMPLETED:
            icon = "pause" if task.isSeeding else "play_arrow"
            isEnabled = task.canSeed and (not task.hasOutputFile or isExisting(task.outputPath))
        else:
            icon, isEnabled = "play_arrow", True
        self.toggleButton.icon = loadIcon(icon)
        self.toggleButton.enabled = isEnabled

        fileAction = self.selectFilesBox if isMultiFile(task) else self.checksumBox
        if fileAction not in self.fileActionSlot.children:
            if self.fileActionSlot.children:
                self.fileActionSlot.remove_child(0)
            self.fileActionSlot.append_child(fileAction)
        # 计算中按钮换成停止图标，点了取消；对应 Qt 界面 ChecksumButton 的进度环和停止方块
        self.checksumButton.icon = loadIcon("stop" if checksumProgress is not None else "fingerprint")
        self.checksumButton.enabled = (task.status == TaskStatus.COMPLETED and task.hasOutputFile
                                       and isExisting(task.outputPath))
        self.openFileButton.enabled = canOpenFile(task)

    def _onToggleClicked(self) -> None:
        task = self._task
        if task.isSeeding:
            self._taskService.stopSeeding(task)
        elif task.status == TaskStatus.COMPLETED:
            self._taskService.startSeeding(task)
        elif task.status == TaskStatus.RUNNING:
            self._taskService.pause(task)
        else:
            self._taskService.start(task)
        self.refresh()

    def _onSelectFilesClicked(self) -> None:
        dialog = FileSelectDialog(self._task, self._categoryService, self)

        def onAccepted() -> None:
            self._taskService.updateSelection(self._task, dialog.selectedIndexes())
            self.refresh(force=True)

        dialog.accepted.connect(onAccepted)
        dialog.open()
        self._fileSelectDialog = dialog

    def _onDeleteClicked(self) -> None:
        box = MessageBox(T("删除任务"), T("确定要删除这个下载任务吗？"), self)
        deleteFilesRow, deleteFiles = checkBox(T("同时删除已下载的文件"), cfg.shouldDeleteFilesOnRemove.value)
        box.viewLayout.append_child(deleteFilesRow)

        def onAccepted() -> None:
            cfg.set(cfg.shouldDeleteFilesOnRemove, deleteFiles.checked)
            self._taskService.delete(self._task, deleteFiles.checked)

        box.accepted.connect(onAccepted)
        box.open()
        self._deleteBox = box

    def _onChecksumClicked(self) -> None:
        task = self._task
        if self._taskService.checksumProgress(task) is not None:
            self._taskService.cancelChecksum(task)
            return
        if isFolder(task.outputPath) or not isExisting(task.outputPath):
            self._setStatus(T("文件不存在，无法校验"))
            return
        menu = buildMenu(self.checksumButton)
        common = [a for a in ALGORITHMS if a in COMMON_ALGORITHMS]
        for algorithm in common:
            self._addChecksumItem(menu, menu, algorithm)
        moreMenu = menu.add_submenu(T("更多"))
        for algorithm in ALGORITHMS:
            if algorithm not in COMMON_ALGORITHMS:
                self._addChecksumItem(menu, moreMenu, algorithm)
        self._menu = menu
        menu.expanded = True

    def _addChecksumItem(self, root: ui.DropdownMenu, menu: ui.DropdownMenu, algorithm: str) -> None:
        def onCheckedChange(_checked: bool) -> None:
            root.dismiss_all()
            self._taskService.startChecksum(self._task, algorithm)

        menu.add_checkable_item(algorithm.upper(), algorithm in self._task.checksums, onCheckedChange)

    # ── 选择 ──

    def setSelectionMode(self, enter: bool) -> None:
        self._isSelectionMode = enter
        if enter and not self.checkBoxSlot.children:
            self.checkBoxSlot.append_child(self.checkBox)
        elif not enter and self.checkBoxSlot.children:
            self.checkBoxSlot.remove_child(0)
        if not enter:
            self.setChecked(False)
        self._refreshBorder()

    def isChecked(self) -> bool:
        return self._isChecked

    def setChecked(self, checked: bool) -> None:
        if checked == self._isChecked:
            return
        self._isChecked = checked
        self.checkBox.checked = checked
        self._refreshBorder()

    def _refreshBorder(self) -> None:
        color = colorOf(self, "primary") if self._isSelectionMode and self._isChecked else None
        self.card.set_border(2 if color is not None else 0, color or 0)

    def _onCheckBoxChanged(self, checked: bool) -> None:
        self.selectionChanged.emit(checked, False)

    def on_attach(self) -> None:
        super().on_attach()
        # 选中边框取主题色，要等卡片挂到主题之下
        self._refreshBorder()

    # ── 鼠标 ──

    def on_pointer_event(self, event: ui.PointerEvent, pass_: ui.PointerEventPass,
                         bounds: tuple[float, float], /) -> None:
        # MAIN 阶段子节点先处理：按钮消费过的点击不算卡片的
        if pass_ != ui.PointerEventPass.MAIN or not event.changes:
            return
        change = event.changes[0]
        if event.type == ui.PointerEventType.PRESS:
            self._pressedButtons = 0 if change.is_consumed else int(event.buttons)
            self._pressPosition = change.position
        elif event.type == ui.PointerEventType.RELEASE and self._pressedButtons:
            buttons, self._pressedButtons = self._pressedButtons, 0
            if change.is_consumed or not isClick(change.position, self._pressPosition, self.density):
                return
            change.consume()
            if buttons & ui.PointerButtons.SECONDARY:
                self._openContextMenu(*change.position)
            elif buttons & ui.PointerButtons.PRIMARY:
                self._onClicked(change.uptime_millis, event.keyboard_modifiers)

    def _onClicked(self, time: int, modifiers: ui.KeyboardModifiers) -> None:
        extend = bool(modifiers & ui.KeyboardModifiers.SHIFT)
        isDoubleClick = (not extend and self._lastClickTime is not None
                         and time - self._lastClickTime <= DOUBLE_CLICK_INTERVAL)
        self._lastClickTime = None if isDoubleClick else time
        checked = True if extend or not self._isSelectionMode else not self._isChecked
        self.selectionChanged.emit(checked, extend)
        if isDoubleClick and canOpenFile(self._task):
            openFile(self._task.outputPath)

    def _openContextMenu(self, x: float, y: float) -> None:
        task = self._task
        service = self._taskService
        menu = buildMenu(self)
        menu.add_item(T("任务详情"), buildMenuAction(menu, lambda: self._openDrawer(task))).set_leading_icon(
            loadIcon("info"))
        menu.add_divider()
        actions = [
            ("content_copy", T("复制下载链接"), lambda: self._copyUrls([task.url])),
            ("arrow_upward", T("移到最前"), lambda: service.moveToFront([task.taskId])),
            ("update", T("重新下载"), lambda: service.redownload(task)),
        ]
        for icon, label, action in actions:
            menu.add_item(label, buildMenuAction(menu, action)).set_leading_icon(loadIcon(icon))
        if cfg.isCategoryEnabled.value:
            addCategoryItems(menu.add_submenu(T("移动到分类")), self._categoryService.categories(), T("未分类"),
                             lambda categoryId: service.setCategory(task, categoryId), firstIcon="more_horiz")
        self._menu = menu
        openMenuAt(menu, self, x, y)
