# SPDX-License-Identifier: Apache-2.0
"""맨 위에 뜨는 창들(HUD·sysmon·눈·PIP …)의 앞뒤 순서를 정한다.

  pythonw layers.py            띄우기 (트레이 아이콘만 뜸)
  python layers.py --toggle    떠 있으면 치우고, 없으면 띄움 (layers.bat 이 이걸 부름)
  python layers.py --stop      치우기
  python layers.py --check     자체 점검

트레이 메뉴 '순서 정하기…' 로 창을 열어 목록에 창을 넣고 위아래로 옮긴다. 0.5초마다 목록에 든 창끼리의
상대 순서만 맞춘다 — 순서가 틀린 창을 바로 위 순위 창 밑으로 내리기만 하고 끌어올리지는 않으므로,
목록에 없는 캡처 도구·작업 관리자 같은 창은 묻히지 않는다. 목록에 넣은 일반 창은 맨 위로 고정되고,
빼거나 끝내면 풀린다. 놀이방 오버레이는 이게 떠 있는 동안 스스로 맨 위로 올리지 않는다(overlay.layers_running).
창은 실행 파일·클래스·제목으로 알아보므로, 한 번 넣은 PIP 는 다음에 뜨는 PIP 에도 그대로 적용된다.
"""
import argparse
import ctypes
import json
import os
import queue
import subprocess
import sys
import tempfile
import tkinter as tk
from ctypes import wintypes
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "shared"))
import overlay
import startup
from tray import Tray, write_ico

PID_FILE = Path(tempfile.gettempdir()) / "playroom-layers.pid"
ICON_FILE = Path(tempfile.gettempdir()) / "playroom-layers.ico"
SETTINGS = Path(os.environ.get("LOCALAPPDATA", tempfile.gettempdir())) / "playroom" / "layers.json"
OPEN, AUTOSTART, EXIT = 1, 50, 99
RUN_NAME = "PlayroomLayers"
ENFORCE_MS = 500

# 값이 없는 칸은 아무것이나 맞음. HUD 는 python/pythonw 어느 쪽으로 떠도 맞게 exe 를 비움
DEFAULT_RULES = [{"name": "usage-hud", "cls": "TkTopLevel", "title": "usage-hud"},
                 {"name": "sysmon", "cls": "PlayroomSysmonSurface"},
                 {"name": "pomodoro", "cls": "PlayroomPomodoroSurface"},
                 {"name": "pomodoro 색종이", "cls": "PlayroomPomodoroBurst"},
                 {"name": "weather (눈·비)", "cls": "PlayroomWeatherSurface"}]
SKIP_CLASSES = {"Shell_TrayWnd", "Shell_SecondaryTrayWnd", "Progman", "WorkerW", "ThumbnailDeviceHelperWnd"}

ICON_COLORS = {"b": "#5b6ee1", "y": "#feae34", "g": "#63c74d"}
ICON = ("bbbb....",
        "bbbb....",
        "bbyyyy..",
        "bbyyyy..",
        "..yygggg",
        "..yygggg",
        "....gggg",
        "....gggg")

user32, kernel32 = ctypes.windll.user32, ctypes.windll.kernel32
user32.GetTopWindow.restype = wintypes.HWND
user32.FindWindowW.restype = wintypes.HWND
user32.GetWindow.restype = wintypes.HWND
user32.GetWindow.argtypes = (wintypes.HWND, wintypes.UINT)
user32.GetWindowLongW.argtypes = (wintypes.HWND, ctypes.c_int)
user32.IsWindowVisible.argtypes = (wintypes.HWND,)
user32.IsWindow.argtypes = (wintypes.HWND,)
user32.GetClassNameW.argtypes = (wintypes.HWND, wintypes.LPWSTR, ctypes.c_int)
user32.GetWindowTextW.argtypes = (wintypes.HWND, wintypes.LPWSTR, ctypes.c_int)
user32.GetWindowRect.argtypes = (wintypes.HWND, ctypes.POINTER(wintypes.RECT))
user32.GetWindowThreadProcessId.argtypes = (wintypes.HWND, ctypes.POINTER(wintypes.DWORD))
user32.SetWindowPos.argtypes = (wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                ctypes.c_int, wintypes.UINT)
HWND_TOPMOST, HWND_NOTOPMOST = wintypes.HWND(-1), wintypes.HWND(-2)
SWP_KEEP = 0x1 | 0x2 | 0x10  # NOSIZE | NOMOVE | NOACTIVATE


def exe_name(pid, cache={}):
    if pid not in cache:
        name = ""
        h = kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        if h:
            buf, size = ctypes.create_unicode_buffer(260), wintypes.DWORD(260)
            if kernel32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size)):
                name = Path(buf.value).name.lower()
            kernel32.CloseHandle(h)
        cache[pid] = name  # ponytail: pid 재사용은 안 따짐. 이름이 틀리면 그 창이 목록에서 안 맞을 뿐
    return cache[pid]


def windows():
    """보이는 최상위 창, 앞에서 뒤 순서. 각 항목은 dict(hwnd, exe, cls, title, topmost)."""
    me, out = os.getpid(), []
    cloaked, cls, title, rect, pid = ctypes.c_int(), ctypes.create_unicode_buffer(256), \
        ctypes.create_unicode_buffer(256), wintypes.RECT(), wintypes.DWORD()
    h = user32.GetTopWindow(None)
    while h:
        if user32.IsWindowVisible(h):
            user32.GetWindowThreadProcessId(h, ctypes.byref(pid))
            user32.GetClassNameW(h, cls, 256)
            user32.GetWindowTextW(h, title, 256)
            user32.GetWindowRect(h, ctypes.byref(rect))
            ctypes.windll.dwmapi.DwmGetWindowAttribute(h, 14, ctypes.byref(cloaked), 4)  # DWMWA_CLOAKED
            if (pid.value != me and title.value and not cloaked.value and cls.value not in SKIP_CLASSES
                    and rect.right > rect.left and rect.bottom > rect.top):
                out.append({"hwnd": h, "exe": exe_name(pid.value), "cls": cls.value, "title": title.value,
                            "topmost": bool(user32.GetWindowLongW(h, -20) & 0x8)})  # WS_EX_TOPMOST
        h = user32.GetWindow(h, 2)  # GW_HWNDNEXT
    return out


def all_windows():
    """숨은 것까지 모든 최상위 창 핸들, 앞에서 뒤 순서."""
    out, h = [], user32.GetTopWindow(None)
    while h:
        out.append(h)
        h = user32.GetWindow(h, 2)  # GW_HWNDNEXT
    return out


def matches(rule, win):
    return all(rule.get(k) in (None, win[k]) for k in ("exe", "cls", "title"))


def rule_name(rule):
    return rule.get("name") or rule.get("title") or rule.get("cls")


def plan_moves(zorder, ranked):
    """ranked(앞이 위)가 zorder(앞이 위)에서 그 순서가 되게 할 (창, 바로 위에 둘 창) 목록.
    틀린 창을 윗 순위 창 바로 밑으로 내리기만 하므로 목록 밖 창보다 위로 올라가는 일은 없다."""
    z, moves = list(zorder), []
    for above, h in zip(ranked, ranked[1:]):
        if z.index(h) < z.index(above):
            z.remove(h)
            z.insert(z.index(above) + 1, h)
            moves.append((h, above))
    return moves


def load_rules():
    try:
        rules = json.loads(SETTINGS.read_text(encoding="utf-8"))["rules"]
        if isinstance(rules, list) and all(isinstance(r, dict) for r in rules):
            return [{k: r[k] for k in ("name", "exe", "cls", "title") if isinstance(r.get(k), str)} for r in rules]
    except (OSError, ValueError, KeyError, TypeError):
        pass
    return [dict(r) for r in DEFAULT_RULES]


def save_rules(rules):
    SETTINGS.parent.mkdir(parents=True, exist_ok=True)
    SETTINGS.write_text(json.dumps({"rules": rules}, ensure_ascii=False, indent=1), encoding="utf-8")


class Layers:
    def __init__(self):
        self.rules = load_rules()
        self.pinned = set()  # 원래 맨 위가 아니었는데 여기서 올린 창 → 빼거나 끝낼 때 풀어 줌
        self.root = tk.Tk()
        self.root.withdraw()
        self.win = None
        self.commands = queue.Queue()
        write_ico(ICON_FILE, ICON, ICON_COLORS)
        self.tray = Tray(overlay.LAYERS_TRAY, ICON_FILE, "창 순서", self.menu, self.commands.put)

    def menu(self):
        return [("순서 정하기…", OPEN, False), ("Windows 시작 시 실행", AUTOSTART, startup.is_on(RUN_NAME, __file__)), None, ("끝내기", EXIT, False)]

    def poll(self):
        try:
            while True:
                cid = self.commands.get_nowait()
                if cid is None:
                    self.unpin(set())
                    self.root.destroy()
                    return
                if cid == OPEN:
                    self.open()
                elif cid == AUTOSTART:
                    startup.toggle(RUN_NAME, __file__)
                elif cid == EXIT:
                    self.tray.close()  # 트레이가 닫히면 None 이 와서 끝남
        except queue.Empty:
            pass
        self.root.after(100, self.poll)

    # ── 순서 맞추기 ──
    def ranked(self, wins):
        """목록 순서대로 지금 떠 있는 창들. 한 규칙에 창이 여럿이면 지금 앞뒤 그대로, 두 규칙에 맞으면 윗 규칙."""
        out = []
        for rule in self.rules:
            out += [w for w in wins if matches(rule, w) and w not in out]
        return out

    def enforce(self):
        wins = windows()
        ranked = self.ranked(wins)
        for w in ranked:
            if not w["topmost"]:
                user32.SetWindowPos(w["hwnd"], HWND_TOPMOST, 0, 0, 0, 0, SWP_KEEP)
                self.pinned.add(w["hwnd"])
        if any(not w["topmost"] for w in ranked):  # 방금 올린 창은 자리가 바뀌었으니 다시 읽음
            wins = windows()
            ranked = self.ranked(wins)
        order = [w["hwnd"] for w in ranked]
        bar = user32.FindWindowW("Shell_TrayWnd", None)
        if bar and order:  # 작업 표시줄은 누르면 앞으로 오므로 늘 목록 맨 아래로 — 그래야 sysmon 이 그 위에 보임
            order.append(bar)
        # 관리자 권한 창은 SetWindowPos 가 막혀 그냥 실패함. 다음 차례에 또 시도할 뿐
        for h, above in plan_moves(all_windows(), order):
            user32.SetWindowPos(h, above, 0, 0, 0, 0, SWP_KEEP)
        self.unpin({w["hwnd"] for w in ranked})
        self.root.after(ENFORCE_MS, self.enforce)

    def unpin(self, keep):
        for h in self.pinned - keep:
            if user32.IsWindow(h):
                user32.SetWindowPos(h, HWND_NOTOPMOST, 0, 0, 0, 0, SWP_KEEP)
        self.pinned &= keep

    # ── 창 ──
    def open(self):
        if self.win:
            self.win.deiconify()
            self.win.lift()
            self.refresh()
            return
        self.win = w = tk.Toplevel(self.root)
        w.title("창 순서 — layers")
        w.protocol("WM_DELETE_WINDOW", self.close_window)
        pad = {"padx": 10, "pady": 4}
        tk.Label(w, text="순서 — 위에 있을수록 앞에 뜸 (● 지금 떠 있음)", anchor="w").pack(fill="x", **pad)
        self.order_box = tk.Listbox(w, height=8, width=60, exportselection=False)
        self.order_box.pack(fill="both", expand=True, padx=10)
        row = tk.Frame(w)
        row.pack(fill="x", **pad)
        for text, cmd in (("위로", lambda: self.move(-1)), ("아래로", lambda: self.move(1)), ("빼기", self.remove)):
            tk.Button(row, text=text, width=8, command=cmd).pack(side="left", padx=(0, 6))
        tk.Label(w, text="지금 열린 창 (★ 원래 맨 위) — 두 번 누르거나 '추가'로 순서 맨 아래에 넣음",
                 anchor="w").pack(fill="x", padx=10, pady=(12, 4))
        self.open_box = tk.Listbox(w, height=10, width=60, exportselection=False)
        self.open_box.pack(fill="both", expand=True, padx=10)
        self.open_box.bind("<Double-Button-1>", lambda e: self.add())
        row = tk.Frame(w)
        row.pack(fill="x", padx=10, pady=(4, 10))
        tk.Button(row, text="추가", width=8, command=self.add).pack(side="left", padx=(0, 6))
        tk.Button(row, text="새로 고침", width=8, command=self.refresh).pack(side="left")
        self.refresh()

    def close_window(self):
        self.win.destroy()
        self.win = None

    def refresh(self, select=None):
        wins = windows()
        self.candidates = [w for w in wins if not any(matches(r, w) for r in self.rules)]
        self.order_box.delete(0, "end")
        for r in self.rules:
            here = any(matches(r, w) for w in wins)
            extra = "  (%s)" % r["exe"] if r.get("exe") else ""
            self.order_box.insert("end", ("● " if here else "○ ") + rule_name(r) + extra)
        if select is not None:
            self.order_box.selection_set(select)
        self.open_box.delete(0, "end")
        for w in self.candidates:
            self.open_box.insert("end", ("★ " if w["topmost"] else "   ") + "%s  (%s)" % (w["title"], w["exe"]))

    def changed(self, select=None):
        save_rules(self.rules)
        self.refresh(select)

    def move(self, d):
        sel = self.order_box.curselection()
        if not sel or not 0 <= sel[0] + d < len(self.rules):
            return
        i = sel[0]
        self.rules[i], self.rules[i + d] = self.rules[i + d], self.rules[i]
        self.changed(i + d)

    def remove(self):
        sel = self.order_box.curselection()
        if sel:
            del self.rules[sel[0]]
            self.changed()

    def add(self):
        sel = self.open_box.curselection()
        if sel:
            w = self.candidates[sel[0]]
            self.rules.append({"exe": w["exe"], "cls": w["cls"], "title": w["title"]})
            self.changed(len(self.rules) - 1)

    def run(self):
        self.root.after(100, self.poll)
        self.root.after(ENFORCE_MS, self.enforce)
        self.root.mainloop()


def check():
    assert plan_moves(["c", "b", "a"], ["a", "b", "c"]) == [("b", "a"), ("c", "b")]
    assert plan_moves(["a", "b", "c"], ["a", "b", "c"]) == [], "맞으면 안 건드림"
    assert plan_moves(["x", "b", "y", "a"], ["a", "b"]) == [("b", "a")], "x·y 는 그대로"
    z, ranked = ["x", "c", "y", "a", "z", "b"], ["a", "b", "c"]
    for h, above in plan_moves(z, ranked):
        z.remove(h)
        z.insert(z.index(above) + 1, h)
    assert [h for h in z if h in ranked] == ranked and z[0] == "x", "목록 밖 창보다 위로 안 올라감"
    w = {"exe": "pythonw.exe", "cls": "TkTopLevel", "title": "usage-hud"}
    assert matches(DEFAULT_RULES[0], w) and not matches(DEFAULT_RULES[1], w)
    assert not matches({"exe": "python.exe", "cls": "TkTopLevel"}, w)
    assert windows(), "보이는 창이 하나는 있어야 함"
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
        print("치움" if overlay.stop(PID_FILE, overlay.LAYERS_TRAY) else "떠 있는 것이 없음")
        return
    if overlay.running_pid(PID_FILE) is not None:
        if args.toggle:
            overlay.stop(PID_FILE, overlay.LAYERS_TRAY)
        return
    if args.toggle and Path(sys.executable).name.lower() == "python.exe":
        pythonw = Path(sys.executable).with_name("pythonw.exe")  # 콘솔 창이 남지 않게
        if pythonw.exists():
            subprocess.Popen([str(pythonw), str(Path(__file__).resolve())], close_fds=True)
            return
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except (AttributeError, OSError):
        pass
    PID_FILE.write_text(str(os.getpid()))
    try:
        Layers().run()
    finally:
        if overlay.running_pid(PID_FILE) == os.getpid():
            PID_FILE.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
