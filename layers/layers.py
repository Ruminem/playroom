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
앱 ID 가 붙은 창(크롬 PWA 등)은 제목 대신 앱 ID 로 알아본다 — 제목이 영상·알림 수마다 바뀌기 때문이다.
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
import tkinter.font as tkfont
from tkinter import ttk
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
                 {"name": "weather (눈·비)", "cls": "PlayroomWeatherSurface"}]
UI_FONT = "Malgun Gothic"
MUTED = "#6b7080"
DOTS = {"on": "#3fa34d", "off": "#c4c8d0", "pin": "#f2a60c", "none": None}  # 순서 창의 점 색. None 은 빈칸 (줄 맞춤용)
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


class GUID(ctypes.Structure):
    _fields_ = [("a", ctypes.c_uint32), ("b", ctypes.c_uint16), ("c", ctypes.c_uint16), ("d", ctypes.c_ubyte * 8)]


class PROPKEY(ctypes.Structure):
    _fields_ = [("fmtid", GUID), ("pid", wintypes.DWORD)]


class PROPVARIANT(ctypes.Structure):
    _fields_ = [("vt", ctypes.c_ushort), ("r1", ctypes.c_ushort), ("r2", ctypes.c_ushort), ("r3", ctypes.c_ushort),
                ("p", ctypes.c_void_p), ("p2", ctypes.c_void_p)]


IID_IPropertyStore = GUID(0x886D8EEB, 0x8CF2, 0x4446, (ctypes.c_ubyte * 8)(0x8D, 0x02, 0xCD, 0xBA, 0x1D, 0xBD, 0xCF, 0x99))
PKEY_AppUserModel_ID = PROPKEY(GUID(0x9F4C2855, 0x9F79, 0x4B39, (ctypes.c_ubyte * 8)(0xA8, 0xD0, 0xE1, 0xD4, 0x2D, 0xE1, 0xD5, 0xF3)), 5)
ctypes.windll.shell32.SHGetPropertyStoreForWindow.argtypes = (wintypes.HWND, ctypes.POINTER(GUID), ctypes.POINTER(ctypes.c_void_p))
GET_VALUE = ctypes.WINFUNCTYPE(ctypes.HRESULT, ctypes.c_void_p, ctypes.POINTER(PROPKEY), ctypes.POINTER(PROPVARIANT))
RELEASE = ctypes.WINFUNCTYPE(ctypes.c_ulong, ctypes.c_void_p)


def app_id(hwnd):
    """창에 붙은 AppUserModelID — 크롬 PWA(YouTube 앱 등)는 앱마다 다르고 제목이 바뀌어도 그대로. 없으면 None."""
    ps = ctypes.c_void_p()
    if ctypes.windll.shell32.SHGetPropertyStoreForWindow(hwnd, ctypes.byref(IID_IPropertyStore), ctypes.byref(ps)) or not ps:
        return None
    vtbl = ctypes.cast(ctypes.cast(ps, ctypes.POINTER(ctypes.c_void_p))[0], ctypes.POINTER(ctypes.c_void_p))
    pv = PROPVARIANT()
    try:
        GET_VALUE(vtbl[5])(ps, ctypes.byref(PKEY_AppUserModel_ID), ctypes.byref(pv))  # IPropertyStore::GetValue
        return ctypes.wstring_at(pv.p) if pv.vt == 31 and pv.p else None  # VT_LPWSTR
    finally:
        ctypes.windll.ole32.PropVariantClear(ctypes.byref(pv))
        RELEASE(vtbl[2])(ps)


def windows():
    """보이는 최상위 창, 앞에서 뒤 순서. 각 항목은 dict(hwnd, exe, cls, title, app, topmost)."""
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
                            "app": app_id(h), "topmost": bool(user32.GetWindowLongW(h, -20) & 0x8)})  # WS_EX_TOPMOST
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
    return all(rule.get(k) in (None, win.get(k)) for k in ("exe", "cls", "title", "app"))


def rule_for(win):
    """창 목록에서 넣은 창의 규칙. 앱 ID 가 있으면 제목 대신 그걸로 알아봄 — PWA 제목은 영상·알림 수마다 바뀜.
    일반 크롬 창도 프로필 ID 가 붙어 있어 그 프로필 창 전부가 맞지만, 탭마다 바뀌는 제목으로는 어차피 못 붙잡음."""
    if win.get("app"):
        return {"name": win["title"], "exe": win["exe"], "cls": win["cls"], "app": win["app"]}
    return {"exe": win["exe"], "cls": win["cls"], "title": win["title"]}


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
            return [{k: r[k] for k in ("name", "exe", "cls", "title", "app") if isinstance(r.get(k), str)} for r in rules]
    except (OSError, ValueError, KeyError, TypeError):
        pass
    return [dict(r) for r in DEFAULT_RULES]


def save_rules(rules):
    SETTINGS.parent.mkdir(parents=True, exist_ok=True)
    SETTINGS.write_text(json.dumps({"rules": rules}, ensure_ascii=False, indent=1), encoding="utf-8")


def dot(master, color, size):
    """size×size 투명 그림 가운데 동그라미. color 가 None 이면 빈 그림."""
    img = tk.PhotoImage(master=master, width=size, height=size)
    if color:
        r, c = size * 0.3, (size - 1) / 2
        for y in range(size):
            half = (r * r - (y - c) ** 2) ** 0.5 if abs(y - c) <= r else -1
            if half >= 0.5:
                img.put(color, to=(round(c - half + 0.5), y, round(c + half + 0.5), y + 1))
    return img


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
        w.iconbitmap(str(ICON_FILE))
        w.protocol("WM_DELETE_WINDOW", self.close_window)
        px = lambda n: round(n * float(w.tk.call("tk", "scaling")) * 0.75)  # 96dpi 기준 px → 지금 화면 px
        font = tkfont.Font(w, family=UI_FONT, size=10)
        style = ttk.Style(w)
        style.configure(".", font=font, background="white")
        w.configure(bg="white")
        style.configure("Treeview", rowheight=round(font.metrics("linespace") * 1.8))
        style.configure("Treeview.Heading", font=(UI_FONT, 9), foreground=MUTED)
        style.configure("Title.TLabel", font=(UI_FONT, 12, "bold"))
        style.configure("Hint.TLabel", foreground=MUTED)
        style.configure("TButton", padding=(px(10), px(3)))
        self.dots = {k: dot(w, c, px(14)) for k, c in DOTS.items()}

        f = ttk.Frame(w, padding=px(16))
        f.pack(fill="both", expand=True)
        f.columnconfigure(0, weight=1)

        def section(row, title, hint, legend):
            ttk.Label(f, text=title, style="Title.TLabel").grid(row=row, column=0, columnspan=2, sticky="w")
            line = ttk.Frame(f)
            line.grid(row=row + 1, column=0, columnspan=2, sticky="w", pady=(px(2), px(8)))
            ttk.Label(line, text=hint, style="Hint.TLabel").pack(side="left")
            for key, text in legend:
                ttk.Label(line, text=text, image=self.dots[key], compound="left",
                          style="Hint.TLabel").pack(side="left", padx=(px(12), 0))

        def table(row, columns, height):
            box = ttk.Frame(f)
            box.grid(row=row, column=0, sticky="nsew")
            f.rowconfigure(row, weight=1)
            tree = ttk.Treeview(box, columns=[c for c, _, _ in columns], height=height, selectmode="browse")
            bar = ttk.Scrollbar(box, orient="vertical", command=tree.yview)
            def scrolled(lo, hi):  # 다 보이면 스크롤바를 숨김
                bar.set(lo, hi)
                if float(lo) <= 0 and float(hi) >= 1:
                    bar.pack_forget()
                elif not bar.winfo_ismapped():
                    bar.pack(side="left", fill="y")
            tree.configure(yscrollcommand=scrolled)
            tree.pack(side="left", fill="both", expand=True)
            tree.column("#0", width=px(54), minwidth=px(54), stretch=False)
            for c, text, width in columns:
                tree.heading(c, text=text, anchor="w")
                tree.column(c, width=px(width), minwidth=px(60), stretch=c != "exe")
            return tree

        def buttons(row, specs):
            col = ttk.Frame(f)
            col.grid(row=row, column=1, sticky="n", padx=(px(10), 0))
            out = []
            for text, cmd in specs:
                b = ttk.Button(col, text=text, command=cmd)
                b.pack(fill="x", pady=(0, px(6)))
                out.append(b)
            return out

        section(0, "앞에 띄울 순서", "위에 있을수록 앞에 뜸", (("on", "지금 떠 있음"), ("off", "안 떠 있음")))
        self.order_box = table(2, (("name", "창", 260), ("exe", "프로그램", 140)), 6)
        self.order_box.heading("#0", text="순위", anchor="w")
        self.order_buttons = buttons(2, (("▲  위로", lambda: self.move(-1)), ("▼  아래로", lambda: self.move(1)),
                                         ("빼기", self.remove)))
        ttk.Separator(f).grid(row=3, column=0, columnspan=2, sticky="ew", pady=px(16))
        section(4, "지금 열린 창", "두 번 누르면 순서 맨 아래에 넣음", (("pin", "원래 맨 위"),))
        self.open_box = table(6, (("name", "창 제목", 260), ("exe", "프로그램", 140)), 8)
        self.add_button, _ = buttons(6, (("＋  추가", self.add), ("새로 고침", self.refresh)))

        self.order_box.bind("<<TreeviewSelect>>", lambda e: self.sync_buttons())
        self.open_box.bind("<<TreeviewSelect>>", lambda e: self.sync_buttons())
        self.order_box.bind("<Delete>", lambda e: self.remove())
        self.order_box.bind("<Alt-Up>", lambda e: self.move(-1))
        self.order_box.bind("<Alt-Down>", lambda e: self.move(1))
        self.open_box.bind("<Double-Button-1>", lambda e: self.add())
        self.open_box.bind("<Return>", lambda e: self.add())
        self.refresh()
        w.update_idletasks()
        w.minsize(w.winfo_width(), w.winfo_height() * 2 // 3)

    def close_window(self):
        self.win.destroy()
        self.win = None

    def refresh(self, select=None):
        wins = windows()
        self.candidates = [w for w in wins if not any(matches(r, w) for r in self.rules)]
        self.order_box.delete(*self.order_box.get_children())
        for i, r in enumerate(self.rules):
            here = any(matches(r, w) for w in wins)
            self.order_box.insert("", "end", iid=str(i), text=" %d" % (i + 1), image=self.dots["on" if here else "off"],
                                  values=(rule_name(r), r.get("exe") or "놀이방"))
        if select is not None:
            self.order_box.selection_set(str(select))
            self.order_box.see(str(select))
        self.open_box.delete(*self.open_box.get_children())
        for i, w in enumerate(self.candidates):
            self.open_box.insert("", "end", iid=str(i), image=self.dots["pin" if w["topmost"] else "none"],
                                 values=(w["title"], w["exe"]))
        self.sync_buttons()

    def sync_buttons(self):
        i = self.selected(self.order_box)
        up, down, rm = self.order_buttons
        up.state(["!disabled"] if i is not None and i > 0 else ["disabled"])
        down.state(["!disabled"] if i is not None and i < len(self.rules) - 1 else ["disabled"])
        rm.state(["!disabled"] if i is not None else ["disabled"])
        self.add_button.state(["!disabled"] if self.selected(self.open_box) is not None else ["disabled"])

    @staticmethod
    def selected(tree):
        sel = tree.selection()
        return int(sel[0]) if sel else None

    def changed(self, select=None):
        save_rules(self.rules)
        self.refresh(select)

    def move(self, d):
        i = self.selected(self.order_box)
        if i is None or not 0 <= i + d < len(self.rules):
            return
        self.rules[i], self.rules[i + d] = self.rules[i + d], self.rules[i]
        self.changed(i + d)

    def remove(self):
        i = self.selected(self.order_box)
        if i is not None:
            del self.rules[i]
            self.changed()

    def add(self):
        i = self.selected(self.open_box)
        if i is not None:
            w = self.candidates[i]
            self.rules.append(rule_for(w))
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
    pwa = {"exe": "chrome.exe", "cls": "Chrome_WidgetWin_1", "title": "YouTube - (161) YouTube", "app": "Chrome._crx_x"}
    rule = rule_for(pwa)
    assert matches(rule, dict(pwa, title="YouTube - 고양이 - YouTube")), "PWA 는 제목이 바뀌어도 맞음"
    assert not matches(rule, dict(pwa, app="Chrome.UserData")), "같은 크롬이라도 다른 앱이면 안 맞음"
    assert not matches(rule, dict(w, app=None)) and matches(rule_for(dict(w, app=None)), dict(w, app=None))
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
