"""浏览器扩展解包后的安装引导。Qt 界面的演示动画是 Qt 资源里的动图，这里显示同名的静态图片。"""
from __future__ import annotations

from pathlib import Path

from bkit import ui

from app.config.paths import EXECUTABLE_DIR
from app.platform.browser import openChromiumUrl
from app.platform.shell import revealInFolder, setClipboardText
from app.ui.components.message_box import MessageBoxBase
from app.i18n import tr
from app.ui.icons import buildImage
from app.ui.layout import row, text

EXTENSIONS_URL = "chrome://extensions"
PREVIEW_PATH = EXECUTABLE_DIR / "app" / "assets" / "install_chrome_extension_guidance.png"
PREVIEW_SIZE = (720, 405)
WIDTH = PREVIEW_SIZE[0] + 48


def T(text: str) -> str:
    return tr("ExtensionInstallDialog", text)


class ExtensionInstallDialog(MessageBoxBase):

    def __init__(self, path: Path, host: ui.Node) -> None:
        super().__init__(host)
        self._path = path
        self._initWidget()
        self._initLayout()

    def _initWidget(self) -> None:
        self.dialog.set_title(T("扩展已解包，按以下步骤安装"))
        self.dialog.platform_default_width = WIDTH
        self.yesButton.text = T("打开扩展页面并定位目录")
        self.yesButton.set_style(ui.ButtonStyle.FILLED)
        self.cancelButton.text = T("关闭")
        self.hintLabel = text(maxLines=2)

    def _initLayout(self) -> None:
        self.viewLayout.append_child(buildImage(PREVIEW_PATH, PREVIEW_SIZE))
        steps = [
            T("在浏览器中打开 {}").format(EXTENSIONS_URL),
            T("开启 {}").format(T("开发者模式")),
            T("将 {} 拖入浏览器窗口").format(T("扩展文件夹")),
            T("启用扩展"),
            T("打开 {}，点击 {}").format(T("扩展弹窗"), T("自动配对")),
        ]
        for index, step in enumerate(steps, 1):
            self.viewLayout.append_child(row(ui.Badge(str(index)), text(step, maxLines=2), spacing=12))
        self.viewLayout.append_child(self.hintLabel)

    def _onYesClicked(self) -> None:
        # 与 Qt 界面一样，打开扩展页后对话框留着，方便照着步骤操作
        revealInFolder(self._path)
        if not openChromiumUrl(EXTENSIONS_URL):
            setClipboardText(EXTENSIONS_URL)
            self.hintLabel.text = f"{T('请手动打开浏览器')}：{T('chrome://extensions 已复制到剪贴板，请粘贴到地址栏')}"
