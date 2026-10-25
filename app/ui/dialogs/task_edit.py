from copy import copy, deepcopy

from bkit import ui

from app.format import toReadableSize
from app.i18n import tr, toLocalizedError
from app.models.task import TaskOptions, toTaskError
from app.ui.components.message_box import MessageBox, MessageBoxBase
from app.ui.components.option_cards import OutputFolderCard


class TaskEditDialog(MessageBoxBase):
    def __init__(self, task, view, host):
        super().__init__(host)
        self._task, self._view, self._host = task, view, host
        self._draft = copy(task)
        self._draft.files = deepcopy(task.files)
        # 运行中的步骤持有事件循环对象，编辑副本只替换参数，不复制这些对象。
        self._draft.steps = [copy(step) for step in task.steps]
        for step in self._draft.steps:
            step._bindTask(self._draft)
        self._confirm = None
        self._workId = ""
        self.folderCard = OutputFolderCard(view.services.uiLoop.post, initial=task.outputFolder)
        self.cards = view.commonOptions(self._draft, includeFolder=False) + view.options(self._draft, isEditing=True)
        self.dialog.set_title(tr("LiveEditDialog", "编辑任务"))
        self.urlEdit = ui.OutlinedTextField(ui.TextFieldState(task.url))
        self.urlEdit.set_label(tr("UrlEditCard", "下载链接"))
        if view.canChangeUrl:
            self.viewLayout.append_child(self.urlEdit)
        self.viewLayout.append_child(self.folderCard)
        for card in self.cards:
            self.viewLayout.append_child(card)
        self.errorText = ui.Text("")
        self.viewLayout.append_child(self.errorText)

    def _onYesClicked(self):
        if not all([card.apply() for card in self.cards]):
            return
        options = self.folderCard.options()
        step = self._draft.steps[0] if self._draft.steps else None
        if step:
            options.update({key: getattr(step, key) for key in self._view.editKeys if hasattr(step, key)})
        url = self.urlEdit.state.text.strip()
        if not self._view.canChangeUrl or url == self._task.url:
            self._view.services.taskService.edit(self._task, options)
            self.close(True)
            return
        self.yesButton.enabled = False
        self._workId = self._view.services.coroutineRunner.submit(
            self._view.pack.parse(TaskOptions.fromOptions({**options, "url": url})),
            done=lambda task: self._onParsed(task, options), failed=self._onFailed)

    def _onParsed(self, task, options):
        self._workId = ""
        self.yesButton.enabled = True
        received = self._task.currentSnapshot()[2]
        if received and not self._task.canReuseProgress(task):
            self._confirm = MessageBox(tr("LiveEditDialog", "确认更换链接"),
                tr("LiveEditDialog", "新链接与原链接的内容不一致，将清除已下载的 {0} 数据，是否继续？").format(
                    toReadableSize(received)), self._host)
            self._confirm.accepted.connect(lambda: self._apply(task, options))
            self._confirm.open()
        else:
            self._apply(task, options)

    def _apply(self, task, options):
        self._view.services.taskService.edit(self._task, options, newTask=task)
        self.close(True)

    def _onFailed(self, error):
        self._workId = ""
        self.yesButton.enabled = True
        self.errorText.text = toLocalizedError(toTaskError(error))

    def close(self, isAccepted):
        if self._workId:
            self._view.services.coroutineRunner.cancel(self._workId)
            self._workId = ""
        for card in self.cards:
            if hasattr(card, "dispose"):
                card.dispose()
        super().close(isAccepted)
