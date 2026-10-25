"""新建任务对话框：输入链接后由 TaskDraft 解析，确认后交给 TaskService。

Qt 界面的 StandaloneWrapper 不移植：bkit 只有一个窗口，对话框总盖在主窗口上。
"""
from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING

from bkit import ui

from app.config.cfg import addRecentFolder
from app.platform.file_dialog import openFileDialog
from app.platform.shell import clipboardText
from app.ui.cards.draft_cards import DraftCard
from app.ui.components.card_groups import DraftCardGroup, OptionCardGroup
from app.ui.components.info_bar import InfoBarArea, InfoBarIcon
from app.ui.components.message_box import MessageBoxBase
from app.ui.components.option_cards import OutputFolderCard, SubworkerCountCard
from app.ui.dialogs.batch_url import BatchUrlDialog
from app.i18n import toLocalizedError, tr
from app.ui.icons import buildButton, buildIconButton
from app.ui.layout import row, text
from app.ui.loop import SingleShotTimer, UiLoop

if TYPE_CHECKING:
    from app.models.task import Task, TaskError
    from app.services.category_service import CategoryService
    from app.services.feature_service import FeatureService
    from app.services.task_draft import TaskDraft

WIDTH = 700
PARSE_INTERVAL = 1.0


def T(text: str) -> str:
    return tr("TaskDraftDialog", text)


class TaskDraftDialog(MessageBoxBase):

    def __init__(self, draft: TaskDraft, featureService: FeatureService, categoryService: CategoryService,
                 probeConflict: Callable[[Task], Path | None], host: ui.Node, uiLoop: UiLoop) -> None:
        super().__init__(host)
        self._draft = draft
        self._featureService = featureService
        self._categoryService = categoryService
        self._probeConflict = probeConflict
        self._isSettingText = False
        self._uiLoop = uiLoop
        self._batchDialog: BatchUrlDialog | None = None
        self._parseTimer = SingleShotTimer(uiLoop.post, PARSE_INTERVAL, self._onParseNeeded)
        self.infoBars = InfoBarArea(uiLoop)
        self._initWidget()
        self._initLayout()
        self._bind()

    def _initWidget(self) -> None:
        self.dialog.platform_default_width = WIDTH
        # 点到外面就丢掉输入的链接太容易误触，只认取消按钮和 Esc
        self.dialog.set_dismiss_on_click_outside(False)
        self.batchButton = buildButton("content_copy", T("批量添加"), self._onBatchClicked)
        self._fileTypes = self._featureService.fileTypes()
        self.importButton = buildButton("create_new_folder", T("导入文件"), lambda: self._uiLoop.post(self._onImport))
        self.urlEdit = ui.OutlinedTextField()
        self.urlEdit.set_placeholder(T("添加多个下载链接时，请确保每行只有一个下载链接"))
        self.urlEdit.set_line_limits(min_lines=3, max_lines=6)
        self.progressBar = ui.LinearProgressIndicator(indeterminate=True)
        self.progressSlot = ui.Box()
        self.draftGroup = DraftCardGroup()
        self.optionGroup = OptionCardGroup()
        self.optionGroup.addCard(OutputFolderCard(self._uiLoop.post))
        self.optionGroup.addCard(SubworkerCountCard())

        self.cancelButton.text = T("取消")
        self.yesButton.text = T("下载")
        self.laterBox, _ = buildIconButton("history", T("稍后下载"), self._onLaterClicked, ui.IconButtonVariant.FILLED)
        index = self.buttonLayout.children.index(self.yesButton)
        self.buttonLayout.remove_child(index)
        self.buttonLayout.insert_child(index, row(self.yesButton, self.laterBox, spacing=2, flex=0))

    def _initLayout(self) -> None:
        self.headerLayout = row(text(T("添加任务"), fontSize=20, fontWeight=600), ui.Spacer(), self.batchButton,
                                spacing=8, flex=1)
        if self._fileTypes:
            self.headerLayout.append_child(self.importButton)
        for node in (self.headerLayout, self.urlEdit, self.progressSlot, self.draftGroup, self.optionGroup,
                     self.infoBars.node):
            self.viewLayout.append_child(node)

    def _bind(self) -> None:
        self.urlEdit.on_value_change = self._onUrlTextChanged
        self._draft.parsingBusyChanged.connect(self._onParsingBusyChanged)
        self._draft.parseSucceeded.connect(self._onParseSucceeded)
        self._draft.parseFailed.connect(self._onParseFailed)
        self._draft.itemsChanged.connect(self._onItemsChanged)
        self._draft.itemsCleared.connect(self._onCleared)

    def open(self) -> None:
        if not self.isOpen:
            self.optionGroup.reset()
            if not self._urls():
                urls = self._clipboardUrls()
                if urls:
                    self._addUrlLines(urls)
                    self._parseTimer.start()
            super().open()
        self.urlEdit.request_focus()

    def addUrls(self, urls: list[str]) -> None:
        if not urls:
            return
        existing = set(self._urls())
        toAdd = [stripped for u in urls if (stripped := u.strip()) and stripped not in existing]
        if not toAdd:
            return
        self._addUrlLines(toAdd)
        self._parseTimer.stop()
        self._onParseNeeded()

    def addParsedTasks(self, tasks: list[Task]) -> None:
        if not tasks:
            return
        newUrls = self._draft.addParsedTasks(tasks)
        if newUrls:
            self._addUrlLines(newUrls)
        self._parseTimer.stop()

    def close(self, isAccepted: bool, autoStart: bool = True) -> None:
        if isAccepted:
            self._parseTimer.stop()
            self._onParseNeeded()
            if not self._draft.canConfirm():
                return
            self._draft.confirm(autoStart=autoStart)
            addRecentFolder(str(self.optionGroup.options()["outputFolder"]))
        else:
            self._draft.clear()

        self._setText("")
        self._parseTimer.stop()
        self.draftGroup.clear()
        self.draftGroup.updateStats(0, 0, 0)
        super().close(isAccepted)

    def _onLaterClicked(self) -> None:
        self.close(True, autoStart=False)

    def _setText(self, value: str) -> None:
        self._isSettingText = True
        try:
            self.urlEdit.state.text = value
        finally:
            self._isSettingText = False

    def _addUrlLines(self, urls: list[str]) -> None:
        current = self.urlEdit.state.text.rstrip("\n")
        self._setText("\n".join([current, *urls]) if current else "\n".join(urls))

    def _onUrlTextChanged(self) -> None:
        if not self._isSettingText:
            self._parseTimer.start()

    def _onParseNeeded(self) -> None:
        self._draft.setBaseOptions(self.optionGroup.options())
        self._draft.setUrls(self._urls())

    def _onParsingBusyChanged(self, isBusy: bool) -> None:
        if isBusy and not self.progressSlot.children:
            self.progressSlot.append_child(self.progressBar)
        elif not isBusy and self.progressSlot.children:
            self.progressSlot.remove_child(0)

    def _onParseSucceeded(self, url: str, task: Task) -> None:
        card = DraftCard(task, self._categoryService, self._probeConflict)
        card.categoryPicked.connect(lambda categoryId: self._draft.setUrlCategory(url, categoryId))
        self.draftGroup.addCard(url, card)
        self._refreshStats()

    def _onParseFailed(self, url: str, error: TaskError) -> None:
        self._refreshStats()
        displayUrl = url if len(url) <= 48 else f"{url[:45]}..."
        self.infoBars.add(T("链接解析失败"), f"{displayUrl}\n{toLocalizedError(error)}", icon=InfoBarIcon.ERROR)

    def _onItemsChanged(self) -> None:
        self.draftGroup.setUrls(self._draft.urls())
        self._refreshStats()

    def _onCleared(self) -> None:
        self.draftGroup.clear()
        self.draftGroup.updateStats(0, 0, 0)

    def _refreshStats(self) -> None:
        tasks = [self._draft.taskByUrl(url) for url in self._draft.urls()]
        successCount = sum(1 for t in tasks if t is not None)
        totalSize = sum(t.fileSize for t in tasks if t is not None and t.fileSize > 0)
        self.draftGroup.updateStats(successCount, self._draft.failCount(), totalSize)

    def _urls(self) -> list[str]:
        return [line.strip() for line in self.urlEdit.state.text.splitlines() if line.strip()]

    def _onBatchClicked(self) -> None:
        dialog = BatchUrlDialog(self.viewLayout, self._uiLoop)
        dialog.accepted.connect(lambda: self.addUrls(dialog.urls()))
        dialog.open()
        self._batchDialog = dialog

    def _onImport(self) -> None:
        globs = ";".join(f"*{ext}" for ft in self._fileTypes for ext in ft.extensions)
        filters = [(T("所有可导入文件 ({0})").format(globs.replace(";", " ")), globs)]
        filters += [(ft.displayName, ";".join(f"*{ext}" for ext in ft.extensions)) for ft in self._fileTypes]
        paths = openFileDialog(T("导入文件"), filters, isMultiple=True)
        if paths:
            self.addUrls([Path(p).as_uri() for p in paths])

    def _clipboardUrls(self) -> list[str]:
        return [url for line in clipboardText().splitlines()
                if (url := line.strip()) and self._featureService.match(url)]
