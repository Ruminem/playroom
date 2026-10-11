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
class ULWINFO(ctypes.Structure):  # UPDATELAYEREDWINDOWINFO — 바뀐 사각형만 넘길 때
    _fields_ = [("cbSize", wintypes.DWORD), ("hdcDst", wintypes.HDC), ("pptDst", ctypes.POINTER(wintypes.POINT)),
                ("psize", ctypes.POINTER(wintypes.SIZE)), ("hdcSrc", wintypes.HDC),
                ("pptSrc", ctypes.POINTER(wintypes.POINT)), ("crKey", wintypes.DWORD),
                ("pblend", ctypes.POINTER(BLENDFUNCTION)), ("dwFlags", wintypes.DWORD),
                ("prcDirty", ctypes.POINTER(wintypes.RECT))]


user32.UpdateLayeredWindowIndirect.argtypes = (wintypes.HWND, ctypes.POINTER(ULWINFO))
user32.UpdateLayeredWindow.argtypes = (wintypes.HWND, wintypes.HDC, ctypes.POINTER(wintypes.POINT),
                                       ctypes.POINTER(wintypes.SIZE), wintypes.HDC,
                                       ctypes.POINTER(wintypes.POINT), wintypes.DWORD,
                                       ctypes.POINTER(BLENDFUNCTION), wintypes.DWORD)
user32.DestroyWindow.argtypes = (wintypes.HWND,)
gdi32.DeleteDC.argtypes = (wintypes.HDC,)
gdi32.DeleteObject.argtypes = (wintypes.HGDIOBJ,)
user32.GetWindowLongPtrW.argtypes = (wintypes.HWND, ctypes.c_int)
user32.GetWindowLongPtrW.restype = ctypes.c_ssize_t
user32.SetWindowLongPtrW.argtypes = (wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t)
user32.SetCapture.argtypes = (wintypes.HWND,)
user32.LoadCursorW.argtypes = (wintypes.HINSTANCE, ctypes.c_void_p)
user32.LoadCursorW.restype = wintypes.HANDLE
gdi32.CreateCompatibleDC.restype = wintypes.HDC
gdi32.CreateDIBSection.restype = wintypes.HBITMAP
gdi32.CreateDIBSection.argtypes = (wintypes.HDC, ctypes.c_void_p, wintypes.UINT,
                                   ctypes.POINTER(ctypes.c_void_p), wintypes.HANDLE, wintypes.DWORD)
gdi32.SelectObject.argtypes = (wintypes.HDC, wintypes.HGDIOBJ)
kernel32.GetModuleHandleW.restype = wintypes.HMODULE

# 겹친 창 · 클릭 통과 · 작업 표시줄에 안 뜸 · 포커스 안 뺏음 · 맨 위
EX_STYLE = 0x80000 | 0x20 | 0x80 | 0x8000000 | 0x8
WS_EX_TRANSPARENT = 0x20
HWND_TOPMOST, HWND_NOTOPMOST = wintypes.HWND(-1), wintypes.HWND(-2)
WM_LBUTTONDOWN, WM_LBUTTONUP, WM_CAPTURECHANGED = 0x201, 0x202, 0x215
_procs, _owners = {}, {}  # 클래스 이름 → 등록한 창 함수(붙들어 둬야 GC 가 안 걷어 감) · 창 → 그 창의 Surface


def _route(hwnd, msg, wparam, lparam):
    """같은 클래스 이름은 처음 등록한 창 함수가 다 받음(RegisterClassW 는 두 번째부터 실패) — 창마다 제 Surface 로 보냄.
    weather 는 모니터마다 판(Surface)을 따로 만듦."""
    s = _owners.get(hwnd)
    return s._wndproc(hwnd, msg, wparam, lparam) if s else user32.DefWindowProcW(hwnd, msg, wparam, lparam)


def to_buffer(x, y, panes):
    """화면 (x, y) → 버퍼 자리. panes 는 [(화면 x, 화면 y, 버퍼 x, 버퍼 y, 폭, 높이)] — 커서가 든 창, 어느 창에도
    없으면 가장 가까운 창을 기준으로 셈(창 밖이라 버퍼 밖 값이 나옴)."""
    l, t, sx, sy, _, _ = min(panes, key=lambda p: max(p[0] - x, 0, x - p[0] - p[4] + 1) + max(p[1] - y, 0, y - p[1] - p[5] + 1))
    return x - l + sx, y - t + sy


class Surface:
    def __init__(self, left, top, width, height, class_name, on_mouse=None, panes=None):
        """on_mouse 를 주면 catch(True) 인 동안 왼쪽 단추를 on_mouse(True)·(False) 로 알림(pump 안에서, 이 스레드).
        panes 를 주면 width × height 버퍼 하나를 창 여럿에 나눠 보임: [(화면 x, 화면 y, 버퍼 x, 버퍼 y, 폭, 높이)] —
        weather 가 모니터 여럿을 이은 판. 안 주면 버퍼 전체를 (left, top) 에 창 하나로."""
        self.w, self.h = width, height
        hinst = kernel32.GetModuleHandleW(None)
        self.on_mouse = on_mouse
        if class_name not in _procs:  # 마우스를 안 받는 창은 파이썬을 안 거침
            _procs[class_name] = WNDPROC(_route if on_mouse else user32.DefWindowProcW)
            hand = user32.LoadCursorW(None, 32649) if on_mouse else None  # IDC_HAND — 집을 수 있는 자리에서만 보임
            user32.RegisterClassW(ctypes.byref(WNDCLASSW(lpfnWndProc=_procs[class_name], hInstance=hinst, hCursor=hand,
                                                         lpszClassName=class_name)))
        self._panes = []  # [창, 화면 자리, 버퍼 자리, 크기]. 하나일 때 move · view 가 고침
        for l, t, sx, sy, pw, ph in panes or [(left, top, 0, 0, width, height)]:
            h = user32.CreateWindowExW(EX_STYLE, class_name, class_name, 0x80000000,  # WS_POPUP
                                       l, t, pw, ph, None, None, hinst, None)
            _owners[h] = self
            self._panes.append([h, wintypes.POINT(l, t), wintypes.POINT(sx, sy), wintypes.SIZE(pw, ph)])
        self.hwnd = self._panes[0][0]
        bih = BITMAPINFOHEADER(ctypes.sizeof(BITMAPINFOHEADER), width, -height, 1, 32, 0, 0, 0, 0, 0, 0)
        bits = ctypes.c_void_p()
        self.hdc = gdi32.CreateCompatibleDC(None)
        self._bmp = gdi32.CreateDIBSection(self.hdc, ctypes.byref(bih), 0, ctypes.byref(bits), None, 0)
        gdi32.SelectObject(self.hdc, self._bmp)
        self._bits, self.nbytes = bits.value, width * height * 4
        self.pixels = memoryview((ctypes.c_ubyte * self.nbytes).from_address(self._bits)).cast("B")
        self._blend = BLENDFUNCTION(0, 0, 255, 1)  # AC_SRC_OVER, AC_SRC_ALPHA
        self._msg = wintypes.MSG()

    def clear(self, top=0):
        """top 행부터 아래를 지움."""
        ctypes.memset(self._bits + top * self.w * 4, 0, self.nbytes - top * self.w * 4)

    def fill(self, src):
        """clear 대신 미리 칠해 둔 같은 크기 버퍼(bytes)로 통째로 덮어씀 — weather 어항의 물빛."""
        ctypes.memmove(self._bits, src, self.nbytes)

    def present(self, top=0):
        """top 을 주면 그 행부터 아래만 바뀌었다고 알림 — 위쪽은 화면에 남은 그대로 두고, 넘기는 양이 그만큼 줆
        (2560×1392 통째 한 번 1.2ms CPU, 작은 사각형은 거의 0)."""
        for hwnd, pos, src, size in self._panes:
            if not top:
                user32.UpdateLayeredWindow(hwnd, None, ctypes.byref(pos), ctypes.byref(size), self.hdc,
                                           ctypes.byref(src), 0, ctypes.byref(self._blend), 2)  # ULW_ALPHA
                continue
            dirty = wintypes.RECT(0, max(0, top - src.y), size.cx, size.cy)  # 창 기준. 위가 잘린 창은 그만큼 덜 내려옴
            info = ULWINFO(ctypes.sizeof(ULWINFO), None, ctypes.pointer(pos), ctypes.pointer(size), self.hdc,
                           ctypes.pointer(src), 0, ctypes.pointer(self._blend), 2, ctypes.pointer(dirty))
            user32.UpdateLayeredWindowIndirect(hwnd, ctypes.byref(info))

    def move(self, left, top):
        """다음 present() 부터 이 자리에 그림. 창 하나일 때만."""
        self._panes[0][1] = wintypes.POINT(left, top)

    def view(self, left, top, sx, width, sy=0, height=None):
        """다음 present() 부터 버퍼의 [sx, sx + width) × [sy, sy + height) 만 (left, top) 에 보임. 창도 그 크기가 됨 —
        버퍼를 다시 안 만들고 보이는 크기만 바꿀 때 씀. 창이 그린 것에 꼭 맞아야 weather 가 그 위에 눈을 얹음. 창 하나일 때만."""
        self._panes[0][1:] = [wintypes.POINT(left, top), wintypes.POINT(sx, sy),
                              wintypes.SIZE(width, self.h - sy if height is None else height)]

    def show(self, on, hide=()):
        """hide 는 on 이어도 숨길 창 조각 번호들(전체 화면 앱이 뜬 모니터의 조각)."""
        for i, p in enumerate(self._panes):
            user32.ShowWindow(p[0], 4 if on and i not in hide else 0)  # SW_SHOWNOACTIVATE · SW_HIDE

    def topmost(self, on=True):
        """다른 맨 위 창(PIP 등)이 앞을 가져가도 다시 올라옴. layers 가 떠 있으면 그쪽에 맡김.
        on=False 는 맨 위에서 내림('항상 위' 끔). 부를 때마다 보통 창들 맨 앞으로 오므로 뜰 때 한 번만 부름."""
        if on and overlay.layers_running():
            return
        for p in self._panes:
            user32.SetWindowPos(p[0], HWND_TOPMOST if on else HWND_NOTOPMOST, 0, 0, 0, 0, 0x1 | 0x2 | 0x10)  # NOSIZE NOMOVE NOACTIVATE

    def catch(self, on):
        """on 이면 클릭을 받음(WS_EX_TRANSPARENT 를 뺌). 그래도 알파 0 인 픽셀은 겹친 창이라 아래 창으로 감.
        바뀔 때만 부름 — 다른 비트(맨 위 등)는 그대로 둠."""
        for p in self._panes:
            ex = user32.GetWindowLongPtrW(p[0], -20)  # GWL_EXSTYLE
            user32.SetWindowLongPtrW(p[0], -20, ex & ~WS_EX_TRANSPARENT if on else ex | WS_EX_TRANSPARENT)

    def cursor(self):
        """마우스 커서 자리. 창 하나면 그 창 왼쪽 위 기준 px, 여럿이면 버퍼 기준(to_buffer). 한 번 1.3µs."""
        pt = wintypes.POINT()
        user32.GetCursorPos(ctypes.byref(pt))
        if len(self._panes) == 1:
            pos = self._panes[0][1]
            return pt.x - pos.x, pt.y - pos.y
        return to_buffer(pt.x, pt.y, [(p.x, p.y, s.x, s.y, z.cx, z.cy) for _, p, s, z in self._panes])

    def hovered(self):
        """커서가 지금 보이는 창 안에 있으면 True. 창 하나일 때만."""
        x, y = self.cursor()
        size = self._panes[0][3]
        return 0 <= x < size.cx and 0 <= y < size.cy

    def fade(self, on):
        """on 이면 창 전체를 HOVER_ALPHA 로 흐리게, 아니면 원래대로. 다음 present() 부터. 바뀌었으면 True."""
        alpha = overlay.HOVER_ALPHA if on else 255
        if self._blend.alpha == alpha:
            return False
        self._blend.alpha = alpha
        return True

    def _wndproc(self, hwnd, msg, wparam, lparam):
        if msg == WM_LBUTTONDOWN:
            user32.SetCapture(hwnd)  # 끄는 동안 커서가 동물 밖으로 나가도 뗀 것을 받음
            self.on_mouse(True)
            return 0
        if msg in (WM_LBUTTONUP, WM_CAPTURECHANGED):  # 떼면 ReleaseCapture 가 CAPTURECHANGED 를 또 부름 — 두 번 와도 됨
            if msg == WM_LBUTTONUP:
                user32.ReleaseCapture()
            self.on_mouse(False)
            return 0
        return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

    def pump(self):
        while user32.PeekMessageW(ctypes.byref(self._msg), None, 0, 0, 1):  # PM_REMOVE
            user32.DispatchMessageW(ctypes.byref(self._msg))

    def close(self):
        """창과 버퍼를 치움 — weather 는 모니터가 바뀔 때마다 판을 새로 만들어서 안 치우면 버퍼(2560×1440 에 15MB)가 샘.
        닫은 뒤엔 pixels 를 만지면 안 됨."""
        for p in self._panes:
            _owners.pop(p[0], None)
            user32.DestroyWindow(p[0])
        gdi32.DeleteDC(self.hdc)
        gdi32.DeleteObject(self._bmp)
