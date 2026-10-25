from base64 import b64decode
from datetime import datetime

from app.format import toReadableSize, toReadableTime
from app.i18n import tr
from app.ui.components.detail_table import DetailTable
from app.ui.dialogs.task_drawer import DetailCard, InfoRow
from .session import btSession
from .swarm import toTorrentMeta


class TorrentCard(DetailCard):
    def __init__(self, task, runner):
        super().__init__(tr("TorrentCard", "种子"))
        self.task, self.runner, self._isBusy = task, runner, False
        self._rows = {}
        meta = toTorrentMeta(b64decode(task.torrentData)) if task.torrentData else None
        if meta:
            values = [
                ("Info Hash v1", meta.infoHashV1), ("Info Hash v2", meta.infoHashV2),
                ("注释", meta.comment), ("创建者", meta.creator),
                ("创建时间", datetime.fromtimestamp(meta.createdAt).isoformat(" ") if meta.createdAt else ""),
                ("分块", f"{meta.pieceCount} × {toReadableSize(meta.pieceSize)}" + (" · Private" if meta.isPrivate else "")),
            ]
            for caption, value in values:
                if value:
                    self._set(caption, value)

    def _set(self, caption, value):
        if caption not in self._rows:
            info = InfoRow(tr("TorrentCard", caption))
            info.addCopyButton()
            self._rows[caption] = info
            self.bodyLayout.append_child(info)
        self._rows[caption].setValue(str(value))

    def refresh(self):
        self._set("分享率", f"{self.task.shareRatioPercent / 100:.2f} · {toReadableTime(self.task.seedingTimeSeconds)}")
        if not self._isBusy:
            self._isBusy = True
            async def fetch():
                return btSession.swarmInfo(self.task.taskId)
            self.runner.submit(fetch(), done=self._onSwarm, failed=self._onFailed)
        return True

    def _onSwarm(self, swarm):
        self._isBusy = False
        if not swarm:
            return
        for caption, value in [
            ("做种", f"{swarm.seeds}/{swarm.totalSeeds}"), ("下载者", f"{swarm.peers}/{swarm.totalPeers}"),
            ("可用副本", f"{swarm.distributedCopies:.2f}"), ("已上传", toReadableSize(swarm.totalUpload)),
            ("已下载", toReadableSize(swarm.totalDownload)),
            ("下次汇报", toReadableTime(max(0, swarm.nextAnnounceSeconds))),
        ]:
            self._set(caption, value)

    def _onFailed(self, error):
        self._isBusy = False


class TrackerCard(DetailCard):
    def __init__(self, task, runner):
        super().__init__("Tracker")
        self.task, self.runner, self._isBusy = task, runner, False
        self.table = DetailTable([tr("TrackerCard", value) for value in ("地址", "状态", "做种", "下载", "Peer")])
        self.bodyLayout.append_child(self.table)

    def refresh(self):
        if not self._isBusy:
            self._isBusy = True
            async def fetch():
                return btSession.trackers(self.task.taskId)
            self.runner.submit(fetch(), done=self._onTrackers, failed=self._onFailed)
        return True

    def _onTrackers(self, trackers):
        self._isBusy = False
        self.table.setRows([(item.url, f"{item.status.name}: {item.message}", item.seeds, item.leeches, item.peers)
                            for item in trackers])

    def _onFailed(self, error):
        self._isBusy = False


class PeerCard(DetailCard):
    def __init__(self, task, runner):
        super().__init__("Peer")
        self.task, self.runner, self._isBusy = task, runner, False
        self.table = DetailTable([tr("PeerCard", value) for value in ("地址", "客户端", "下载", "上传", "进度", "标志")])
        self.bodyLayout.append_child(self.table)

    def refresh(self):
        if not self._isBusy:
            self._isBusy = True
            async def fetch():
                return btSession.peers(self.task.taskId)
            self.runner.submit(fetch(), done=self._onPeers, failed=self._onFailed)
        return True

    def _onPeers(self, peers):
        self._isBusy = False
        self.table.setRows([(f"{item.host}:{item.port}", item.client, toReadableSize(item.downloadRate) + "/s",
                            toReadableSize(item.uploadRate) + "/s", f"{item.progress * 100:.1f}%", item.flags)
                           for item in sorted(peers, key=lambda peer: peer.downloadRate, reverse=True)])

    def _onFailed(self, error):
        self._isBusy = False
