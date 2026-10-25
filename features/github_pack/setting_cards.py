from app.i18n import tr
from app.ui.components.proxy_site import ProxySiteCard
from .config import githubConfig, GITHUB_PROXY_SITES, CUSTOM_SITE_KEY, AUTO_SITE_KEY
from .probe import probeProxyLatencies


class GitHubProxySiteCard(ProxySiteCard):
    def __init__(self, runner):
        super().__init__(tr("GitHubProxySiteCard", "代理站"), githubConfig, GITHUB_PROXY_SITES,
                          CUSTOM_SITE_KEY, runner, probeProxyLatencies, autoKey=AUTO_SITE_KEY)
