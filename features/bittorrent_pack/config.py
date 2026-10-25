from __future__ import annotations

from app.config.cfg import (
    BoolValidator,
    ConfigItem,
    OptionsConfigItem,
    OptionsValidator,
    RangeConfigItem,
    RangeValidator,
)
from app.i18n import N
from app.models.pack import PackConfig

DEFAULT_TRACKER_LIST_SOURCES = [
    "https://trackerslist.com/best.txt",
    "https://cdn.jsdelivr.net/gh/XIU2/TrackersListCollection/best.txt",
    "https://ngosang.github.io/trackerslist/trackers_best.txt",
    "https://newtrackon.com/api/stable",
]


class StringListValidator:
    def validate(self, value) -> bool:
        return isinstance(value, list) and all(isinstance(i, str) for i in value)

    def correct(self, value) -> list:
        if not isinstance(value, list):
            return []
        return [i for i in value if isinstance(i, str)]


class BitTorrentConfig(PackConfig):
    enableDht = ConfigItem("BitTorrent", "EnableDHT", True, BoolValidator())
    enableLsd = ConfigItem("BitTorrent", "EnableLSD", True, BoolValidator())
    enableWebTrackers = ConfigItem("BitTorrent", "EnableWebTrackers", True, BoolValidator())
    autoRefreshWebTrackers = ConfigItem("BitTorrent", "AutoRefreshWebTrackers", True, BoolValidator())
    saveMagnetFile = ConfigItem("BitTorrent", "SaveMagnetTorrentFile", False, BoolValidator())
    seedingRatioLimit = RangeConfigItem("BitTorrent", "SeedRatioLimitPercent", 0, RangeValidator(0, 10000))
    seedingTimeLimit = RangeConfigItem("BitTorrent", "SeedTimeLimitMinutes", 0, RangeValidator(0, 43200))
    maxConnections = RangeConfigItem("BitTorrent", "ConnectionsLimit", 500, RangeValidator(20, 2000))
    maxUploadSpeed = RangeConfigItem("BitTorrent", "UploadRateLimit", 0, RangeValidator(0, 1024 * 1024 * 100))
    listenPort = RangeConfigItem("BitTorrent", "ListenPort", 0, RangeValidator(0, 65535))
    metadataTimeout = RangeConfigItem("BitTorrent", "MetadataTimeout", 60, RangeValidator(5, 300))
    enableSequentialDownload = ConfigItem("BitTorrent", "SequentialDownload", False, BoolValidator())
    storageMode = OptionsConfigItem(
        "BitTorrent", "StorageMode", "sparse", OptionsValidator(["sparse", "allocate"]),
    )
    associateFileTypes = ConfigItem("BitTorrent", "AssociateFileTypes", False, BoolValidator())
    associateUriSchemes = ConfigItem("BitTorrent", "AssociateUriSchemes", False, BoolValidator())
    webTrackerSources = ConfigItem(
        "BitTorrent", "WebTrackerSources", DEFAULT_TRACKER_LIST_SOURCES, StringListValidator(),
    )
    webTrackerCustomList = ConfigItem("BitTorrent", "WebTrackerCustomList", "")


    async def _probeDhtText(self) -> tuple[str, dict]:
        from .session import btSession
        nodes = await btSession.probeDhtNodes()
        return ("", {}) if nodes is None else (N("BootstrapList", "DHT 节点 {nodes}"), {"nodes": nodes})


bittorrentConfig = BitTorrentConfig()
