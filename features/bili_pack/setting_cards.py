import io

import qrcode
from qrcode.image.pure import PyPNGImage
from bkit import ui

from app.i18n import tr
from app.platform.shell import openUrl
from app.ui.components.account import CookieCard
from app.ui.components.message_box import MessageBoxBase
from .account import toCookie, QR_GOT_URL, QR_LOGIN_SUCCESS, QR_SCANNED, QR_UNSCANNED, QR_EXPIRED


class ScanLoginDialog(MessageBoxBase):
    def __init__(self, account, host):
        super().__init__(host)
        self.account = account
        self._loginUrl = ""
        self.dialog.set_title(tr("ScanLoginDialog", "扫码登录"))
        self.image = ui.Image()
        self.image.set_size(240, 240)
        self.status = ui.Text(tr("ScanLoginDialog", "正在获取二维码..."))
        self.viewLayout.append_child(self.image)
        self.viewLayout.append_child(self.status)
        self.viewLayout.append_child(ui.Button(tr("ScanLoginDialog", "刷新二维码"), account.startQrLogin))
        self.viewLayout.append_child(ui.Button(tr("ScanLoginDialog", "打开登录链接"), self._onOpenUrl))
        self.account.qrStateChanged.connect(self._onQrState)

    def open(self):
        super().open()
        self.account.startQrLogin()

    def close(self, isAccepted):
        self.account.cancelQrLogin()
        self.account.qrStateChanged.disconnect(self._onQrState)
        super().close(isAccepted)

    def _onOpenUrl(self):
        if self._loginUrl:
            openUrl(self._loginUrl)

    def _onQrState(self, status, message):
        if status == QR_GOT_URL:
            self._loginUrl = message
            output = io.BytesIO()
            qrcode.make(message, image_factory=PyPNGImage).save(output)
            self.image.painter = ui.Painter.decode(output.getvalue())
        elif status == QR_LOGIN_SUCCESS:
            self.close(True)
        self.status.text = tr("ScanLoginDialog", {
            QR_GOT_URL: "请使用哔哩哔哩客户端扫码", QR_UNSCANNED: "等待扫码",
            QR_SCANNED: "二维码已扫码，请在手机端确认登录", QR_EXPIRED: "二维码已失效，请刷新二维码",
            QR_LOGIN_SUCCESS: "登录成功",
        }.get(status, message))


class BilibiliLoginSettingCard(CookieCard):
    def __init__(self, account):
        self.account = account
        super().__init__(tr("BilibiliLoginSettingCard", "账号登录"), lambda: account.cookie,
                          lambda value: account.setCookie(toCookie(value)), account.logout)
        self.actions.insert_child(0, ui.Button(tr("BilibiliLoginSettingCard", "扫码登录"), self._onScan))
        account.accountChanged.connect(self.refresh)

    def _onScan(self):
        self._dialog = ScanLoginDialog(self.account, self)
        self._dialog.open()

    def refresh(self, *_):
        self.setContent(tr("BilibiliLoginSettingCard", "状态：未登录") if not self.account.isLoggedIn else
                        f"{self.account.username} · UID {self.account.mid} · {self.account.vip}")
