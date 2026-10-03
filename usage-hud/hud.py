# SPDX-License-Identifier: Apache-2.0
"""화면 구석에 늘 떠 있는 레트로 게임 HUD — Claude Code 구독 한도를 체력바로.

  pythonw hud.py              띄우기 (창 없이 뒤에서 돎)
  python hud.py --toggle      떠 있으면 치우고, 없으면 띄움 (hud.bat 이 이걸 부름)
  python hud.py --stop        치우기
  python hud.py --corner tr   자리: bl(기본) · br · tl · tr
  python hud.py --scale 4     픽셀 하나의 크기 (기본 3)

HP 는 7일 창, ST 는 5시간 창의 **남은** 양이다. 칸 옆은 재설정까지 남은 시간.
동전 줄은 오늘 쓴 정가. 창은 맨 위에 있지만 클릭을 아래로 통과시키고 포커스도 안 뺏으므로,
닫을 때는 --toggle 이나 --stop 을 쓴다.
"""
import argparse
import ctypes
import os
import subprocess
import sys
import tempfile
import threading
import time
import tkinter as tk
from pathlib import Path

import usage
from font import COLORS, ICONS, text_pixels, text_width

PID_FILE = Path(tempfile.gettempdir()) / "playroom-usage-hud.pid"
REFRESH_SEC = 60   # 정가를 다시 셈. 한도는 usage.LIMIT_EVERY 가 따로 5분에 한 번으로 묶음
MARGIN = 12        # 작업 영역 가장자리에서 띄울 px
SEGMENTS = 10      # 칸 수. 한 칸 = 10%
W, H = 90, 29      # 패널 크기 (픽셀 단위)


# ── 한 번만 뜨게 하기 (cursor-playground 의 cat.py 와 같은 방식) ─────────────
def running_pid():
    try:
        pid = int(PID_FILE.read_text())
    except (OSError, ValueError):
        return None
    k32 = ctypes.windll.kernel32
    handle = k32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
    if not handle:
        return None
    code = ctypes.c_ulong()
    alive = k32.GetExitCodeProcess(handle, ctypes.byref(code)) and code.value == 259  # STILL_ACTIVE
    k32.CloseHandle(handle)
    return pid if alive else None


def stop():
    pid = running_pid()
    if pid is None:
        return False
    os.kill(pid, 9)
    PID_FILE.unlink(missing_ok=True)
    return True


def work_area():
    """작업 표시줄을 뺀 주 모니터 영역 (left, top, right, bottom)."""
    rect = (ctypes.c_long * 4)()
    ctypes.windll.user32.SystemParametersInfoW(0x30, 0, rect, 0)  # SPI_GETWORKAREA
    return tuple(rect)


def level_color(left):
    return COLORS["good"] if left > 0.5 else COLORS["mid"] if left > 0.2 else COLORS["low"]


class Hud:
    def __init__(self, scale, corner):
        self.s = scale
        self.root = tk.Tk()
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.canvas = tk.Canvas(self.root, width=W * scale, height=H * scale,
                                bg=COLORS["bg"], bd=0, highlightthickness=0)
        self.canvas.pack()
        l, t, r, b = work_area()
        x = l + MARGIN if "l" in corner else r - MARGIN - W * scale
        y = t + MARGIN if "t" in corner else b - MARGIN - H * scale
        self.root.geometry(f"{W * scale}x{H * scale}+{x}+{y}")
        self.root.update_idletasks()
        self.make_click_through()
        self.snap = None
        self.last_topmost = time.monotonic()
        threading.Thread(target=self.fetch_loop, daemon=True).start()

    def make_click_through(self):
        user32 = ctypes.windll.user32
        hwnd = int(self.root.wm_frame(), 16)
        # 겹친 창, 클릭 통과, 작업 표시줄에 안 뜸, 포커스 안 뺏음
        flags = 0x80000 | 0x20 | 0x80 | 0x8000000
        user32.SetWindowLongW(hwnd, -20, user32.GetWindowLongW(hwnd, -20) | flags)
        # 겹친 창은 알파를 한 번 정해 줘야 그려진다. 255 = 불투명
        user32.SetLayeredWindowAttributes(hwnd, 0, 255, 2)

    def fetch_loop(self):
        # 네트워크가 최대 usage.TIMEOUT 초 막으므로 그리는 쪽과 떼어 돌린다
        while True:
            try:
                self.snap = usage.snapshot(days=1)
            except Exception:  # noqa: BLE001 — HUD 는 죽지 않고 '?' 를 그리는 쪽이 낫다
                pass
            time.sleep(REFRESH_SEC)

    # ── 그리기 ──
    def px(self, x, y, color, w=1, h=1):
        s = self.s
        self.canvas.create_rectangle(x * s, y * s, (x + w) * s, (y + h) * s, fill=color, width=0)

    def text(self, x, y, s, color):
        for dx, dy in text_pixels(s):
            self.px(x + dx, y + dy, color)

    def icon(self, x, y, name):
        for dy, row in enumerate(ICONS[name]):
            for dx, c in enumerate(row):
                if c != ".":
                    self.px(x + dx, y + dy, COLORS[c])

    def bar_row(self, y, icon, label, bar, expired, blink):
        self.icon(2, y, icon)
        self.text(11, y + 1, label, COLORS["text"])
        x0 = 20
        if bar is None:
            for i in range(SEGMENTS):
                self.px(x0 + i * 3, y + 1, COLORS["slot"], 2, 5)
            self.text(x0 + SEGMENTS * 3 + 2, y + 1, "?", COLORS["dim"])
            if expired:  # 로그인 토큰 만료 — 터미널에서 claude 를 열면 풀림
                self.text(W - 2 - text_width("LOGIN"), y + 1, "LOGIN", COLORS["low"])
            return
        left = bar["left"]
        filled = round(left * SEGMENTS)
        color = level_color(left)
        if left < 0.1 and blink:
            color = COLORS["slot"]
        for i in range(SEGMENTS):
            self.px(x0 + i * 3, y + 1, color if i < filled else COLORS["slot"], 2, 5)
        pct = "%d%%" % round(left * 100)
        self.text(x0 + SEGMENTS * 3 + 2, y + 1, pct, color)
        until = usage.left(bar["reset"] - time.time())
        self.text(W - 2 - text_width(until), y + 1, until, COLORS["dim"])

    def draw(self):
        c = self.canvas
        c.delete("all")
        self.px(0, 0, COLORS["edge"], W, 1)
        self.px(0, H - 1, COLORS["edge"], W, 1)
        self.px(0, 0, COLORS["edge"], 1, H)
        self.px(W - 1, 0, COLORS["edge"], 1, H)
        snap = self.snap
        blink = int(time.time()) % 2 == 0
        bars = snap["bars"] if snap else {"7d": None, "5h": None}
        expired = bool(snap and snap["expired"])
        self.bar_row(2, "heart", "HP", bars["7d"], expired, blink)
        self.bar_row(11, "bolt", "ST", bars["5h"], expired, blink)
        self.icon(2, 20, "coin")
        gold = "%.2f" % snap["today"] if snap else "?"  # 동전이 달러 표시를 대신함
        self.text(11, 21, gold, COLORS["y"])
        self.text(W - 2 - text_width("TODAY"), 21, "TODAY", COLORS["dim"])

    def tick(self):
        self.draw()
        now = time.monotonic()
        # 다른 맨 위 창(PIP 등)이 앞을 가져가도 가끔 다시 올라옴
        if now - self.last_topmost > 2:
            self.root.attributes("-topmost", True)
            self.last_topmost = now
        self.root.after(1000, self.tick)

    def run(self):
        self.tick()
        self.root.mainloop()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--stop", action="store_true", help="떠 있는 HUD 를 치움")
    ap.add_argument("--toggle", action="store_true", help="떠 있으면 치우고, 없으면 띄움")
    ap.add_argument("--corner", default="bl", choices=("bl", "br", "tl", "tr"), help="자리 (기본 bl)")
    ap.add_argument("--scale", type=int, default=3, choices=range(1, 9), help="픽셀 크기 (기본 3)")
    args = ap.parse_args()

    if args.stop:
        print("HUD 를 치움" if stop() else "떠 있는 HUD 가 없음")
        return
    if running_pid() is not None:
        if args.toggle:
            stop()
        return
    if args.toggle and Path(sys.executable).name.lower() == "python.exe":
        # hud.bat 에서 콘솔 창이 남지 않게 pythonw 로 다시 띄움
        pythonw = Path(sys.executable).with_name("pythonw.exe")
        if pythonw.exists():
            subprocess.Popen([str(pythonw), str(Path(__file__).resolve()),
                              "--corner", args.corner, "--scale", str(args.scale)], close_fds=True)
            return

    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)  # 배율 높은 화면에서 흐려지지 않게
    except (AttributeError, OSError):
        pass
    PID_FILE.write_text(str(os.getpid()))
    try:
        Hud(args.scale, args.corner).run()
    finally:
        if running_pid() == os.getpid():
            PID_FILE.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
