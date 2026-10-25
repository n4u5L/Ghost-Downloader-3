from app.models.task import TaskStatus
from app.ui.cards.task_cards import TaskCard
from app.ui.icons import loadIcon
from app.i18n import tr


class M3U8TaskCard(TaskCard):
    def _refreshInfo(self, task, speed, received):
        super()._refreshInfo(task, speed, received)
        step = task.steps[0] if task.steps else None
        if step and task.isLive:
            self.etaLabel.setText(f"{step.liveElapsed or '00m00s'} / {step.recordLimit}" if step.recordLimit else step.liveElapsed)
            if task.status == TaskStatus.RUNNING:
                self._setStatus(tr("M3U8LiveTaskCard", "等待中" if step.liveStatus == "Waiting" else "录制中"))
            elif task.status == TaskStatus.COMPLETED:
                self._setStatus(tr("M3U8LiveTaskCard", "录制已结束"))
        self._refreshInfoLayout()

    def _refreshButtons(self, task, checksumProgress):
        super()._refreshButtons(task, checksumProgress)
        if task.isLive and task.status == TaskStatus.RUNNING:
            self.toggleButton.icon = loadIcon("check")
            self.toggleButton.enabled = True

    def _onToggleClicked(self):
        if self._task.isLive and self._task.status == TaskStatus.RUNNING:
            self._task.steps[0].terminate()
            self.toggleButton.enabled = False
        else:
            super()._onToggleClicked()
