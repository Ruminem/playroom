# SPDX-License-Identifier: Apache-2.0
"""shared/surface.py 의 맥판. 투명하고 클릭이 통과하며 전체 화면 앱 위에도 뜨는 창에 BGRA 픽셀을 그린다.

픽셀은 IOSurface 두 벌에 번갈아 그리고 레이어에 그대로 넘긴다. 프레임마다 CGImage 를 만들면
내보내기만으로 CPU 25% 를 썼고, 이쪽은 0.4% 였다(2026-10-04 맥북, 1680×924). 그래서 pixels 는
present 할 때마다 다른 버퍼를 가리킨다 — 쓰는 쪽은 매 프레임 surface.pixels 를 다시 잡아야 한다.
ponytail: 1배 버퍼를 레티나에 키워 보인다. 흐려 보이면 backingScaleFactor 배로 키우면 됨(CPU 도 그만큼)
"""
import ctypes as C

from cocoa import Rect, Point, Size, cls, drain, main_screen, pool, pump, send

IOS = C.cdll.LoadLibrary("/System/Library/Frameworks/IOSurface.framework/IOSurface")
CF = C.cdll.LoadLibrary("/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation")
CF.CFNumberCreate.restype = C.c_void_p
CF.CFNumberCreate.argtypes = [C.c_void_p, C.c_long, C.c_void_p]
CF.CFDictionaryCreate.restype = C.c_void_p
CF.CFDictionaryCreate.argtypes = [C.c_void_p, C.c_void_p, C.c_void_p, C.c_long, C.c_void_p, C.c_void_p]
CF.CFRelease.argtypes = [C.c_void_p]
IOS.IOSurfaceCreate.restype = C.c_void_p
IOS.IOSurfaceCreate.argtypes = [C.c_void_p]
IOS.IOSurfaceGetBaseAddress.restype = C.c_void_p
IOS.IOSurfaceGetBaseAddress.argtypes = [C.c_void_p]
IOS.IOSurfaceGetBytesPerRow.restype = C.c_size_t
IOS.IOSurfaceGetBytesPerRow.argtypes = [C.c_void_p]
IOS.IOSurfaceLock.argtypes = [C.c_void_p, C.c_uint32, C.c_void_p]
IOS.IOSurfaceUnlock.argtypes = [C.c_void_p, C.c_uint32, C.c_void_p]

STATUS_LEVEL = 25  # NSStatusWindowLevel: 보통 창과 전체 화면 앱 위
# canJoinAllSpaces | stationary | ignoresCycle | fullScreenAuxiliary — 모든 데스크톱·전체 화면에 따라감
BEHAVIOR = 1 | 16 | 64 | 256


def io_surface(w, h):
    names = ("kIOSurfaceWidth", "kIOSurfaceHeight", "kIOSurfaceBytesPerElement", "kIOSurfaceBytesPerRow",
             "kIOSurfacePixelFormat")
    vals = (w, h, 4, w * 4, 0x42475241)  # 'BGRA'
    keys = (C.c_void_p * 5)(*[C.c_void_p.in_dll(IOS, n).value for n in names])
    nums = (C.c_void_p * 5)(*[CF.CFNumberCreate(None, 4, C.byref(C.c_int64(v))) for v in vals])  # SInt64
    d = CF.CFDictionaryCreate(None, keys, nums, 5, C.addressof(C.c_char.in_dll(CF, "kCFTypeDictionaryKeyCallBacks")),
                              C.addressof(C.c_char.in_dll(CF, "kCFTypeDictionaryValueCallBacks")))
    s = IOS.IOSurfaceCreate(d)
    CF.CFRelease(d)
    for n in nums:
        CF.CFRelease(n)
    if not s or IOS.IOSurfaceGetBytesPerRow(s) != w * 4:  # 줄 폭이 w*4 라야 그리는 쪽의 stride 와 맞음
        raise RuntimeError("IOSurface 를 %dx%d, 줄 폭 w*4 로 못 만듦" % (w, h))
    return s


class Surface:
    def __init__(self, left, top, width, height, class_name=None):
        """left·top 은 윈도우판처럼 주 화면 왼쪽 위가 원점. class_name 은 맥에선 안 씀."""
        self.w, self.h = width, height
        frame, _ = main_screen()
        y = frame.s.h - top - height  # 코코아는 왼쪽 아래가 원점
        win = send(cls("NSWindow"), "alloc")
        win = send(win, "initWithContentRect:styleMask:backing:defer:", Rect(Point(left, y), Size(width, height)),
                   0, 2, False, argtypes=(Rect, C.c_ulong, C.c_ulong, C.c_bool))  # 테두리 없음, 버퍼드
        flag = lambda sel, v: send(win, sel, v, restype=None, argtypes=(C.c_bool,))
        flag("setOpaque:", False)
        flag("setHasShadow:", False)
        flag("setIgnoresMouseEvents:", True)
        flag("setReleasedWhenClosed:", False)
        send(win, "setBackgroundColor:", send(cls("NSColor"), "clearColor"), restype=None, argtypes=(C.c_void_p,))
        send(win, "setLevel:", STATUS_LEVEL, restype=None, argtypes=(C.c_long,))
        send(win, "setCollectionBehavior:", BEHAVIOR, restype=None, argtypes=(C.c_ulong,))
        view = send(win, "contentView")
        send(view, "setWantsLayer:", True, restype=None, argtypes=(C.c_bool,))
        self.win, self.layer = win, send(view, "layer")
        self.nbytes = width * height * 4
        self.bufs = [io_surface(width, height) for _ in range(2)]
        self._use(0)

    def _use(self, i):
        self.back = i
        self._addr = IOS.IOSurfaceGetBaseAddress(self.bufs[i])
        self.pixels = memoryview((C.c_ubyte * self.nbytes).from_address(self._addr)).cast("B")

    def clear(self):
        IOS.IOSurfaceLock(self.bufs[self.back], 0, None)
        C.memset(self._addr, 0, self.nbytes)

    def fill(self, src):
        """clear 대신 미리 칠해 둔 같은 크기 버퍼(bytes)로 통째로 덮어씀. 잠그는 것은 clear 와 같음."""
        IOS.IOSurfaceLock(self.bufs[self.back], 0, None)
        C.memmove(self._addr, src, self.nbytes)

    def present(self):
        s = self.bufs[self.back]
        IOS.IOSurfaceUnlock(s, 0, None)
        p = pool()
        send(self.layer, "setContents:", s, restype=None, argtypes=(C.c_void_p,))
        send(cls("CATransaction"), "flush", restype=None)
        drain(p)
        self._use(1 - self.back)

    def show(self, on, hide=()):  # hide: 윈도우만 씀(전체 화면 모니터 조각)
        if on:
            send(self.win, "orderFrontRegardless", restype=None)
        else:
            send(self.win, "orderOut:", None, restype=None, argtypes=(C.c_void_p,))

    def topmost(self):
        pass  # 창 수준(STATUS_LEVEL)이 이미 맨 위라 다시 올릴 일이 없음

    def pump(self):
        pump()

    def close(self):
        send(self.win, "orderOut:", None, restype=None, argtypes=(C.c_void_p,))
