"""系统托盘图标，对应 Qt 界面的 SystemTrayIcon，用 Shell_NotifyIcon 实现。

托盘消息由一个隐藏窗口接收；它同时是单实例的门铃：第二个进程找到这个窗口，用 WM_COPYDATA
送来命令行参数和工作目录，对应 Qt 版经 QLocalSocket 转发给主实例的 Invocation（不回传输出）。
右键菜单的 TrackPopupMenu 运行自己的模态循环，经 post 放到 bkit 的调用之外运行。
"""
from __future__ import annotations

import ctypes
import json
from collections.abc import Callable
from ctypes import wintypes
from pathlib import Path
from typing import TYPE_CHECKING

from loguru import logger

from app.format import toReadableSize
from app.platform.shell import loadIconHandle
from app.signal import Signal
from app.ui.i18n import tr

if TYPE_CHECKING:
    from app.services.speed_meter import SpeedMeter
    from app.services.task_service import TaskService
    from app.ui.loop import Timer

CLASS_NAME = "GhostDownloaderBkitTray"
WM_NULL = 0x0000
WM_COPYDATA = 0x004A
WM_LBUTTONUP = 0x0202
WM_RBUTTONUP = 0x0205
WM_APP = 0x8000
TRAY_MESSAGE = WM_APP + 1
# WM_COPYDATA 的 dwData，标明是本程序的参数，不是别的程序误发来的
INVOCATION_TAG = 0x47443342
NIM_ADD = 0
NIM_MODIFY = 1
NIM_DELETE = 2
NIF_MESSAGE = 0x1
NIF_ICON = 0x2
NIF_TIP = 0x4
MF_STRING = 0x0
MF_SEPARATOR = 0x800
TPM_RIGHTBUTTON = 0x2
TPM_RETURNCMD = 0x100
TPM_NONOTIFY = 0x80
ASFW_ANY = 0xFFFFFFFF
ERROR_CLASS_ALREADY_EXISTS = 1410
DASHBOARD, START_ALL, PAUSE_ALL, QUIT = 1, 2, 3, 4

LRESULT = wintypes.LPARAM
WNDPROC = ctypes.WINFUNCTYPE(LRESULT, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)


class WNDCLASSEXW(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.UINT), ("style", wintypes.UINT), ("lpfnWndProc", WNDPROC),
        ("cbClsExtra", ctypes.c_int), ("cbWndExtra", ctypes.c_int), ("hInstance", wintypes.HINSTANCE),
        ("hIcon", wintypes.HICON), ("hCursor", wintypes.HANDLE), ("hbrBackground", wintypes.HBRUSH),
        ("lpszMenuName", wintypes.LPCWSTR), ("lpszClassName", wintypes.LPCWSTR), ("hIconSm", wintypes.HICON),
    ]


class COPYDATASTRUCT(ctypes.Structure):
    _fields_ = [("dwData", ctypes.c_size_t), ("cbData", wintypes.DWORD), ("lpData", ctypes.c_void_p)]


class NOTIFYICONDATAW(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD), ("hWnd", wintypes.HWND), ("uID", wintypes.UINT), ("uFlags", wintypes.UINT),
        ("uCallbackMessage", wintypes.UINT), ("hIcon", wintypes.HICON), ("szTip", wintypes.WCHAR * 128),
        ("dwState", wintypes.DWORD), ("dwStateMask", wintypes.DWORD), ("szInfo", wintypes.WCHAR * 256),
        ("uVersion", wintypes.UINT), ("szInfoTitle", wintypes.WCHAR * 64), ("dwInfoFlags", wintypes.DWORD),
        ("guidItem", ctypes.c_byte * 16), ("hBalloonIcon", wintypes.HICON),
    ]


user32 = ctypes.WinDLL("user32", use_last_error=True)
shell32 = ctypes.WinDLL("shell32")
kernel32 = ctypes.WinDLL("kernel32")
user32.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
user32.DefWindowProcW.restype = LRESULT
user32.RegisterClassExW.argtypes = [ctypes.POINTER(WNDCLASSEXW)]
user32.RegisterClassExW.restype = wintypes.ATOM
user32.CreateWindowExW.argtypes = [
    wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD, ctypes.c_int, ctypes.c_int,
    ctypes.c_int, ctypes.c_int, wintypes.HWND, wintypes.HMENU, wintypes.HINSTANCE, wintypes.LPVOID,
]
user32.CreateWindowExW.restype = wintypes.HWND
user32.DestroyWindow.argtypes = [wintypes.HWND]
user32.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
user32.FindWindowW.restype = wintypes.HWND
user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
user32.SendMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
user32.SendMessageW.restype = LRESULT
user32.RegisterWindowMessageW.argtypes = [wintypes.LPCWSTR]
user32.RegisterWindowMessageW.restype = wintypes.UINT
user32.CreatePopupMenu.restype = wintypes.HMENU
user32.AppendMenuW.argtypes = [wintypes.HMENU, wintypes.UINT, ctypes.c_size_t, wintypes.LPCWSTR]
user32.TrackPopupMenu.argtypes = [
    wintypes.HMENU, wintypes.UINT, ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.HWND, ctypes.c_void_p,
]
user32.TrackPopupMenu.restype = wintypes.BOOL
user32.DestroyMenu.argtypes = [wintypes.HMENU]
user32.GetCursorPos.argtypes = [ctypes.POINTER(wintypes.POINT)]
user32.SetForegroundWindow.argtypes = [wintypes.HWND]
user32.AllowSetForegroundWindow.argtypes = [wintypes.DWORD]
shell32.Shell_NotifyIconW.argtypes = [wintypes.DWORD, ctypes.POINTER(NOTIFYICONDATAW)]
shell32.Shell_NotifyIconW.restype = wintypes.BOOL
kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
kernel32.GetModuleHandleW.restype = wintypes.HMODULE


def T(text: str) -> str:
    return tr("SystemTrayIcon", text)


def requestInvocation(argv: list[str], cwd: str) -> bool:
    """把命令行交给已在运行的 bkit 进程；找不到它时返回 False。"""
    hwnd = user32.FindWindowW(CLASS_NAME, None)
    if not hwnd:
        return False
    # 允许对方把窗口切到前台：前台权限只能由当前前台进程让出
    user32.AllowSetForegroundWindow(ASFW_ANY)
    data = json.dumps({"argv": argv, "cwd": cwd}).encode()
    buffer = ctypes.create_string_buffer(data, len(data))
    copyData = COPYDATASTRUCT(INVOCATION_TAG, len(data), ctypes.cast(buffer, ctypes.c_void_p))
    return bool(user32.SendMessageW(hwnd, WM_COPYDATA, 0, ctypes.addressof(copyData)))


class SystemTrayIcon:
    NAME = "Ghost Downloader"

    activationRequested = Signal()
    invocationRequested = Signal(list, str)
    quitRequested = Signal()

    def __init__(self, taskService: TaskService, speedMeter: SpeedMeter, iconPath: Path,
                 post: Callable[[Callable[[], object], float], Timer]) -> None:
        self._taskService = taskService
        self._post = post
        self._tip = self.NAME
        self._isAdded = False
        # ctypes 回调对象必须一直被引用，窗口类和窗口存活期间都会调用它
        self._wndProc = WNDPROC(self._onMessage)
        self._taskbarCreated = user32.RegisterWindowMessageW("TaskbarCreated")
        self._icon = loadIconHandle(iconPath, isSmall=True)
        self._hwnd = self._createWindow()
        speedMeter.speedChanged.connect(self._onSpeedChanged)

    def _createWindow(self) -> int:
        instance = kernel32.GetModuleHandleW(None)
        windowClass = WNDCLASSEXW(cbSize=ctypes.sizeof(WNDCLASSEXW), lpfnWndProc=self._wndProc,
                                  hInstance=instance, lpszClassName=CLASS_NAME)
        if not user32.RegisterClassExW(ctypes.byref(windowClass)) \
                and ctypes.get_last_error() != ERROR_CLASS_ALREADY_EXISTS:
            raise ctypes.WinError(ctypes.get_last_error())
        hwnd = user32.CreateWindowExW(0, CLASS_NAME, self.NAME, 0, 0, 0, 0, 0, None, None, instance, None)
        if not hwnd:
            raise ctypes.WinError(ctypes.get_last_error())
        return hwnd

    def add(self) -> None:
        self._isAdded = shell32.Shell_NotifyIconW(NIM_ADD, ctypes.byref(self._buildData()))

    def remove(self) -> None:
        if self._isAdded:
            shell32.Shell_NotifyIconW(NIM_DELETE, ctypes.byref(self._buildData()))
            self._isAdded = False
        if self._hwnd:
            user32.DestroyWindow(self._hwnd)
            self._hwnd = 0

    def _buildData(self) -> NOTIFYICONDATAW:
        data = NOTIFYICONDATAW(cbSize=ctypes.sizeof(NOTIFYICONDATAW), hWnd=self._hwnd, uID=1,
                               uFlags=NIF_MESSAGE | NIF_ICON | NIF_TIP, uCallbackMessage=TRAY_MESSAGE,
                               hIcon=self._icon)
        data.szTip = self._tip[:127]
        return data

    def _onSpeedChanged(self, speed: int) -> None:
        self._tip = f"{self.NAME}\n↓ {toReadableSize(speed)}/s" if speed > 0 else self.NAME
        if self._isAdded:
            shell32.Shell_NotifyIconW(NIM_MODIFY, ctypes.byref(self._buildData()))

    def _onMessage(self, hwnd: int, message: int, wParam: int, lParam: int) -> int:
        try:
            if message == TRAY_MESSAGE:
                if lParam == WM_LBUTTONUP:
                    self._post(self.activationRequested.emit, 0.0)
                elif lParam == WM_RBUTTONUP:
                    self._post(self._openMenu, 0.0)
                return 0
            if message == WM_COPYDATA:
                return self._onCopyData(lParam)
            if message == self._taskbarCreated and self._isAdded:
                # 资源管理器重启后托盘图标会丢失，需要重新添加
                self.add()
                return 0
        except Exception as e:
            logger.opt(exception=e).error("tray message failed")
        return user32.DefWindowProcW(hwnd, message, wParam, lParam)

    def _onCopyData(self, lParam: int) -> int:
        copyData = COPYDATASTRUCT.from_address(lParam)
        if copyData.dwData != INVOCATION_TAG:
            return 0
        # 数据只在这次消息内有效，先复制出来，再放到 bkit 之外处理
        request = json.loads(ctypes.string_at(copyData.lpData, copyData.cbData))
        argv, cwd = list(request["argv"]), str(request["cwd"])
        self._post(lambda: self.invocationRequested.emit(argv, cwd), 0.0)
        return 1

    def _openMenu(self) -> None:
        menu = user32.CreatePopupMenu()
        for command, label in ((DASHBOARD, T("仪表盘")), (START_ALL, T("全部开始")), (PAUSE_ALL, T("全部暂停"))):
            user32.AppendMenuW(menu, MF_STRING, command, label)
        user32.AppendMenuW(menu, MF_SEPARATOR, 0, None)
        user32.AppendMenuW(menu, MF_STRING, QUIT, T("退出程序"))
        position = wintypes.POINT()
        user32.GetCursorPos(ctypes.byref(position))
        # 不先切到前台，点菜单外面时菜单不会消失
        user32.SetForegroundWindow(self._hwnd)
        command = user32.TrackPopupMenu(menu, TPM_RIGHTBUTTON | TPM_RETURNCMD | TPM_NONOTIFY,
                                        position.x, position.y, 0, self._hwnd, None)
        user32.PostMessageW(self._hwnd, WM_NULL, 0, 0)
        user32.DestroyMenu(menu)
        if command == DASHBOARD:
            self.activationRequested.emit()
        elif command == START_ALL:
            self._taskService.startAll()
        elif command == PAUSE_ALL:
            self._taskService.pauseAll()
        elif command == QUIT:
            self.quitRequested.emit()
