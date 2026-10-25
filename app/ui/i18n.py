"""bkit 界面的翻译：直接读取 app/assets/i18n 下的 .ts，沿用 Qt 界面的 context，现有译文因此可复用。"""
from __future__ import annotations

import ctypes
import xml.etree.ElementTree as ElementTree
from pathlib import Path

from loguru import logger

from app.config.paths import EXECUTABLE_DIR

I18N_DIR = EXECUTABLE_DIR / "app" / "assets" / "i18n"
SOURCE_LOCALE = "zh_CN"
FALLBACK_LOCALE = "en_US"
LOCALE_NAME_MAX_LENGTH = 85
# 没有独立译文的语言借用相近的
LOCALE_ALIASES = {"yue_HK": "zh_HK"}


class Translator:
    def __init__(self) -> None:
        self._translations: dict[tuple[str, str], str] = {}

    def load(self, localeName: str) -> None:
        if localeName == "Auto":
            localeName = systemLocaleName()
        localeName = LOCALE_ALIASES.get(localeName, localeName)
        self._translations = {}
        if localeName == SOURCE_LOCALE:
            return
        path = I18N_DIR / f"gd3.{localeName}.ts"
        if not path.is_file():
            path = I18N_DIR / f"gd3.{FALLBACK_LOCALE}.ts"
        try:
            self._translations = parseTs(path)
        except (OSError, ElementTree.ParseError) as e:
            logger.opt(exception=e).warning("无法读取翻译 {}", path)

    def tr(self, context: str, text: str) -> str:
        return self._translations.get((context, text)) or text


def parseTs(path: Path) -> dict[tuple[str, str], str]:
    translations: dict[tuple[str, str], str] = {}
    for context in ElementTree.parse(path).getroot().iter("context"):
        name = context.findtext("name") or ""
        for message in context.iter("message"):
            translation = message.find("translation")
            if translation is None or translation.get("type") in ("vanished", "obsolete"):
                continue
            if translation.text:
                translations[(name, message.findtext("source") or "")] = translation.text
    return translations


def systemLocaleName() -> str:
    buffer = ctypes.create_unicode_buffer(LOCALE_NAME_MAX_LENGTH)
    if not ctypes.windll.kernel32.GetUserDefaultLocaleName(buffer, LOCALE_NAME_MAX_LENGTH):
        return FALLBACK_LOCALE
    language, _, region = buffer.value.partition("-")
    # zh-Hant-TW 之类带书写系统的名字只取首尾
    region = region.rpartition("-")[2]
    return f"{language}_{region}" if region else language


# 与 QCoreApplication.translate 一样是进程级的：界面各处直接调用 tr()，不逐层传递
translator = Translator()
tr = translator.tr


def toLocalizedError(error) -> str:
    text = tr("TaskErrors", error.message)
    return text.format_map(error.params) if error.params else text
