from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path


def loadKnownFolder(folderId: str) -> Path:
    import ctypes
    import uuid

    shell32 = ctypes.WinDLL("shell32")
    ole32 = ctypes.WinDLL("ole32")
    shell32.SHGetKnownFolderPath.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ctypes.c_void_p,
                                           ctypes.POINTER(ctypes.c_wchar_p)]
    shell32.SHGetKnownFolderPath.restype = ctypes.c_long
    ole32.CoTaskMemFree.argtypes = [ctypes.c_void_p]
    folder = (ctypes.c_ubyte * 16).from_buffer_copy(uuid.UUID(folderId).bytes_le)
    value = ctypes.c_wchar_p()
    result = shell32.SHGetKnownFolderPath(folder, 0, None, ctypes.byref(value))
    if result < 0:
        raise OSError(result, "Cannot resolve Windows known folder")
    try:
        return Path(value.value)
    finally:
        ole32.CoTaskMemFree(ctypes.cast(value, ctypes.c_void_p))


def loadDataFolder() -> Path:
    if sys.platform == "win32":
        return loadKnownFolder("3eb685db-65f9-4cf6-a03a-e3ef65729f3d")
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support"
    return Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")


def loadDownloadFolder() -> Path:
    if sys.platform == "win32":
        return loadKnownFolder("374de290-123f-4565-9164-39c4925e467b")
    if sys.platform != "darwin":
        configFolder = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
        try:
            for line in (configFolder / "user-dirs.dirs").read_text(encoding="utf-8").splitlines():
                key, separator, value = line.partition("=")
                if separator and key.strip() == "XDG_DOWNLOAD_DIR":
                    return Path(value.strip().strip('"').replace("${HOME}", str(Path.home()))
                                .replace("$HOME", str(Path.home())))
        except OSError:
            pass
    return Path.home() / "Downloads"

EXECUTABLE_PATH = (
    Path(os.environ["APPIMAGE"]) if "APPIMAGE" in os.environ
    else Path(sys.argv[0]).resolve() if "__compiled__" in globals()
    else Path(sys.executable).resolve()
)

EXECUTABLE_DIR = (
    Path(sys.executable).resolve().parent
    if "__compiled__" in globals()
    else Path(".")
)

APP_DATA_DIR = (
    Path(os.environ["GHOST_DOWNLOADER_DATA_DIR"])
    if os.environ.get("GHOST_DOWNLOADER_DATA_DIR")
    else EXECUTABLE_DIR / "GhostDownloader"
    if (EXECUTABLE_DIR / "GhostDownloader").is_dir()
    else loadDataFolder() / "GhostDownloader"
)

PORTABLE_DIR = EXECUTABLE_DIR / "GhostDownloader"

SEED_FEATURES_DIR = EXECUTABLE_DIR / "features"
FEATURES_DIR = (
    SEED_FEATURES_DIR
    if "__compiled__" not in globals()
    else APP_DATA_DIR / "features"
)
USER_DATA_DIR = loadDataFolder() / "GhostDownloader"

DOWNLOAD_DIR = loadDownloadFolder()


def isPortable() -> bool:
    return APP_DATA_DIR == PORTABLE_DIR


def migrate(target: Path) -> None:
    from loguru import logger
    logger.remove()
    source = APP_DATA_DIR
    target.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source, target, dirs_exist_ok=True)
    if isPortable():
        source.rename(source.with_suffix(".bak"))
