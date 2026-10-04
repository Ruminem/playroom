# SPDX-License-Identifier: Apache-2.0
"""작업 표시줄 오른쪽, 알림 영역 바로 왼쪽에 CPU·메모리 사용률을 두 줄로 띄운다.

  pythonw sysmon.py            띄우기 (창 없이 뒤에서 돎)
  python sysmon.py --toggle    떠 있으면 치우고, 없으면 띄움 (sysmon.bat 이 이걸 부름)
  python sysmon.py --stop      치우기
  python sysmon.py --check     자체 점검

작업 표시줄 위에 얹은 맨 위·클릭 통과 알파 창(shared/surface.py)이다. 글자는 GDI 로 흰색 회색조
안티에일리어싱으로 그린 뒤 밝기를 알파로 바꿔 색을 입힌다. 1초마다 다시 재고, 트레이 아이콘이
늘거나 줄면 따라 옮기며, 전체 화면 앱이 돌면 숨는다. 끝내기는 트레이의 막대 아이콘 메뉴에서 한다.
"""
import argparse
import ctypes
import os
import queue
import subprocess
import sys
import tempfile
import time
from ctypes import wintypes
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "shared"))
import overlay
from surface import Surface
from tray import Tray, write_ico

PID_FILE = Path(tempfile.gettempdir()) / "playroom-sysmon.pid"
ICON_FILE = Path(tempfile.gettempdir()) / "playroom-sysmon.ico"
TRAY_CLASS = "PlayroomSysmonTray"
SURFACE_CLASS = "PlayroomSysmonSurface"

GAP = 8            # 알림 영역과 띄울 px
WARN, HOT = 70, 90  # 이 % 를 넘으면 주황, 빨강
WHITE, ORANGE, RED = (255, 255, 255), (254, 174, 52), (228, 59, 68)
EXIT = 99

ICON_COLORS = {"g": "#63c74d", "y": "#feae34"}
ICON = (".......",
        ".....g.",
        ".....g.",
        "...g.g.",
        "...g.g.",
        ".y.g.g.",
        ".y.g.g.")

user32, gdi32, kernel32 = ctypes.windll.user32, ctypes.windll.gdi32, ctypes.windll.kernel32
user32.FindWindowW.restype = wintypes.HWND
user32.FindWindowExW.restype = wintypes.HWND
user32.FindWindowExW.argtypes = (wintypes.HWND, wintypes.HWND, wintypes.LPCWSTR, wintypes.LPCWSTR)
user32.GetWindowRect.argtypes = (wintypes.HWND, ctypes.POINTER(wintypes.RECT))
user32.DrawTextW.argtypes = (wintypes.HDC, wintypes.LPCWSTR, ctypes.c_int, ctypes.POINTER(wintypes.RECT),
                             wintypes.UINT)
gdi32.CreateFontW.restype = wintypes.HFONT
gdi32.SetTextColor.argtypes = (wintypes.HDC, wintypes.DWORD)
gdi32.SetBkMode.argtypes = (wintypes.HDC, ctypes.c_int)


class MEMORYSTATUSEX(ctypes.Structure):
    _fields_ = [("dwLength", wintypes.DWORD), ("dwMemoryLoad", wintypes.DWORD),
                ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]


def cpu_times():
    """(쉰 시간, 전체 시간). GetSystemTimes 의 커널 시간에는 쉰 시간이 들어 있다."""
    idle, kern, user = wintypes.FILETIME(), wintypes.FILETIME(), wintypes.FILETIME()
    kernel32.GetSystemTimes(ctypes.byref(idle), ctypes.byref(kern), ctypes.byref(user))
    v = lambda f: f.dwHighDateTime << 32 | f.dwLowDateTime
    return v(idle), v(kern) + v(user)


def cpu_percent(prev, cur):
    total = cur[1] - prev[1]
    if total <= 0:
        return 0
    return max(0, min(100, round(100 * (1 - (cur[0] - prev[0]) / total))))


def memory():
    """(사용률 %, 쓰는 GB, 전체 GB)."""
    m = MEMORYSTATUSEX(dwLength=ctypes.sizeof(MEMORYSTATUSEX))
    kernel32.GlobalMemoryStatusEx(ctypes.byref(m))
    gb = 1024 ** 3
    return m.dwMemoryLoad, (m.ullTotalPhys - m.ullAvailPhys) / gb, m.ullTotalPhys / gb


def level_color(p):
    return RED if p > HOT else ORANGE if p > WARN else WHITE


def fullscreen_app():
    """전체 화면 앱(영상·게임·발표)이 앞에 있으면 True. 그때는 작업 표시줄도 사라짐."""
    state = ctypes.c_int()
    if ctypes.windll.shell32.SHQueryUserNotificationState(ctypes.byref(state)) != 0:
        return False
    return state.value in (2, 3, 4)  # QUNS_BUSY · RUNNING_D3D_FULL_SCREEN · PRESENTATION_MODE


def taskbar_spot():
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


class Monitor:
    def __init__(self):
        spot = taskbar_spot()
        x, top, self.bar_h = spot or (overlay.work_area()[2], overlay.work_area()[3], 48)
        h = self.bar_h
        self.w, self.h = round(h * 2.3), h
        self.line = round(h * 0.44)
        self.surface = Surface(x - GAP - self.w, top, self.w, self.h, SURFACE_CLASS)
        hdc = self.surface.hdc
        # ANTIALIASED_QUALITY: 회색조라 R=G=B=덮인 정도. ClearType 이면 색 번짐이 남음
        gdi32.SelectObject(hdc, gdi32.CreateFontW(-round(h * 0.36), 0, 0, 0, 600, 0, 0, 0, 1, 0, 0, 4, 0,
                                                  "Segoe UI"))
        gdi32.SetTextColor(hdc, 0xFFFFFF)
        gdi32.SetBkMode(hdc, 1)  # TRANSPARENT
        self.commands = queue.Queue()
        write_ico(ICON_FILE, ICON, ICON_COLORS)
        self.tray = Tray(TRAY_CLASS, ICON_FILE, "CPU·메모리", self.menu, self.commands.put)
        self.shown, self.last_lines, self.where = None, None, None
        self.prev = cpu_times()

    def menu(self):
        return [("끝내기", EXIT, False)]

    def render(self, lines):
        """글자를 흰색으로 그린 뒤, 밝기(초록 칸)를 알파로 삼아 줄마다 색을 입힌다."""
        s, w = self.surface, self.w
        s.clear()
        top = (self.h - 2 * self.line) // 2
        for i, (text, _) in enumerate(lines):
            r = wintypes.RECT(0, top + i * self.line, w - 2, top + (i + 1) * self.line)
            user32.DrawTextW(s.hdc, text, -1, ctypes.byref(r), 0x2 | 0x20)  # DT_RIGHT | DT_SINGLELINE
        gdi32.GdiFlush()
        px = s.pixels
        for i, (_, (cr, cg, cb)) in enumerate(lines):
            for o in range((top + i * self.line) * w * 4, (top + (i + 1) * self.line) * w * 4, 4):
                a = px[o + 1]
                if a:
                    px[o:o + 4] = bytes((cb * a // 255, cg * a // 255, cr * a // 255, a))

    def update(self):
        cur = cpu_times()
        cpu, self.prev = cpu_percent(self.prev, cur), cur
        mem, used, total = memory()
        self.tray.set_tip("CPU %d%%\n메모리 %.1f / %.1f GB (%d%%)" % (cpu, used, total, mem))
        show = not fullscreen_app()
        if show != self.shown:
            self.shown = show
            self.surface.show(show)
        if not show:
            return
        spot = taskbar_spot()
        if spot and spot[:2] != self.where:  # 트레이 아이콘이 늘거나 줄면 따라감
            self.where = spot[:2]
            self.surface.move(spot[0] - GAP - self.w, spot[1])
        lines = [("CPU %d%%" % cpu, level_color(cpu)), ("MEM %d%%" % mem, level_color(mem))]
        if lines != self.last_lines:
            self.last_lines = lines
            self.render(lines)
        self.surface.present()
        self.surface.topmost()  # 작업 표시줄을 누르면 그쪽이 앞으로 오므로 1초마다 다시 올라옴

    def run(self):
        next_update = 0.0
        while True:
            self.surface.pump()
            try:
                if self.commands.get_nowait() in (None, EXIT):
                    if self.tray.hwnd:
                        self.tray.close()  # 아이콘을 지우고 나면 None 이 다시 옴
                        continue
                    break
            except queue.Empty:
                pass
            now = time.monotonic()
            if now >= next_update:
                next_update = now + 1
                self.update()
            time.sleep(0.1)
        self.surface.close()


def check():
    assert cpu_percent((100, 1000), (150, 1100)) == 50
    assert cpu_percent((100, 1000), (200, 1100)) == 0, "다 쉬었으면 0"
    assert cpu_percent((100, 1000), (100, 1100)) == 100, "하나도 안 쉬었으면 100"
    assert cpu_percent((100, 1000), (100, 1000)) == 0, "시간이 안 흘렀으면 0"
    assert level_color(WARN) == WHITE and level_color(WARN + 1) == ORANGE and level_color(HOT + 1) == RED
    a = cpu_times()
    time.sleep(0.2)
    assert 0 <= cpu_percent(a, cpu_times()) <= 100
    mem, used, total = memory()
    assert 0 < mem <= 100 and 0 < used < total
    print("자체 점검 통과")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--stop", action="store_true", help="떠 있는 것을 치움")
    ap.add_argument("--toggle", action="store_true", help="떠 있으면 치우고, 없으면 띄움")
    ap.add_argument("--check", action="store_true", help="자체 점검")
    args = ap.parse_args()
    if args.check:
        check()
        return
    if args.stop:
        print("치움" if overlay.stop(PID_FILE, TRAY_CLASS) else "떠 있는 것이 없음")
        return
    if overlay.running_pid(PID_FILE) is not None:
        if args.toggle:
            overlay.stop(PID_FILE, TRAY_CLASS)
        return
    if args.toggle and Path(sys.executable).name.lower() == "python.exe":
        # sysmon.bat 에서 콘솔 창이 남지 않게 pythonw 로 다시 띄움
        pythonw = Path(sys.executable).with_name("pythonw.exe")
        if pythonw.exists():
            subprocess.Popen([str(pythonw), str(Path(__file__).resolve())], close_fds=True)
            return
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)  # 배율 높은 화면에서 흐려지지 않게
    except (AttributeError, OSError):
        pass
    PID_FILE.write_text(str(os.getpid()))
    try:
        Monitor().run()
    finally:
        if overlay.running_pid(PID_FILE) == os.getpid():
            PID_FILE.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
