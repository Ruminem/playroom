# SPDX-License-Identifier: Apache-2.0
"""화면 구석에 늘 떠 있는 레트로 게임 HUD — Claude Code 구독 한도를 체력바로.

  pythonw hud.py              띄우기 (창 없이 뒤에서 돎)
  python hud.py --toggle      떠 있으면 치우고, 없으면 띄움 (hud.bat 이 이걸 부름)
  python hud.py --stop        치우기
  python hud.py --corner tr   자리: bl(기본) · br · tl · tr
  python hud.py --scale 4     픽셀 하나의 크기 (기본 3)

HP 는 7일 창, ST 는 5시간 창의 **남은** 양이다. 칸 옆은 재설정까지 남은 시간.
동전 줄은 오늘 쓴 정가. 창은 맨 위에 있지만 클릭을 아래로 통과시키고 포커스도 안 뺏는다.
대신 트레이(알림 영역)에 하트 아이콘이 뜨고, 그 메뉴에서 숨기기·위치·크기·페이지·끝내기를 한다.
메뉴에서 고른 위치와 크기는 SETTINGS 에 남아 다음에 켤 때도 쓰인다.
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
import webbrowser
import winreg
from pathlib import Path

import usage
from font import COLORS, ICONS, text_pixels, text_width
from tray import Tray, write_ico

PID_FILE = Path(tempfile.gettempdir()) / "playroom-usage-hud.pid"
ICON_FILE = Path(tempfile.gettempdir()) / "playroom-usage-hud.ico"
SETTINGS = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "playroom" / "usage-hud.json"
TRAY_CLASS = "PlayroomUsageHudTray"  # --stop 이 이 이름으로 창을 찾아 닫으라고 보냄
REFRESH_SEC = 60   # 정가를 다시 셈. 한도는 usage.LIMIT_EVERY 가 따로 5분에 한 번으로 묶음
MARGIN = 12        # 작업 영역 가장자리에서 띄울 px
SEGMENTS = 10      # 칸 수. 한 칸 = 10%
W, H = 90, 29      # 패널 크기 (픽셀 단위)
PAGE_PORT = 8765

# 메뉴 id
SHOW, PAGE, HELP, AUTOSTART, EXIT = 1, 30, 40, 50, 99

# 윈도우 시작 시 실행: 현재 사용자의 Run 키. 설정 앱 '시작 앱' 에서 끄면 Run 값은 남고
# StartupApproved 에 첫 바이트가 홀수인 값이 생긴다 (이 PC 실측 2026-10-04: 켬 2 · 끔 3)
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
APPROVED_KEY = r"Software\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved\Run"
RUN_NAME = "PlayroomUsageHud"
CORNERS = {10: ("bl", "왼쪽 아래"), 11: ("br", "오른쪽 아래"), 12: ("tl", "왼쪽 위"), 13: ("tr", "오른쪽 위")}
SCALES = {20 + s: s for s in (2, 3, 4, 5)}

HELP_TEXT = """HP (하트) — 7일 한도의 남은 양
ST (번개) — 5시간 한도의 남은 양
동전 — 이 PC 에서 오늘 쓴 토큰을 API 정가로 친 달러. 구독이면 실제로 나가는 돈은 아님

막대 옆은 재설정까지 남은 시간이고, 10% 아래로 내려가면 깜빡입니다.
한도는 5분, 정가는 1분마다 다시 받습니다.

LOGIN 이 뜨면 CLI 로그인 토큰이 만료된 것입니다. 터미널에서 claude 를 한 번 열면 풀립니다.

HUD 는 클릭이 통과하므로 이 트레이 메뉴로 숨기거나 끕니다."""


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
    """트레이 창에 닫으라고 보내고 기다린다. 그냥 죽이면 트레이에 유령 아이콘이 남는다."""
    pid = running_pid()
    if pid is None:
        return False
    hwnd = ctypes.windll.user32.FindWindowW(TRAY_CLASS, None)
    if hwnd:
        ctypes.windll.user32.PostMessageW(hwnd, 0x0010, 0, 0)  # WM_CLOSE
        for _ in range(30):
            if running_pid() is None:
                return True
            time.sleep(0.1)
    os.kill(pid, 9)  # 3초 안에 안 끝나면 강제로
    PID_FILE.unlink(missing_ok=True)
    return True


def autostart_command():
    """시작할 때 부를 명령. 콘솔 창이 안 뜨게 pythonw, 위치·크기는 저장된 설정을 따름."""
    exe = Path(sys.executable)
    w = exe.with_name("pythonw.exe")
    return '"%s" "%s"' % (w if w.exists() else exe, Path(__file__).resolve())


def autostart_on():
    """Run 값이 지금 이 파일을 가리키고, 설정 앱에서 꺼 두지도 않았으면 True.
    저장소 폴더를 옮겨 경로가 달라졌으면 False — 다시 켜면 새 경로로 고쳐 씀."""
    hkcu = winreg.HKEY_CURRENT_USER
    try:
        with winreg.OpenKey(hkcu, RUN_KEY) as k:
            if winreg.QueryValueEx(k, RUN_NAME)[0] != autostart_command():
                return False
    except OSError:
        return False
    try:
        with winreg.OpenKey(hkcu, APPROVED_KEY) as k:
            data = winreg.QueryValueEx(k, RUN_NAME)[0]
    except OSError:
        return True  # 설정 앱에서 손댄 적 없음
    return not (data and data[0] & 1)


def set_autostart(on):
    hkcu = winreg.HKEY_CURRENT_USER
    with winreg.CreateKey(hkcu, RUN_KEY) as k:
        if on:
            winreg.SetValueEx(k, RUN_NAME, 0, winreg.REG_SZ, autostart_command())
        else:
            try:
                winreg.DeleteValue(k, RUN_NAME)
            except FileNotFoundError:
                pass
    # 설정 앱에서 꺼 둔 표식이 남아 있으면 켜도 안 뜨므로 같이 지운다. 끌 때도 지워 흔적을 안 남김
    try:
        with winreg.OpenKey(hkcu, APPROVED_KEY, 0, winreg.KEY_SET_VALUE) as k:
            winreg.DeleteValue(k, RUN_NAME)
    except OSError:
        pass


def load_settings():
    """손으로 고친 파일이 이상해도 엉뚱한 크기로 뜨지 않게 아는 값만 남긴다."""
    try:
        data = json.loads(SETTINGS.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(data, dict):
        return {}
    ok = {}
    if data.get("corner") in ("bl", "br", "tl", "tr"):
        ok["corner"] = data["corner"]
    if data.get("scale") in range(1, 9):
        ok["scale"] = data["scale"]
    return ok


def work_area():
    """작업 표시줄을 뺀 주 모니터 영역 (left, top, right, bottom)."""
    rect = (ctypes.c_long * 4)()
    ctypes.windll.user32.SystemParametersInfoW(0x30, 0, rect, 0)  # SPI_GETWORKAREA
    return tuple(rect)


def level_color(left):
    return COLORS["good"] if left > 0.5 else COLORS["mid"] if left > 0.2 else COLORS["low"]


class Hud:
    def __init__(self, scale, corner):
        self.s, self.corner, self.visible = scale, corner, True
        self.root = tk.Tk()
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.canvas = tk.Canvas(self.root, bg=COLORS["bg"], bd=0, highlightthickness=0)
        self.canvas.pack()
        self.place()
        self.root.update_idletasks()
        self.make_click_through()
        self.snap = None
        self.server = None
        self.last_topmost = time.monotonic()
        self.commands = queue.Queue()  # 트레이 스레드 → tk 스레드
        write_ico(ICON_FILE, ICONS["heart"], COLORS)
        self.tray = Tray(TRAY_CLASS, ICON_FILE, "사용량 HUD", self.menu, self.commands.put)
        threading.Thread(target=self.fetch_loop, daemon=True).start()

    def place(self):
        s = self.s
        self.canvas.configure(width=W * s, height=H * s)
        l, t, r, b = work_area()
        x = l + MARGIN if "l" in self.corner else r - MARGIN - W * s
        y = t + MARGIN if "t" in self.corner else b - MARGIN - H * s
        self.root.geometry(f"{W * s}x{H * s}+{x}+{y}")

    # ── 트레이 ──
    def menu(self):
        return [("HUD 보이기", SHOW, self.visible),
                ("위치", [(name, cid, c == self.corner) for cid, (c, name) in CORNERS.items()]),
                ("크기", [("%d배" % s, cid, s == self.s) for cid, s in SCALES.items()]),
                ("Windows 시작 시 실행", AUTOSTART, autostart_on()),
                None,
                ("페이지 열기 (7일치)", PAGE, False),
                ("도움말", HELP, False),
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
        self.root.after(100, self.poll)

    def handle(self, cid):
        if cid == SHOW:
            self.visible = not self.visible
            self.root.deiconify() if self.visible else self.root.withdraw()
            if self.visible:
                self.make_click_through()  # 다시 보일 때 확장 스타일이 풀리지 않게
        elif cid in CORNERS or cid in SCALES:
            self.corner = CORNERS[cid][0] if cid in CORNERS else self.corner
            self.s = SCALES.get(cid, self.s)
            self.place()
            self.save()
        elif cid == AUTOSTART:
            try:
                set_autostart(not autostart_on())
            except OSError:
                pass  # 레지스트리를 못 쓰면 체크가 그대로 남아 실패가 보임
        elif cid == PAGE:
            self.open_page()
        elif cid == HELP:
            # MessageBox 는 닫힐 때까지 막으므로 HUD 가 멈추지 않게 따로 띄움
            threading.Thread(target=ctypes.windll.user32.MessageBoxW, daemon=True,
                             args=(None, HELP_TEXT, "사용량 HUD 도움말", 0x40040)).start()  # 정보 · 맨 위
        elif cid == EXIT:
            self.tray.close()  # 트레이가 닫히면 None 이 와서 poll 이 끝냄

    def save(self):
        try:
            SETTINGS.parent.mkdir(parents=True, exist_ok=True)
            SETTINGS.write_text(json.dumps({"corner": self.corner, "scale": self.s}), encoding="utf-8")
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
                self.tray.set_tip(self.tip(self.snap))
            except Exception:  # noqa: BLE001 — HUD 는 죽지 않고 '?' 를 그리는 쪽이 낫다
                pass
            time.sleep(REFRESH_SEC)

    @staticmethod
    def tip(snap):
        """트레이 아이콘에 마우스를 올리면 뜨는 글. 127자까지."""
        if snap["expired"]:
            limits = "LOGIN 만료 — 터미널에서 claude"
        else:
            def pct(bar):
                return "?" if bar is None else "%d%%" % round(bar["left"] * 100)
            limits = "HP %s · ST %s" % (pct(snap["bars"]["7d"]), pct(snap["bars"]["5h"]))
        return "사용량 HUD\n%s\n오늘 $%.2f" % (limits, snap["today"])

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
        if self.visible and now - self.last_topmost > 2:
            self.root.attributes("-topmost", True)
            self.last_topmost = now
        self.root.after(1000, self.tick)

    def run(self):
        self.tick()
        self.poll()
        self.root.mainloop()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--stop", action="store_true", help="떠 있는 HUD 를 치움")
    ap.add_argument("--toggle", action="store_true", help="떠 있으면 치우고, 없으면 띄움")
    # 안 주면 트레이 메뉴에서 마지막으로 고른 값, 그것도 없으면 bl · 3
    saved = load_settings()
    ap.add_argument("--corner", default=saved.get("corner", "bl"), choices=("bl", "br", "tl", "tr"),
                    help="자리 (기본 bl)")
    ap.add_argument("--scale", type=int, default=saved.get("scale", 3), choices=range(1, 9),
                    help="픽셀 크기 (기본 3)")
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
