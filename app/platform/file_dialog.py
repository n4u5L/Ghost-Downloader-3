"""系统的打开文件、保存文件和选择文件夹对话框（IFileDialog），不依赖 Qt；供 bkit 界面使用。

对话框运行自己的模态消息循环，期间 bkit 窗口的消息都成了重入消息、改动推迟到外层调用返回：
不要在 bkit 的回调里直接调用，经 UiLoop.post 在 bkit 之外调用。
"""
from __future__ import annotations

import ctypes
import uuid
from ctypes import wintypes

S_OK = 0
S_FALSE = 1
COINIT_APARTMENTTHREADED = 0x2
CLSCTX_INPROC_SERVER = 0x1
FOS_OVERWRITEPROMPT = 0x2
FOS_PICKFOLDERS = 0x20
FOS_FORCEFILESYSTEM = 0x40
FOS_ALLOWMULTISELECT = 0x200
FOS_PATHMUSTEXIST = 0x800
FOS_FILEMUSTEXIST = 0x1000
SIGDN_FILESYSPATH = 0x80058000

# 虚表下标：IUnknown 0-2，IModalWindow 3，IFileDialog 4-26，IFileOpenDialog 27-28
RELEASE = 2
SHOW = 3
SET_FILE_TYPES = 4
SET_OPTIONS = 9
GET_OPTIONS = 10
SET_FOLDER = 12
SET_FILE_NAME = 15
SET_TITLE = 17
GET_RESULT = 20
SET_DEFAULT_EXTENSION = 22
GET_RESULTS = 27
ITEM_GET_DISPLAY_NAME = 5
ARRAY_GET_COUNT = 7
ARRAY_GET_ITEM_AT = 8


class GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", wintypes.DWORD),
        ("Data2", wintypes.WORD),
        ("Data3", wintypes.WORD),
        ("Data4", ctypes.c_ubyte * 8),
    ]


class COMDLG_FILTERSPEC(ctypes.Structure):
    _fields_ = [("pszName", wintypes.LPCWSTR), ("pszSpec", wintypes.LPCWSTR)]


def toGuid(text: str) -> GUID:
    return GUID.from_buffer_copy(uuid.UUID(text).bytes_le)


CLSID_FILE_OPEN_DIALOG = toGuid("DC1C5A9C-E88A-4DDE-A5A1-60F82A20AEF7")
IID_IFILE_OPEN_DIALOG = toGuid("D57C7288-D4AD-4768-BE02-9D969532D960")
CLSID_FILE_SAVE_DIALOG = toGuid("C0B4E2F3-BA21-4773-8DBA-335EC946EB8B")
IID_IFILE_SAVE_DIALOG = toGuid("84BCCD23-5FDE-4CDB-AEA4-AF64B83D78AB")
IID_ISHELL_ITEM = toGuid("43826D1E-E718-42EE-BC55-A1E261C37BFE")

ole32 = ctypes.WinDLL("ole32")
shell32 = ctypes.WinDLL("shell32")
user32 = ctypes.WinDLL("user32")
ole32.CoInitializeEx.argtypes = [ctypes.c_void_p, wintypes.DWORD]
ole32.CoInitializeEx.restype = ctypes.c_long
ole32.CoUninitialize.argtypes = []
ole32.CoCreateInstance.argtypes = [
    ctypes.POINTER(GUID), ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(GUID), ctypes.POINTER(ctypes.c_void_p),
]
ole32.CoCreateInstance.restype = ctypes.c_long
ole32.CoTaskMemFree.argtypes = [ctypes.c_void_p]
shell32.SHCreateItemFromParsingName.argtypes = [
    wintypes.LPCWSTR, ctypes.c_void_p, ctypes.POINTER(GUID), ctypes.POINTER(ctypes.c_void_p),
]
shell32.SHCreateItemFromParsingName.restype = ctypes.c_long
user32.GetActiveWindow.restype = wintypes.HWND


def runMethod(pointer: int, index: int, argtypes: list, *args) -> int:
    """调用 COM 接口虚表的第 index 个方法，返回 HRESULT。"""
    vtable = ctypes.cast(ctypes.c_void_p(pointer), ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
    prototype = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, *argtypes)
    return prototype(vtable[index])(pointer, *args)


def toItemPath(item: int) -> str | None:
    name = ctypes.c_void_p()
    if runMethod(item, ITEM_GET_DISPLAY_NAME, [wintypes.DWORD, ctypes.POINTER(ctypes.c_void_p)],
                 SIGDN_FILESYSPATH, ctypes.byref(name)) != S_OK or not name.value:
        return None
    try:
        return ctypes.wstring_at(name.value)
    finally:
        ole32.CoTaskMemFree(name)


def runDialog(clsid: GUID, iid: GUID, title: str, options: int, filters: list[tuple[str, str]],
              folder: str, fileName: str) -> list[str]:
    """显示对话框，返回选中的路径；用户取消时为空列表。"""
    hr = ole32.CoInitializeEx(None, COINIT_APARTMENTTHREADED)
    isInitialized = hr in (S_OK, S_FALSE)
    try:
        dialog = ctypes.c_void_p()
        if ole32.CoCreateInstance(ctypes.byref(clsid), None, CLSCTX_INPROC_SERVER, ctypes.byref(iid),
                                  ctypes.byref(dialog)) != S_OK or not dialog.value:
            return []
        pointer = dialog.value
        try:
            current = wintypes.DWORD()
            runMethod(pointer, GET_OPTIONS, [ctypes.POINTER(wintypes.DWORD)], ctypes.byref(current))
            runMethod(pointer, SET_OPTIONS, [wintypes.DWORD], current.value | options | FOS_FORCEFILESYSTEM)
            runMethod(pointer, SET_TITLE, [wintypes.LPCWSTR], title)
            if filters:
                specs = (COMDLG_FILTERSPEC * len(filters))(*(COMDLG_FILTERSPEC(n, s) for n, s in filters))
                runMethod(pointer, SET_FILE_TYPES, [wintypes.UINT, ctypes.POINTER(COMDLG_FILTERSPEC)],
                          len(filters), specs)
                # 保存时按第一个筛选项补全扩展名，如 "*.crx" 补 "crx"
                extension = filters[0][1].split(";")[0].removeprefix("*.")
                if extension and "*" not in extension:
                    runMethod(pointer, SET_DEFAULT_EXTENSION, [wintypes.LPCWSTR], extension)
            if fileName:
                runMethod(pointer, SET_FILE_NAME, [wintypes.LPCWSTR], fileName)
            if folder:
                item = ctypes.c_void_p()
                if shell32.SHCreateItemFromParsingName(folder, None, ctypes.byref(IID_ISHELL_ITEM),
                                                       ctypes.byref(item)) == S_OK and item.value:
                    runMethod(pointer, SET_FOLDER, [ctypes.c_void_p], item.value)
                    runMethod(item.value, RELEASE, [])

            if runMethod(pointer, SHOW, [wintypes.HWND], user32.GetActiveWindow()) != S_OK:
                return []
            if options & FOS_ALLOWMULTISELECT:
                return toResultPaths(pointer)
            item = ctypes.c_void_p()
            if runMethod(pointer, GET_RESULT, [ctypes.POINTER(ctypes.c_void_p)], ctypes.byref(item)) != S_OK:
                return []
            try:
                path = toItemPath(item.value)
            finally:
                runMethod(item.value, RELEASE, [])
            return [path] if path else []
        finally:
            runMethod(pointer, RELEASE, [])
    finally:
        if isInitialized:
            ole32.CoUninitialize()


def toResultPaths(dialog: int) -> list[str]:
    array = ctypes.c_void_p()
    if runMethod(dialog, GET_RESULTS, [ctypes.POINTER(ctypes.c_void_p)], ctypes.byref(array)) != S_OK:
        return []
    paths: list[str] = []
    try:
        count = wintypes.DWORD()
        runMethod(array.value, ARRAY_GET_COUNT, [ctypes.POINTER(wintypes.DWORD)], ctypes.byref(count))
        for index in range(count.value):
            item = ctypes.c_void_p()
            if runMethod(array.value, ARRAY_GET_ITEM_AT, [wintypes.DWORD, ctypes.POINTER(ctypes.c_void_p)],
                         index, ctypes.byref(item)) != S_OK:
                continue
            try:
                if path := toItemPath(item.value):
                    paths.append(path)
            finally:
                runMethod(item.value, RELEASE, [])
    finally:
        runMethod(array.value, RELEASE, [])
    return paths


def openFileDialog(title: str, filters: list[tuple[str, str]] | None = None, *,
                   isMultiple: bool = False) -> list[str]:
    """filters 是 (显示名, "*.torrent;*.metalink") 的列表。"""
    options = FOS_FILEMUSTEXIST | FOS_PATHMUSTEXIST | (FOS_ALLOWMULTISELECT if isMultiple else 0)
    return runDialog(CLSID_FILE_OPEN_DIALOG, IID_IFILE_OPEN_DIALOG, title, options, filters or [], "", "")


def openFolderDialog(title: str, folder: str = "") -> str | None:
    paths = runDialog(CLSID_FILE_OPEN_DIALOG, IID_IFILE_OPEN_DIALOG, title,
                      FOS_PICKFOLDERS | FOS_PATHMUSTEXIST, [], folder, "")
    return paths[0] if paths else None


def openSaveFileDialog(title: str, fileName: str, filters: list[tuple[str, str]] | None = None) -> str | None:
    paths = runDialog(CLSID_FILE_SAVE_DIALOG, IID_IFILE_SAVE_DIALOG, title, FOS_OVERWRITEPROMPT,
                      filters or [], "", fileName)
    return paths[0] if paths else None
