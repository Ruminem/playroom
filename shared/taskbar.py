# SPDX-License-Identifier: Apache-2.0
"""작업 표시줄 위에 글자를 얹는 오버레이(sysmon)가 쓰는 것.

자리 찾기, 전체 화면 앱 알아보기, GDI 회색조 글자를 알파로 바꿔 줄마다 색 입히기.
"""
import ctypes
import sys
import time
from ctypes import wintypes
from pathlib import Path

import overlay

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


ole32, oleaut32 = ctypes.windll.ole32, ctypes.windll.oleaut32
ole32.CLSIDFromString.argtypes = (wintypes.LPCWSTR, ctypes.c_void_p)
ole32.CoCreateInstance.argtypes = (ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.c_void_p,
                                   ctypes.POINTER(ctypes.c_void_p))
ole32.CoCreateInstance.restype = ctypes.HRESULT
oleaut32.SysFreeString.argtypes = (ctypes.c_void_p,)
PTR = ctypes.POINTER(ctypes.c_void_p)


def guid(text):
    g = (ctypes.c_byte * 16)()
    ole32.CLSIDFromString(text, g)
    return g


def com(obj, index, *argtypes):
    """COM 객체의 vtable index 번째 메서드. 실패한 HRESULT 는 OSError 로 올라옴."""
    fn = ctypes.cast(obj, ctypes.POINTER(PTR))[0][index]
    return lambda *args: ctypes.WINFUNCTYPE(ctypes.HRESULT, ctypes.c_void_p, *argtypes)(fn)(obj, *args)


def ui_items(hwnd):
    """창 아래 UI 자동화 요소 전부의 (클래스 이름, (왼, 위, 오른, 아래)). 윈도우 11 작업 표시줄 단추는 XAML 이라
    Win32 창으로는 안 보이고 이걸로만 자리가 나옴. 작업 표시줄에 18개, 한 번 몇십 ms."""
    ole32.CoInitializeEx(None, 0)  # MTA. 이미 했으면 S_FALSE 라 그냥 넘어감
    uia, root, cond, arr = (ctypes.c_void_p() for _ in range(4))
    out = []
    try:
        ole32.CoCreateInstance(guid("{ff48dba4-60ef-4201-aa87-54103eef594e}"), None, 1,  # CUIAutomation
                               guid("{30cbe57d-d9d0-452a-ab13-7ac5ac4825ee}"), ctypes.byref(uia))  # IUIAutomation
        com(uia, 6, wintypes.HWND, PTR)(hwnd, ctypes.byref(root))  # ElementFromHandle
        com(uia, 21, PTR)(ctypes.byref(cond))  # CreateTrueCondition
        com(root, 6, ctypes.c_int, ctypes.c_void_p, PTR)(4, cond, ctypes.byref(arr))  # FindAll(TreeScope_Descendants)
        n = ctypes.c_int()
        com(arr, 3, ctypes.POINTER(ctypes.c_int))(ctypes.byref(n))  # get_Length
        for i in range(n.value):
            el, name, r = ctypes.c_void_p(), ctypes.c_void_p(), wintypes.RECT()
            com(arr, 4, ctypes.c_int, PTR)(i, ctypes.byref(el))  # GetElement
            try:
                com(el, 30, PTR)(ctypes.byref(name))  # get_CurrentClassName
                com(el, 43, ctypes.POINTER(wintypes.RECT))(ctypes.byref(r))  # get_CurrentBoundingRectangle
                out.append((ctypes.wstring_at(name.value) if name.value else "", (r.left, r.top, r.right, r.bottom)))
            finally:
                oleaut32.SysFreeString(name)
                com(el, 2)()  # Release
    finally:
        for p in (arr, cond, root, uia):
            if p.value:
                com(p, 2)()
    return out


def frames():
    """작업 표시줄에서 눈에 보이는 틀 [(왼, 위, 오른)] — 앱 단추 묶음, 알림 영역 단추들, 그 위에 얹힌 usage-hud ·
    sysmon 창. 작업 표시줄 테마(FrostyGlass 등)가 바탕을 투명하게 두고 이것들만 알약으로 띄우면 그 모양이 됨.
    단추 묶음을 못 찾으면 None — 그때는 모양을 모르니 작업 표시줄 윗변 전체를 바닥으로 봄.
    ponytail: 기본 작업 표시줄이면 단추 묶음이 전체 폭이라 윗변 전체와 같다고 보고 따로 안 가림(직접 못 봄)"""
    bar = user32.FindWindowW("Shell_TrayWnd", None)
    if not bar:
        return None
    try:
        items = ui_items(bar)
    except OSError:
        return None
    out = [r for c, r in items if c == "Taskbar.TaskbarFrameAutomationPeer"]
    if not out:
        return None
    tray = [r for c, r in items if c.startswith("SystemTray.")]
    if tray:  # TrayNotifyWnd 는 알약보다 왼쪽으로 12px 넓어서 단추들을 합침
        out.append((min(r[0] for r in tray), min(r[1] for r in tray), max(r[2] for r in tray), 0))
    for cls, title in ((None, "usage-hud"), ("PlayroomSysmonSurface", None)):
        h = user32.FindWindowW(cls, title)
        if h and user32.IsWindowVisible(h):
            r = wintypes.RECT()
            user32.GetWindowRect(h, ctypes.byref(r))
            out.append((r.left, r.top, r.right, 0))
    return [(l, t, r) for l, t, r, _ in out if r > l]


user32.GetTopWindow.restype = wintypes.HWND
user32.GetTopWindow.argtypes = (wintypes.HWND,)
user32.GetWindow.restype = wintypes.HWND
user32.GetWindow.argtypes = (wintypes.HWND, wintypes.UINT)
user32.GetWindowLongW.argtypes = (wintypes.HWND, ctypes.c_int)
user32.GetClassNameW.argtypes = (wintypes.HWND, wintypes.LPWSTR, ctypes.c_int)
user32.GetWindowTextW.argtypes = (wintypes.HWND, wintypes.LPWSTR, ctypes.c_int)
user32.GetWindowThreadProcessId.argtypes = (wintypes.HWND, ctypes.POINTER(wintypes.DWORD))
EX_FLAGS = ((0x8, "topmost"), (0x80, "toolwindow"), (0x80000, "layered"), (0x20, "transparent"),
            (0x08000000, "noactivate"))


def siblings(h):
    """h 부터 같은 층의 창을 앞에서 뒤 순서로."""
    while h:
        yield h
        h = user32.GetWindow(h, 2)  # GW_HWNDNEXT


def rect_of(h):
    r = wintypes.RECT()
    user32.GetWindowRect(h, ctypes.byref(r))
    return r.left, r.top, r.right, r.bottom


def class_of(h):
    buf = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(h, buf, 256)
    return buf.value


def describe(h):
    """창 한 줄: 핸들 · 클래스 · 제목 · (왼, 위, 오른, 아래) · 확장 스타일과 숨김 · exe 이름."""
    title, pid, cloaked = ctypes.create_unicode_buffer(256), wintypes.DWORD(), ctypes.c_int()
    user32.GetWindowTextW(h, title, 256)
    user32.GetWindowThreadProcessId(h, ctypes.byref(pid))
    ctypes.windll.dwmapi.DwmGetWindowAttribute(h, 14, ctypes.byref(cloaked), 4)  # DWMWA_CLOAKED
    ex = user32.GetWindowLongW(h, -20)  # GWL_EXSTYLE
    flags = [name for bit, name in EX_FLAGS if ex & bit]
    flags += ["hidden"] * (not user32.IsWindowVisible(h)) + ["cloaked"] * bool(cloaked.value)
    exe = Path(overlay.exe_of(pid.value) or "?").name
    return "%#x %r %r %s %s %s" % (h, class_of(h), title.value, rect_of(h), " ".join(flags) or "-", exe)


def report():
    """작업 표시줄 위에 무엇이 있는지 글로 — 다른 프로그램의 창을 피해 자리를 잡으려고 먼저 실물을 봄.
    작업 표시줄(모니터마다)과 그 안의 자식 창, 띠와 겹치는 보이는 최상위 창(앞에서 뒤 순서), UI 자동화 요소."""
    out = [time.strftime("%Y-%m-%d %H:%M:%S"), "windows %s" % (sys.getwindowsversion()[:3],)]
    tops = list(siblings(user32.GetTopWindow(None)))
    bars = [h for h in tops if class_of(h) in ("Shell_TrayWnd", "Shell_SecondaryTrayWnd")]
    bar_rects = [rect_of(h) for h in bars]
    out.append("\n## 작업 표시줄 %d개" % len(bars))
    for bar in bars:
        out.append(describe(bar))
        stack = [(user32.GetWindow(bar, 5), 1)]  # GW_CHILD
        while stack:  # 자식을 깊이 우선으로, 들여쓰기가 깊이
            h, depth = stack.pop()
            if h:
                out.append("  " * depth + describe(h))
                stack += [(user32.GetWindow(h, 2), depth), (user32.GetWindow(h, 5), depth + 1)]
    out.append("\nspot %s\nframes %s" % (spot(), frames()))
    out.append("\n## 띠와 겹치는 보이는 최상위 창 (앞에서 뒤)")
    hidden = 0
    for z, h in enumerate(tops):
        l, t, r, b = rect_of(h)
        if h in bars or not any(l < br and r > bl and t < bb and b > bt for bl, bt, br, bb in bar_rects):
            continue
        if user32.IsWindowVisible(h):
            out.append("z%d %s" % (z, describe(h)))
        else:
            hidden += 1
    out.append("숨은 창 %d개는 뺌" % hidden)
    main_bar = user32.FindWindowW("Shell_TrayWnd", None)
    if main_bar:
        out.append("\n## Shell_TrayWnd 의 UI 자동화 요소")
        try:
            out += ["%r %s" % item for item in ui_items(main_bar)]
        except OSError as e:
            out.append("못 읽음: %s" % e)
    return "\n".join(out) + "\n"


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
