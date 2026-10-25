import time

from app.format import toReadableSize, toReadableTime
from app.i18n import tr
from app.ui.components.detail_table import DetailTable
from app.ui.dialogs.task_drawer import DetailCard, InfoRow
from .cards import toHeldText
from .kelpie import Link
from .session import ed2kSession


class ED2kCard(DetailCard):
    def __init__(self, task):
        super().__init__("eD2k")
        self.task = task
        self._rows = {}
        self._set("文件哈希", Link.parse(task.url).hash)
        aich = next((field[2:] for field in task.url.split("|") if field.startswith("h=")), "")
        if aich:
            self._set("AICH 根哈希", aich)
        self._set("分块", f"{-(-task.fileSize // 9728000)} × {toReadableSize(9728000)}")

    def _set(self, caption, value):
        if caption not in self._rows:
            info = InfoRow(tr("ED2kCard", caption))
            info.addCopyButton()
            self._rows[caption] = info
            self.bodyLayout.append_child(info)
        self._rows[caption].setValue(str(value))

    def refresh(self):
        progress = ed2kSession.progressOf(self.task)
        if progress:
            self._set("速度", f"↓ {toReadableSize(progress.downloadRate)}/s · ↑ {toReadableSize(progress.uploadRate)}/s")
            self._set("来源", f"{progress.activePeers}/{progress.peers}")
            self._set("暂缓", toHeldText(progress, int(time.time() * 1000)) or "—")
        self._set("已上传", toReadableSize(self.task.uploadedBytes))
        self._set("分享率", f"{self.task.shareRatioPercent / 100:.2f} · {toReadableTime(self.task.seedingTimeSeconds)}")
        return True


class ED2kSourceCard(DetailCard):
    def __init__(self, task):
        super().__init__(tr("ED2kSourceCard", "来源"))
        self.task = task
        self.table = DetailTable([tr("ED2kSourceCard", value) for value in ("地址", "客户端", "状态", "下载", "渠道")])
        self.bodyLayout.append_child(self.table)

    def refresh(self):
        progress = ed2kSession.progressOf(self.task)
        statuses = {"transferring": "传输中", "queued": "排队", "connecting": "连接中", "held": "暂缓"}
        channels = {"link": "链接", "server": "服务器", "kad": "KAD", "exchange": "来源交换", "incoming": "对方连入"}
        self.table.setRows([(source.address, source.software,
                            tr("ED2kSourceCard", statuses.get(source.status, source.status)) +
                            (f" #{source.rank}" if source.rank > 0 else ""),
                            toReadableSize(source.downloadRate) + "/s",
                            tr("ED2kSourceCard", channels.get(source.channel, source.channel)))
                           for source in progress.sources] if progress else [])
        return True
