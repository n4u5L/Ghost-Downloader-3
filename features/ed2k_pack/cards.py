import time

from app.format import toReadableSize, toReadableTime
from app.i18n import tr
from app.models.task import TaskStatus
from app.ui.cards.task_cards import TaskCard
from app.ui.theme import statusColor
from .session import ed2kSession, toHeldMinutes


def toHeldText(progress, now):
    minutes = toHeldMinutes(progress, now)
    if minutes is None:
        return None
    wait = tr("ED2kTaskCard", "不到 1 分钟") if not minutes else tr("ED2kTaskCard", "约 {0} 分钟").format(minutes)
    return tr("ED2kTaskCard", "{0} 个来源{1}后恢复").format(progress.heldSources, wait)


class ED2kTaskCard(TaskCard):
    def _refreshInfo(self, task, speed, received):
        super()._refreshInfo(task, speed, received)
        progress = ed2kSession.progressOf(task)
        held = toHeldText(progress, int(time.time() * 1000))
        if held and task.status == TaskStatus.RUNNING:
            self._setStatus(held)
            self.statusLabel.setTextColor(statusColor("warning"))
        elif progress:
            self._setStatus(f"{progress.activePeers}/{progress.peers} · ↑ {toReadableSize(progress.uploadRate)}/s")
        if task.isSeeding:
            self._setStatus(tr("ED2kTaskCard", "做种中") +
                            f" · {task.shareRatioPercent / 100:.2f} · {toReadableTime(task.seedingTimeSeconds)}")
