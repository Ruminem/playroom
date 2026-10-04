# SPDX-License-Identifier: Apache-2.0
"""놀이방 도구를 한 창에서: 설치(시작 메뉴 바로가기)·제거, 실행·중단, 항상 위, Windows 시작 시 실행.

  python launcher.py           창을 띄움
  python launcher.py --check   자체 점검 (바로가기는 임시 폴더에 만들었다 지움)
"""
import ctypes
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import threading
import tkinter as tk
from pathlib import Path
from tkinter import messagebox

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "shared"))
import overlay  # noqa: E402
import startup  # noqa: E402
from icon import write_ico  # noqa: E402

DATA = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "playroom"
MENU = Path(os.environ.get("APPDATA", Path.home())) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Playroom"
EXE = Path(sys.executable).with_name("pythonw.exe")
EXE = EXE if EXE.exists() else Path(sys.executable)
NO_WINDOW = 0x08000000  # CREATE_NO_WINDOW
# ponytail: 바로가기 아이콘은 pythonw 것. 도구 아이콘은 임시 폴더에 그려지는 것이라 가리키면 지워질 수 있음
LINK_PS = ("$s = (New-Object -ComObject WScript.Shell).CreateShortcut($env:LNK); $s.TargetPath = $env:EXE; "
           "$s.Arguments = $env:ARGS; $s.WorkingDirectory = $env:DIR; $s.Save()")
UI_FONT = "Malgun Gothic"
ICON_FILE = DATA / "launcher.ico"  # 임시 폴더가 아닌 곳 — 창이 떠 있는 동안 지워지면 안 됨
ICON_COLORS = {"r": "#e43b44", "b": "#3b6ef5", "g": "#63c74d", "y": "#feae34"}  # 도구 넷: HUD 하트 · 날씨 · sysmon · layers
ICON = ("rrr.bbb",
        "rrr.bbb",
        "rrr.bbb",
        ".......",
        "ggg.yyy",
        "ggg.yyy",
        "ggg.yyy")


class Tool:
    """도구 하나. 값은 각 도구에서 옮겨 적은 것이고 check() 가 도구를 import 해서 같은지 대조함."""

    def __init__(self, name, label, script, tray, run, pick_top):
        self.name, self.label, self.tray, self.run, self.pick_top = name, label, tray, run, pick_top
        self.script = ROOT / script
        self.pid = Path(tempfile.gettempdir()) / f"playroom-{name}.pid"
        self.settings = DATA / f"{name}.json"
        self.link = MENU / f"{name}.lnk"
        self.busy = False


TOOLS = [Tool("usage-hud", "사용량 HUD", "usage-hud/hud.py", "PlayroomUsageHudTray", "PlayroomUsageHud", True),
         Tool("weather", "날씨", "weather/weather.py", "PlayroomWeatherTray", "PlayroomWeather", True),
         Tool("sysmon", "CPU·메모리", "sysmon/sysmon.py", "PlayroomSysmonTray", "PlayroomSysmon", True),
         Tool("layers", "창 순서", "layers/layers.py", overlay.LAYERS_TRAY, "PlayroomLayers", False)]


def running(t):
    return overlay.running_pid(t.pid) is not None


def start(t):
    """인자 없이 띄우면 도구가 저장된 설정을 따름. 이미 떠 있으면 도구가 알아서 그냥 끝남."""
    subprocess.Popen([str(EXE), str(t.script)], cwd=t.script.parent, close_fds=True, creationflags=NO_WINDOW)


def stop(t):
    overlay.stop(t.pid, t.tray)


def set_on_top(t, on):
    """launcher.json 의 below 를 고치고, 떠 있으면 다시 띄워 적용함 (도구는 뜰 때 한 번 읽음)."""
    try:
        data = json.loads(overlay.LAUNCHER_FILE.read_text(encoding="utf-8"))
        data = data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        data = {}
    off = overlay.below() - {t.name} | (set() if on else {t.name})
    data["below"] = sorted(off)
    overlay.LAUNCHER_FILE.parent.mkdir(parents=True, exist_ok=True)
    overlay.LAUNCHER_FILE.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    if running(t):
        stop(t)
        start(t)


def install(t):
    """시작 메뉴 Playroom 폴더에 바로가기. 누르면 .bat 처럼 켜고 끔."""
    t.link.parent.mkdir(parents=True, exist_ok=True)
    env = {**os.environ, "LNK": str(t.link), "EXE": str(EXE), "ARGS": f'"{t.script}" --toggle', "DIR": str(t.script.parent)}
    subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", LINK_PS],
                   env=env, check=True, capture_output=True, creationflags=NO_WINDOW)


def uninstall(t):
    """끄고, 시작 시 실행을 풀고, 바로가기와 설정 파일을 지움. 저장소의 파일은 안 건드림."""
    stop(t)
    startup.set(t.run, t.script, False)
    t.link.unlink(missing_ok=True)
    t.settings.unlink(missing_ok=True)
    if t.name in overlay.below():
        set_on_top(t, True)
    try:
        t.link.parent.rmdir()  # 비었을 때만 지워짐
    except OSError:
        pass


BG, CARD, LINE, TEXT, MUTED = "#ffffff", "#f5f6f8", "#e4e6eb", "#1f2329", "#6b7080"
ACCENT, ACCENT_DOWN, GREEN, GREY, AMBER, RED = "#3b6ef5", "#2f5bd6", "#34a853", "#c4c8d0", "#f2a60c", "#d93025"


class Switch(tk.Canvas):
    """둥근 켜고 끄기 스위치. 누르면 command(새 값). 화면은 refresh 가 set 으로 맞춤."""

    def __init__(self, parent, px, command, enabled=True):
        self.w, self.h = px(36), px(20)
        super().__init__(parent, width=self.w, height=self.h, bg=CARD, highlightthickness=0,
                         cursor="hand2" if enabled else "")
        self.px, self.enabled, self.on = px, enabled, None
        if enabled:
            self.bind("<Button-1>", lambda e: command(not self.on))
        self.set(False)

    def set(self, on):
        if on == self.on:
            return
        self.on = on
        self.delete("all")
        w, h, k = self.w, self.h, self.px(3)
        fill = (ACCENT if on else GREY) if self.enabled else LINE
        for box in ((0, 0, h, h), (w - h, 0, w, h)):
            self.create_oval(*box, fill=fill, outline=fill)
        self.create_rectangle(h / 2, 0, w - h / 2, h, fill=fill, outline=fill)
        x = w - h if on else 0
        self.create_oval(x + k, k, x + h - k, h - k, fill=BG, outline=BG)


class Launcher:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("playroom")
        self.root.resizable(False, False)
        self.root.configure(bg=BG)
        try:
            ICON_FILE.parent.mkdir(parents=True, exist_ok=True)
            write_ico(ICON_FILE, ICON, ICON_COLORS)
            self.root.iconbitmap(default=str(ICON_FILE))
        except (OSError, tk.TclError):
            pass  # 아이콘이 없어도 창은 뜸
        px = self.px = lambda n: round(n * float(self.root.tk.call("tk", "scaling")) * 0.75)  # 96dpi 기준 px → 지금 화면 px
        body = tk.Frame(self.root, bg=BG, padx=px(18), pady=px(16))
        body.pack(fill="both")
        head = tk.Frame(body, bg=BG)
        head.pack(fill="x", pady=(0, px(10)))
        tk.Label(head, text="playroom", font=(UI_FONT, 15, "bold"), fg=TEXT, bg=BG).pack(side="left")
        self.summary = tk.Label(head, font=(UI_FONT, 9), fg=MUTED, bg=BG)
        self.summary.pack(side="left", padx=px(10), pady=(px(5), 0))

        cols = (px(16), px(170), px(72), px(96), px(96), px(72))  # 점 · 이름 · 항상 위 · 시작 시 실행 · 시작 메뉴 · 실행
        caps = tk.Frame(body, bg=BG, padx=px(14))
        caps.pack(fill="x")
        for c, text in ((2, "항상 위"), (3, "시작 시 실행"), (4, "시작 메뉴")):
            tk.Label(caps, text=text, font=(UI_FONT, 8), fg=MUTED, bg=BG).grid(row=0, column=c)
        for c, w in enumerate(cols):
            caps.columnconfigure(c, minsize=w)

        self.rows = []
        for t in TOOLS:
            card = tk.Frame(body, bg=CARD, padx=px(14), pady=px(10), highlightthickness=1, highlightbackground=LINE)
            card.pack(fill="x", pady=px(3))
            for c, w in enumerate(cols):
                card.columnconfigure(c, minsize=w)
            row = {"dot": tk.Canvas(card, width=px(10), height=px(10), bg=CARD, highlightthickness=0)}
            row["dot"].create_oval(0, 0, px(10) - 1, px(10) - 1, outline="", tags="d")
            row["dot"].grid(row=0, column=0, rowspan=2, sticky="w")
            tk.Label(card, text=t.label, font=(UI_FONT, 10, "bold"), fg=TEXT, bg=CARD).grid(row=0, column=1, sticky="w")
            tk.Label(card, text=t.name, font=(UI_FONT, 8), fg=MUTED, bg=CARD).grid(row=1, column=1, sticky="w")
            row["top"] = Switch(card, px, lambda on, t=t: self.work(t, lambda t: set_on_top(t, on)), t.pick_top)
            row["auto"] = Switch(card, px, lambda on, t=t: self.work(t, lambda t: startup.set(t.run, t.script, on)))
            row["top"].grid(row=0, column=2, rowspan=2)
            row["auto"].grid(row=0, column=3, rowspan=2)
            row["inst"] = tk.Label(card, font=(UI_FONT, 8), bg=CARD)
            row["inst"].grid(row=0, column=4)
            row["uninst"] = self.link(card, "제거", RED, lambda t=t: self.install_click(t))
            row["uninst"].grid(row=1, column=4)
            row["run"] = tk.Label(card, font=(UI_FONT, 9, "bold"), width=6, pady=px(4), cursor="hand2", highlightthickness=1)
            row["run"].grid(row=0, column=5, rowspan=2, sticky="e")
            row["run"].bind("<Button-1>", lambda e, t=t: self.work(t, stop if running(t) else start))
            row["inst"].bind("<Button-1>", lambda e, t=t: None if t.link.exists() else self.work(t, install))
            self.rows.append((t, row))
        self.refresh()

    def link(self, parent, text, color, command):
        lab = tk.Label(parent, text=text, font=(UI_FONT, 8, "underline"), fg=color, bg=CARD, cursor="hand2")
        lab.bind("<Button-1>", lambda e: command())
        return lab

    def work(self, t, fn):
        """끄기는 3초까지, 바로가기는 1초쯤 걸리므로 따로 돌림. 화면은 refresh 가 따라 고침."""
        if t.busy:
            return
        t.busy = True

        def go():
            try:
                fn(t)
            except (OSError, subprocess.CalledProcessError):
                pass  # 다음 refresh 에 원래 상태가 그대로 보여 실패가 드러남
            finally:
                t.busy = False
        threading.Thread(target=go, daemon=True).start()

    def install_click(self, t):
        if t.link.exists() and messagebox.askyesno("playroom", f"{t.label}({t.name}) 를 제거할까요?\n\n끄고, 시작 시 실행을 풀고, "
                                 f"시작 메뉴 바로가기와 설정 파일({t.settings.name})을 지웁니다.", parent=self.root):
            self.work(t, uninstall)

    def refresh(self):
        off, n = overlay.below(), 0
        for t, row in self.rows:
            on = running(t)
            n += on
            row["dot"].itemconfig("d", fill=AMBER if t.busy else GREEN if on else GREY)
            # 실행은 채운 파란 단추, 중단은 테두리 단추. 일하는 동안은 흐리게
            fg, bg, edge = (MUTED, CARD, LINE) if t.busy else (TEXT, BG, LINE) if on else ("white", ACCENT, ACCENT)
            row["run"].config(text="중단" if on else "실행", fg=fg, bg=bg, highlightbackground=edge,
                              cursor="" if t.busy else "hand2")
            linked = t.link.exists()
            row["inst"].config(text="✓ 설치됨" if linked else "설치", fg=GREEN if linked else ACCENT,
                               font=(UI_FONT, 8, "" if linked else "underline"), cursor="" if linked else "hand2")
            row["inst"].grid(rowspan=1 if linked else 2)  # 제거 링크가 없으면 가운데로
            if linked:
                row["uninst"].grid()
            else:
                row["uninst"].grid_remove()
            if not t.busy:
                row["top"].set(t.pick_top and t.name not in off)
                row["auto"].set(startup.is_on(t.run, t.script))
        self.summary.config(text=f"도구 {len(self.rows)}개 · {n}개 실행 중")
        self.root.after(1000, self.refresh)


def check():
    mods = {}
    for t in TOOLS:
        sys.path.insert(0, str(t.script.parent))
        spec = importlib.util.spec_from_file_location("tool_" + t.name.replace("-", "_"), t.script)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        mods[t.name] = mod
        assert (mod.PID_FILE, mod.SETTINGS, mod.RUN_NAME) == (t.pid, t.settings, t.run), (t.name, "도구의 값과 같음")
        assert getattr(mod, "TRAY_CLASS", overlay.LAYERS_TRAY) == t.tray, (t.name, "트레이 창")
        src = t.script.read_text(encoding="utf-8")
        assert (f'overlay.on_top("{t.name}")' in src) == t.pick_top, (t.name, "항상 위를 읽는 이름")

    tmp = Path(tempfile.mkdtemp())
    real = overlay.LAUNCHER_FILE
    overlay.LAUNCHER_FILE = tmp / "launcher.json"
    try:
        w, s = (Tool(t.name, t.label, "launcher/launcher.py", "PlayroomNoSuchTray", "", True) for t in TOOLS[1:3])
        w.pid = s.pid = tmp / "none.pid"  # 떠 있는 진짜 도구를 다시 띄우지 않게
        set_on_top(w, False)
        assert not overlay.on_top("weather") and overlay.on_top("sysmon"), "끈 것만 내려감"
        overlay.LAUNCHER_FILE.write_text('{"below": ["weather"], "x": 1}', encoding="utf-8")
        set_on_top(s, False)
        assert overlay.below() == {"weather", "sysmon"}, "다른 도구 값은 그대로"
        assert json.loads(overlay.LAUNCHER_FILE.read_text(encoding="utf-8"))["x"] == 1, "모르는 칸도 그대로"
        for bad in ("", "[1]", '{"below": "weather"}', '{"below": [1, "sysmon"]}'):
            overlay.LAUNCHER_FILE.write_text(bad, encoding="utf-8")
            assert overlay.below() <= {"sysmon"}, ("깨진 파일은 다 켠 것으로", bad)

        layers = mods["layers"]
        wins = [{"cls": "PlayroomWeatherSurface"}, {"cls": "PlayroomSysmonSurface"}]
        fake = type("F", (), {"rules": layers.DEFAULT_RULES})()
        overlay.LAUNCHER_FILE.write_text('{"below": ["weather"]}', encoding="utf-8")
        assert layers.Layers.ranked(fake, wins) == wins[1:], "layers 는 항상 위를 끈 도구를 안 올림"

        fake_tool = Tool("selfcheck", "점검", "launcher/launcher.py", "PlayroomNoSuchTray", "PlayroomLauncherSelfCheck", True)
        fake_tool.pid, fake_tool.settings = tmp / "none.pid", tmp / "selfcheck.json"
        fake_tool.link = tmp / "menu" / "selfcheck.lnk"
        fake_tool.settings.write_text("{}", encoding="utf-8")
        install(fake_tool)
        assert fake_tool.link.stat().st_size > 0, "바로가기 만듦"
        overlay.LAUNCHER_FILE.write_text('{"below": ["selfcheck"]}', encoding="utf-8")
        uninstall(fake_tool)
        assert not fake_tool.link.exists() and not fake_tool.settings.exists(), "제거하면 바로가기·설정이 지워짐"
        assert not fake_tool.link.parent.exists(), "빈 폴더도 지움"
        assert overlay.below() == set(), "항상 위 표식도 지움"
    finally:
        overlay.LAUNCHER_FILE = real
    print("자체 점검 통과")


if __name__ == "__main__":
    if "--check" in sys.argv:
        check()
    else:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)  # 배율 높은 화면에서 흐려지지 않게
        # 작업 표시줄이 pythonw 로 묶어 파이썬 아이콘을 띄우지 않고 창 아이콘을 쓰게
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("Ruminem.playroom.launcher")
        Launcher().root.mainloop()
