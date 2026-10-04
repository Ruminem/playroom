# SPDX-License-Identifier: Apache-2.0
"""놀이방 도구를 한 창에서: 설치(시작 메뉴 바로가기)·제거, 실행·중단, 항상 위, Windows 시작 시 실행.

  python launcher.py           창을 띄움
  python launcher.py --check   자체 점검 (바로가기는 임시 폴더에 만들었다 지움)
"""
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

DATA = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "playroom"
MENU = Path(os.environ.get("APPDATA", Path.home())) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Playroom"
EXE = Path(sys.executable).with_name("pythonw.exe")
EXE = EXE if EXE.exists() else Path(sys.executable)
NO_WINDOW = 0x08000000  # CREATE_NO_WINDOW
# ponytail: 바로가기 아이콘은 pythonw 것. 도구 아이콘은 임시 폴더에 그려지는 것이라 가리키면 지워질 수 있음
LINK_PS = ("$s = (New-Object -ComObject WScript.Shell).CreateShortcut($env:LNK); $s.TargetPath = $env:EXE; "
           "$s.Arguments = $env:ARGS; $s.WorkingDirectory = $env:DIR; $s.Save()")
UI_FONT = "Malgun Gothic"


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


class Launcher:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("playroom")
        self.root.resizable(False, False)
        self.rows = []
        heads = ("", "", "", "", "항상 위", "Windows 시작 시 실행")
        for c, h in enumerate(heads):
            tk.Label(self.root, text=h, font=(UI_FONT, 9), fg="#6b7080").grid(row=0, column=c, padx=6, pady=(10, 2))
        for r, t in enumerate(TOOLS, 1):
            row = {"dot": tk.Label(self.root, text="●", font=(UI_FONT, 12)),
                   "run": tk.Button(self.root, width=6, command=lambda t=t: self.work(t, stop if running(t) else start)),
                   "inst": tk.Button(self.root, width=6, command=lambda t=t: self.install_click(t)),
                   "top": tk.BooleanVar(), "auto": tk.BooleanVar()}
            tk.Label(self.root, text=t.label, font=(UI_FONT, 10, "bold"), anchor="w", width=10).grid(row=r, column=0, padx=(12, 0), pady=4, sticky="w")
            tk.Label(self.root, text=t.name, font=(UI_FONT, 9), fg="#6b7080", anchor="w", width=9).grid(row=r, column=1, sticky="w")
            row["dot"].grid(row=r, column=2)
            row["run"].grid(row=r, column=3, padx=6)
            row["inst"].grid(row=r, column=6, padx=(6, 12))
            row["topbox"] = tk.Checkbutton(self.root, variable=row["top"], state="normal" if t.pick_top else "disabled",
                                           command=lambda t=t, v=row["top"]: self.work(t, lambda t: set_on_top(t, v.get())))
            row["topbox"].grid(row=r, column=4)
            tk.Checkbutton(self.root, variable=row["auto"],
                           command=lambda t=t, v=row["auto"]: self.work(t, lambda t: startup.set(t.run, t.script, v.get()))
                           ).grid(row=r, column=5)
            self.rows.append((t, row))
        tk.Label(self.root, text="").grid(row=len(TOOLS) + 1, column=0, pady=2)
        self.refresh()

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
        if not t.link.exists():
            self.work(t, install)
        elif messagebox.askyesno("playroom", f"{t.label}({t.name}) 를 제거할까요?\n\n끄고, 시작 시 실행을 풀고, "
                                 f"시작 메뉴 바로가기와 설정 파일({t.settings.name})을 지웁니다.", parent=self.root):
            self.work(t, uninstall)

    def refresh(self):
        off = overlay.below()
        for t, row in self.rows:
            on = running(t)
            row["dot"].config(fg="#3fa34d" if on else "#c4c8d0")
            state = "disabled" if t.busy else "normal"
            row["run"].config(text="중단" if on else "실행", state=state)
            row["inst"].config(text="제거" if t.link.exists() else "설치", state=state)
            if not t.busy:
                row["top"].set(t.pick_top and t.name not in off)
                row["auto"].set(startup.is_on(t.run, t.script))
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
        Launcher().root.mainloop()
