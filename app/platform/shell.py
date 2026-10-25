"""Windows Shell 与剪贴板操作，不依赖 Qt；供 bkit 界面使用。"""
from __future__ import annotations

import ctypes
import os
from ctypes import wintypes
from os import PathLike
from pathlib import Path

from app.platform.filesystem import isExisting

FO_DELETE = 3
FOF_SILENT = 0x0004
FOF_NOCONFIRMATION = 0x0010
FOF_ALLOWUNDO = 0x0040
FOF_NOERRORUI = 0x0400
S_OK = 0
S_FALSE = 1
COINIT_APARTMENTTHREADED = 0x2
CF_UNICODETEXT = 13
GMEM_MOVEABLE = 0x0002
SW_HIDE = 0
SW_SHOW = 5
SW_RESTORE = 9
WM_SETICON = 0x0080
ICON_SMALL = 0
ICON_BIG = 1
IMAGE_ICON = 1
LR_LOADFROMFILE = 0x10
SM_CXICON = 11
SM_CYICON = 12
SM_CXSMICON = 49
SM_CYSMICON = 50


class SHFILEOPSTRUCTW(ctypes.Structure):
    _fields_ = [
        ("hwnd", wintypes.HWND),
        ("wFunc", wintypes.UINT),
        ("pFrom", wintypes.LPCWSTR),
        ("pTo", wintypes.LPCWSTR),
        ("fFlags", wintypes.WORD),
        ("fAnyOperationsAborted", wintypes.BOOL),
        ("hNameMappings", wintypes.LPVOID),
        ("lpszProgressTitle", wintypes.LPCWSTR),
    ]


shell32 = ctypes.WinDLL("shell32")
ole32 = ctypes.WinDLL("ole32")
user32 = ctypes.WinDLL("user32")
kernel32 = ctypes.WinDLL("kernel32")
shell32.SHFileOperationW.argtypes = [ctypes.POINTER(SHFILEOPSTRUCTW)]
shell32.SHFileOperationW.restype = ctypes.c_int
shell32.SHParseDisplayName.argtypes = [
    wintypes.LPCWSTR, ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p), wintypes.ULONG, ctypes.c_void_p,
]
shell32.SHParseDisplayName.restype = ctypes.c_long
shell32.SHOpenFolderAndSelectItems.argtypes = [ctypes.c_void_p, wintypes.UINT, ctypes.c_void_p, wintypes.DWORD]
shell32.SHOpenFolderAndSelectItems.restype = ctypes.c_long
ole32.CoInitializeEx.argtypes = [ctypes.c_void_p, wintypes.DWORD]
ole32.CoInitializeEx.restype = ctypes.c_long
ole32.CoUninitialize.argtypes = []
ole32.CoTaskMemFree.argtypes = [ctypes.c_void_p]
user32.OpenClipboard.argtypes = [wintypes.HWND]
user32.OpenClipboard.restype = wintypes.BOOL
user32.EmptyClipboard.restype = wintypes.BOOL
user32.CloseClipboard.restype = wintypes.BOOL
user32.GetClipboardData.argtypes = [wintypes.UINT]
user32.GetClipboardData.restype = wintypes.HANDLE
user32.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]
user32.SetClipboardData.restype = wintypes.HANDLE
user32.GetClipboardSequenceNumber.restype = wintypes.DWORD
user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
user32.IsIconic.argtypes = [wintypes.HWND]
user32.IsWindowVisible.argtypes = [wintypes.HWND]
user32.SetForegroundWindow.argtypes = [wintypes.HWND]
user32.SendMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
user32.SendMessageW.restype = wintypes.LPARAM
user32.LoadImageW.argtypes = [wintypes.HINSTANCE, wintypes.LPCWSTR, wintypes.UINT, ctypes.c_int, ctypes.c_int,
                              wintypes.UINT]
user32.LoadImageW.restype = wintypes.HANDLE
user32.GetSystemMetrics.argtypes = [ctypes.c_int]
kernel32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
kernel32.GlobalAlloc.restype = wintypes.HGLOBAL
kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
kernel32.GlobalLock.restype = ctypes.c_void_p
kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
kernel32.GlobalFree.argtypes = [wintypes.HGLOBAL]


def loadIconHandle(path: Path, isSmall: bool) -> int:
    """.ico 文件按系统的大图标或小图标尺寸加载，返回 HICON；失败时为 0。"""
    width = user32.GetSystemMetrics(SM_CXSMICON if isSmall else SM_CXICON)
    height = user32.GetSystemMetrics(SM_CYSMICON if isSmall else SM_CYICON)
    return user32.LoadImageW(None, str(path), IMAGE_ICON, width, height, LR_LOADFROMFILE) or 0


def setWindowIcon(hwnd: int, path: Path) -> None:
    for kind, isSmall in ((ICON_BIG, False), (ICON_SMALL, True)):
        if icon := loadIconHandle(path, isSmall):
            user32.SendMessageW(hwnd, WM_SETICON, kind, icon)


def isWindowVisible(hwnd: int) -> bool:
    return bool(user32.IsWindowVisible(hwnd))


def setWindowVisible(hwnd: int, isVisible: bool) -> None:
    """显示时还原最小化并切到前台，对应 Qt 界面的 raiseWindow()。"""
    if not isVisible:
        user32.ShowWindow(hwnd, SW_HIDE)
        return
    user32.ShowWindow(hwnd, SW_RESTORE if user32.IsIconic(hwnd) else SW_SHOW)
    user32.SetForegroundWindow(hwnd)


def deleteRecoverably(path: Path) -> bool:
    # pFrom 以两个 NUL 结尾，ctypes 只补一个
    operation = SHFILEOPSTRUCTW(
        wFunc=FO_DELETE, pFrom=f"{path}\0",
        fFlags=FOF_ALLOWUNDO | FOF_NOCONFIRMATION | FOF_SILENT | FOF_NOERRORUI,
    )
    return shell32.SHFileOperationW(ctypes.byref(operation)) == 0 and not operation.fAnyOperationsAborted


def openFile(path: str | PathLike[str]) -> None:
    os.startfile(str(path))


def openFolder(path: str | PathLike[str]) -> None:
    os.startfile(str(path))


def openUrl(url: str) -> None:
    os.startfile(url)


def clipboardSequenceNumber() -> int:
    """剪贴板内容每变一次加一；读它不必打开剪贴板。"""
    return user32.GetClipboardSequenceNumber()


def clipboardText() -> str:
    if not user32.OpenClipboard(None):
        return ""
    try:
        handle = user32.GetClipboardData(CF_UNICODETEXT)
        pointer = kernel32.GlobalLock(handle) if handle else None
        if not pointer:
            return ""
        try:
            return ctypes.wstring_at(pointer)
        finally:
            kernel32.GlobalUnlock(handle)
    finally:
        user32.CloseClipboard()


def setClipboardText(text: str) -> None:
    data = ctypes.create_unicode_buffer(text)
    if not user32.OpenClipboard(None):
        return
    try:
        user32.EmptyClipboard()
        handle = kernel32.GlobalAlloc(GMEM_MOVEABLE, ctypes.sizeof(data))
        pointer = kernel32.GlobalLock(handle) if handle else None
        if not pointer:
            if handle:
                kernel32.GlobalFree(handle)
            return
        ctypes.memmove(pointer, data, ctypes.sizeof(data))
        kernel32.GlobalUnlock(handle)
        # 成功后内存归剪贴板所有，失败时才由调用方释放
        if not user32.SetClipboardData(CF_UNICODETEXT, handle):
            kernel32.GlobalFree(handle)
    finally:
        user32.CloseClipboard()


def revealInFolder(path: str | PathLike[str]) -> None:
    path = Path(path)
    if isExisting(path):
        if not _revealInExplorer(path):
            os.startfile(str(path.parent))
    elif isExisting(path.parent):
        openFolder(path.parent)


def _revealInExplorer(path: Path) -> bool:
    hr = ole32.CoInitializeEx(None, COINIT_APARTMENTTHREADED)
    weInitialized = hr == S_OK
    if hr not in (S_OK, S_FALSE):
        return False
    try:
        pidl = ctypes.c_void_p()
        hr = shell32.SHParseDisplayName(str(path), None, ctypes.byref(pidl), 0, None)
        if hr != S_OK or not pidl.value:
            return False
        try:
            return shell32.SHOpenFolderAndSelectItems(pidl, 0, None, 0) == S_OK
        finally:
            ole32.CoTaskMemFree(pidl)
    finally:
        if weInitialized:
            ole32.CoUninitialize()
