"""任务详情，对应 Qt 界面的 TaskDrawer。

bkit 没有从侧边滑出的抽屉，改用居中的对话框；功能包的详情卡片依赖 Qt，未移植。
"""
from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import TYPE_CHECKING

from bkit import ui

from app.checksum import matchChecksum
from app.config.cfg import cfg
from app.format import toReadableSize, toReadableTime
from app.models.task import TaskStatus
from app.platform.shell import clipboardText, revealInFolder, setClipboardText
from app.ui.cards.task_cards import isMultiFile, toFileIcon
from app.ui.components.category_settings import toCategoryName
from app.ui.components.message_box import MessageBoxBase
from app.ui.i18n import toLocalizedError, tr
from app.ui.icons import buildIcon, buildIconButton
from app.ui.layout import column, row, text
from app.ui.loop import SingleShotTimer, UiLoop

if TYPE_CHECKING:
    from app.models.task import Task, TaskFile
    from app.services.category_service import CategoryService
    from app.services.task_service import TaskService

DRAWER_WIDTH = 592
CAPTION_WIDTH = 88
REFRESH_INTERVAL = 1.0
FILE_ROW_HEIGHT = 32
MAX_VISIBLE_FILES = 10
ERROR_COLOR = 0xFFB3261E


def toTimeText(timestamp: int) -> str:
    return datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M:%S")


class InfoRow(ui.Node):
    """左侧说明、中间可换行的值、右侧几个小按钮。"""

    def __init__(self, caption: str) -> None:
        super().__init__()
        self.captionLabel = text(caption)
        captionBox = ui.Box()
        captionBox.set_size(CAPTION_WIDTH, None)
        captionBox.append_child(self.captionLabel)
        self.valueText = ui.Text("")
        self.buttonLayout = ui.Row(spacing=2)
        self.append_child(row(captionBox, self.valueText, self.buttonLayout, spacing=12, flex=1))

    def setValue(self, value: str) -> None:
        if value != self.valueText.text:
            self.valueText.text = value

    def addButton(self, icon: str, tooltip: str, onClick: Callable[[], object]) -> None:
        box, _ = buildIconButton(icon, tooltip, onClick)
        self.buttonLayout.append_child(box)

    def addCopyButton(self) -> None:
        self.addButton("content_copy", tr("InfoRow", "复制"), lambda: setClipboardText(self.valueText.text))


class DetailCard(ui.Node):
    """标题和其下的一张卡片；refresh() 每秒调用一次，返回是否显示。"""

    def __init__(self, title: str) -> None:
        super().__init__()
        self.bodyLayout = column(spacing=10)
        card = ui.Card(ui.CardStyle.OUTLINED)
        card.set_padding(16, 12)
        card.append_child(self.bodyLayout)
        self.append_child(column(text(title, fontWeight=600), card, spacing=8))

    def refresh(self) -> bool:
        return True


class HeaderCard(ui.Node):
    def __init__(self, task: Task, categoryService: CategoryService) -> None:
        super().__init__()
        self._task = task
        self._categoryService = categoryService
        self.iconSlot = ui.Box()
        self.nameText = ui.Text("")
        self.nameText.set_text_style(font_size=20, line_height=28, font_weight=600)
        self.statusLabel = text()
        self.progressBar = ui.LinearProgressIndicator()
        self.progressBar.set_size(DRAWER_WIDTH, 4)
        self.progressSlot = ui.Box()
        self._iconName = ""
        self.append_child(row(self.iconSlot, column(self.nameText, self.statusLabel, self.progressSlot, spacing=4),
                              spacing=16, flex=1))

    def refresh(self) -> bool:
        task = self._task
        self.nameText.text = task.name
        iconName = toFileIcon(task, self._categoryService)
        if iconName != self._iconName:
            self._iconName = iconName
            if self.iconSlot.children:
                self.iconSlot.remove_child(0)
            self.iconSlot.append_child(buildIcon(iconName, 48))
        progress, speed, received = task.currentSnapshot()
        isProgressVisible = task.status != TaskStatus.COMPLETED and task.fileSize > 0
        if isProgressVisible and not self.progressSlot.children:
            self.progressSlot.append_child(self.progressBar)
        elif not isProgressVisible and self.progressSlot.children:
            self.progressSlot.remove_child(0)
        self.progressBar.progress = progress / 100
        self.statusLabel.text = self._toStatusText(speed, received)
        return True

    def _toStatusText(self, speed: int, received: int) -> str:
        task = self._task
        if task.status == TaskStatus.RUNNING:
            parts = [f"{toReadableSize(speed)}/s"]
            if task.fileSize > 0:
                parts.append(f"{toReadableSize(received)} / {toReadableSize(task.fileSize)}")
                if speed > 0:
                    parts.append(toReadableTime(int((task.fileSize - received) / speed)))
            return " · ".join(parts)
        if task.status == TaskStatus.COMPLETED:
            return tr("HeaderCard", "做种中") if task.isSeeding else tr("HeaderCard", "已完成")
        if task.status == TaskStatus.FAILED:
            return tr("HeaderCard", "失败")
        if task.status == TaskStatus.PAUSED:
            return tr("HeaderCard", "已暂停")
        return tr("HeaderCard", "等待中")


class ErrorBar(ui.Node):
    def __init__(self, task: Task) -> None:
        super().__init__()
        self._task = task
        self.errorText = ui.Text("")
        copyBox, _ = buildIconButton("content_copy", tr("ErrorBar", "复制"),
                                     lambda: setClipboardText(self.errorText.text))
        title = text(tr("ErrorBar", "下载失败"), fontWeight=600)
        title.set_color(ERROR_COLOR)
        card = ui.Card(ui.CardStyle.OUTLINED)
        card.set_padding(16, 12, 8, 12)
        card.append_child(row(buildIcon("error", tint=ERROR_COLOR), column(title, self.errorText, spacing=4), copyBox,
                              spacing=12, flex=1))
        self.append_child(card)

    def refresh(self) -> bool:
        error = self._task.lastError if self._task.status == TaskStatus.FAILED else None
        message = toLocalizedError(error) if error is not None else ""
        if message != self.errorText.text:
            self.errorText.text = message
        return bool(message)


class InfoCard(DetailCard):
    def __init__(self, task: Task, categoryService: CategoryService) -> None:
        super().__init__(tr("InfoCard", "信息"))
        self._task = task
        self._categoryService = categoryService
        self.urlRow = InfoRow(tr("InfoCard", "下载链接"))
        self.pathRow = InfoRow(tr("InfoCard", "保存位置"))
        self.sizeRow = InfoRow(tr("InfoCard", "大小"))
        self.categoryRow = InfoRow(tr("InfoCard", "分类"))
        self.createdRow = InfoRow(tr("InfoCard", "创建时间"))
        self.completedRow = InfoRow(tr("InfoCard", "完成时间"))
        self.urlRow.addCopyButton()
        self.pathRow.addCopyButton()
        self.pathRow.addButton("folder_open", tr("InfoCard", "在文件夹中显示"),
                               lambda: revealInFolder(self._task.outputPath))

    def refresh(self) -> bool:
        task = self._task
        category = self._categoryService.categoryById(task.category) if task.category else None
        rows = [
            (self.urlRow, task.url, True),
            (self.pathRow, str(task.outputPath), True),
            (self.sizeRow, toReadableSize(task.fileSize), task.fileSize > 0),
            (self.categoryRow, toCategoryName(category) if category else tr("InfoCard", "未分类"),
             bool(cfg.isCategoryEnabled.value)),
            (self.createdRow, toTimeText(task.createdAt), True),
            (self.completedRow, toTimeText(task.completedAt) if task.completedAt else "", bool(task.completedAt)),
        ]
        visible = [infoRow for infoRow, _, isVisible in rows if isVisible]
        for infoRow, value, _ in rows:
            infoRow.setValue(value)
        if list(self.bodyLayout.children) != visible:
            while self.bodyLayout.children:
                self.bodyLayout.remove_child(0)
            for infoRow in visible:
                self.bodyLayout.append_child(infoRow)
        return True


class ChecksumCard(DetailCard):
    def __init__(self, task: Task) -> None:
        super().__init__(tr("ChecksumCard", "校验值"))
        self._task = task
        self._shownChecksums: dict[str, str] = {}
        self.rowsLayout = column(spacing=10)
        self.expectedEdit = ui.OutlinedTextField()
        self.expectedEdit.set_label(tr("ChecksumCard", "比对"))
        self.expectedEdit.set_placeholder(tr("ChecksumCard", "粘贴期望值"))
        self.expectedEdit.set_line_limits(single_line=True)
        self.expectedEdit.on_value_change = self._refreshMatch
        pasteBox, _ = buildIconButton("content_copy", tr("ChecksumCard", "粘贴"), self._onPasteClicked)
        self.bodyLayout.append_child(self.rowsLayout)
        self.bodyLayout.append_child(row(self.expectedEdit, pasteBox, spacing=8, flex=0))

    def refresh(self) -> bool:
        task = self._task
        if task.checksums != self._shownChecksums:
            self._shownChecksums = dict(task.checksums)
            while self.rowsLayout.children:
                self.rowsLayout.remove_child(0)
            for algorithm, value in sorted(task.checksums.items()):
                checksumRow = InfoRow(algorithm.upper())
                checksumRow.setValue(value)
                checksumRow.addCopyButton()
                self.rowsLayout.append_child(checksumRow)
            self._refreshMatch()
        return bool(task.checksums) and not isMultiFile(task)

    def _refreshMatch(self) -> None:
        expected = self.expectedEdit.state.text
        algorithm = matchChecksum(self._task.checksums, expected)
        self.expectedEdit.is_error = bool(expected.strip()) and algorithm is None
        if algorithm:
            self.expectedEdit.set_supporting_text(tr("ChecksumCard", "与 {0} 一致").format(algorithm.upper()))
        elif expected.strip():
            self.expectedEdit.set_supporting_text(tr("ChecksumCard", "与已计算的校验值都不一致"))
        else:
            self.expectedEdit.set_supporting_text("")

    def _onPasteClicked(self) -> None:
        self.expectedEdit.state.text = clipboardText()
        self.expectedEdit.request_focus()


class FileListCard(DetailCard):
    def __init__(self, task: Task) -> None:
        super().__init__(tr("FileListCard", "文件"))
        self._task = task
        self._lastStatus: TaskStatus | None = None
        self._rows: list[tuple[str, str, str]] = []
        self.table = ui.LazyColumn()
        self.table.set_item_provider(0, self._createRow)
        self.tableBox = ui.Box()
        self.tableBox.append_child(self.table)
        self.bodyLayout.append_child(self.tableBox)

    def refresh(self) -> bool:
        task = self._task
        files = task.files or []
        if len(files) <= 1:
            return False
        if task.status == self._lastStatus and task.status != TaskStatus.RUNNING:
            return True
        self._lastStatus = task.status
        self._rows = [(task.toDisplayPath(f), toReadableSize(f.size), self._toFileStatusText(f)) for f in files]
        self.tableBox.set_size(None, min(len(self._rows), MAX_VISIBLE_FILES) * FILE_ROW_HEIGHT)
        self.table.notify_data_set_changed(len(self._rows))
        return True

    def _createRow(self, index: int) -> ui.Node:
        name, size, status = self._rows[index]
        box = ui.Box()
        box.set_size(None, FILE_ROW_HEIGHT)
        nameLabel = text(name)
        nameLabel.overflow = ui.TextOverflow.MIDDLE_ELLIPSIS
        box.append_child(row(nameLabel, text(size), text(status), spacing=12, flex=0))
        return box

    def _toFileStatusText(self, file: TaskFile) -> str:
        if not file.selected:
            return tr("FileListCard", "未选择")
        if file.completed:
            return tr("FileListCard", "已完成")
        return f"{file.downloadedBytes * 100 // file.size}%" if file.size > 0 else "--"


class TaskDrawer(MessageBoxBase):

    def __init__(self, task: Task, taskService: TaskService, categoryService: CategoryService, host: ui.Node,
                 uiLoop: UiLoop) -> None:
        super().__init__(host)
        self._task = task
        self._taskService = taskService
        self.cards: list[ui.Node] = [
            HeaderCard(task, categoryService),
            ErrorBar(task),
            InfoCard(task, categoryService),
            ChecksumCard(task),
            FileListCard(task),
        ]
        self._refreshTimer = SingleShotTimer(uiLoop.post, REFRESH_INTERVAL, self._onRefreshTimeout)
        self._initWidget()
        self._bind()
        self._refresh()

    def _initWidget(self) -> None:
        self.dialog.platform_default_width = DRAWER_WIDTH
        self.contentLayout.remove_child(self.contentLayout.children.index(self.buttonLayout))
        closeButton = ui.IconButton(ui.MaterialIcon.CLOSE, self._onCancelClicked)
        self.contentLayout.insert_child(0, row(text(tr("TaskDrawer", "任务详情"), fontSize=20, fontWeight=600),
                                               ui.Spacer(), closeButton, flex=1))

    def _bind(self) -> None:
        self._taskService.taskRemoved.connect(self._onTaskRemoved)

    def open(self) -> None:
        super().open()
        self._refreshTimer.start()

    def close(self, isAccepted: bool) -> None:
        self._refreshTimer.stop()
        super().close(isAccepted)

    def _refresh(self) -> None:
        visible = [card for card in self.cards if card.refresh()]
        if list(self.viewLayout.children) != visible:
            while self.viewLayout.children:
                self.viewLayout.remove_child(0)
            for card in visible:
                self.viewLayout.append_child(card)

    def _onRefreshTimeout(self) -> None:
        if self.isOpen:
            self._refresh()
            self._refreshTimer.start()

    def _onTaskRemoved(self, taskId: str) -> None:
        if taskId == self._task.taskId:
            self.close(False)
