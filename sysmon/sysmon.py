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
import json
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
import startup
import taskbar
from surface import Surface
from tray import Tray, write_ico

PID_FILE = Path(tempfile.gettempdir()) / "playroom-sysmon.pid"
ICON_FILE = Path(tempfile.gettempdir()) / "playroom-sysmon.ico"
TRAY_CLASS = "PlayroomSysmonTray"
SURFACE_CLASS = "PlayroomSysmonSurface"
SETTINGS = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "playroom" / "sysmon.json"

GAP = 8            # 알림 영역과 띄울 px
WARN, HOT = 70, 90  # 이 % 를 넘으면 주황, 빨강
WHITE, ORANGE, RED = (255, 255, 255), (254, 174, 52), (228, 59, 68)
AUTOSTART, EXIT = 50, 99
RUN_NAME = "PlayroomSysmon"
# 메모리 줄 모양: id → (키, 메뉴 글). 글자 색은 어느 모양이든 사용률로 정함
MEM_MODES = {60: ("pct", "퍼센트 (MEM 22%)"), 61: ("gb", "용량 (MEM 14.2/63.9G)"), 62: ("both", "둘 다 (MEM 14.2/63.9G 22%)")}
MEM_KEYS = {key for key, _ in MEM_MODES.values()}

ICON_COLORS = {"g": "#63c74d", "y": "#feae34"}
ICON = (".......",
        ".....g.",
        ".....g.",
        "...g.g.",
        "...g.g.",
        ".y.g.g.",
        ".y.g.g.")

kernel32 = ctypes.windll.kernel32

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


def mem_text(mode, mem, used, total):
    if mode == "gb":
        return "MEM %.1f/%.1fG" % (used, total)
    if mode == "both":
        return "MEM %.1f/%.1fG %d%%" % (used, total, mem)
    return "MEM %d%%" % mem


def load_mode():
    try:
        mode = json.loads(SETTINGS.read_text(encoding="utf-8")).get("mem")
    except (OSError, ValueError, AttributeError):
        return "pct"
    return mode if mode in MEM_KEYS else "pct"


def level_color(p):
    return RED if p > HOT else ORANGE if p > WARN else WHITE


class Monitor:
    def __init__(self):
        spot = taskbar.spot()
        x, top, h = spot or (overlay.work_area()[2], overlay.work_area()[3], 48)
        font = taskbar.font(h)
        # 창은 가장 긴 모양에 맞춰 한 번 잡고 글자는 오른쪽에 붙임 — 모양을 바꿔도 창을 다시 안 만듦.
        # 남는 왼쪽은 투명하고 클릭이 통과함
        total = memory()[2]
        widest = taskbar.text_width(font, ["CPU 100%"] + [mem_text(k, 100, total, total) for k in MEM_KEYS])
        self.w, self.h = widest + round(h * 0.2), h
        self.line = round(h * 0.44)
        self.mode = load_mode()
        self.surface = Surface(x - GAP - self.w, top, self.w, self.h, SURFACE_CLASS)
        taskbar.prepare(self.surface, font)
        self.commands = queue.Queue()
        write_ico(ICON_FILE, ICON, ICON_COLORS)
        self.tray = Tray(TRAY_CLASS, ICON_FILE, "CPU·메모리", self.menu, self.commands.put)
        self.shown, self.last_lines, self.where = None, None, None
        self.prev = cpu_times()

    def menu(self):
        return [("메모리 표시", [(label, cid, key == self.mode) for cid, (key, label) in MEM_MODES.items()]),
                ("Windows 시작 시 실행", AUTOSTART, startup.is_on(RUN_NAME, __file__)),
                None,
                ("끝내기", EXIT, False)]

    def update(self):
        cur = cpu_times()
        cpu, self.prev = cpu_percent(self.prev, cur), cur
        mem, used, total = memory()
        self.tray.set_tip("CPU %d%%\n메모리 %.1f / %.1f GB (%d%%)" % (cpu, used, total, mem))
        show = not taskbar.fullscreen_app()
        if show != self.shown:
            self.shown = show
            self.surface.show(show)
        if not show:
            return
        spot = taskbar.spot()
        if spot and spot[:2] != self.where:  # 트레이 아이콘이 늘거나 줄면 따라감
            self.where = spot[:2]
            self.surface.move(spot[0] - GAP - self.w, spot[1])
        lines = [("CPU %d%%" % cpu, level_color(cpu)), (mem_text(self.mode, mem, used, total), level_color(mem))]
        if lines != self.last_lines:
            self.last_lines = lines
            taskbar.paint_lines(self.surface, lines, self.line)
        self.surface.present()
        self.surface.topmost()  # 작업 표시줄을 누르면 그쪽이 앞으로 오므로 1초마다 다시 올라옴

    def run(self):
        next_update = 0.0
        while True:
            self.surface.pump()
            try:
                cid = self.commands.get_nowait()
                if cid == AUTOSTART:
                    startup.toggle(RUN_NAME, __file__)
                elif cid in MEM_MODES:
                    self.mode = MEM_MODES[cid][0]
                    next_update = 0.0  # 바로 다시 그림
                    try:
                        SETTINGS.parent.mkdir(parents=True, exist_ok=True)
                        SETTINGS.write_text(json.dumps({"mem": self.mode}), encoding="utf-8")
                    except OSError:
                        pass  # 못 남기면 다음에 퍼센트로 뜰 뿐
                elif cid in (None, EXIT):
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
    assert mem_text("pct", 22, 14.24, 63.9) == "MEM 22%"
    assert mem_text("gb", 22, 14.24, 63.9) == "MEM 14.2/63.9G"
    assert mem_text("both", 22, 14.24, 63.9) == "MEM 14.2/63.9G 22%"
    assert set(MEM_KEYS) == {"pct", "gb", "both"} and len(MEM_MODES) == 3, "메뉴 id 가 겹치지 않음"
    font = taskbar.font(48)
    assert taskbar.text_width(font, ["MEM 14.2/63.9G"]) > taskbar.text_width(font, ["MEM 22%"]) > 0, "긴 글이 더 넓음"
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
