from app.ui.pack import PackUi as BasePackUi
from app.i18n import tr
from .config import githubConfig


LABELS = {'enabled': ('启用 GitHub 加速', '经代理站下载 GitHub 文件，不可用时自动切换其他站点或直连')}


class PackUi(BasePackUi):
    def settings(self):
        from app.ui.components.pack_controls import buildConfigGroup
        labels = {name: (tr('GitHubConfig', label), tr('GitHubConfig', description)) for name, (label, description) in LABELS.items()}
        group = buildConfigGroup(githubConfig, tr('GitHubConfig', 'GitHub 加速'), 'github_pack',
                                 labels, self.services.uiLoop.post, exclude=('selectedSite', 'customSite'))
        from .setting_cards import GitHubProxySiteCard
        group.addSettingCardFactory(lambda: GitHubProxySiteCard(self.services.coroutineRunner))
        return [group]
