from __future__ import annotations

import sys
from pathlib import Path
from typing import TYPE_CHECKING

from app.config.cfg import (
    BoolValidator, ConfigItem, RangeConfigItem, RangeValidator, StringListValidator, proxy,
)
from app.i18n import N

from app.config.paths import APP_DATA_DIR
from app.models.pack import BinaryRuntime, PackConfig
from app.platform.android import IS_ANDROID, nativeLibraryDir
from app.platform.arch import MACHINE_ARCH
from app.install import installFile
from app.platform.filesystem import findExecutable
from app.sources import Repo, fetchLatestRelease, fetchReleaseAsset

from .kelpie import PROXY_SCHEMES


KELPIE_REPO = Repo("XiaoYouChR/Kelpie", mirrors={"gitcode": "XiaoYouChR/Kelpie"})
DEFAULT_SERVER_LIST_SOURCES = [
    "https://upd.emule-security.org/server.met",
    "https://shortypower.org/server.met",
    "http://www.gruk.org/server.met",
]
DEFAULT_NODE_LIST_SOURCES = ["https://upd.emule-security.org/nodes.dat"]


class ED2kConfig(PackConfig):
    associateUriSchemes = ConfigItem("ED2k", "AssociateUriSchemes", False, BoolValidator())
    installFolder = ConfigItem("ED2k", "InstallFolder", f"{APP_DATA_DIR}/kelpie")
    enableKad = ConfigItem("ED2k", "EnableKad", True, BoolValidator())
    enableUpnp = ConfigItem("ED2k", "EnableUPnP", True, BoolValidator())
    listenPort = RangeConfigItem("ED2k", "ListenPort", 0, RangeValidator(0, 65535), restart=True)
    uploadRateLimit = RangeConfigItem("ED2k", "UploadRateLimit", 0, RangeValidator(0, 1024 * 1024 * 100))
    serverListSources = ConfigItem(
        "ED2k", "ServerListSources", DEFAULT_SERVER_LIST_SOURCES, StringListValidator(), restart=True,
    )
    nodeListSources = ConfigItem(
        "ED2k", "NodeListSources", DEFAULT_NODE_LIST_SOURCES, StringListValidator(), restart=True,
    )
    shouldRefreshLists = ConfigItem("ED2k", "ShouldRefreshLists", True, BoolValidator())
    seedingRatioLimit = RangeConfigItem("ED2k", "SeedRatioLimitPercent", 0, RangeValidator(0, 10000))
    seedingTimeLimit = RangeConfigItem("ED2k", "SharingTimeLimitMinutes", 0, RangeValidator(0, 43200))


    async def _probeServerText(self) -> tuple[str, dict]:
        from .session import ed2kSession
        network = ed2kSession.network
        if network is None:
            return N("BootstrapList", "未运行"), {}
        if network.proxyIssue == "unreachable":
            return N("BootstrapList", "无法连接代理"), {}
        if not network.isServerConnected:
            return N("BootstrapList", "未连接服务器"), {}
        if network.isHighId:
            return N("BootstrapList", "已连接服务器（HighID）"), {}
        if proxy(PROXY_SCHEMES):
            return N("BootstrapList", "已连接服务器（LowID，经代理连接时无法获得 HighID）"), {}
        if network.isBehindCarrierNat:
            return N("BootstrapList", "已连接服务器（LowID，运营商 NAT，无法获得 HighID）"), {}
        return N("BootstrapList", "已连接服务器（LowID，开启 UPnP 或在路由器转发监听端口可获得 HighID）"), {}

    async def _probeKadText(self) -> tuple[str, dict]:
        if not self.enableKad.value:
            return N("BootstrapList", "KAD 已关闭"), {}
        from .session import ed2kSession
        network = ed2kSession.network
        if network is None:
            return N("BootstrapList", "未运行"), {}
        if network.proxyIssue == "unreachable":
            return N("BootstrapList", "无法连接代理"), {}
        if network.proxyIssue == "noUdp":
            return N("BootstrapList", "代理不转发 UDP，KAD 无法使用"), {}
        if network.isKadFirewalled:
            return N("BootstrapList", "KAD 节点 {nodes}（处于防火墙后）"), {"nodes": network.kadNodes}
        return N("BootstrapList", "KAD 节点 {nodes}"), {"nodes": network.kadNodes}


ed2kConfig = ED2kConfig()


class KelpieRuntime(BinaryRuntime):
    name = "Kelpie"
    canInstall = not IS_ANDROID
    title = N("BinaryRuntime", "eD2k / eMule")
    description = N("BinaryRuntime", "支持电驴协议，适合下载经典资源")
    icon = "BOOK_SHELF"

    def installFolder(self) -> Path:
        return Path(ed2kConfig.installFolder.value)

    def path(self) -> str:
        if IS_ANDROID:
            nativeDir = nativeLibraryDir()
            if not nativeDir:
                return ""
            binary = Path(nativeDir) / "libkelpie.so"
            return str(binary) if binary.exists() else ""
        return findExecutable(self.installFolder(), "kelpie")

    async def fetchLatestVersion(self) -> str:
        return (await fetchLatestRelease(KELPIE_REPO)).version

    def installedPaths(self) -> list[Path]:
        return [self.installFolder() / ("kelpie.exe" if sys.platform == "win32" else "kelpie")]

    async def install(self, version: str, onProgress) -> None:
        tag = version or await self.fetchLatestVersion()
        binary = self.installedPaths()[0]
        downloadPath = binary.with_name(f"{binary.name}.download")
        try:
            await fetchReleaseAsset(KELPIE_REPO, tag, buildAssetName(), downloadPath, onProgress)
            downloadPath.chmod(0o755)
            installFile(downloadPath, binary)
        finally:
            downloadPath.unlink(missing_ok=True)


def buildAssetName() -> str:
    arch = "arm64" if MACHINE_ARCH == "arm64" else "amd64"
    if sys.platform == "win32":
        return f"kelpie-windows-{arch}.exe"
    elif sys.platform == "darwin":
        return f"kelpie-darwin-{arch}"
    else:
        return f"kelpie-linux-{arch}"


kelpieRuntime = KelpieRuntime()
