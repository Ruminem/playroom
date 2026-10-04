# SPDX-License-Identifier: Apache-2.0
"""작업 표시줄 알림 영역(트레이) 아이콘과 오른쪽 클릭 메뉴. ctypes 로 Shell_NotifyIconW 를 직접 부른다.

pystray 는 LGPL 이라 들이지 않았다. 트레이는 제 스레드에서 숨은 창 하나와 메시지 루프를 돌리고,
메뉴에서 고른 명령은 on_command(id) 로 넘긴다 — tk 처럼 스레드를 가리는 쪽은 받은 것을 큐에 넣어
제 스레드에서 처리한다. 루프가 끝나면(끝내기·WM_CLOSE) on_command(None) 을 한 번 부른다.
"""
import ctypes
import struct
import threading
from ctypes import wintypes

user32 = ctypes.windll.user32
shell32 = ctypes.windll.shell32
kernel32 = ctypes.windll.kernel32

LRESULT = ctypes.c_ssize_t
WNDPROC = ctypes.WINFUNCTYPE(LRESULT, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)

WM_DESTROY, WM_CLOSE, WM_NULL, WM_USER = 0x0002, 0x0010, 0x0000, 0x0400
WM_LBUTTONUP, WM_RBUTTONUP = 0x0202, 0x0205
WM_TRAY = WM_USER + 1
NIM_ADD, NIM_MODIFY, NIM_DELETE = 0, 1, 2
NIF_MESSAGE, NIF_ICON, NIF_TIP = 1, 2, 4
MF_STRING, MF_POPUP, MF_SEPARATOR, MF_CHECKED = 0x0, 0x10, 0x800, 0x8
TPM_RIGHTBUTTON, TPM_RETURNCMD = 0x2, 0x100


class WNDCLASSW(ctypes.Structure):
    _fields_ = [("style", wintypes.UINT), ("lpfnWndProc", WNDPROC), ("cbClsExtra", ctypes.c_int),
                ("cbWndExtra", ctypes.c_int), ("hInstance", wintypes.HINSTANCE), ("hIcon", wintypes.HICON),
                ("hCursor", wintypes.HANDLE), ("hbrBackground", wintypes.HBRUSH),
                ("lpszMenuName", wintypes.LPCWSTR), ("lpszClassName", wintypes.LPCWSTR)]


class NOTIFYICONDATAW(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.DWORD), ("hWnd", wintypes.HWND), ("uID", wintypes.UINT),
                ("uFlags", wintypes.UINT), ("uCallbackMessage", wintypes.UINT), ("hIcon", wintypes.HICON),
                ("szTip", wintypes.WCHAR * 128), ("dwState", wintypes.DWORD), ("dwStateMask", wintypes.DWORD),
                ("szInfo", wintypes.WCHAR * 256), ("uVersion", wintypes.UINT),
                ("szInfoTitle", wintypes.WCHAR * 64), ("dwInfoFlags", wintypes.DWORD),
                ("guidItem", ctypes.c_byte * 16), ("hBalloonIcon", wintypes.HICON)]


# 64비트에서 핸들이 잘리지 않게 포인터 크기 인자는 타입을 박아 둔다
user32.DefWindowProcW.argtypes = (wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)
user32.DefWindowProcW.restype = LRESULT
user32.CreateWindowExW.argtypes = (wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD,
                                   ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.HWND,
                                   wintypes.HMENU, wintypes.HINSTANCE, wintypes.LPVOID)
user32.CreateWindowExW.restype = wintypes.HWND
user32.FindWindowW.restype = wintypes.HWND
user32.PostMessageW.argtypes = (wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)
user32.CreatePopupMenu.restype = wintypes.HMENU
user32.AppendMenuW.argtypes = (wintypes.HMENU, wintypes.UINT, ctypes.c_size_t, wintypes.LPCWSTR)
user32.TrackPopupMenu.argtypes = (wintypes.HMENU, wintypes.UINT, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                  wintypes.HWND, wintypes.LPVOID)
user32.DestroyMenu.argtypes = (wintypes.HMENU,)
user32.SetForegroundWindow.argtypes = (wintypes.HWND,)
user32.DestroyWindow.argtypes = (wintypes.HWND,)
user32.LoadImageW.argtypes = (wintypes.HINSTANCE, wintypes.LPCWSTR, wintypes.UINT, ctypes.c_int, ctypes.c_int,
                              wintypes.UINT)
user32.LoadImageW.restype = wintypes.HANDLE
kernel32.GetModuleHandleW.restype = wintypes.HMODULE
shell32.Shell_NotifyIconW.argtypes = (wintypes.DWORD, ctypes.POINTER(NOTIFYICONDATAW))


def write_ico(path, art, colors, sizes=(16, 20, 24, 32, 40, 48)):
    """픽셀 그림(글자 하나 = 색 하나, '.' = 비움)을 크기 여러 벌짜리 .ico 로. 32비트 BGRA.

    윈도우가 화면 배율에 맞는 크기를 골라 가므로, 정수배로 키운 벌을 여럿 넣어 흐려지지 않게 한다.
    """
    n = len(art)
    blobs = []
    for size in sizes:
        k = size // n
        off = (size - n * k) // 2
        xor = bytearray()
        for y in reversed(range(size)):  # BMP 는 아래 줄부터
            for x in range(size):
                ax, ay = (x - off) // k, (y - off) // k
                c = art[ay][ax] if off <= x < off + n * k and off <= y < off + n * k else "."
                if c == ".":
                    xor += b"\0\0\0\0"
                else:
                    r, g, b = (int(colors[c][i:i + 2], 16) for i in (1, 3, 5))
                    xor += bytes((b, g, r, 255))
        mask = bytes(((size + 31) // 32) * 4 * size)  # 알파를 쓰므로 AND 마스크는 다 0
        head = struct.pack("<IiiHHIIiiII", 40, size, size * 2, 1, 32, 0, len(xor) + len(mask), 0, 0, 0, 0)
        blobs.append(head + bytes(xor) + mask)
    out = struct.pack("<HHH", 0, 1, len(sizes))
    offset = 6 + 16 * len(sizes)
    for size, blob in zip(sizes, blobs):
        out += struct.pack("<BBBBHHII", size % 256, size % 256, 0, 0, 1, 32, len(blob), offset)
        offset += len(blob)
    with open(path, "wb") as f:
        f.write(out + b"".join(blobs))


class Tray:
    """menu() 는 메뉴를 열 때마다 불린다. 항목: (글, id, 체크?) · (글, [하위 항목]) · None(구분선)."""

    def __init__(self, class_name, icon_path, tip, menu, on_command):
        self.class_name, self.icon_path, self.tip = class_name, str(icon_path), tip
        self.menu, self.on_command = menu, on_command
        self.hwnd = None
        self.ready = threading.Event()
        threading.Thread(target=self._run, daemon=True).start()
        self.ready.wait(5)

    def _data(self, flags):
        nid = NOTIFYICONDATAW()
        nid.cbSize = ctypes.sizeof(NOTIFYICONDATAW)
        nid.hWnd, nid.uID, nid.uFlags = self.hwnd, 1, flags
        nid.uCallbackMessage, nid.hIcon = WM_TRAY, self.hicon
        nid.szTip = self.tip[:127]
        return nid

    def set_tip(self, tip):
        """아무 스레드에서나 불러도 된다 — Shell_NotifyIconW 는 창 핸들만 본다."""
        self.tip = tip
        if self.hwnd:
            shell32.Shell_NotifyIconW(NIM_MODIFY, ctypes.byref(self._data(NIF_TIP)))

    def close(self):
        if self.hwnd:
            user32.PostMessageW(self.hwnd, WM_CLOSE, 0, 0)

    def _run(self):
        hinst = kernel32.GetModuleHandleW(None)
        self._proc = WNDPROC(self._wndproc)  # 붙들어 둬야 GC 가 콜백을 안 걷어 감
        wc = WNDCLASSW(lpfnWndProc=self._proc, hInstance=hinst, lpszClassName=self.class_name)
        user32.RegisterClassW(ctypes.byref(wc))
        # 탐색기가 다시 뜨면(작업 표시줄 재시작) 이 메시지가 오고, 아이콘을 다시 넣어야 한다.
        # 메시지 전용 창은 이 방송을 못 받으므로 보이지 않는 보통 창을 쓴다
        self.taskbar_created = user32.RegisterWindowMessageW("TaskbarCreated")
        self.hwnd = user32.CreateWindowExW(0, self.class_name, self.class_name, 0, 0, 0, 0, 0,
                                           None, None, hinst, None)
        sm = user32.GetSystemMetrics(49)  # SM_CXSMICON — 배율이 반영된 작은 아이콘 크기
        self.hicon = user32.LoadImageW(None, self.icon_path, 1, sm, sm, 0x10)  # IMAGE_ICON, LR_LOADFROMFILE
        shell32.Shell_NotifyIconW(NIM_ADD, ctypes.byref(self._data(NIF_MESSAGE | NIF_ICON | NIF_TIP)))
        self.ready.set()
        msg = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))
        self.hwnd = None
        self.on_command(None)

    def _wndproc(self, hwnd, msg, wparam, lparam):
        if msg == WM_TRAY and lparam in (WM_LBUTTONUP, WM_RBUTTONUP):
            self._popup()
            return 0
        if msg == self.taskbar_created:
            shell32.Shell_NotifyIconW(NIM_ADD, ctypes.byref(self._data(NIF_MESSAGE | NIF_ICON | NIF_TIP)))
            return 0
        if msg == WM_CLOSE:
            shell32.Shell_NotifyIconW(NIM_DELETE, ctypes.byref(self._data(0)))
            user32.DestroyWindow(hwnd)
            return 0
        if msg == WM_DESTROY:
            user32.PostQuitMessage(0)
            return 0
        return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

    def _build(self, items):
        h = user32.CreatePopupMenu()
        for item in items:
            if item is None:
                user32.AppendMenuW(h, MF_SEPARATOR, 0, None)
            elif isinstance(item[1], list):
                user32.AppendMenuW(h, MF_POPUP, self._build(item[1]), item[0])
            else:
                label, cid, checked = item
                user32.AppendMenuW(h, MF_STRING | (MF_CHECKED if checked else 0), cid, label)
        return h

    def _popup(self):
        pt = wintypes.POINT()
        user32.GetCursorPos(ctypes.byref(pt))
        menu = self._build(self.menu())
        # 메뉴 밖을 눌렀을 때 닫히려면 먼저 이 창이 앞에 와야 하고, 뒤에 WM_NULL 을 보내야 한다
        # (TrackPopupMenu 문서의 비고에 적힌 우회)
        user32.SetForegroundWindow(self.hwnd)
        cid = user32.TrackPopupMenu(menu, TPM_RIGHTBUTTON | TPM_RETURNCMD, pt.x, pt.y, 0, self.hwnd, None)
        user32.PostMessageW(self.hwnd, WM_NULL, 0, 0)
        user32.DestroyMenu(menu)  # 하위 메뉴도 같이 지워짐
        if cid:
            self.on_command(cid)
