from __future__ import annotations

import sys
from pathlib import Path

from app.config.cfg import (
    BoolValidator,
    ConfigItem,
    FolderValidator,
    OptionsConfigItem,
    OptionsValidator,
    RangeConfigItem,
    RangeValidator,
)
from app.i18n import N

from app.config.paths import APP_DATA_DIR
from app.install import installArchive
from app.models.pack import BinaryRuntime, PackConfig
from app.platform.android import IS_ANDROID, nativeLibraryDir
from app.platform.arch import MACHINE_ARCH
from app.platform.filesystem import findExecutable
from app.models.task import TaskError
from app.sources import Repo, fetchLatestRelease, fetchReleaseAsset

M3U8_REPO = Repo("nilaoda/N_m3u8DL-RE", mirrors={"gitcode": "XiaoYouChR/N_m3u8DL-RE-mirror"})


class M3U8Config(PackConfig):
    installFolder = ConfigItem("M3U8", "InstallFolder", f"{APP_DATA_DIR}/M3U8DL", FolderValidator())
    associateFileTypes = ConfigItem("M3U8", "AssociateFileTypes", False, BoolValidator())
    outputFormat = OptionsConfigItem("M3U8", "OutputFormat", "mp4", OptionsValidator(["mp4", "mkv"]))
    threadCount = RangeConfigItem("M3U8", "ThreadCount", 8, RangeValidator(1, 64))
    retryCount = RangeConfigItem("M3U8", "RetryCount", 3, RangeValidator(0, 20))
    requestTimeout = RangeConfigItem("M3U8", "RequestTimeout", 100, RangeValidator(5, 600))
    shouldAutoSelect = ConfigItem("M3U8", "AutoSelect", True, BoolValidator())
    shouldConcurrentDownload = ConfigItem("M3U8", "ConcurrentDownload", True, BoolValidator())
    shouldAppendUrlParams = ConfigItem("M3U8", "AppendUrlParams", False, BoolValidator())
    shouldBinaryMerge = ConfigItem("M3U8", "BinaryMerge", False, BoolValidator())
    shouldCheckSegmentsCount = ConfigItem("M3U8", "CheckSegmentsCount", True, BoolValidator())
    shouldKeepLiveSegments = ConfigItem("M3U8", "LiveKeepSegments", False, BoolValidator())
    shouldUseLivePipeMux = ConfigItem("M3U8", "LivePipeMux", False, BoolValidator())
    shouldFixLiveVtt = ConfigItem("M3U8", "LiveFixVtt", False, BoolValidator())
    liveWaitTime = RangeConfigItem("M3U8", "LiveWaitTime", 0, RangeValidator(0, 100000))
    liveTakeCount = RangeConfigItem("M3U8", "LiveTakeCount", 0, RangeValidator(0, 1000))
    decryptionEngine = OptionsConfigItem(
        "M3U8", "DecryptionEngine", "FFmpeg",
        OptionsValidator(["FFmpeg", "MP4Decrypt", "Shaka Packager"]),
    )
    decryptionBinaryPath = ConfigItem("M3U8", "DecryptionBinaryPath", "")
    shouldUseMp4RealTimeDecryption = ConfigItem("M3U8", "MP4RealTimeDecryption", True, BoolValidator())
    maxSpeed = RangeConfigItem("M3U8", "MaxSpeed", -1, RangeValidator(-1, 1000000))
    speedUnit = OptionsConfigItem("M3U8", "SpeedUnit", "Mbps", OptionsValidator(["Mbps", "Kbps"]))
    adKeyword = ConfigItem("M3U8", "AdKeyword", "")
    subtitleFormat = OptionsConfigItem("M3U8", "SubtitleFormat", "SRT", OptionsValidator(["SRT", "VTT"]))
    shouldOmitDateInfo = ConfigItem("M3U8", "NoDateInfo", False, BoolValidator())
    shouldKeepImageSegments = ConfigItem("M3U8", "KeepImageSegments", False, BoolValidator())
    shouldDeleteTemp = ConfigItem("M3U8", "DelAfterDone", True, BoolValidator())
    customMuxAfterDone = ConfigItem("M3U8", "CustomMuxAfterDone", "")
    shouldSelectAllAudioSubtitle = ConfigItem("M3U8", "SelectAllAudioSubtitle", True, BoolValidator())



m3u8Config = M3U8Config()


class M3U8Runtime(BinaryRuntime):
    name = "N_m3u8DL-RE"
    binaryName = "N_m3u8DL-RE"
    canInstall = not IS_ANDROID
    title = N("BinaryRuntime", "M3U8 / 直播下载")
    description = N("BinaryRuntime", "支持 HLS、DASH 等流媒体协议，可录制直播流")
    icon = "MEDIA"
    isRecommended = True

    def installFolder(self) -> Path:
        return Path(m3u8Config.installFolder.value)

    def path(self) -> str:
        if IS_ANDROID:
            nativeDir = nativeLibraryDir()
            if not nativeDir:
                return ""
            binary = Path(nativeDir) / "libnm3u8dlre.so"
            return str(binary) if binary.exists() else ""
        return findExecutable(self.installFolder(), "N_m3u8DL-RE")

    async def fetchLatestVersion(self) -> str:
        return (await fetchLatestRelease(M3U8_REPO)).version

    def installedPaths(self) -> list[Path]:
        suffix = ".exe" if sys.platform == "win32" else ""
        return [self.installFolder() / f"N_m3u8DL-RE{suffix}"]

    async def install(self, version: str, onProgress) -> None:
        if sys.platform == "win32":
            target = "win-arm64" if MACHINE_ARCH == "arm64" else "win-x64"
        elif sys.platform == "darwin":
            target = "osx-arm64" if MACHINE_ARCH == "arm64" else "osx-x64"
        elif sys.platform == "linux":
            target = "linux-arm64" if MACHINE_ARCH == "arm64" else "linux-x64"
        else:
            raise TaskError("当前平台暂不支持一键安装 N_m3u8DL-RE: {platform}", platform=sys.platform)

        release = await fetchLatestRelease(M3U8_REPO)
        extension = ".zip" if sys.platform == "win32" else ".tar.gz"
        assetName = ""
        for asset in release.assets:
            if target in asset.name and asset.name.endswith(extension):
                assetName = asset.name
                break
        if not assetName:
            raise TaskError("未找到适配 {target} 的 N_m3u8DL-RE 安装包", target=target)

        archive = self.installFolder() / assetName
        await fetchReleaseAsset(M3U8_REPO, release.version, assetName, archive, onProgress)
        await installArchive(archive, self.installFolder())


m3u8Runtime = M3U8Runtime()
