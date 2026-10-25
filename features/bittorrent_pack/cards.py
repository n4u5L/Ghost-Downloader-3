from app.format import toReadableSize, toReadableTime
from app.i18n import tr
from app.models.task import TaskStatus
from app.ui.cards.task_cards import TaskCard

BT_STATE_LABELS = {
    "checking_files": "校验已有文件", "checking_resume_data": "检查续传状态",
    "downloading_metadata": "获取元数据", "downloading": "下载中", "finished": "下载完成",
    "seeding": "做种中", "allocating": "分配文件中", "queued_for_checking": "等待校验",
    "paused_downloading": "已暂停下载",
}


class BTTaskCard(TaskCard):
    def _refreshInfo(self, task, speed, received):
        super()._refreshInfo(task, speed, received)
        if task.status == TaskStatus.RUNNING or task.isSeeding:
            parts = [tr("BTTaskCard", BT_STATE_LABELS.get(task.stateText, task.stateText))]
            parts.append(f"↑ {toReadableSize(task.uploadRate)}/s")
            parts.append(f"{task.peerCount}/{task.totalPeerCount} Peers")
            if task.isSeeding:
                parts.append(f"{task.shareRatioPercent / 100:.2f} · {toReadableTime(task.seedingTimeSeconds)}")
            self._setStatus(" · ".join(part for part in parts if part))
