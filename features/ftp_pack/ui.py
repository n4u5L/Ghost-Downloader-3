from app.ui.pack import PackUi as BasePackUi
from app.i18n import tr
from .config import ftpConfig


class PackUi(BasePackUi):
    def settings(self):
        return []
