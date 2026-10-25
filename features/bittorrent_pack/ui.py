from app.ui.pack import PackUi as BasePackUi
from app.i18n import tr
from .config import bittorrentConfig


LABELS = {'listenPort': ('监听端口', '0 表示交给系统自动分配可用端口'),
 'metadataTimeout': ('元数据超时', '解析 magnet 链接时等待元数据的最长时间'),
 'maxConnections': ('连接数上限', '单个 BT 任务对应 session 的最大连接数'),
 'maxUploadSpeed': ('上传限速', '0 表示不限速，单位为 session 级别的 KB/s'),
 'seedingRatioLimit': ('自动停止做种分享率', '0 表示不按分享率自动停止，100% 表示分享率 1.0'),
 'seedingTimeLimit': ('自动停止做种时长', '0 表示不按做种时长自动停止'),
 'storageMode': ('文件分配模式', '稀疏分配更省磁盘写入，预分配更容易提前暴露空间不足'),
 'saveMagnetFile': ('保存 Magnet 种子文件', '下载 magnet 链接时额外保存 .torrent 文件'),
 'enableSequentialDownload': ('顺序下载', '按文件顺序下载，适合边下边看但通常会影响整体效率'),
 'enableDht': ('启用 DHT', '允许通过 DHT 网络发现 peers'),
 'enableLsd': ('启用 LSD', '在局域网中广播并发现同一 torrent 的 peers'),
 'enableWebTrackers': ('附加 Tracker 列表', '把 Tracker 列表合并到新建的 BT 任务中'),
 'autoRefreshWebTrackers': ('自动更新订阅', '每天在后台更新一次 Tracker 列表')}


class PackUi(BasePackUi):
    def taskCard(self, task, copyUrls, openDrawer):
        from .cards import BTTaskCard
        return BTTaskCard(task, self.services.taskService, self.services.categoryService, copyUrls, openDrawer)

    def details(self, task):
        from .detail_cards import TorrentCard, TrackerCard, PeerCard
        return [card(task, self.services.coroutineRunner) for card in (TorrentCard, TrackerCard, PeerCard)]

    def settings(self):
        from app.ui.components.pack_controls import buildConfigGroup
        labels = {name: (tr('BitTorrentConfig', label), tr('BitTorrentConfig', description)) for name, (label, description) in LABELS.items()}
        group = buildConfigGroup(bittorrentConfig, tr('BitTorrentConfig', 'BitTorrent 下载'), 'bittorrent_pack',
                                 labels, self.services.uiLoop.post, exclude=('webTrackerSources', 'webTrackerCustomList'),
                                 units={"maxUploadSpeed": (1024, "KB/s"), "metadataTimeout": (1, "s"),
                                        "seedingRatioLimit": (1, "%"), "seedingTimeLimit": (1, "min")})
        from app.ui.components.pack_controls import BootstrapListCard
        from .trackers import trackerList
        group.addSettingCardFactory(lambda: BootstrapListCard(tr("BitTorrentConfig", "Tracker 列表"), trackerList,
            bittorrentConfig.webTrackerSources, self.services.coroutineRunner,
            custom=bittorrentConfig.webTrackerCustomList, probe=bittorrentConfig._probeDhtText))
        return [group]
