"""共享翻译：直接读取 app/assets/i18n 下的 .ts，沿用 Qt 界面的 context，现有译文因此可复用。"""
from __future__ import annotations

import ctypes
import locale
import sys
from collections.abc import Callable
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
        self._translate: Callable[[str, str], str] | None = None

    def set(self, translate: Callable[[str, str], str]) -> None:
        self._translate = translate

    def load(self, localeName: str) -> None:
        self._translate = None
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
        if self._translate is not None:
            return self._translate(context, text) or text
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
    if sys.platform != "win32":
        return locale.getlocale()[0] or FALLBACK_LOCALE
    buffer = ctypes.create_unicode_buffer(LOCALE_NAME_MAX_LENGTH)
    if not ctypes.windll.kernel32.GetUserDefaultLocaleName(buffer, LOCALE_NAME_MAX_LENGTH):
        return FALLBACK_LOCALE
    language, _, region = buffer.value.partition("-")
    # zh-Hant-TW 之类带书写系统的名字只取首尾
    region = region.rpartition("-")[2]
    return f"{language}_{region}" if region else language


translator = Translator()
tr = translator.tr


def toLocalizedError(error) -> str:
    text = tr("TaskErrors", error.message)
    return text.format_map(error.params) if error.params else text


def N(context, text):
    return text


N("TaskErrors", "进程异常退出（{code}）：{detail}")
N("TaskErrors", "发生了意外错误：{detail}")
N("TaskErrors", "压缩包包含不安全路径：{path}")
N("TaskErrors", "压缩包未找到：{path}")
N("TaskErrors", "不支持的压缩格式：{name}")
N("TaskErrors", "解压后未找到可执行文件：{name}")
N("TaskErrors", "无法读取校验文件：{path}")
N("TaskErrors", "无法读取文件：{detail}")
N("TaskErrors", "SHA256 校验失败：期望 {expected}，实际 {actual}")
N("TaskErrors", "下载的文件未找到：{path}")
N("TaskErrors", "无法获取 {name} 的最新 release")
N("TaskErrors", "无法获取 {name}/{branch}/{path}")
N("TaskErrors", "无法下载 {name}/{branch}/{path}")
N("TaskErrors", "无法下载 {name}/{tag}/{asset}")
N("TaskErrors", "无法获取 PyPI 包信息: {package}")
N("TaskErrors", "{name} 未安装，请在设置中安装")

N("TaskErrors", "无法获取版本信息")
N("TaskErrors", "校验失败")
N("TaskErrors", "当前平台无可用更新")
N("TaskErrors", "{path} 已被其他文件占用")
N("TaskErrors", "未获得管理员授权")
N("TaskErrors", "DMG 中未找到 .app")

N("TaskErrors", "端口 {port} 被占用，请更换端口")
N("TaskErrors", "没有权限监听端口 {port}，请更换端口")
N("TaskErrors", "无法监听端口 {port}，详情见日志")
