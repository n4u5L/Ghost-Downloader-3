from app.ui.pack import PackUi as BasePackUi
from app.i18n import tr
from .config import bilibiliConfig, QUALITY_LABELS


LABELS = {'defaultQuality': ('默认画质', '选择偏好的视频画质'),
 'alternativeQuality': ('画质不可用时', '当选择的画质不可用时的替代策略'),
 'shouldIncludeHdr': ('HDR', '请求 HDR 视频流（需要大会员）'),
 'shouldIncludeDolby': ('杜比全景声/视界', '请求杜比全景声和杜比视界（需要大会员）')}


class PackUi(BasePackUi):
    def draftCard(self, task, probeConflict):
        from .draft_cards import BilibiliDraftCard
        return BilibiliDraftCard(task, self.services.categoryService, probeConflict, self.services)

    def taskCard(self, task, copyUrls, openDrawer):
        from .task_cards import BilibiliTaskCard
        return BilibiliTaskCard(task, self.services.taskService, self.services.categoryService, copyUrls, openDrawer)

    def settings(self):
        from app.ui.components.pack_controls import buildConfigGroup
        labels = {name: (tr('BilibiliConfig', label), tr('BilibiliConfig', description)) for name, (label, description) in LABELS.items()}
        group = buildConfigGroup(bilibiliConfig, tr('BilibiliConfig', 'Bilibili 下载'), 'bili_pack',
                                 labels, self.services.uiLoop.post, exclude=('userCookie',),
                                 choices={"defaultQuality": QUALITY_LABELS,
                                          "alternativeQuality": [tr("BilibiliConfig", "最高画质"), tr("BilibiliConfig", "最低画质")]})
        group.addSettingCardFactory(self._buildLoginCard)
        return [group]

    def _buildLoginCard(self):
        from .setting_cards import BilibiliLoginSettingCard
        return BilibiliLoginSettingCard(self.pack.account)
