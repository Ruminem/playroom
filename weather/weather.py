# SPDX-License-Identifier: Apache-2.0
"""모든 창 위에 내리는 픽셀 눈과 비. 보이기만 하고 클릭은 그대로 아래 창으로 간다.

  pythonw weather.py            띄우기 (창 없이 뒤에서 돎)
  python weather.py --toggle    떠 있으면 치우고, 없으면 띄움 (weather.bat 이 이걸 부름)
  python weather.py --stop      치우기
  python weather.py --kind rain --amount many
  python weather.py --check     자체 점검

작업 영역(작업 표시줄 뺀 주 모니터) 전체를 덮는 맨 위 창이다. 색 키로 배경을 뚫고
WS_EX_TRANSPARENT 로 클릭을 통과시킨다. 눈은 작업 표시줄 위에 쌓였다가 천천히 녹고, 비는 바닥에서 튄다.
트레이의 눈송이 메뉴에서 눈·비·양·숨기기·끝내기를 하고, 고른 것은 SETTINGS 에 남는다.
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
import tkinter as tk
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "shared"))
import overlay
from tray import Tray, write_ico

PID_FILE = Path(tempfile.gettempdir()) / "playroom-weather.pid"
ICON_FILE = Path(tempfile.gettempdir()) / "playroom-weather.ico"
SETTINGS = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "playroom" / "weather.json"
TRAY_CLASS = "PlayroomWeatherTray"

KEY = "#ff00fe"    # 투명으로 뚫리는 색. 그림에는 안 씀
S = 3              # 픽셀 하나의 크기 px
# 15fps 를 요청하면 윈도우 타이머 간격(15.6ms) 탓에 실제 13fps 쯤 나온다. 30 을 요청해도 21.5 에서
# 멈추고 CPU 만 두 배가 된다 (2026-10-04 실측, 150개 13fps 에 한 코어 6–8%)
FRAME_MS = 66
PILE_MAX = 5       # 쌓인 눈의 최대 높이 (픽셀 단위)
MELT = 0.008       # 눈 쌓인 칸 하나가 1초에 한 칸 녹을 확률. '보통' 에서 평균 두세 칸 높이로 머묾
WIND = 0.12        # 빗줄기의 기울기 (가로 / 세로)

SNOW, RAIN, SHOW, EXIT = 1, 2, 3, 99
AMOUNTS = {10: ("few", "적게", 60), 11: ("normal", "보통", 150), 12: ("many", "많이", 300)}
COUNT = {key: n for key, _, n in AMOUNTS.values()}

WHITE, EDGE, RAIN_COLOR = "#ffffff", "#8b9bb4", "#8b9bb4"  # 흰 창 위에서도 보이게 눈송이에 테두리
ICON_COLORS = {"b": "#0099db", "w": "#ffffff"}
ICON = ("...b...",
        ".b.b.b.",
        "..bbb..",
        "bbbwbbb",
        "..bbb..",
        ".b.b.b.",
        "...b...")


def settle(pile, col):
    """눈송이가 col 에 닿았을 때 실제로 쌓일 칸. 양옆이 더 낮으면 그쪽으로 굴러 내려가 둔덕이 매끈해진다.
    다 찼으면 None."""
    for n in (col - 1, col + 1):
        if 0 <= n < len(pile) and pile[n] < pile[col]:
            col = n
    return col if pile[col] < PILE_MAX else None


def load_settings():
    try:
        data = json.loads(SETTINGS.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(data, dict):
        return {}
    ok = {}
    if data.get("kind") in ("snow", "rain"):
        ok["kind"] = data["kind"]
    if data.get("amount") in COUNT:
        ok["amount"] = data["amount"]
    return ok


class Weather:
    def __init__(self, kind, amount):
        self.kind, self.amount, self.visible = kind, amount, True
        self.root = tk.Tk()
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.configure(bg=KEY)
        self.root.attributes("-transparentcolor", KEY)
        # ponytail: 시작할 때의 주 모니터 작업 영역에 고정. 해상도·작업 표시줄이 바뀌면 다시 켜야 함
        l, t, r, b = overlay.work_area()
        self.w, self.h = r - l, b - t
        self.root.geometry(f"{self.w}x{self.h}+{l}+{t}")
        self.canvas = tk.Canvas(self.root, bg=KEY, highlightthickness=0, width=self.w, height=self.h)
        self.canvas.pack()
        self.root.update_idletasks()
        overlay.click_through(self.root)
        self.commands = queue.Queue()  # 트레이 스레드 → tk 스레드
        write_ico(ICON_FILE, ICON, ICON_COLORS)
        self.tray = Tray(TRAY_CLASS, ICON_FILE, "날씨", self.menu, self.commands.put)
        self.last = self.last_melt = self.last_topmost = time.monotonic()
        self.reset()

    # ── 트레이 ──
    def menu(self):
        return [("눈", SNOW, self.kind == "snow"),
                ("비", RAIN, self.kind == "rain"),
                ("양", [(label, cid, key == self.amount) for cid, (key, label, _) in AMOUNTS.items()]),
                None,
                ("보이기", SHOW, self.visible),
                None,
                ("끝내기", EXIT, False)]

    def handle(self, cid):
        if cid in (SNOW, RAIN):
            self.kind = "snow" if cid == SNOW else "rain"
        elif cid in AMOUNTS:
            self.amount = AMOUNTS[cid][0]
        elif cid == SHOW:
            self.visible = not self.visible
            self.root.deiconify() if self.visible else self.root.withdraw()
            if self.visible:
                overlay.click_through(self.root)  # 다시 보일 때 확장 스타일이 풀리지 않게
            return
        elif cid == EXIT:
            self.tray.close()  # 트레이가 닫히면 None 이 와서 poll 이 끝냄
            return
        self.reset()
        try:
            SETTINGS.parent.mkdir(parents=True, exist_ok=True)
            SETTINGS.write_text(json.dumps({"kind": self.kind, "amount": self.amount}), encoding="utf-8")
        except OSError:
            pass  # 못 남겨도 지금 화면은 바뀌었으니 넘어감

    def poll(self):
        """트레이에서 온 명령을 처리. None 이면 트레이가 닫힌 것 → 같이 끝냄. 끝났으면 True."""
        try:
            while True:
                cid = self.commands.get_nowait()
                if cid is None:
                    self.root.destroy()
                    return True
                self.handle(cid)
        except queue.Empty:
            return False

    # ── 눈과 비 ──
    def reset(self):
        c = self.canvas
        c.delete("all")
        n = COUNT[self.amount]
        self.drops = []
        self.pile = [0] * (self.w // S + 1)
        self.pile_items = {}
        self.splashes, self.free = [], []
        if self.kind == "snow":
            for _ in range(n):
                size = 2 if random.random() < 0.2 else 1  # 큰 것은 가까이 있는 것 — 더 빨리 떨어짐
                speed = random.uniform(55, 85) if size == 2 else random.uniform(25, 55)
                item = c.create_rectangle(0, 0, 0, 0, fill=WHITE, outline=EDGE, width=1)
                # [x, y, 속도 px/초, 흔들림 위상, 크기, 항목]
                self.drops.append([random.uniform(0, self.w), random.uniform(0, self.h), speed,
                                   random.uniform(0, 6.3), size, item])
        else:
            for _ in range(n):
                item = c.create_line(0, 0, 0, 0, fill=RAIN_COLOR, width=S - 1)
                # [x, y, 속도 px/초, 길이 px, 항목]
                self.drops.append([random.uniform(-self.h * WIND, self.w), random.uniform(0, self.h),
                                   random.uniform(700, 1000), random.randint(4, 7) * S, item])
            for _ in range(n // 2):  # 튀는 물방울 풀. 모자라면 그 방울은 안 튐
                self.free.append(c.create_rectangle(-9, -9, -9, -9, fill=RAIN_COLOR, width=0))

    def snow(self, dt, now):
        c, pile = self.canvas, self.pile
        for f in self.drops:
            f[1] += f[2] * dt
            x = f[0] + math.sin(f[3] + now) * 2 * S  # 좌우로 살랑
            size = f[4] * S
            col = min(max(int(x // S), 0), len(pile) - 1)
            if f[1] + size >= self.h - pile[col] * S:
                self.land(col)
                f[0], f[1] = random.uniform(0, self.w), -size - random.uniform(0, self.h * 0.2)
            c.coords(f[5], x, f[1], x + size, f[1] + size)
        if now - self.last_melt >= 1:
            self.last_melt = now
            for col, height in enumerate(pile):
                if height and random.random() < MELT:
                    pile[col] -= 1
                    self.draw_pile(col)

    def land(self, col):
        col = settle(self.pile, col)
        if col is not None:
            self.pile[col] += 1
            self.draw_pile(col)

    def draw_pile(self, col):
        item = self.pile_items.get(col)
        if item is None:
            item = self.pile_items[col] = self.canvas.create_rectangle(0, 0, 0, 0, fill=WHITE, width=0)
        x = col * S
        self.canvas.coords(item, x, self.h - self.pile[col] * S, x + S, self.h)  # 높이 0 이면 안 보임

    def rain(self, dt, now):
        c = self.canvas
        for d in self.drops:
            d[1] += d[2] * dt
            d[0] += d[2] * WIND * dt
            if d[1] >= self.h:
                self.splash(d[0])
                d[0], d[1] = random.uniform(-self.h * WIND, self.w), -random.uniform(0, self.h * 0.3)
            c.coords(d[4], d[0], d[1], d[0] - d[3] * WIND, d[1] - d[3])
        live = []
        for sp in self.splashes:  # [x, y, vx, vy, 남은 초, 항목]
            sp[4] -= dt
            if sp[4] <= 0:
                c.coords(sp[5], -9, -9, -9, -9)
                self.free.append(sp[5])
                continue
            sp[3] += 900 * dt  # 중력
            sp[0] += sp[2] * dt
            sp[1] += sp[3] * dt
            c.coords(sp[5], sp[0], sp[1], sp[0] + S - 1, sp[1] + S - 1)
            live.append(sp)
        self.splashes = live

    def splash(self, x):
        for vx in (-60, 60):
            if not self.free:
                return
            self.splashes.append([x, self.h - S, vx + random.uniform(-20, 20), random.uniform(-180, -120),
                                  0.3, self.free.pop()])

    def tick(self):
        if self.poll():
            return
        now = time.monotonic()
        dt = min(now - self.last, 0.2)  # 멈췄다 돌아와도 한 번에 순간 이동하지 않게
        self.last = now
        if self.visible:
            (self.snow if self.kind == "snow" else self.rain)(dt, now)
            # 다른 맨 위 창(PIP 등)이 앞을 가져가도 가끔 다시 올라옴
            if now - self.last_topmost > 2:
                self.root.attributes("-topmost", True)
                self.last_topmost = now
        self.root.after(FRAME_MS if self.visible else 200, self.tick)

    def run(self):
        self.tick()
        self.root.mainloop()


def check():
    p = [0, 0, 0]
    assert settle(p, 1) == 1
    p = [3, 2, 1]
    assert settle(p, 1) == 2, "낮은 옆으로 굴러야 함"
    p = [0, 2, 1]
    assert settle(p, 1) == 0, "양옆 중 더 낮은 쪽"
    p = [1, 2, 0]
    assert settle(p, 1) == 2, "더 낮은 쪽이 이김"
    p = [PILE_MAX] * 3
    assert settle(p, 1) is None, "다 차면 안 쌓임"
    p = [0, 0]
    assert settle(p, 1) == 1 and settle(p, 0) == 0, "가장자리에서 넘어가지 않음"
    print("자체 점검 통과")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--stop", action="store_true", help="떠 있는 날씨를 치움")
    ap.add_argument("--toggle", action="store_true", help="떠 있으면 치우고, 없으면 띄움")
    ap.add_argument("--check", action="store_true", help="자체 점검")
    saved = load_settings()  # 안 주면 트레이 메뉴에서 마지막으로 고른 값
    ap.add_argument("--kind", default=saved.get("kind", "snow"), choices=("snow", "rain"))
    ap.add_argument("--amount", default=saved.get("amount", "normal"), choices=tuple(COUNT))
    args = ap.parse_args()

    if args.check:
        check()
        return
    if args.stop:
        print("날씨를 치움" if overlay.stop(PID_FILE, TRAY_CLASS) else "떠 있는 날씨가 없음")
        return
    if overlay.running_pid(PID_FILE) is not None:
        if args.toggle:
            overlay.stop(PID_FILE, TRAY_CLASS)
        return
    if args.toggle and Path(sys.executable).name.lower() == "python.exe":
        # weather.bat 에서 콘솔 창이 남지 않게 pythonw 로 다시 띄움
        pythonw = Path(sys.executable).with_name("pythonw.exe")
        if pythonw.exists():
            subprocess.Popen([str(pythonw), str(Path(__file__).resolve()),
                              "--kind", args.kind, "--amount", args.amount], close_fds=True)
            return

    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)  # 배율 높은 화면에서 흐려지지 않게
    except (AttributeError, OSError):
        pass
    PID_FILE.write_text(str(os.getpid()))
    try:
        Weather(args.kind, args.amount).run()
    finally:
        if overlay.running_pid(PID_FILE) == os.getpid():
            PID_FILE.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
