# SPDX-License-Identifier: Apache-2.0
"""화면 구석에 늘 떠 있는 레트로 게임 HUD — Claude Code 구독 한도를 체력바로.

  pythonw hud.py              띄우기 (창 없이 뒤에서 돎)
  python hud.py --toggle      떠 있으면 치우고, 없으면 띄움 (hud.bat 이 이걸 부름)
  python hud.py --stop        치우기
  python hud.py --corner tr   자리: bl(기본) · br · tl · tr · bar(작업 표시줄, sysmon 왼쪽)
  python hud.py --scale 4     픽셀 하나의 크기 (기본 3)

HP 는 7일 창, ST 는 5시간 창의 **남은** 양이다. 칸 옆은 재설정까지 남은 시간.
동전 줄은 오늘 쓴 정가. 옆의 고양이는 이 PC 의 Claude Code 세션이 일하는 동안 달리고 쉬면 잠들며,
한 차례가 끝나면 테두리가 잠깐 깜빡인다. 창은 맨 위에 있지만 클릭을 아래로 통과시키고 포커스도 안 뺏는다.
대신 트레이(알림 영역)에 하트 아이콘이 뜨고, 그 메뉴에서 숨기기·위치·크기·테마·페이지·끝내기를 한다.
메뉴에서 고른 위치·크기·테마는 SETTINGS 에 남아 다음에 켤 때도 쓰인다. '작업 표시줄' 자리에서는 두 줄짜리
납작한 모양으로 sysmon(없으면 알림 영역) 왼쪽에 붙고, 크기는 작업 표시줄 높이에 맞춰 정해진다.
"""
import argparse
import ctypes
import json
import os
import queue
import subprocess
import sys
import tempfile
import threading
import time
import tkinter as tk
import traceback
import webbrowser
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "shared"))
import overlay
import startup
import taskbar
import usage
from pixelfont import COLORS, ICONS, PALETTES, text_pixels, text_width, use_palette
from tray import Tray, write_ico

PID_FILE = Path(tempfile.gettempdir()) / "playroom-usage-hud.pid"
ICON_FILE = Path(tempfile.gettempdir()) / "playroom-usage-hud.ico"
LOG_FILE = Path(tempfile.gettempdir()) / "playroom-usage-hud.log"  # pythonw 로 돌다 죽을 때 남는 traceback
DIAG_FILE = Path(tempfile.gettempdir()) / "playroom-taskbar.txt"  # 메뉴의 작업 표시줄 진단
SETTINGS = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "playroom" / "usage-hud.json"
TRAY_CLASS = "PlayroomUsageHudTray"  # --stop 이 이 이름으로 창을 찾아 닫으라고 보냄
REFRESH_SEC = 60   # 정가를 다시 셈. 한도는 usage.LIMIT_EVERY 가 따로 5분에 한 번으로 묶음
MARGIN = 12        # 작업 영역 가장자리에서 띄울 px
SEGMENTS = 10      # 칸 수. 한 칸 = 10%
W, H = 90, 29      # 패널 크기 (픽셀 단위)
BAR_W, BAR_H = 145, 19  # 작업 표시줄 자리의 납작한 패널: 두 줄 + 오른쪽에 동전 칸과 고양이 칸
BAR_RIGHT = 92     # 그 패널에서 남은 시간 글자의 오른쪽 끝
BAR_GAP = 8        # sysmon 과 띄울 px
SYSMON_CLASS = "PlayroomSysmonSurface"
ACTIVITY_SEC = 2   # 세션 기록을 다시 봄
FLASH_SEC = 3      # 한 차례가 끝나면 테두리가 깜빡이는 동안
PET_MS = 250       # 고양이 한 장면

# 고양이 10×7, 오른쪽을 봄. y 몸 · o 감은 눈 · p 잠꼬대 Z. 눈은 비운 칸(배경색)
PET = {"run1": ("......y..y", "y.....yyyy", "y.....yy.y", ".yyyyyyyyy", ".yyyyyyyy.", ".y......y.", "y........y"),
       "run2": ("......y..y", "y.....yyyy", "y.....yy.y", ".yyyyyyyyy", ".yyyyyyyy.", "..y....y..", "...y..y..."),
       "sleep": ("..........", "......y..y", "......yyyy", "..yyyyoyoy", ".yyyyyyyyy", "yyyyyyyyyy", ".yyyyyyyy.")}
ZZZ = ("pppp", "..p.", ".p..", "pppp")
PAGE_PORT = 8765

# 메뉴 id
SHOW, PAGE, HELP, DIAG, AUTOSTART, EXIT = 1, 30, 40, 45, 50, 99

RUN_NAME = "PlayroomUsageHud"  # Run 키 값 이름. 바꾸면 이미 켜 둔 등록이 꺼진 것으로 보임
CORNERS = {10: ("bl", "왼쪽 아래"), 11: ("br", "오른쪽 아래"), 12: ("tl", "왼쪽 위"), 13: ("tr", "오른쪽 위"),
           14: ("bar", "작업 표시줄 (sysmon 왼쪽)")}
CORNER_KEYS = tuple(c for c, _ in CORNERS.values())
SCALES = {20 + s: s for s in (2, 3, 4, 5)}
THEMES = {60 + i: key for i, key in enumerate(PALETTES)}

HELP_TEXT = """HP (하트) — 7일 한도의 남은 양
ST (번개) — 5시간 한도의 남은 양
동전 — 이 PC 에서 오늘 쓴 토큰을 API 정가로 친 달러. 구독이면 실제로 나가는 돈은 아님

막대 옆은 재설정까지 남은 시간이고, 10% 아래로 내려가면 깜빡입니다.
창이 열린 뒤의 평균 속도로 가면 재설정 전에 바닥나는 때는 그 자리에 빨간 ! 와 바닥까지 남은 시간이 뜹니다.
한도는 5분, 정가는 1분마다 다시 받습니다.

고양이 — 이 PC 의 Claude Code 세션이 일하는 동안 달리고, 쉬면 잠듭니다. 한 차례가 끝나면 테두리가 3초 깜빡입니다.
권한 허락을 기다리는 동안도 달리고, 10분 넘게 도는 도구는 잠든 것으로 보입니다.

LOGIN 이 뜨면 CLI 로그인 토큰이 만료됐고 자동으로 고치지도 못한 것입니다. 터미널에서 claude 를 한 번 열면 풀립니다.

HUD 는 클릭이 통과하므로 이 트레이 메뉴로 숨기거나 끕니다."""


def running_pid():
    return overlay.running_pid(PID_FILE)


def stop():
    return overlay.stop(PID_FILE, TRAY_CLASS)


def load_settings():
    """손으로 고친 파일이 이상해도 엉뚱한 크기로 뜨지 않게 아는 값만 남긴다."""
    try:
        data = json.loads(SETTINGS.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(data, dict):
        return {}
    ok = {}
    if data.get("corner") in CORNER_KEYS:
        ok["corner"] = data["corner"]
    if data.get("scale") in range(1, 9):
        ok["scale"] = data["scale"]
    if data.get("theme") in PALETTES:
        ok["theme"] = data["theme"]
    return ok


def level_color(left):
    return COLORS["good"] if left > 0.5 else COLORS["mid"] if left > 0.2 else COLORS["low"]


class Hud:
    def __init__(self, scale, corner, theme):
        self.s, self.corner, self.visible, self.theme = scale, corner, True, theme
        use_palette(theme)
        # 지금 그리는 픽셀 크기 · 납작한 모양인가 · 창 자리 · 전체 화면에 가려 숨었나
        self.ps, self.flat, self.geom, self.covered = scale, False, None, False
        self.root = tk.Tk()
        self.root.title("usage-hud")  # layers 가 이 제목으로 알아봄
        self.root.overrideredirect(True)
        self.on_top = overlay.on_top("usage-hud")  # 런처의 '항상 위'
        self.root.attributes("-topmost", self.on_top)
        self.canvas = tk.Canvas(self.root, bg=COLORS["bg"], bd=0, highlightthickness=0)
        self.canvas.pack()
        self.place()
        self.root.update_idletasks()
        overlay.click_through(self.root)
        self.faded = False  # 커서가 올라와 흐려져 있나
        self.snap = None
        self.server = None
        self.last_topmost = time.monotonic()
        self.commands = queue.Queue()  # 트레이 스레드 → tk 스레드
        write_ico(ICON_FILE, ICONS["heart"], COLORS)
        self.tray = Tray(TRAY_CLASS, ICON_FILE, "사용량 HUD", self.menu, self.commands.put)
        self.working, self.flash_until = False, 0.0  # watch_loop 가 고치고 tk 쪽이 읽음
        threading.Thread(target=self.fetch_loop, daemon=True).start()
        threading.Thread(target=self.watch_loop, daemon=True).start()

    def place(self):
        """자리를 다시 셈. 작업 표시줄 자리면 sysmon 이 옮기거나 폭이 바뀔 때 따라가려고 1초마다 부름."""
        spot = taskbar.spot() if self.corner == "bar" else None
        if spot:
            notify, top, bar_h = spot
            s = max(1, (bar_h - 4) // BAR_H)
            w, h = BAR_W * s, BAR_H * s
            x = (taskbar.window_left(SYSMON_CLASS) or notify) - BAR_GAP - w
            y = top + (bar_h - h) // 2
        else:  # 작업 표시줄을 못 찾으면 왼쪽 아래 구석
            s = self.s
            w, h = W * s, H * s
            l, t, r, b = overlay.work_area()
            x = r - MARGIN - w if "r" in self.corner else l + MARGIN
            y = t + MARGIN if "t" in self.corner else b - MARGIN - h
        geom = f"{w}x{h}+{x}+{y}"
        if geom != self.geom:
            self.geom, self.ps, self.flat = geom, s, bool(spot)
            self.canvas.configure(width=w, height=h)
            self.root.geometry(geom)

    # ── 트레이 ──
    def menu(self):
        return [("HUD 보이기", SHOW, self.visible),
                ("위치", [(name, cid, c == self.corner) for cid, (c, name) in CORNERS.items()]),
                ("크기", [("%d배" % s, cid, s == self.s) for cid, s in SCALES.items()]),
                ("테마", [(PALETTES[t][0], cid, t == self.theme) for cid, t in THEMES.items()]),
                ("Windows 시작 시 실행", AUTOSTART, startup.is_on(RUN_NAME, __file__)),
                None,
                ("페이지 열기 (7일치)", PAGE, False),
                ("도움말", HELP, False),
                ("작업 표시줄 진단", DIAG, False),
                None,
                ("끝내기", EXIT, False)]

    def poll(self):
        """트레이에서 온 명령을 tk 스레드에서 처리. None 은 트레이가 닫혔다는 뜻 → 같이 끝남."""
        try:
            while True:
                cid = self.commands.get_nowait()
                if cid is None:
                    self.root.destroy()
                    return
                self.handle(cid)
        except queue.Empty:
            pass
        # 커서가 올라오면 흐려져 밑의 작업 표시줄 단추가 보임. 클릭은 원래 통과됨
        r, (x, y) = self.root, self.root.winfo_pointerxy()
        over = r.winfo_rootx() <= x < r.winfo_rootx() + r.winfo_width() and r.winfo_rooty() <= y < r.winfo_rooty() + r.winfo_height()
        if over != self.faded:
            self.faded = over
            overlay.fade(r, over)
        self.root.after(100, self.poll)

    def handle(self, cid):
        if cid == SHOW:
            self.visible = not self.visible
            self.show(self.visible and not self.covered)
        elif cid in CORNERS or cid in SCALES:
            self.corner = CORNERS[cid][0] if cid in CORNERS else self.corner
            self.s = SCALES.get(cid, self.s)
            if self.corner != "bar" and self.covered:
                self.covered = False
                self.show(self.visible)
            self.place()
            self.draw()
            self.save()
        elif cid in THEMES:
            self.theme = THEMES[cid]
            use_palette(self.theme)
            self.canvas.configure(bg=COLORS["bg"])  # 트레이 아이콘은 다음에 켤 때 새 색으로
            self.draw()
            self.save()
        elif cid == AUTOSTART:
            startup.toggle(RUN_NAME, __file__)
        elif cid == PAGE:
            self.open_page()
        elif cid == HELP:
            # MessageBox 는 닫힐 때까지 막으므로 HUD 가 멈추지 않게 따로 띄움
            threading.Thread(target=ctypes.windll.user32.MessageBoxW, daemon=True,
                             args=(None, HELP_TEXT, "사용량 HUD 도움말", 0x40040)).start()  # 정보 · 맨 위
        elif cid == DIAG:
            threading.Thread(target=self.diagnose, daemon=True).start()  # UI 자동화가 몇십 ms 막음
        elif cid == EXIT:
            self.tray.close()  # 트레이가 닫히면 None 이 와서 poll 이 끝냄

    def diagnose(self):
        """작업 표시줄 위의 창 목록을 파일로 남기고 메모장으로 염. 다른 프로그램을 피해 자리를 잡기 전에 실물을 보려고."""
        try:
            DIAG_FILE.write_text(taskbar.report(), encoding="utf-8")
        except Exception:  # noqa: BLE001 — 진단이 HUD 를 죽이면 안 됨. 무엇이 났는지는 파일에 남김
            DIAG_FILE.write_text(traceback.format_exc(), encoding="utf-8")
        os.startfile(DIAG_FILE)

    def show(self, on):
        self.root.deiconify() if on else self.root.withdraw()
        if on:
            overlay.click_through(self.root)  # 다시 보일 때 확장 스타일이 풀리지 않게
            self.faded = False  # click_through 가 불투명으로 돌려 놓음

    def save(self):
        try:
            SETTINGS.parent.mkdir(parents=True, exist_ok=True)
            SETTINGS.write_text(json.dumps({"corner": self.corner, "scale": self.s, "theme": self.theme}), encoding="utf-8")
        except OSError:
            pass  # 못 남겨도 지금 화면은 바뀌었으니 넘어감

    def open_page(self):
        """page.py 의 서버를 이 프로세스 안에서 띄우고 브라우저로 연다.
        page.py 가 따로 떠 있어 포트가 차 있으면 그쪽을 그대로 연다."""
        if self.server is None:
            from http.server import ThreadingHTTPServer
            import page
            try:
                self.server = ThreadingHTTPServer(("127.0.0.1", PAGE_PORT), page.Handler)
                threading.Thread(target=self.server.serve_forever, daemon=True).start()
            except OSError:
                pass
        webbrowser.open("http://127.0.0.1:%d/" % PAGE_PORT)

    def fetch_loop(self):
        # 네트워크가 최대 usage.TIMEOUT 초 막으므로 그리는 쪽과 떼어 돌린다
        while True:
            try:
                self.snap = usage.snapshot(days=1)
                self.tray.set_tip(self.tip(self.snap))
            except Exception:  # noqa: BLE001 — HUD 는 죽지 않고 '?' 를 그리는 쪽이 낫다
                pass
            time.sleep(REFRESH_SEC)

    def watch_loop(self):
        """세션마다 일하는 중인지 봄. 어느 세션이든 일하다(work) 끝나면(done) 깜빡임 —
        Esc 로 끊었거나 오래 조용해 목록에서 빠진 것은 끝난 것이 아니라 안 깜빡임."""
        turns = {}
        while True:
            try:
                now = usage.activity()
                if any(turns.get(p) == "work" and s == "done" for p, s in now.items()):
                    self.flash_until = time.monotonic() + FLASH_SEC
                self.working, turns = "work" in now.values(), now
            except Exception:  # noqa: BLE001 — 못 읽으면 잠든 고양이로 남는 쪽이 낫다
                pass
            time.sleep(ACTIVITY_SEC)

    @staticmethod
    def tip(snap):
        """트레이 아이콘에 마우스를 올리면 뜨는 글. 127자까지."""
        if snap["expired"]:
            limits = "LOGIN 만료 — 터미널에서 claude"
        else:
            def pct(bar):
                if bar is None:
                    return "?"
                return "%d%%" % round(bar["left"] * 100) + (" (%s 뒤 바닥)" % bar["empty"] if bar.get("empty") else "")
            limits = "HP %s · ST %s" % (pct(snap["bars"]["7d"]), pct(snap["bars"]["5h"]))
        return "사용량 HUD\n%s\n오늘 $%.2f" % (limits, snap["today"])

    # ── 그리기 ──
    def px(self, x, y, color, w=1, h=1, tag=()):
        s = self.ps
        self.canvas.create_rectangle(x * s, y * s, (x + w) * s, (y + h) * s, fill=color, width=0, tags=tag)

    def art(self, x, y, rows, tag=()):
        for dy, row in enumerate(rows):
            for dx, c in enumerate(row):
                if c != ".":
                    self.px(x + dx, y + dy, COLORS[c], tag=tag)

    def draw_pet(self):
        """고양이와 끝난 뒤 깜빡이는 테두리. 1초마다 그리는 draw 와 따로 PET_MS 마다 이 몫만 다시 그림."""
        self.canvas.delete("pet")
        now = time.monotonic()
        frame = int(now * 1000 / PET_MS) % 2
        if self.flat:
            x, y, zx, zy = BAR_W - 12, BAR_H - 9, BAR_W - 6, 3
        else:
            x, y, zx, zy = 50, H - 9, 61, H - 9
        if self.working:
            self.art(x, y, PET["run1" if frame else "run2"], "pet")
        else:
            self.art(x, y, PET["sleep"], "pet")
            self.art(zx, zy + int(now) % 2, ZZZ, "pet")  # 1초마다 한 칸 들썩
        if now < self.flash_until and frame:
            w, h = (BAR_W, BAR_H) if self.flat else (W, H)
            for args in ((0, 0, w, 1), (0, h - 1, w, 1), (0, 0, 1, h), (w - 1, 0, 1, h)):
                self.px(*args[:2], COLORS["good"], *args[2:], tag="pet")

    def animate(self):
        self.draw_pet()
        self.root.after(PET_MS, self.animate)

    def text(self, x, y, s, color):
        for dx, dy in text_pixels(s):
            self.px(x + dx, y + dy, color)

    def icon(self, x, y, name):
        for dy, row in enumerate(ICONS[name]):
            for dx, c in enumerate(row):
                if c != ".":
                    self.px(x + dx, y + dy, COLORS[c])

    def bar_row(self, y, icon, label, bar, expired, blink, right):
        self.icon(2, y, icon)
        self.text(11, y + 1, label, COLORS["text"])
        x0 = 20
        if bar is None:
            for i in range(SEGMENTS):
                self.px(x0 + i * 3, y + 1, COLORS["slot"], 2, 5)
            self.text(x0 + SEGMENTS * 3 + 2, y + 1, "?", COLORS["dim"])
            if expired:  # 로그인 토큰 만료 — 터미널에서 claude 를 열면 풀림
                self.text(right - text_width("LOGIN"), y + 1, "LOGIN", COLORS["low"])
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
        if bar.get("empty_at"):  # 지금 속도면 재설정 전에 바닥 — 재설정 대신 바닥까지 남은 시간을 빨갛게
            until, tint = "!" + usage.left(bar["empty_at"] - time.time()), COLORS["low"]
        else:
            until, tint = usage.left(bar["reset"] - time.time()), COLORS["dim"]
        self.text(right - text_width(until), y + 1, until, tint)

    def draw(self):
        c = self.canvas
        c.delete("all")
        flat = self.flat
        w, h = (BAR_W, BAR_H) if flat else (W, H)
        self.px(0, 0, COLORS["edge"], w, 1)
        self.px(0, h - 1, COLORS["edge"], w, 1)
        self.px(0, 0, COLORS["edge"], 1, h)
        self.px(w - 1, 0, COLORS["edge"], 1, h)
        snap = self.snap
        blink = int(time.time()) % 2 == 0
        bars = snap["bars"] if snap else {"7d": None, "5h": None}
        expired = bool(snap and snap["expired"])
        right = BAR_RIGHT if flat else W - 2
        pitch = 8 if flat else 9  # 납작한 모양은 줄 사이를 1칸 줄여 작업 표시줄에 들어가게
        self.bar_row(2, "heart", "HP", bars["7d"], expired, blink, right)
        self.bar_row(2 + pitch, "bolt", "ST", bars["5h"], expired, blink, right)
        gold = "%.2f" % snap["today"] if snap else "?"  # 동전이 달러 표시를 대신함
        if flat:  # 두 줄 오른쪽에 칸막이를 두고 동전과 오늘 정가, 또 칸막이를 두고 고양이
            pet = w - 14
            self.px(right + 3, 2, COLORS["edge"], 1, h - 4)
            self.icon(right + 6, 2, "coin")
            self.text(right + 15, 3, gold, COLORS["y"])
            self.text(pet - 2 - text_width("TODAY"), 11, "TODAY", COLORS["dim"])
            self.px(pet, 2, COLORS["edge"], 1, h - 4)
        else:  # 고양이는 금액과 TODAY 사이
            self.icon(2, 20, "coin")
            self.text(11, 21, gold, COLORS["y"])
            self.text(W - 2 - text_width("TODAY"), 21, "TODAY", COLORS["dim"])
        self.draw_pet()

    def tick(self):
        bar = self.corner == "bar"
        if bar:
            covered = taskbar.fullscreen_app()  # 전체 화면이면 작업 표시줄과 같이 숨음
            if covered != self.covered:
                self.covered = covered
                self.show(self.visible and not covered)
            self.place()
        self.draw()
        now = time.monotonic()
        # 다른 맨 위 창(PIP 등)이 앞을 가져가도 가끔 다시 올라옴. 작업 표시줄 자리는 누르면 그쪽이
        # 앞으로 오므로 sysmon 처럼 1초마다
        if self.on_top and self.visible and now - self.last_topmost > (0.9 if bar else 2) and not overlay.layers_running():
            self.root.attributes("-topmost", True)
            self.last_topmost = now
        self.root.after(1000, self.tick)

    def run(self):
        self.tick()
        self.poll()
        self.animate()
        self.root.mainloop()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--stop", action="store_true", help="떠 있는 HUD 를 치움")
    ap.add_argument("--toggle", action="store_true", help="떠 있으면 치우고, 없으면 띄움")
    # 안 주면 트레이 메뉴에서 마지막으로 고른 값, 그것도 없으면 bl · 3
    saved = load_settings()
    ap.add_argument("--corner", default=saved.get("corner", "bl"), choices=CORNER_KEYS,
                    help="자리 (기본 bl)")
    ap.add_argument("--scale", type=int, default=saved.get("scale", 3), choices=range(1, 9),
                    help="픽셀 크기 (기본 3)")
    args = ap.parse_args()

    if args.stop:
        print("HUD 를 치움" if stop() else "떠 있는 HUD 가 없음")
        return
    if overlay.already_running(PID_FILE, TRAY_CLASS, __file__, args.toggle):
        return
    if args.toggle and Path(sys.executable).name.lower() == "python.exe":
        # hud.bat 에서 콘솔 창이 남지 않게 pythonw 로 다시 띄움
        pythonw = Path(sys.executable).with_name("pythonw.exe")
        if pythonw.exists():
            subprocess.Popen([str(pythonw), str(Path(__file__).resolve()),
                              "--corner", args.corner, "--scale", str(args.scale)], close_fds=True)
            return

    if sys.stderr is None:  # pythonw 는 stderr 가 없어 죽어도 흔적이 없음. tk 콜백 오류도 여기로 감
        sys.stderr = open(LOG_FILE, "a", encoding="utf-8", buffering=1)
        print(time.strftime("--- %Y-%m-%d %H:%M:%S 시작"), file=sys.stderr)
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)  # 배율 높은 화면에서 흐려지지 않게
    except (AttributeError, OSError):
        pass
    startup.follow(RUN_NAME, __file__)
    overlay.claim(PID_FILE, __file__)
    try:
        Hud(args.scale, args.corner, saved.get("theme", "classic")).run()
    finally:
        if running_pid() == os.getpid():
            PID_FILE.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
