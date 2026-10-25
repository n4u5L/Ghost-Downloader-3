from app.ui.pack import PackUi as BasePackUi
from app.i18n import tr
from .config import ed2kConfig


LABELS = {'installFolder': ('Kelpie 安装目录', ''),
 'shouldRefreshLists': ('自动更新订阅', '每天在后台更新一次服务器列表和 KAD 节点列表'),
 'enableKad': ('启用 KAD', '通过 KAD 网络查找来源，关闭后仅使用 eD2k 服务器'),
 'enableUpnp': ('启用 UPnP', '自动配置路由器端口转发'),
 'listenPort': ('监听端口', '0 表示交给系统自动分配可用端口'),
 'uploadRateLimit': ('上传限速', '0 表示不限速。上传越多积分越高，在别人的队列里排得越靠前，自己下载也越快'),
 'seedingRatioLimit': ('自动停止做种分享率', '0 表示不按分享率自动停止，100% 表示分享率 1.0'),
 'seedingTimeLimit': ('自动停止做种时长', '0 表示不按做种时长自动停止')}


class PackUi(BasePackUi):
    def taskCard(self, task, copyUrls, openDrawer):
        from .cards import ED2kTaskCard
        return ED2kTaskCard(task, self.services.taskService, self.services.categoryService, copyUrls, openDrawer)

    def details(self, task):
        from .detail_cards import ED2kCard, ED2kSourceCard
        return [ED2kCard(task), ED2kSourceCard(task)]

    def settings(self):
        from app.ui.components.pack_controls import buildConfigGroup
        labels = {name: (tr('ED2kConfig', label), tr('ED2kConfig', description)) for name, (label, description) in LABELS.items()}
        group = buildConfigGroup(ed2kConfig, tr('ED2kConfig', 'eD2k 下载'), 'ed2k_pack',
                                 labels, self.services.uiLoop.post, exclude=('serverListSources', 'nodeListSources'),
                                 units={"uploadRateLimit": (1024, "KB/s"), "seedingRatioLimit": (1, "%"),
                                        "seedingTimeLimit": (1, "min")})
        from app.ui.components.pack_controls import BootstrapListCard
        from .lists import serverList, nodeList
        group.addSettingCardFactory(lambda: BootstrapListCard(tr("ED2kConfig", "服务器列表"), serverList,
            ed2kConfig.serverListSources, self.services.coroutineRunner, probe=ed2kConfig._probeServerText))
        group.addSettingCardFactory(lambda: BootstrapListCard(tr("ED2kConfig", "KAD 节点列表"), nodeList,
            ed2kConfig.nodeListSources, self.services.coroutineRunner, probe=ed2kConfig._probeKadText))
        group.addSettingCardFactory(self._buildStopCard)
        return [group]

    def _buildStopCard(self):
        from .setting_cards import KelpieStopCard
        from .session import ed2kSession
        return KelpieStopCard(ed2kSession, self.services.coroutineRunner)
