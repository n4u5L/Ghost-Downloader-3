from app.ui.pack import PackUi as BasePackUi
from app.i18n import tr
from .config import ytDlpConfig


LABELS = {'shouldPreferMp4': ('优先 MP4 格式', '优先选择 H.264/MP4 编码，避免输出 WebM/MKV'),
 'shouldEmbedMetadata': ('嵌入元数据', '下载完成后将标题、作者等信息嵌入文件'),
 'shouldEmbedChapters': ('嵌入章节', '下载完成后将章节标记嵌入文件')}


class PackUi(BasePackUi):
    def options(self, task, isEditing=False):
        if isEditing:
            return []
        from .cards import YouTubeOptions
        return [YouTubeOptions(task, self.services.coroutineRunner, self.services.uiLoop.post,
                                self.services.previewCache)]

    def taskCard(self, task, copyUrls, openDrawer):
        from .cards import YtDlpTaskCard
        return YtDlpTaskCard(task, self.services.taskService, self.services.categoryService, copyUrls, openDrawer)

    def settings(self):
        from app.ui.components.pack_controls import buildConfigGroup
        labels = {name: (tr('YtDlpConfig', label), tr('YtDlpConfig', description)) for name, (label, description) in LABELS.items()}
        group = buildConfigGroup(ytDlpConfig, tr('YtDlpConfig', 'YouTube 下载'), 'yt_dlp_pack',
                                 labels, self.services.uiLoop.post, exclude=())
        from .setting_cards import CookieSettingCard
        group.addSettingCardFactory(CookieSettingCard)
        return [group]
