# SPDX-License-Identifier: Apache-2.0
"""작업 표시줄에서 sysmon 바로 왼쪽에 뽀모도로 남은 시간을 띄운다.

  pythonw pomodoro.py            띄우기 (트레이의 토마토 메뉴에서 시작)
  python pomodoro.py --toggle    떠 있으면 치우고, 없으면 띄움 (pomodoro.bat 이 이걸 부름)
  python pomodoro.py --stop      치우기
  python pomodoro.py --check     자체 점검

집중이 끝나면 소리와 함께 작업 표시줄 위로 픽셀 색종이가 터지고 휴식이 바로 이어진다. 휴식이
끝나면 한 번 더 터지고 멈춘다 — 다음 집중은 메뉴로 시작한다. 쉬는 동안(멈춤)에는 글자가 안 뜬다.
"""
import argparse
import ctypes
import json
import math
import os
import queue
import random
import subprocess
import sys
import tempfile
import time
import winsound
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "shared"))
import overlay
import startup
import taskbar
from surface import Surface
from tray import Tray, write_ico

PID_FILE = Path(tempfile.gettempdir()) / "playroom-pomodoro.pid"
ICON_FILE = Path(tempfile.gettempdir()) / "playroom-pomodoro.ico"
TRAY_CLASS = "PlayroomPomodoroTray"
SURFACE_CLASS = "PlayroomPomodoroSurface"
BURST_CLASS = "PlayroomPomodoroBurst"
SYSMON_SURFACE = "PlayroomSysmonSurface"
SETTINGS = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "playroom" / "pomodoro.json"

GAP = 8  # 옆 창과 띄울 px
WHITE, GREY = (255, 255, 255), (150, 150, 150)
LABELS = {"focus": ("FOCUS", (238, 92, 82)), "break": ("BREAK", (99, 199, 77))}
# 메뉴 id → (키, 메뉴 글, 집중 초, 휴식 초)
PRESETS = {30: ("25/5", "25분 · 5분", 25 * 60, 5 * 60), 31: ("50/10", "50분 · 10분", 50 * 60, 10 * 60)}
PRESET_KEYS = {v[0]: v for v in PRESETS.values()}
START, PAUSE, SKIP, STOP, SOUND, AUTOSTART, EXIT = 1, 2, 3, 4, 40, 50, 99
RUN_NAME = "PlayroomPomodoro"

# 색종이: 작업 표시줄 높이에 비례 (48px 기준 값)
BURST_SEC = 3.0
BURST_FADE = 1.0          # 끝나기 전 이만큼 동안 옅어짐
BURST_N = 140
BURST_W, BURST_H = 9.0, 7.5  # 창 크기 = 작업 표시줄 높이 × 이 값
CONFETTI = ((228, 59, 68), (254, 174, 52), (254, 231, 97), (99, 199, 77), (44, 232, 245), (181, 80, 136),
            (255, 255, 255))

ICON_COLORS = {"r": "#e43b44", "g": "#63c74d", "w": "#ffffff"}
ICON = ("...g...",
        "..ggg..",
        ".rrrrr.",
        "rrwrrrr",
        "rrrrrrr",
        "rrrrrrr",
        ".rrrrr.")


class Timer:
    """phase: idle · focus · break. 멈춤은 남은 초(left)를 들고 있는 것. 시각은 밖에서 받음 — 점검이 가짜 시계로 돌림."""

    def __init__(self, focus, rest):
        self.focus, self.rest = focus, rest
        self.phase, self.ends, self.left = "idle", 0.0, None

    @property
    def paused(self):
        return self.left is not None

    def start(self, now):
        self.phase, self.ends, self.left = "focus", now + self.focus, None

    def stop(self):
        self.phase, self.left = "idle", None

    def pause(self, now):
        """멈춤 ↔ 계속."""
        if self.phase == "idle":
            return
        if self.left is None:
            self.left = max(0.0, self.ends - now)
        else:
            self.ends, self.left = now + self.left, None

    def skip(self, now):
        if self.phase == "focus":
            self.phase, self.ends, self.left = "break", now + self.rest, None
        else:
            self.stop()

    def remaining(self, now):
        return self.left if self.left is not None else max(0.0, self.ends - now)

    def tick(self, now):
        """끝난 단계 이름을 돌려주고 다음으로 넘어감. 안 끝났으면 None.
        잠자기에서 깨어 이미 지났으면 휴식은 깨어난 때부터 셈."""
        if self.phase == "idle" or self.left is not None or now < self.ends:
            return None
        done = self.phase
        self.skip(now)
        return done


def clock(sec):
    """남은 초 → '24:13'. 올림이라 시작하자마자 25:00 이고 0:00 은 안 보임."""
    m, s = divmod(math.ceil(sec), 60)
    return "%d:%02d" % (m, s)


def load_settings():
    try:
        data = json.loads(SETTINGS.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = {}
    if not isinstance(data, dict):
        data = {}
    return (data["preset"] if data.get("preset") in PRESET_KEYS else "25/5",
            data["sound"] if isinstance(data.get("sound"), bool) else True)


class Burst:
    """작업 표시줄 위로 3초 동안 터지는 색종이. 끝나면 frame() 이 False."""

    def __init__(self, right, bottom, bar_h):
        k = bar_h / 48
        self.w, self.h = round(bar_h * BURST_W), round(bar_h * BURST_H)
        self.surface = Surface(right - self.w, bottom - self.h, self.w, self.h, BURST_CLASS)
        ox, oy = self.w - bar_h * 1.2, self.h - 2  # 타이머 글자 바로 위에서 터짐
        self.g = 1100 * k
        self.parts = [[ox + random.uniform(-6, 6) * k, oy,
                       random.uniform(-330, 90) * k, random.uniform(-760, -380) * k,
                       round(random.choice((3, 4, 4, 5)) * k), random.choice(CONFETTI)]
                      for _ in range(BURST_N)]
        self.rows = {}  # (크기, 색, 알파 단계) → 한 행 bytes
        self.t = 0.0
        self.surface.show(True)

    def row(self, size, color, a):
        key = (size, color, a)
        if key not in self.rows:
            r, g, b = color
            self.rows[key] = bytes((b * a // 255, g * a // 255, r * a // 255, a)) * size
        return self.rows[key]

    def frame(self, dt):
        self.t += dt
        if self.t >= BURST_SEC:
            self.surface.close()
            return False
        fade = min(1.0, (BURST_SEC - self.t) / BURST_FADE)
        a = max(16, round(fade * 15) * 17)  # 16단계 — 행 캐시가 안 불어나게
        s, w, h, px = self.surface, self.w, self.h, self.surface.pixels
        s.clear()
        for p in self.parts:
            p[0] += p[2] * dt
            p[1] += p[3] * dt
            p[3] += self.g * dt
            p[2] *= 0.985  # 공기 저항 — 옆으로 끝없이 안 날아감
            x, y, size = int(p[0]), int(p[1]), p[4]
            if x < 0 or y < 0 or x + size > w or y + size > h:
                continue
            row = self.row(size, p[5], a)
            for r in range(size):
                o = ((y + r) * w + x) * 4
                px[o:o + size * 4] = row
        s.present()
        s.topmost()
        return True


class Pomodoro:
    def __init__(self):
        spot = taskbar.spot()
        x, self.top, self.bar_h = spot or (overlay.work_area()[2], overlay.work_area()[3], 48)
        font = taskbar.font(self.bar_h)
        self.w = taskbar.text_width(font, ["FOCUS", "BREAK", "50:00"]) + round(self.bar_h * 0.2)
        self.line = round(self.bar_h * 0.44)
        self.surface = Surface(x - GAP - self.w, self.top, self.w, self.bar_h, SURFACE_CLASS)
        taskbar.prepare(self.surface, font)
        self.preset, self.sound = load_settings()
        _, _, focus, rest = PRESET_KEYS[self.preset]
        self.timer = Timer(focus, rest)
        self.burst = None
        self.commands = queue.Queue()
        write_ico(ICON_FILE, ICON, ICON_COLORS)
        self.tray = Tray(TRAY_CLASS, ICON_FILE, "뽀모도로", self.menu, self.commands.put)
        self.shown, self.last_lines, self.last_tip, self.right = None, None, None, None

    def menu(self):
        t = self.timer
        if t.phase == "idle":
            items = [("집중 시작", START, False)]
        else:
            items = [("계속" if t.paused else "일시정지", PAUSE, False), ("건너뛰기", SKIP, False), ("그만", STOP, False)]
        return items + [None,
                        ("길이", [(label, cid, key == self.preset) for cid, (key, label, _, _) in PRESETS.items()]),
                        ("소리", SOUND, self.sound),
                        ("Windows 시작 시 실행", AUTOSTART, startup.is_on(RUN_NAME, __file__)),
                        None,
                        ("끝내기", EXIT, False)]

    def save(self):
        try:
            SETTINGS.parent.mkdir(parents=True, exist_ok=True)
            SETTINGS.write_text(json.dumps({"preset": self.preset, "sound": self.sound}), encoding="utf-8")
        except OSError:
            pass  # 못 남기면 다음에 기본값으로 뜰 뿐

    def handle(self, cid, now):
        t = self.timer
        if cid == START:
            t.start(now)
        elif cid == PAUSE:
            t.pause(now)
        elif cid == SKIP:
            t.skip(now)
        elif cid == STOP:
            t.stop()
        elif cid in PRESETS:
            self.preset, _, t.focus, t.rest = PRESETS[cid]  # 지금 세는 단계는 그대로, 다음 단계부터 적용
            self.save()
        elif cid == SOUND:
            self.sound = not self.sound
            self.save()
        elif cid == AUTOSTART:
            startup.toggle(RUN_NAME, __file__)

    def finished(self):
        if self.sound:
            winsound.MessageBeep(winsound.MB_ICONASTERISK)
        if self.burst:
            self.burst.surface.close()
        right = self.right if self.right is not None else self.surface.w
        self.burst = Burst(right, self.top, self.bar_h)

    def place(self):
        """sysmon 이 보이면 그 왼쪽, 아니면 알림 영역 왼쪽.
        ponytail: sysmon 창은 가장 긴 모양 너비라 '퍼센트' 모양이면 그 사이가 조금 빔"""
        spot = taskbar.spot()
        if spot:
            self.top, self.bar_h = spot[1], spot[2]
            left = taskbar.window_left(SYSMON_SURFACE)
            right = (left if left is not None else spot[0]) - GAP
            if right != self.right:
                self.right = right
                self.surface.move(right - self.w, self.top)

    def update(self, now):
        t = self.timer
        show = t.phase != "idle" and not taskbar.fullscreen_app()
        if show != self.shown:
            self.shown = show
            self.surface.show(show)
        left = t.remaining(now)
        if t.phase == "idle":
            tip = "뽀모도로 — 메뉴에서 집중 시작"
        else:
            tip = "%s %s 남음%s" % ("집중" if t.phase == "focus" else "휴식", clock(left), " (일시정지)" if t.paused else "")
        if tip != self.last_tip:
            self.last_tip = tip
            self.tray.set_tip(tip)
        if not show:
            return
        self.place()
        label, color = LABELS[t.phase]
        lines = [(label, GREY if t.paused else color), (clock(left), GREY if t.paused else WHITE)]
        if lines != self.last_lines:
            self.last_lines = lines
            taskbar.paint_lines(self.surface, lines, self.line)
        self.surface.present()
        self.surface.topmost()

    def run(self):
        next_update, last = 0.0, time.monotonic()
        while True:
            self.surface.pump()
            if self.burst:
                self.burst.surface.pump()
            now = time.monotonic()
            try:
                cid = self.commands.get_nowait()
                if cid in (None, EXIT):
                    if self.tray.hwnd:
                        self.tray.close()  # 아이콘을 지우고 나면 None 이 다시 옴
                        continue
                    break
                self.handle(cid, now)
                next_update = 0.0  # 바로 다시 그림
            except queue.Empty:
                pass
            if self.timer.tick(now):
                self.finished()
                next_update = 0.0
            if now >= next_update:
                next_update = now + 0.25  # 초가 넘어가는 것을 늦어도 1/4초 안에 보임
                self.update(now)
            if self.burst and not self.burst.frame(now - last):
                self.burst = None
            last = now
            time.sleep(1 / 30 if self.burst else 0.1)
        if self.burst:
            self.burst.surface.close()
        self.surface.close()


def check():
    t = Timer(10, 3)
    assert t.phase == "idle" and t.tick(100) is None, "멈춰 있으면 아무 일 없음"
    t.pause(0)
    assert not t.paused, "멈춰 있을 때 일시정지는 무시"
    t.start(0)
    assert t.remaining(4) == 6 and t.tick(9.9) is None
    assert t.tick(10) == "focus" and t.phase == "break" and t.remaining(10) == 3, "집중 끝 → 휴식이 바로 이어짐"
    t.pause(11)
    assert t.paused and t.remaining(50) == 2 and t.tick(50) is None, "일시정지 중엔 시간이 안 감"
    t.pause(60)
    assert not t.paused and t.remaining(60) == 2 and t.tick(61.9) is None
    assert t.tick(62) == "break" and t.phase == "idle", "휴식 끝 → 멈춤"
    t.start(100)
    t.skip(101)
    assert t.phase == "break" and t.remaining(101) == 3, "건너뛰면 휴식"
    t.skip(102)
    assert t.phase == "idle", "휴식을 건너뛰면 멈춤"
    t.start(150)
    t.pause(151)
    t.skip(152)
    assert t.phase == "break" and not t.paused and t.remaining(153) == 2, "멈춘 채 건너뛰면 휴식은 흐름"
    t.start(200)
    t.pause(201)
    t.stop()
    assert t.phase == "idle" and not t.paused, "그만이면 일시정지도 풀림"
    t.start(300)
    assert t.tick(5000) == "focus" and t.remaining(5000) == 3, "잠자기 뒤엔 깨어난 때부터 휴식"
    assert clock(1500) == "25:00" and clock(1499.2) == "25:00" and clock(1499) == "24:59"
    assert clock(0.2) == "0:01" and clock(61) == "1:01"
    assert set(PRESET_KEYS) == {"25/5", "50/10"} and not set(PRESETS) & {START, PAUSE, SKIP, STOP, SOUND, AUTOSTART, EXIT}
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
        # pomodoro.bat 에서 콘솔 창이 남지 않게 pythonw 로 다시 띄움
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
        Pomodoro().run()
    finally:
        if overlay.running_pid(PID_FILE) == os.getpid():
            PID_FILE.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
