"""Material Symbols 图标：Outlined、opsz 24、weight 400，
取自 google/material-design-icons@10ecc147，Apache-2.0（app/assets/icons/LICENSE）。

图标是单色 SVG：Icon 用主题的内容色着色，所以浅色、深色主题共用一份文件。
"""
from __future__ import annotations

from collections.abc import Callable
from functools import cache
from pathlib import Path

from bkit import ui

from app.config.paths import EXECUTABLE_DIR

ICON_DIR = EXECUTABLE_DIR / "app" / "assets" / "icons"
ICON_SIZE = 24

# 分类的 icon 字段沿用 Qt 界面的 FluentIcon 名字，已保存的分类因此不用迁移
CATEGORY_ICONS = {
    "DOCUMENT": "description", "MUSIC": "music_note", "VIDEO": "videocam", "ZIP_FOLDER": "folder_zip",
    "APPLICATION": "apps", "LIBRARY": "library_books", "ALBUM": "album", "PHOTO": "photo", "MOVIE": "movie",
    "MEDIA": "perm_media", "GAME": "sports_esports", "CODE": "code", "EDUCATION": "school", "LANGUAGE": "language",
    "BRUSH": "brush", "FOLDER": "folder", "CHAT": "subtitles", "MAIL": "mail", "PRINT": "print", "GLOBE": "public",
    "CAMERA": "photo_camera", "IMAGE_EXPORT": "image", "MUSIC_FOLDER": "library_music", "MARKET": "storefront",
    "HELP": "help",
}
# Qt 界面对未知图标名回退到 FluentIcon.TAG
CATEGORY_FALLBACK_ICON = "label"


@cache
def loadIcon(name: str) -> ui.Painter:
    # 一个图标只解码一次：Painter 按绘制尺寸各缓存一份光栅，不同尺寸可共用
    return ui.Painter.load(ICON_DIR / f"{name}.svg")


def buildIcon(name: str, size: float = ICON_SIZE, *, tint: int | None = None) -> ui.Icon:
    # SVG 的固有尺寸是像素，不随缩放变化，显式给出 dp 尺寸
    icon = ui.Icon(loadIcon(name), tint=tint)
    icon.set_size(size)
    return icon


def buildIconButton(
    name: str, tooltip: str, onClick: Callable[[], object] | None = None,
    variant: ui.IconButtonVariant = ui.IconButtonVariant.STANDARD,
) -> tuple[ui.TooltipBox, ui.IconButton]:
    """图标按钮没有文字，由悬停提示说明。返回放进布局的 TooltipBox 和按钮本身。"""
    button = ui.IconButton(loadIcon(name), onClick, variant)
    box = ui.TooltipBox(button)
    box.set_plain_tooltip(tooltip)
    return box, button


def buildButton(
    name: str, text: str, onClick: Callable[[], object] | None = None,
    style: ui.ButtonStyle = ui.ButtonStyle.OUTLINED,
) -> ui.Button:
    """带前导图标的按钮，对应 qfluentwidgets 的 PushButton(icon, text)。"""
    button = ui.Button([buildIcon(name, ui.ButtonDefaults.ICON_SIZE), ui.Spacer(ui.ButtonDefaults.ICON_SPACING),
                        ui.Text(text)], onClick, style)
    if style == ui.ButtonStyle.TEXT:
        button.set_content_padding(*ui.ButtonDefaults.TEXT_BUTTON_WITH_ICON_CONTENT_PADDING)
    else:
        button.set_content_padding(*ui.ButtonDefaults.BUTTON_WITH_ICON_CONTENT_PADDING)
    return button


def buildImage(path: Path, size: tuple[float, float]) -> ui.Node:
    """按 size（dp）等比显示的图片；文件读不出时是同样大小的空白。"""
    try:
        image = ui.Image(ui.Painter.load(path))
    except (OSError, ValueError):
        return ui.Spacer(*size)
    image.set_size(*size)
    image.content_scale = ui.ContentScale.FIT
    return image


def toCategoryIcon(fluentName: str) -> str:
    return CATEGORY_ICONS.get(fluentName, CATEGORY_FALLBACK_ICON)
