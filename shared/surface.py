# SPDX-License-Identifier: Apache-2.0
"""픽셀마다 알파가 있는 맨 위·클릭 통과 창. tk 의 색 키는 투명/불투명 둘뿐이라 부드러운 가장자리가 안 된다.

DIB 섹션(32비트, 위에서 아래로) 하나에 premultiplied BGRA 로 그리고 UpdateLayeredWindow 로 내보낸다.
pixels 는 그 메모리를 바로 가리키는 memoryview 라 슬라이스 대입이 곧 그리기다.
창을 만든 스레드가 pump() 로 메시지를 비워 줘야 한다.
"""
import ctypes
from ctypes import wintypes

import overlay

user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32
kernel32 = ctypes.windll.kernel32

WNDPROC = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)


class WNDCLASSW(ctypes.Structure):
    _fields_ = [("style", wintypes.UINT), ("lpfnWndProc", WNDPROC), ("cbClsExtra", ctypes.c_int),
                ("cbWndExtra", ctypes.c_int), ("hInstance", wintypes.HINSTANCE), ("hIcon", wintypes.HICON),
                ("hCursor", wintypes.HANDLE), ("hbrBackground", wintypes.HBRUSH),
                ("lpszMenuName", wintypes.LPCWSTR), ("lpszClassName", wintypes.LPCWSTR)]


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [("biSize", wintypes.DWORD), ("biWidth", ctypes.c_long), ("biHeight", ctypes.c_long),
                ("biPlanes", wintypes.WORD), ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD),
                ("biSizeImage", wintypes.DWORD), ("biXPelsPerMeter", ctypes.c_long),
                ("biYPelsPerMeter", ctypes.c_long), ("biClrUsed", wintypes.DWORD),
                ("biClrImportant", wintypes.DWORD)]


class BLENDFUNCTION(ctypes.Structure):
    _fields_ = [("op", ctypes.c_ubyte), ("flags", ctypes.c_ubyte), ("alpha", ctypes.c_ubyte),
                ("fmt", ctypes.c_ubyte)]


user32.DefWindowProcW.argtypes = (wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)
user32.DefWindowProcW.restype = ctypes.c_ssize_t
user32.CreateWindowExW.argtypes = (wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD,
                                   ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.HWND,
                                   wintypes.HMENU, wintypes.HINSTANCE, wintypes.LPVOID)
user32.CreateWindowExW.restype = wintypes.HWND
user32.ShowWindow.argtypes = (wintypes.HWND, ctypes.c_int)
user32.SetWindowPos.argtypes = (wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                ctypes.c_int, wintypes.UINT)
user32.UpdateLayeredWindow.argtypes = (wintypes.HWND, wintypes.HDC, ctypes.POINTER(wintypes.POINT),
                                       ctypes.POINTER(wintypes.SIZE), wintypes.HDC,
                                       ctypes.POINTER(wintypes.POINT), wintypes.DWORD,
                                       ctypes.POINTER(BLENDFUNCTION), wintypes.DWORD)
user32.DestroyWindow.argtypes = (wintypes.HWND,)
gdi32.CreateCompatibleDC.restype = wintypes.HDC
gdi32.CreateDIBSection.restype = wintypes.HBITMAP
gdi32.CreateDIBSection.argtypes = (wintypes.HDC, ctypes.c_void_p, wintypes.UINT,
                                   ctypes.POINTER(ctypes.c_void_p), wintypes.HANDLE, wintypes.DWORD)
gdi32.SelectObject.argtypes = (wintypes.HDC, wintypes.HGDIOBJ)
kernel32.GetModuleHandleW.restype = wintypes.HMODULE

# 겹친 창 · 클릭 통과 · 작업 표시줄에 안 뜸 · 포커스 안 뺏음 · 맨 위
EX_STYLE = 0x80000 | 0x20 | 0x80 | 0x8000000 | 0x8
HWND_TOPMOST = wintypes.HWND(-1)


class Surface:
    def __init__(self, left, top, width, height, class_name):
        self.w, self.h = width, height
        hinst = kernel32.GetModuleHandleW(None)
        self._proc = WNDPROC(user32.DefWindowProcW)  # 붙들어 둬야 GC 가 콜백을 안 걷어 감
        user32.RegisterClassW(ctypes.byref(WNDCLASSW(lpfnWndProc=self._proc, hInstance=hinst,
                                                     lpszClassName=class_name)))
        self.hwnd = user32.CreateWindowExW(EX_STYLE, class_name, class_name, 0x80000000,  # WS_POPUP
                                           left, top, width, height, None, None, hinst, None)
        bih = BITMAPINFOHEADER(ctypes.sizeof(BITMAPINFOHEADER), width, -height, 1, 32, 0, 0, 0, 0, 0, 0)
        bits = ctypes.c_void_p()
        self.hdc = gdi32.CreateCompatibleDC(None)
        gdi32.SelectObject(self.hdc, gdi32.CreateDIBSection(self.hdc, ctypes.byref(bih), 0, ctypes.byref(bits),
                                                            None, 0))
        self._bits, self.nbytes = bits.value, width * height * 4
        self.pixels = memoryview((ctypes.c_ubyte * self.nbytes).from_address(self._bits)).cast("B")
        self._pos, self._size = wintypes.POINT(left, top), wintypes.SIZE(width, height)
        self._src, self._blend = wintypes.POINT(0, 0), BLENDFUNCTION(0, 0, 255, 1)  # AC_SRC_OVER, AC_SRC_ALPHA
        self._msg = wintypes.MSG()

    def clear(self):
        ctypes.memset(self._bits, 0, self.nbytes)

    def present(self):
        user32.UpdateLayeredWindow(self.hwnd, None, ctypes.byref(self._pos), ctypes.byref(self._size), self.hdc,
                                   ctypes.byref(self._src), 0, ctypes.byref(self._blend), 2)  # ULW_ALPHA

    def move(self, left, top):
        """다음 present() 부터 이 자리에 그림."""
        self._pos = wintypes.POINT(left, top)

    def view(self, left, top, sx, width):
        """다음 present() 부터 버퍼의 가로 [sx, sx + width) 만 (left, top) 에 보임. 창도 그 폭이 됨 —
        버퍼를 다시 안 만들고 보이는 폭만 바꿀 때 씀."""
        self._pos, self._src, self._size = wintypes.POINT(left, top), wintypes.POINT(sx, 0), wintypes.SIZE(width, self.h)

    def show(self, on):
        user32.ShowWindow(self.hwnd, 4 if on else 0)  # SW_SHOWNOACTIVATE · SW_HIDE

    def topmost(self):
        """다른 맨 위 창(PIP 등)이 앞을 가져가도 다시 올라옴. layers 가 떠 있으면 그쪽에 맡김."""
        if overlay.layers_running():
            return
        user32.SetWindowPos(self.hwnd, HWND_TOPMOST, 0, 0, 0, 0, 0x1 | 0x2 | 0x10)  # NOSIZE NOMOVE NOACTIVATE

    def pump(self):
        while user32.PeekMessageW(ctypes.byref(self._msg), None, 0, 0, 1):  # PM_REMOVE
            user32.DispatchMessageW(ctypes.byref(self._msg))

    def close(self):
        user32.DestroyWindow(self.hwnd)
