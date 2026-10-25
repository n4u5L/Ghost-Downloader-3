from __future__ import annotations

from app.config.cfg import BoolValidator, ConfigItem, OptionsConfigItem, OptionsValidator
from app.models.pack import PackConfig

QUALITY_VALUES = [16, 32, 64, 80, 112, 116, 120, 125, 126, 127, 128]
QUALITY_LABELS = [
    "240P", "360P", "480P", "720P", "720P60", "1080P",
    "1080P+", "1080P60", "4K", "HDR", "杜比视界",
]


class BilibiliConfig(PackConfig):
    userCookie = ConfigItem("Bilibili", "UserCookie", "")
    defaultQuality = OptionsConfigItem(
        "Bilibili", "DefaultQuality", 80, OptionsValidator(QUALITY_VALUES),
    )
    alternativeQuality = OptionsConfigItem(
        "Bilibili", "AlternativeQuality", "max", OptionsValidator(["max", "min"]),
    )
    shouldIncludeHdr = ConfigItem("Bilibili", "ParseHDR", False, BoolValidator())
    shouldIncludeDolby = ConfigItem("Bilibili", "ParseDolby", False, BoolValidator())



bilibiliConfig = BilibiliConfig()
