from app.i18n import tr
from app.models.task import TaskStatus
from app.ui.cards.task_cards import TaskCard


class BilibiliTaskCard(TaskCard):
    def _onSelectFilesClicked(self):
        from .cards import buildSelection

        self._fileSelectDialog = buildSelection(self._task, self, shouldUpdate=False)
        self._fileSelectDialog.accepted.connect(lambda: self._taskService.updateSelection(
            self._task, {file.index for file in self._task.files or [] if file.selected}))
        self._fileSelectDialog.open()

    def _refreshInfo(self, task, speed, received):
        super()._refreshInfo(task, speed, received)
        if task.isSeason and task.status in {TaskStatus.RUNNING, TaskStatus.WAITING, TaskStatus.COMPLETED}:
            self._setStatus(tr("TaskCard", "{0}/{1} 集").format(*task.seasonCounts()))
