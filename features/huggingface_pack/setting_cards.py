from bkit import ui

from app.i18n import tr
from app.platform.shell import openUrl
from app.ui.components.proxy_site import ProxySiteCard
from app.ui.components.setting_cards import LineEditSettingCard
from .config import huggingFaceConfig, HF_PROXY_SITES, CUSTOM_SITE_KEY, probeProxyLatencies, TOKEN_URL


class HuggingFaceProxySiteCard(ProxySiteCard):
    def __init__(self, runner):
        super().__init__(tr("HuggingFaceProxySiteCard", "镜像站"), huggingFaceConfig, HF_PROXY_SITES,
                          CUSTOM_SITE_KEY, runner, probeProxyLatencies)


class HuggingFaceTokenCard(LineEditSettingCard):
    def __init__(self, post):
        super().__init__("security", tr("HuggingFaceTokenCard", "Access Token"), "",
                          huggingFaceConfig.accessToken, post, isPassword=True)
        self.vBoxLayout.append_child(ui.Button(tr("HuggingFaceTokenCard", "获取 Token"), lambda: openUrl(TOKEN_URL)))
