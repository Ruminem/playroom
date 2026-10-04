# SPDX-License-Identifier: Apache-2.0
"""작업 표시줄 위에 글자를 얹는 오버레이(sysmon)가 쓰는 것.

자리 찾기, 전체 화면 앱 알아보기, GDI 회색조 글자를 알파로 바꿔 줄마다 색 입히기.
"""
import ctypes
from ctypes import wintypes

user32, gdi32 = ctypes.windll.user32, ctypes.windll.gdi32
user32.FindWindowW.restype = wintypes.HWND
user32.FindWindowExW.restype = wintypes.HWND
user32.FindWindowExW.argtypes = (wintypes.HWND, wintypes.HWND, wintypes.LPCWSTR, wintypes.LPCWSTR)
user32.GetWindowRect.argtypes = (wintypes.HWND, ctypes.POINTER(wintypes.RECT))
user32.IsWindowVisible.argtypes = (wintypes.HWND,)
user32.DrawTextW.argtypes = (wintypes.HDC, wintypes.LPCWSTR, ctypes.c_int, ctypes.POINTER(wintypes.RECT),
                             wintypes.UINT)
user32.GetDC.restype = wintypes.HDC
user32.GetDC.argtypes = (wintypes.HWND,)
user32.ReleaseDC.argtypes = (wintypes.HWND, wintypes.HDC)
gdi32.CreateFontW.restype = wintypes.HFONT
gdi32.SelectObject.restype = wintypes.HGDIOBJ
gdi32.SelectObject.argtypes = (wintypes.HDC, wintypes.HGDIOBJ)
gdi32.SetTextColor.argtypes = (wintypes.HDC, wintypes.DWORD)
gdi32.SetBkMode.argtypes = (wintypes.HDC, ctypes.c_int)
gdi32.GetTextExtentPoint32W.argtypes = (wintypes.HDC, wintypes.LPCWSTR, ctypes.c_int, ctypes.POINTER(wintypes.SIZE))
gdi32.DeleteObject.argtypes = (wintypes.HGDIOBJ,)


def fullscreen_app():
    """전체 화면 앱(영상·게임·발표)이 앞에 있으면 True. 그때는 작업 표시줄도 사라짐."""
    state = ctypes.c_int()
    if ctypes.windll.shell32.SHQueryUserNotificationState(ctypes.byref(state)) != 0:
        return False
    return state.value in (2, 3, 4)  # QUNS_BUSY · RUNNING_D3D_FULL_SCREEN · PRESENTATION_MODE


def spot():
    """(알림 영역 왼쪽 끝 x, 작업 표시줄 위 y, 높이). 못 찾으면 None.
    ponytail: 아래쪽 작업 표시줄만 셈. 자동 숨기기·세로 작업 표시줄은 안 따짐"""
    bar = user32.FindWindowW("Shell_TrayWnd", None)
    notify = user32.FindWindowExW(bar, None, "TrayNotifyWnd", None) if bar else None
    if not notify:
        return None
    b, n = wintypes.RECT(), wintypes.RECT()
    user32.GetWindowRect(bar, ctypes.byref(b))
    user32.GetWindowRect(notify, ctypes.byref(n))
    return n.left, b.top, b.bottom - b.top


def window_left(class_name):
    """그 클래스의 창이 보이면 왼쪽 끝 x, 아니면 None. 옆 오버레이 왼쪽에 붙을 때 씀."""
    h = user32.FindWindowW(class_name, None)
    if not h or not user32.IsWindowVisible(h):
        return None
    r = wintypes.RECT()
    user32.GetWindowRect(h, ctypes.byref(r))
    return r.left


def font(bar_h):
    # ANTIALIASED_QUALITY: 회색조라 R=G=B=덮인 정도. ClearType 이면 색 번짐이 남음
    return gdi32.CreateFontW(-round(bar_h * 0.36), 0, 0, 0, 600, 0, 0, 0, 1, 0, 0, 4, 0, "Segoe UI")


def text_width(fnt, texts):
    """이 글꼴로 그린 가장 긴 줄의 너비 px."""
    dc = user32.GetDC(None)
    old = gdi32.SelectObject(dc, fnt)
    size, widest = wintypes.SIZE(), 0
    for t in texts:
        gdi32.GetTextExtentPoint32W(dc, t, len(t), ctypes.byref(size))
        widest = max(widest, size.cx)
    gdi32.SelectObject(dc, old)
    user32.ReleaseDC(None, dc)
    return widest


def prepare(surface, fnt):
    """surface 의 DC 에 글꼴과 흰 글자·투명 배경을 걸어 둠. 한 번만 부르면 됨."""
    gdi32.SelectObject(surface.hdc, fnt)
    gdi32.SetTextColor(surface.hdc, 0xFFFFFF)
    gdi32.SetBkMode(surface.hdc, 1)  # TRANSPARENT


def paint_lines(surface, lines, line_h):
    """[(글, (r, g, b)), …] 를 세로 가운데에 오른쪽 맞춰 그림.
    글자를 흰색으로 그린 뒤 밝기(초록 칸)를 알파로 삼아 줄마다 색을 입힌다."""
    s, w = surface, surface.w
    s.clear()
    top = (s.h - len(lines) * line_h) // 2
    for i, (text, _) in enumerate(lines):
        r = wintypes.RECT(0, top + i * line_h, w - 2, top + (i + 1) * line_h)
        user32.DrawTextW(s.hdc, text, -1, ctypes.byref(r), 0x2 | 0x20)  # DT_RIGHT | DT_SINGLELINE
    gdi32.GdiFlush()
    px = s.pixels
    for i, (_, (cr, cg, cb)) in enumerate(lines):
        for o in range((top + i * line_h) * w * 4, (top + (i + 1) * line_h) * w * 4, 4):
            a = px[o + 1]
            if a:
                px[o:o + 4] = bytes((cb * a // 255, cg * a // 255, cr * a // 255, a))
