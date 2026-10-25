from app.i18n import tr
from app.ui.components.account import CookieCard
from .config import loadCookieHeader, saveCookies, clearCookies


class CookieSettingCard(CookieCard):
    def __init__(self):
        super().__init__(tr("YtDlpConfig", "YouTube Cookie"), loadCookieHeader, saveCookies, clearCookies)
