"""WIC clips and scales a sprite cell before its pixels enter the UI."""
from __future__ import annotations

import ctypes
import struct
from ctypes import wintypes

from app.platform.file_dialog import GUID, runMethod, toGuid


CLSID_WIC_FACTORY = toGuid("cacaf262-9370-4615-a13b-9f5539da4c0a")
IID_WIC_FACTORY = toGuid("ec5ec8a9-c395-4314-9c77-54d7a935ff70")
PIXEL_FORMAT_BGR = toGuid("6fddc324-4e03-4bfe-b185-3d77768dc90c")
RPC_E_CHANGED_MODE = -2147417850

ole32 = ctypes.WinDLL("ole32")
ole32.CoInitializeEx.argtypes = [ctypes.c_void_p, wintypes.DWORD]
ole32.CoInitializeEx.restype = ctypes.c_long
ole32.CoUninitialize.argtypes = []
ole32.CoCreateInstance.argtypes = [
    ctypes.POINTER(GUID), ctypes.c_void_p, wintypes.DWORD,
    ctypes.POINTER(GUID), ctypes.POINTER(ctypes.c_void_p),
]
ole32.CoCreateInstance.restype = ctypes.c_long


class WicRect(ctypes.Structure):
    _fields_ = [("x", ctypes.c_int), ("y", ctypes.c_int),
                ("width", ctypes.c_int), ("height", ctypes.c_int)]


def toHresult(result):
    if result < 0:
        raise OSError(result, "Windows image decoding failed")


def createWicObject(factory, method, objects):
    pointer = ctypes.c_void_p()
    toHresult(runMethod(factory.value, method, [ctypes.POINTER(ctypes.c_void_p)], ctypes.byref(pointer)))
    objects.append(pointer)
    return pointer


def toSpriteThumbnail(encoded: bytes, columns: int, rows: int, cell: int,
                      width: int = 160, height: int = 90) -> bytes:
    """Return a small bottom-up BMP; no full sprite bitmap is retained."""
    if not encoded or not (1 <= columns <= 256 and 1 <= rows <= 256 and 0 <= cell < columns * rows):
        raise ValueError("Invalid storyboard grid")
    if not (1 <= width <= 640 and 1 <= height <= 360) or len(encoded) > 64 * 1024 * 1024:
        raise ValueError("Storyboard image exceeds the decode limit")
    initialized = ole32.CoInitializeEx(None, 0)
    if initialized != RPC_E_CHANGED_MODE:
        toHresult(initialized)
    objects = []
    # IWICStream borrows this buffer until the decoder and stream are released.
    buffer = ctypes.c_char_p(encoded)
    try:
        factory = ctypes.c_void_p()
        toHresult(ole32.CoCreateInstance(ctypes.byref(CLSID_WIC_FACTORY), None, 1,
                                         ctypes.byref(IID_WIC_FACTORY), ctypes.byref(factory)))
        objects.append(factory)
        stream = createWicObject(factory, 14, objects)
        toHresult(runMethod(stream.value, 16, [ctypes.c_void_p, wintypes.DWORD],
                            ctypes.cast(buffer, ctypes.c_void_p), len(encoded)))
        decoder = ctypes.c_void_p()
        toHresult(runMethod(factory.value, 4,
            [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int, ctypes.POINTER(ctypes.c_void_p)],
            stream, None, 0, ctypes.byref(decoder)))
        objects.append(decoder)
        frame = ctypes.c_void_p()
        toHresult(runMethod(decoder.value, 13, [wintypes.UINT, ctypes.POINTER(ctypes.c_void_p)],
                            0, ctypes.byref(frame)))
        objects.append(frame)
        sourceWidth, sourceHeight = wintypes.UINT(), wintypes.UINT()
        toHresult(runMethod(frame.value, 3, [ctypes.POINTER(wintypes.UINT), ctypes.POINTER(wintypes.UINT)],
                            ctypes.byref(sourceWidth), ctypes.byref(sourceHeight)))
        cellWidth, cellHeight = sourceWidth.value // columns, sourceHeight.value // rows
        if not cellWidth or not cellHeight or sourceWidth.value * sourceHeight.value > 64 * 1024 * 1024:
            raise ValueError("Invalid storyboard dimensions")
        clip = WicRect(cell % columns * cellWidth, cell // columns * cellHeight, cellWidth, cellHeight)
        clipper = createWicObject(factory, 12, objects)
        toHresult(runMethod(clipper.value, 8, [ctypes.c_void_p, ctypes.POINTER(WicRect)], frame, ctypes.byref(clip)))
        scaler = createWicObject(factory, 11, objects)
        toHresult(runMethod(scaler.value, 8, [ctypes.c_void_p, wintypes.UINT, wintypes.UINT, ctypes.c_int],
                            clipper, width, height, 3))
        converter = createWicObject(factory, 10, objects)
        toHresult(runMethod(converter.value, 8,
            [ctypes.c_void_p, ctypes.POINTER(GUID), ctypes.c_int, ctypes.c_void_p, ctypes.c_double, ctypes.c_int],
            scaler, ctypes.byref(PIXEL_FORMAT_BGR), 0, None, 0.0, 0))
        stride = (width * 3 + 3) & ~3
        size = stride * height
        pixels = (ctypes.c_ubyte * size)()
        toHresult(runMethod(converter.value, 7,
            [ctypes.c_void_p, wintypes.UINT, wintypes.UINT, ctypes.c_void_p], None, stride, size, pixels))
        # bkit's dimension probe rejects the negative height of a top-down BMP.
        header = struct.pack("<2sIHHIIiiHHIIiiII", b"BM", 54 + size, 0, 0, 54,
                             40, width, height, 1, 24, 0, size, 0, 0, 0, 0)
        bitmap = bytearray(54 + size)
        bitmap[:54] = header
        source = memoryview(pixels).cast("B")
        for row in range(height):
            start = row * stride
            target = 54 + (height - row - 1) * stride
            bitmap[target:target + stride] = source[start:start + stride]
        return bytes(bitmap)
    finally:
        for pointer in reversed(objects):
            runMethod(pointer.value, 2, [])
        if initialized >= 0:
            ole32.CoUninitialize()
