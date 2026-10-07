# SPDX-License-Identifier: Apache-2.0
"""작업 표시줄 오른쪽, 알림 영역 바로 왼쪽에 CPU·메모리 사용률을 두 줄로 띄운다. 메뉴에서 켜면 그 왼쪽에
디스크 활성 %·네트워크 받기/보내기 속도 두 줄을 더 띄운다(윈도우만).

  pythonw sysmon.py            띄우기 (창 없이 뒤에서 돎)
  python sysmon.py --toggle    떠 있으면 치우고, 없으면 띄움 (sysmon.bat 이 이걸 부름)
  python sysmon.py --stop      치우기
  python sysmon.py --check     자체 점검

작업 표시줄 위에 얹은 맨 위·클릭 통과 알파 창(shared/surface.py)이다. 테마는 글자와 픽셀이다. 기본은 GDI 로
흰색 회색조 안티에일리어싱 글자를 그린 뒤 밝기를 알파로 바꿔 색을 입히고, 픽셀은 usage-hud 와 같은
글꼴(shared/pixelfont.py)로 상자 안에 아이콘·칸 막대·숫자를 그린다. 픽셀은 같은 파일의 팔레트 여섯 중 하나로 칠한다. 1초마다 다시 재고, 트레이 아이콘이
늘거나 줄면 따라 옮기며, 전체 화면 앱이 돌면 숨는다. 끝내기는 트레이의 막대 아이콘 메뉴에서 한다.

맥에서는 작업 표시줄이 없으므로 메뉴 막대에 제 칸(NSStatusItem)을 두고 글자 한 줄이나 픽셀 그림을 넣는다
(MacMonitor). 메뉴·설정은 같고, 재는 것은 host_statistics 로 한다. sysmon.command 가 --toggle 을 부른다.
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
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "shared"))
MAC = sys.platform == "darwin"
if MAC:  # 같은 이름의 맥판(overlay·tray·startup)이 앞에 잡히게
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "shared" / "mac"))
    import cocoa
else:
    from ctypes import wintypes
    import taskbar
    from surface import Surface
import overlay
import startup
from pixelfont import COLORS, ICONS, PALETTES, text_pixels, text_width, use_palette
from tray import Tray, write_ico

PID_FILE = Path(tempfile.gettempdir()) / "playroom-sysmon.pid"
ICON_FILE = Path(tempfile.gettempdir()) / "playroom-sysmon.ico"
TRAY_CLASS = "PlayroomSysmonTray"
SURFACE_CLASS = "PlayroomSysmonSurface"
SETTINGS = (Path.home() / "Library" / "Application Support" if MAC else
            Path(os.environ.get("LOCALAPPDATA", Path.home()))) / "playroom" / "sysmon.json"

GAP = 8            # 알림 영역과 띄울 px
WARN, HOT = 70, 90  # 이 % 를 넘으면 주황, 빨강
WHITE, ORANGE, RED = (255, 255, 255), (254, 174, 52), (228, 59, 68)
AUTOSTART, IO, EXIT = 50, 51, 99
RUN_NAME = "PlayroomSysmon"
# 메모리 줄 모양: id → (키, 메뉴 글). 글자 색은 어느 모양이든 사용률로 정함
MEM_MODES = {60: ("pct", "퍼센트 (MEM 22%)"), 61: ("gb", "용량 (MEM 14.2/63.9G)"), 62: ("both", "둘 다 (MEM 14.2/63.9G 22%)")}
MEM_KEYS = {key for key, _ in MEM_MODES.values()}
# 테마: 글자, 또는 픽셀 상자에 pixelfont 의 팔레트 하나. 예전 설정의 "pixel" 은 클래식 픽셀로 읽음
THEMES = {70: ("text", "기본 (글자)")}
THEMES.update({71 + i: (key, "픽셀 · " + name) for i, (key, (name, _)) in enumerate(PALETTES.items())})
THEME_KEYS = {key for key, _ in THEMES.values()}
SEGMENTS = 8       # 픽셀 테마 막대 칸 수
ROW_GAP = 5        # 칸(세로로 쌓은 줄 묶음) 사이 칸. 맥은 줄마다 한 칸이라 두 줄이 이만큼 띄워 나란히 섬
PIX = {}           # 픽셀 테마가 버퍼에 찍을 RGB. use_theme 이 채움
PCT_W = text_width("100%")
RATE_W = 4         # 속도 글자 수 ('999M'). 픽셀 글꼴은 글자 폭이 같아 이만큼 채우면 폭이 안 변함

ICON_COLORS = {"g": "#63c74d", "y": "#feae34"}
ICON = (".......",
        ".....g.",
        ".....g.",
        "...g.g.",
        "...g.g.",
        ".y.g.g.",
        ".y.g.g.")

if MAC:
    mach = ctypes.CDLL("/usr/lib/libSystem.dylib")
    mach.mach_host_self.restype = ctypes.c_uint
    HOST = mach.mach_host_self()
    U32, U64 = ctypes.c_uint32, ctypes.c_uint64

    class VMStats(ctypes.Structure):  # <mach/vm_statistics.h> 의 vm_statistics64
        _fields_ = ([(n, U32) for n in ("free", "active", "inactive", "wire")] +
                    [(n, U64) for n in ("zero_fill", "reactivations", "pageins", "pageouts", "faults",
                                        "cow_faults", "lookups", "hits", "purges")] +
                    [(n, U32) for n in ("purgeable", "speculative")] +
                    [(n, U64) for n in ("decompressions", "compressions", "swapins", "swapouts")] +
                    [(n, U32) for n in ("compressor", "throttled", "external", "internal")] +
                    [("total_uncompressed_pages_in_compressor", U64)])

    _page = ctypes.c_size_t()
    mach.host_page_size(HOST, ctypes.byref(_page))
    PAGE = _page.value
    _total, _n = U64(), ctypes.c_size_t(8)
    mach.sysctlbyname(b"hw.memsize", ctypes.byref(_total), ctypes.byref(_n), None, 0)
    TOTAL = _total.value

    def cpu_times():
        """(쉰 틱, 전체 틱). host_statistics(HOST_CPU_LOAD_INFO) 의 사용자·시스템·쉼·nice 틱을 코어마다 더한 것.
        32비트라 몇십 일에 한 번 넘쳐 돌아가는데, 그 1초만 0 이나 엉뚱한 값이 뜨고 다음 초부터 맞음"""
        t, n = (U32 * 4)(), U32(4)
        mach.host_statistics(HOST, 3, t, ctypes.byref(n))
        return t[2], sum(t)

    def mac_used(vm):
        """활동 모니터의 '사용한 메모리' 쪽수: 앱 메모리(익명 − 지울 수 있는 것) + 와이어드 + 압축.
        파일 캐시는 안 넣음 — 넣으면(top 의 used) 거의 늘 꽉 차 보임"""
        return vm.internal - vm.purgeable + vm.wire + vm.compressor

    def vm_stats():
        vm, n = VMStats(), U32(ctypes.sizeof(VMStats) // 4)
        mach.host_statistics64(HOST, 4, ctypes.byref(vm), ctypes.byref(n))  # HOST_VM_INFO64
        return vm

    def memory():
        """(사용률 %, 쓰는 GB, 전체 GB)."""
        used = mac_used(vm_stats()) * PAGE
        gb = 1024 ** 3
        return round(100 * used / TOTAL), used / gb, TOTAL / gb
else:
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

    def memory():
        """(사용률 %, 쓰는 GB, 전체 GB)."""
        m = MEMORYSTATUSEX(dwLength=ctypes.sizeof(MEMORYSTATUSEX))
        kernel32.GlobalMemoryStatusEx(ctypes.byref(m))
        gb = 1024 ** 3
        return m.dwMemoryLoad, (m.ullTotalPhys - m.ullAvailPhys) / gb, m.ullTotalPhys / gb

    pdh = ctypes.windll.pdh
    for _f in (pdh.PdhOpenQueryW, pdh.PdhAddEnglishCounterW, pdh.PdhCollectQueryData,
               pdh.PdhGetFormattedCounterArrayW, pdh.PdhCloseQuery):
        _f.restype = wintypes.DWORD
    pdh.PdhOpenQueryW.argtypes = (wintypes.LPCWSTR, ctypes.c_size_t, ctypes.POINTER(ctypes.c_void_p))
    pdh.PdhAddEnglishCounterW.argtypes = (ctypes.c_void_p, wintypes.LPCWSTR, ctypes.c_size_t,
                                          ctypes.POINTER(ctypes.c_void_p))
    pdh.PdhCollectQueryData.argtypes = pdh.PdhCloseQuery.argtypes = (ctypes.c_void_p,)
    pdh.PdhGetFormattedCounterArrayW.argtypes = (ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD),
                                                 ctypes.POINTER(wintypes.DWORD), ctypes.c_void_p)
    PDH_MORE_DATA = 0x800007D2
    PDH_FMT = 0x200 | 0x8000  # DOUBLE | NOCAP100 — 100 에서 자르지 않음. 디스크는 아래에서 직접 자름

    class PdhValue(ctypes.Structure):  # PDH_FMT_COUNTERVALUE. 공용체에서 double 만 씀
        _fields_ = [("status", wintypes.DWORD), ("value", ctypes.c_double)]

    class PdhItem(ctypes.Structure):  # PDH_FMT_COUNTERVALUE_ITEM_W
        _fields_ = [("name", ctypes.c_wchar_p), ("fmt", PdhValue)]

    def counter_items(counter):
        """와일드카드 카운터의 {인스턴스 이름: 값}. 값이 맞지 않은 인스턴스(상태가 VALID·NEW 가 아님)는 뺌"""
        size, count = wintypes.DWORD(0), wintypes.DWORD(0)
        if pdh.PdhGetFormattedCounterArrayW(counter, PDH_FMT, size, count, None) != PDH_MORE_DATA:
            return {}
        buf = (ctypes.c_byte * size.value)()
        if pdh.PdhGetFormattedCounterArrayW(counter, PDH_FMT, size, count, buf):
            return {}
        items = ctypes.cast(buf, ctypes.POINTER(PdhItem))
        return {items[i].name: items[i].fmt.value for i in range(count.value) if items[i].fmt.status in (0, 1)}

    class IoMeter:
        """디스크 활성 %와 네트워크 받기·보내기 B/s 를 성능 카운터(PDH)로 읽음. 켰을 때만 만들고 끄면 닫음.
        영어 이름으로 더하므로(PdhAddEnglishCounterW) 한국어 윈도우에서도 됨. 비율 값이라 두 번째 수집부터 나옴"""
        PATHS = ("\\PhysicalDisk(*)\\% Idle Time", "\\Network Interface(*)\\Bytes Received/sec",
                 "\\Network Interface(*)\\Bytes Sent/sec")

        def __init__(self):
            self.query, self.counters = ctypes.c_void_p(), []
            if pdh.PdhOpenQueryW(None, 0, self.query):
                self.query = None
                return
            for path in self.PATHS:
                c = ctypes.c_void_p()
                if pdh.PdhAddEnglishCounterW(self.query, path, 0, c):
                    self.close()
                    return
                self.counters.append(c)
            pdh.PdhCollectQueryData(self.query)

        def read(self):
            """(디스크 %, 받기 B/s, 보내기 B/s). 못 읽은 것은 None"""
            if not self.query or pdh.PdhCollectQueryData(self.query):
                return None, None, None
            idle, recv, sent = (counter_items(c) for c in self.counters)
            return (busiest_disk(idle),) + busiest_net(recv, sent)

        def close(self):
            if self.query:
                pdh.PdhCloseQuery(self.query)
                self.query = None


def cpu_percent(prev, cur):
    total = cur[1] - prev[1]
    if total <= 0:
        return 0
    return max(0, min(100, round(100 * (1 - (cur[0] - prev[0]) / total))))


def busiest_disk(idle):
    """{디스크: 쉰 %} 에서 가장 바쁜 디스크의 활성 % (작업 관리자의 '활성 시간'). _Total 은 평균이라 뺌"""
    vals = [v for k, v in idle.items() if k != "_Total"]
    return round(max(0, min(100, 100 - min(vals)))) if vals else None


def busiest_net(recv, sent):
    """가장 바쁜 어댑터 하나의 (받기, 보내기) B/s. 다 더하지 않는 것은 Hyper-V 가상 스위치(vEthernet)가
    실제 어댑터와 같은 트래픽을 한 번 더 세기 때문"""
    names = recv.keys() & sent.keys()
    if not names:
        return None, None
    n = max(names, key=lambda k: recv[k] + sent[k])
    return recv[n], sent[n]


def rate_text(bps):
    """B/s → 4글자 안: '0K' · '8.5K' · '512K' · '1.2M' · '999M' · '2.4G'. 1024 단위"""
    if bps is None:
        return "--"
    v = bps / 1024
    for unit in "KMG":
        if v < 999.5 or unit == "G":
            if v < 0.05:
                return "0" + unit
            return ("%.1f" % v if v < 9.95 else "%d" % round(v)) + unit
        v /= 1024


def net_text(down, up):
    return "↓%s ↑%s" % (rate_text(down), rate_text(up))


def mem_text(mode, mem, used, total, pct=lambda p: "%d%%" % p):
    if mode == "gb":
        return "MEM %.1f/%.1fG" % (used, total)
    if mode == "both":
        return "MEM %.1f/%.1fG %s" % (used, total, pct(mem))
    return "MEM " + pct(mem)


def padded_pct(p):
    """'100%' 너비에 맞춘 퍼센트. 자릿수 너비 빈칸(U+2007)으로 채워 메뉴 막대 옆 아이콘이 안 밀림"""
    return " " * (3 - len(str(p))) + "%d%%" % p


def menubar_lines(cpu, mode, mem, used, total):
    """맥 글자 테마의 [(글, 색), …]. 한 줄로 이어 붙여 메뉴 막대에 씀"""
    return [("CPU " + padded_pct(cpu), level_color(cpu)),
            (mem_text(mode, mem, used, total, padded_pct), level_color(mem))]


def load_settings():
    """(메모리 모양, 테마, 디스크·네트워크를 보이는가). 파일이 없거나 이상하면 기본값. 맥은 디스크·네트워크가 없음"""
    try:
        data = json.loads(SETTINGS.read_text(encoding="utf-8"))
        mode, theme, io = data.get("mem"), data.get("theme"), data.get("io")
    except (OSError, ValueError, AttributeError):
        mode = theme = io = None
    theme = "classic" if theme == "pixel" else theme
    return mode if mode in MEM_KEYS else "pct", theme if theme in THEME_KEYS else "text", io is True and not MAC


def use_theme(theme):
    """픽셀 팔레트를 COLORS 에 깔고 PIX 를 다시 만듦. 글자 테마는 이 색들을 안 씀"""
    use_palette(theme)
    PIX.update({k: tuple(int(v[i:i + 2], 16) for i in (1, 3, 5)) for k, v in COLORS.items()})
    if MAC:  # 22pt 메뉴 막대에선 보조 글(dim)과 꺼진 칸(slot)이 바탕에 묻혀 글자색 쪽으로 당김. 윈도우는 상자가 커서 그대로
        mix = lambda a, b, t: tuple(round(x + (y - x) * t) for x, y in zip(a, b))
        PIX["dim"], PIX["slot"] = mix(PIX["dim"], PIX["text"], 0.5), mix(PIX["slot"], PIX["text"], 0.25)


def level_color(p):
    return RED if p > HOT else ORANGE if p > WARN else WHITE


# ── 픽셀 테마 (단위: 픽셀 칸) ──
def pixel_level(p):
    return "low" if p > HOT else "mid" if p > WARN else "good"


def pct_item(p):
    return ("%d%%" % p, pixel_level(p), PCT_W) if p is not None else ("--", "dim", PCT_W)


def pixel_rows(cpu, mode, mem, used, total):
    """[(아이콘, 이름, % 또는 None, [(글, 색 키, 오른쪽 맞출 너비 또는 None), …]), …].
    % 가 None 이면 막대가 없는 줄. 퍼센트는 '100%' 너비에 오른쪽 맞춤."""
    gb = "%.1f/%.1fG" % (used, total)
    tail = {"pct": [pct_item(mem)], "gb": [(gb, pixel_level(mem), None)], "both": [pct_item(mem), (gb, "dim", None)]}
    return [("cpu", "CPU", cpu, [pct_item(cpu)]), ("mem", "MEM", mem, tail[mode])]


def io_rows(disk, down, up):
    """디스크·네트워크 두 줄. 네트워크는 막대 없이 화살표와 속도 둘, 속도는 RATE_W 글자로 채워 폭이 안 변함"""
    rate = lambda c, b: (c + rate_text(b).rjust(RATE_W), "text" if b is not None else "dim", None)
    return [("disk", "DSK", disk or 0, [pct_item(disk)]), ("net", "NET", None, [rate("↓", down), rate("↑", up)])]


def row_width(row):
    """한 줄의 너비: 아이콘 7 + 2, 이름 + 2, 막대 + 1 (있으면), 뒤 글들은 3 씩 띄움."""
    tail = sum(fixed or text_width(t) for t, _, fixed in row[3]) + 3 * (len(row[3]) - 1)
    return 7 + 2 + text_width(row[1]) + 2 + (SEGMENTS * 3 + 1 if row[2] is not None else 0) + tail


def columns(rows, stack):
    """줄들을 앞에서부터 stack 개씩 묶은 칸들. 칸은 왼쪽에서 오른쪽 순서"""
    return [rows[i:i + stack] for i in range(0, len(rows), stack)]


def row_origins(rows, stack=2):
    """줄마다 상자 안 왼쪽 위 칸. 칸 안에서는 위아래로 8 간격, 칸끼리는 넓은 줄 폭 + ROW_GAP 띄워 나란히.
    윈도우는 두 줄씩 쌓고(stack 2), 맥 메뉴 막대는 한 줄에 다 늘어놓음(stack 1)."""
    out, x = [], 2
    for col in columns(rows, stack):
        out += [(x, 2 + i * 8) for i in range(len(col))]
        x += max(row_width(r) for r in col) + ROW_GAP
    return out


def pixel_size(rows, stack=2):
    """상자 (너비, 높이). 테두리 1 + 여백 1. 줄 간격 8 (아이콘 7 + 1)이라 두 줄이면 높이 19, 한 줄이면 11."""
    cols = columns(rows, stack)
    return 2 + sum(max(row_width(r) for r in c) for c in cols) + ROW_GAP * (len(cols) - 1) + 2, 3 + 8 * stack


def pixel_scale(bar_h):
    return max(1, (bar_h - 4) // 19)


def mac_pixel_scale(backing):
    """맥 메뉴 막대(22pt)에서 칸 하나의 화면 픽셀 수. 위아래로 쌓은 19칸은 칸당 1pt 라 글자가 5pt 로 너무 작아,
    나란히 둔 11칸을 칸당 2pt 로 막대에 꽉 차게 그림. 1.5pt(글자 7.5pt)도 시스템 글자보다 작아 안 읽혔음"""
    return backing * 2


def paint_pixel(surface, rows, s, stack=2):
    """오른쪽 끝에 붙여 세로 가운데에 그리고, 보이는 너비 px 를 돌려줌."""
    w, h = pixel_size(rows, stack)
    x0, y0 = surface.w - w * s, (surface.h - h * s) // 2
    px, stride = surface.pixels, surface.w * 4
    surface.clear()

    def rect(x, y, cw, ch, key, a=255):
        r, g, b = PIX[key]
        color = bytes((b * a // 255, g * a // 255, r * a // 255, a)) * (cw * s)
        for yy in range(y0 + y * s, y0 + (y + ch) * s):
            o = yy * stride + (x0 + x * s) * 4
            px[o:o + len(color)] = color

    rect(0, 0, w, h, "bg", 235)
    for x, y, cw, ch in ((0, 0, w, 1), (0, h - 1, w, 1), (0, 0, 1, h), (w - 1, 0, 1, h)):
        rect(x, y, cw, ch, "edge")
    for (icon, label, p, texts), (ox, y) in zip(rows, row_origins(rows, stack)):
        for dy, line in enumerate(ICONS[icon]):
            for dx, c in enumerate(line):
                if c != ".":
                    rect(ox + dx, y + dy, 1, 1, c)
        for dx, dy in text_pixels(label):
            rect(ox + 9 + dx, y + 1 + dy, 1, 1, "text")
        x = ox + 9 + text_width(label) + 2
        if p is not None:
            filled = round(p / 100 * SEGMENTS)
            for k in range(SEGMENTS):
                rect(x + k * 3, y + 1, 2, 5, pixel_level(p) if k < filled else "slot")
            x += SEGMENTS * 3 + 1
        for t, key, fixed in texts:
            tx = x + (fixed - text_width(t) if fixed else 0)
            for dx, dy in text_pixels(t):
                rect(tx + dx, y + 1 + dy, 1, 1, key)
            x += (fixed or text_width(t)) + 3
    return w * s


class Buffer:
    """paint_pixel 이 쓰는 만큼만 있는 Surface: 크기와 BGRA(알파를 곱한) 픽셀"""

    def __init__(self, w, h):
        self.w, self.h, self.pixels = w, h, bytearray(w * h * 4)

    def clear(self):
        self.pixels[:] = bytes(len(self.pixels))


class Monitor:
    def __init__(self):
        spot = taskbar.spot()
        x, top, h = spot or (overlay.work_area()[2], overlay.work_area()[3], 48)
        self.font = taskbar.font(h)
        # 버퍼는 가장 넓은 테마·모양에 맞춰 한 번 잡고 그림은 오른쪽에 붙임. 창은 그린 폭만큼만 보여서
        # (Surface.view) 왼쪽에 붙는 usage-hud 가 빈 칸 없이 바로 옆에 옴
        # 디스크·네트워크 칸까지 켠 폭으로 잡음. 그 칸은 가장 긴 글의 폭으로 고정해 속도가 바뀌어도 안 흔들림
        total, big = memory()[2], 999 * 1024 ** 2
        self.pad, self.col_gap = round(h * 0.1), round(h * 0.25)
        self.io_w = taskbar.text_width(self.font, ["DSK 100%", net_text(big, big)])
        widest = taskbar.text_width(self.font, ["CPU 100%"] + [mem_text(k, 100, total, total) for k in MEM_KEYS])
        self.s = pixel_scale(h)
        widest_pixel = max(pixel_size(io_rows(100, big, big) + pixel_rows(100, k, 100, total, total))[0]
                           for k in MEM_KEYS) * self.s
        self.w, self.h = max(self.io_w + self.col_gap + widest + self.pad + 2, widest_pixel), h
        self.line = round(h * 0.44)
        self.mode, self.theme, self.io_on = load_settings()
        self.io = IoMeter() if self.io_on else None
        use_theme(self.theme)
        self.surface = Surface(x - GAP - self.w, top, self.w, self.h, SURFACE_CLASS)
        self.on_top = MAC or overlay.on_top("sysmon")  # 런처의 '항상 위'. 맥은 런처가 없음
        if not self.on_top:
            self.surface.topmost(False)
        taskbar.prepare(self.surface, self.font)
        self.vis_w, self.vis_h = self.w, self.h
        self.commands = queue.Queue()
        write_ico(ICON_FILE, ICON, ICON_COLORS)
        self.tray = Tray(TRAY_CLASS, ICON_FILE, "CPU·메모리", self.menu, self.commands.put)
        self.shown, self.last_lines, self.where = None, None, None
        self.prev = cpu_times()

    def menu(self):
        items = [("메모리 표시", [(label, cid, key == self.mode) for cid, (key, label) in MEM_MODES.items()]),
                 ("테마", [(label, cid, key == self.theme) for cid, (key, label) in THEMES.items()])]
        if not MAC:
            items.append(("디스크·네트워크 보기", IO, self.io_on))
        return items + [("로그인 시 실행" if MAC else "Windows 시작 시 실행", AUTOSTART, startup.is_on(RUN_NAME, __file__)),
                        None,
                        ("끝내기", EXIT, False)]

    def update(self):
        cur = cpu_times()
        cpu, self.prev = cpu_percent(self.prev, cur), cur
        mem, used, total = memory()
        io = self.io.read() if self.io else None
        tip = "CPU %d%%\n메모리 %.1f / %.1f GB (%d%%)" % (cpu, used, total, mem)
        if io:
            tip += "\n디스크 %s · 받기 %s/s · 보내기 %s/s" % ("--" if io[0] is None else "%d%%" % io[0],
                                                        rate_text(io[1]), rate_text(io[2]))
        self.tray.set_tip(tip)
        show = not taskbar.fullscreen_app()
        if show != self.shown:
            self.shown = show
            self.surface.show(show)
        if not show:
            return
        if self.theme != "text":
            lines = (io_rows(*io) if io else []) + pixel_rows(cpu, self.mode, mem, used, total)
        else:
            lines = [([("CPU %d%%" % cpu, level_color(cpu)), (mem_text(self.mode, mem, used, total), level_color(mem))], 0)]
            if io:
                disk = ("DSK --", WHITE) if io[0] is None else ("DSK %d%%" % io[0], level_color(io[0]))
                lines.insert(0, ([disk, (net_text(io[1], io[2]), WHITE)], self.io_w))
        if lines != self.last_lines:
            self.last_lines = lines
            if self.theme != "text":
                self.vis_w = paint_pixel(self.surface, lines, self.s)
                self.vis_h = pixel_size(lines)[1] * self.s
            else:
                self.vis_w = taskbar.paint_columns(self.surface, self.font, lines, self.line, self.col_gap) + self.pad
                self.vis_h = self.h
        spot = taskbar.spot()
        if spot and (spot[:2], self.vis_w, self.vis_h) != self.where:  # 트레이 아이콘이 늘거나 줄거나 폭이 바뀌면 따라감
            self.where = spot[:2], self.vis_w, self.vis_h
            # 창을 상자 높이에 꼭 맞춤 — weather 가 창 윗변을 상자 윗변으로 보고 그 위에 눈을 얹음
            sy = (self.h - self.vis_h) // 2
            self.surface.view(spot[0] - GAP - self.vis_w, spot[1] + sy, self.w - self.vis_w, self.vis_w, sy, self.vis_h)
        self.surface.present()
        if self.on_top:
            self.surface.topmost()  # 작업 표시줄을 누르면 그쪽이 앞으로 오므로 1초마다 다시 올라옴

    def run(self):
        next_update = 0.0
        while True:
            self.surface.pump()
            try:
                cid = self.commands.get_nowait()
                if cid == AUTOSTART:
                    startup.toggle(RUN_NAME, __file__)
                elif cid in MEM_MODES or cid in THEMES or cid == IO:
                    self.mode = MEM_MODES[cid][0] if cid in MEM_MODES else self.mode
                    self.theme = THEMES[cid][0] if cid in THEMES else self.theme
                    use_theme(self.theme)
                    if cid == IO:
                        self.io_on = not self.io_on
                        if self.io:
                            self.io.close()
                        self.io = IoMeter() if self.io_on else None
                    next_update, self.last_lines = 0.0, None  # 바로 다시 그림
                    try:
                        SETTINGS.parent.mkdir(parents=True, exist_ok=True)
                        SETTINGS.write_text(json.dumps({"mem": self.mode, "theme": self.theme, "io": self.io_on}),
                                            encoding="utf-8")
                    except OSError:
                        pass  # 못 남기면 다음에 기본값으로 뜰 뿐
                elif cid in (None, EXIT):
                    if self.tray.item if MAC else self.tray.hwnd:
                        self.tray.close()  # 아이콘을 지우고 나면 None 이 다시 옴
                        continue
                    break
            except queue.Empty:
                pass
            now = time.monotonic()
            if now >= next_update:
                next_update = now + 1
                self.update()
            # 커서가 올라오면 흐려져 밑의 작업 표시줄 단추가 보임. 맥 메뉴 막대 단추는 안 가리므로 없음
            if not MAC and self.shown and self.surface.fade(self.surface.hovered()):
                self.surface.present()
            time.sleep(0.1)
        self.surface.close()


class MacMonitor(Monitor):
    """맥판. 따로 띄운 창 없이 메뉴 막대 아이콘(NSStatusItem) 자리에 글자나 픽셀 그림을 넣는다.
    메뉴·설정·명령 처리는 Monitor 것을 그대로 쓰고, 재는 것과 그리는 것만 다르다."""

    def __init__(self):
        self.mode, self.theme, self.io_on = load_settings()  # 맥은 io_on 이 늘 False
        self.io = None
        use_theme(self.theme)
        self.commands = queue.Queue()
        write_ico(ICON_FILE, ICON, ICON_COLORS)
        self.tray = Tray(TRAY_CLASS, ICON_FILE, "CPU·메모리", self.menu, self.commands.put)
        self.button = cocoa.send(self.tray.item, "button")
        self.surface = types.SimpleNamespace(pump=cocoa.pump, close=lambda: None)  # run() 이 부르는 둘
        self.backing = max(1, round(cocoa.send(cocoa.send(cocoa.cls("NSScreen"), "mainScreen"), "backingScaleFactor",
                                               restype=ctypes.c_double)))
        self.scale = mac_pixel_scale(self.backing)
        size = cocoa.send(cocoa.send(cocoa.cls("NSFont"), "menuBarFontOfSize:", 0.0, argtypes=(ctypes.c_double,)),
                          "pointSize", restype=ctypes.c_double)
        # 숫자 너비가 같은 글꼴이라 17% 가 18% 로 바뀌어도 폭이 안 변함
        self.font = cocoa.send(cocoa.send(cocoa.cls("NSFont"), "monospacedDigitSystemFontOfSize:weight:", size, 0.0,
                                          argtypes=(ctypes.c_double, ctypes.c_double)), "retain")
        self.last_lines = None
        self.prev = cpu_times()

    def run(self):
        cocoa.while_tracking(self.update, 1.0)  # 메뉴를 연 동안엔 run() 의 루프가 멈추므로 그동안 숫자를 갱신
        super().run()

    def update(self):
        cur = cpu_times()
        cpu, self.prev = cpu_percent(self.prev, cur), cur
        mem, used, total = memory()
        if self.theme != "text":
            lines = pixel_rows(cpu, self.mode, mem, used, total)
        else:
            lines = menubar_lines(cpu, self.mode, mem, used, total)
        # 글자 색은 넣는 순간의 외관으로 굳는다. 단추가 메뉴 막대에 들어가기 전(밝은 외관)이나 배경화면이 바뀌어
        # 막대가 밝고 어두움을 바꾸면 빨강이 어둡게 남으므로, 외관(이름은 상수 문자열이라 주소로 견줌)도 같이 봄
        key = lines, cocoa.send(cocoa.send(self.button, "effectiveAppearance"), "name")
        if key == self.last_lines:
            return
        self.last_lines = key
        p = cocoa.pool()
        self.tray.set_tip("CPU %d%%\n메모리 %.1f / %.1f GB (%d%%)" % (cpu, used, total, mem))
        if self.theme != "text":
            self.show_pixel(lines)
        else:
            self.show_text(lines)
        cocoa.drain(p)

    def show_text(self, lines):
        send, ns = cocoa.send, cocoa.nsstring
        color_of = {WHITE: "labelColor", ORANGE: "systemOrangeColor", RED: "systemRedColor"}  # 밝고 어두운 막대에 맞춰 바뀜
        text = "  ".join(t for t, _ in lines)
        s = send(send(cocoa.cls("NSMutableAttributedString"), "alloc"), "initWithString:", ns(text),
                 argtypes=(ctypes.c_void_p,))
        add = lambda key, value, start, n: send(s, "addAttribute:value:range:", key, value, NSRange(start, n),
                                                restype=None, argtypes=(ctypes.c_void_p, ctypes.c_void_p, NSRange))
        add(FONT_ATTR, self.font, 0, len(text))
        start = 0
        for t, color in lines:
            add(COLOR_ATTR, send(cocoa.cls("NSColor"), color_of[color]), start, len(t))
            start += len(t) + 2
        send(self.button, "setImage:", None, restype=None, argtypes=(ctypes.c_void_p,))
        send(self.button, "setAttributedTitle:", s, restype=None, argtypes=(ctypes.c_void_p,))
        send(s, "release", restype=None)

    def show_pixel(self, rows):
        send, s = cocoa.send, self.scale
        w, h = pixel_size(rows, 1)
        buf = Buffer(w * s, h * s)
        paint_pixel(buf, rows, s, 1)
        px = buf.pixels
        px[0::4], px[2::4] = px[2::4], px[0::4]  # BGRA → RGBA (알파를 곱한 그대로)
        rep = send(send(cocoa.cls("NSBitmapImageRep"), "alloc"),
                   "initWithBitmapDataPlanes:pixelsWide:pixelsHigh:bitsPerSample:samplesPerPixel:hasAlpha:isPlanar:"
                   "colorSpaceName:bytesPerRow:bitsPerPixel:", None, buf.w, buf.h, 8, 4, True, False,
                   cocoa.nsstring("NSDeviceRGBColorSpace"), buf.w * 4, 32,
                   argtypes=(ctypes.c_void_p, ctypes.c_long, ctypes.c_long, ctypes.c_long, ctypes.c_long,
                             ctypes.c_bool, ctypes.c_bool, ctypes.c_void_p, ctypes.c_long, ctypes.c_long))
        ctypes.memmove(send(rep, "bitmapData"), bytes(px), len(px))
        img = send(send(cocoa.cls("NSImage"), "alloc"), "initWithSize:", cocoa.Size(buf.w / self.backing, buf.h / self.backing), argtypes=(cocoa.Size,))
        send(img, "addRepresentation:", rep, restype=None, argtypes=(ctypes.c_void_p,))
        send(self.button, "setTitle:", cocoa.nsstring(""), restype=None, argtypes=(ctypes.c_void_p,))
        send(self.button, "setImage:", img, restype=None, argtypes=(ctypes.c_void_p,))
        send(rep, "release", restype=None)
        send(img, "release", restype=None)


if MAC:
    class NSRange(ctypes.Structure):
        _fields_ = [("location", ctypes.c_ulong), ("length", ctypes.c_ulong)]

    FONT_ATTR = ctypes.c_void_p.in_dll(cocoa.APPKIT, "NSFontAttributeName").value
    COLOR_ATTR = ctypes.c_void_p.in_dll(cocoa.APPKIT, "NSForegroundColorAttributeName").value


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
    if MAC:
        out = subprocess.run(["vm_stat"], capture_output=True, text=True).stdout  # 같은 값을 다른 길로 셈
        v = {k.strip('" '): int(n) for k, n in (ln.rstrip(".").rsplit(":", 1) for ln in out.splitlines()[1:])}
        vm = vm_stats()
        for field, name in (("internal", "Anonymous pages"), ("purgeable", "Pages purgeable"), ("wire", "Pages wired down"),
                            ("compressor", "Pages occupied by compressor")):  # 구조체 칸이 밀리면 여기서 걸림
            assert abs(getattr(vm, field) - v[name]) <= max(200, v[name] * 0.03), (field, getattr(vm, field), v[name])
        pages = v["Anonymous pages"] - v["Pages purgeable"] + v["Pages wired down"] + v["Pages occupied by compressor"]
        assert abs(mem - 100 * pages * PAGE / TOTAL) < 3, ("vm_stat 과 맞아야 함", mem, 100 * pages * PAGE / TOTAL)
        vm.internal, vm.purgeable, vm.wire, vm.compressor, vm.external = 100, 10, 20, 30, 1000
        assert mac_used(vm) == 140, "앱(익명 − 지울 수 있는 것) + 와이어드 + 압축, 파일 캐시는 뺌"
        a, b = menubar_lines(5, "both", 5, 1.0, 16.0), menubar_lines(100, "both", 100, 1.0, 16.0)
        assert [len(t) for t, _ in a] == [len(t) for t, _ in b], "5% 와 100% 의 글 길이가 같아 폭이 안 변함"
        assert a[0][0] == "CPU   5%" and b[1] == ("MEM 1.0/16.0G 100%", RED)
        bar = cocoa.send(cocoa.send(cocoa.cls("NSStatusBar"), "systemStatusBar"), "thickness", restype=ctypes.c_double)
        for backing in (1, 2, 3):  # 칸 하나가 메뉴 막대에서 차지하는 pt 로 상자 높이를 셈
            pt = pixel_size(pixel_rows(1, "pct", 1, 1.0, 16.0), 1)[1] * mac_pixel_scale(backing) / backing
            assert 20 <= pt <= bar, ("픽셀 상자가 메뉴 막대 높이 안에, 너무 작지 않게", backing, pt, bar)
        for theme in PALETTES:  # 흐린 두 색이 팔레트 값보다 바탕에서 멀어짐 (글자색만큼은 아님)
            use_theme(theme)
            far = lambda c: sum(abs(a - b) for a, b in zip(c, PIX["bg"]))
            for key in ("dim", "slot"):
                raw = tuple(int(COLORS[key][i:i + 2], 16) for i in (1, 3, 5))
                assert far(raw) < far(PIX[key]) < far(PIX["text"]), (theme, key)
        rows = pixel_rows(100, "pct", 100, 16.0, 16.0)
        assert pixel_size(rows, 1)[0] == pixel_size(rows)[0] + row_width(rows[1]) + ROW_GAP, "나란히 둔 폭"
    else:
        font = taskbar.font(48)
        assert taskbar.text_width(font, ["MEM 14.2/63.9G"]) > taskbar.text_width(font, ["MEM 22%"]) > 0, "긴 글이 더 넓음"
        # 글자 테마 두 칸: 진짜 창 버퍼에 그려 칸마다 제 색을 받고 왼쪽 칸이 고정 폭만큼 자리를 잡는지 봄
        surf = Surface(-1000, -1000, 400, 48, "PlayroomSysmonCheck")
        taskbar.prepare(surf, font)
        io_w = taskbar.text_width(font, ["DSK 100%", net_text(999 * 1024 ** 2, 999 * 1024 ** 2)])
        cols = [([("DSK 95%", RED), (net_text(1024, 1024), WHITE)], io_w), ([("CPU 5%", ORANGE), ("MEM 1%", ORANGE)], 0)]
        drawn = taskbar.paint_columns(surf, font, cols, 21, 12)
        main_w = taskbar.text_width(font, ["CPU 5%", "MEM 1%"])
        assert drawn == 2 + main_w + 12 + io_w, ("그린 폭", drawn, main_w, io_w)
        tint, px = {}, surf.pixels
        for o in range(0, len(px), 4):
            if px[o + 3] > 128:  # 알파를 곱한 값이라 G/R 비는 덮인 정도와 상관없음: 빨강 0.26 · 주황 0.69 · 흰 1
                g_r = px[o + 1] / max(1, px[o + 2])
                side = "io" if o // 4 % surf.w < surf.w - 2 - main_w - 6 else "main"
                tint.setdefault(side, set()).add("red" if g_r < 0.45 else "orange" if g_r < 0.85 else "white")
        x, y = surf.cursor()  # 창 왼쪽 위를 커서 자리로 옮기면 올라온 것, 1px 더 가면 아님
        surf.move(-1000 + x, -1000 + y)
        assert surf.hovered(), "커서가 창 왼쪽 위 칸에 있음"
        surf.move(-1000 + x + 1, -1000 + y)
        assert not surf.hovered(), "커서가 창 왼쪽 밖"
        assert surf.fade(True) and not surf.fade(True) and surf.fade(False), "흐려짐은 바뀔 때만 True"
        surf.close()
        assert tint["io"] == {"red", "white"} and tint["main"] == {"orange"}, ("칸마다 제 줄 색", tint)
        assert ctypes.sizeof(PdhItem) == 24, "PDH_FMT_COUNTERVALUE_ITEM_W 는 이름 포인터 + 8 맞춤 값 16"
        meter = IoMeter()
        assert meter.query, "성능 카운터를 못 엶"
        time.sleep(1.1)  # 비율 값이라 두 번째 수집이 1초쯤 뒤여야 맞음
        disk, down, up = meter.read()
        meter.close()
        assert disk is not None and 0 <= disk <= 100, ("디스크 활성 %", disk)
        assert down is not None and down >= 0 and up >= 0, ("네트워크 B/s", down, up)
    assert [rate_text(b) for b in (None, 0, 40, 8.5 * 1024, 512 * 1024, 999.4 * 1024, 999.6 * 1024, 1.2 * 1024 ** 2,
                                    999 * 1024 ** 2, 2.4 * 1024 ** 3)] == \
        ["--", "0K", "0K", "8.5K", "512K", "999K", "1.0M", "1.2M", "999M", "2.4G"]
    assert busiest_disk({"_Total": 10.0, "0 C:": 70.0, "1 D:": 20.0}) == 80, "가장 덜 쉰 디스크, _Total 은 뺌"
    assert busiest_disk({"0 C:": 101.5}) == 0 and busiest_disk({"_Total": 3.0}) is None
    assert busiest_net({"wifi": 100.0, "vEthernet": 90.0, "eth": 5.0}, {"wifi": 10.0, "vEthernet": 9.0, "eth": 1.0}) == \
        (100.0, 10.0), "가장 바쁜 어댑터 하나만 — 가상 스위치 몫을 더하지 않음"
    assert busiest_net({"a": 1.0}, {}) == (None, None)
    big = 999 * 1024 ** 2
    assert row_width(io_rows(5, 0, 300)[1]) == row_width(io_rows(100, big, big)[1]) == row_width(io_rows(None, None, None)[1]), \
        "네트워크 줄은 속도가 바뀌어도 폭이 같음"
    assert net_text(1.5 * 1024 ** 2, 300) == "↓1.5M ↑0.3K" and io_rows(None, 1, 1)[0][3][0][:2] == ("--", "dim")
    real = globals()["SETTINGS"]
    try:  # 디스크·네트워크는 true 일 때만 켜지고 맥에서는 늘 꺼짐
        globals()["SETTINGS"] = Path(tempfile.mkdtemp()) / "s.json"
        for raw, io in (('{"io": true}', not MAC), ('{"io": 1}', False), ('{}', False), ("깨짐", False)):
            SETTINGS.write_text(raw, encoding="utf-8")
            assert load_settings()[2] == io, (raw, load_settings())
    finally:
        globals()["SETTINGS"] = real
    total = 63.9
    for k in MEM_KEYS:  # 픽셀 상자는 작업 표시줄 높이 안에, 가장 넓은 모양이 버퍼 안에
        rows = pixel_rows(100, k, 100, total, total)
        w, h = pixel_size(rows)
        assert all(h * pixel_scale(b) <= b - 4 for b in (40, 48, 72, 76))
        assert pixel_rows(5, k, 5, 1.0, total)[1][3][0][1] == "good" and pixel_level(HOT + 1) == "low"
    assert pixel_size(pixel_rows(1, "both", 1, 1.0, total))[0] > pixel_size(pixel_rows(1, "pct", 1, 1.0, total))[0]

    rows = pixel_rows(50, "both", 22, 14.2, total)
    f = Buffer(400, 48)
    assert len(THEME_KEYS) == len(PALETTES) + 1, "글자 + 팔레트마다 하나"
    for theme in PALETTES:  # 테마를 바꾸면 막대도 그 팔레트의 색으로 찍힘
        use_theme(theme)
        vis = paint_pixel(f, rows, 2)
        assert vis == pixel_size(rows)[0] * 2
        cols = {i // 4 % f.w for i in range(3, len(f.pixels), 4) if f.pixels[i]}
        assert min(cols) == f.w - vis and max(cols) == f.w - 1, "오른쪽 끝에 붙고 보이는 폭이 맞음"
        good = tuple(int(PALETTES[theme][1]["good"][i:i + 2], 16) for i in (5, 3, 1))  # BGR
        lit = sum(1 for k in range(SEGMENTS) for o in [((48 - 38) // 2 + 3 * 2) * f.w * 4 + (f.w - vis + (24 + k * 3) * 2) * 4]
                  if tuple(f.pixels[o:o + 3]) == good)
        assert lit == 4, ("CPU 50% 면 8칸 중 4칸", theme, lit)

    def at(f, rows, s, stack, x, y):  # 상자 안 칸 (x, y) 의 BGR
        w, h = pixel_size(rows, stack)
        o = ((f.h - h * s) // 2 + y * s) * f.w * 4 + (f.w - w * s + x * s) * 4
        return tuple(f.pixels[o:o + 3])
    base = pixel_rows(50, "pct", 25, 4.0, total)
    with_io = io_rows(25, 1.5 * 1024 ** 2, 0) + base
    # 줄마다 시작 칸을 손으로 적어 둠: 위아래면 8 간격, 나란히면 첫 줄 폭 + ROW_GAP 옆. 디스크·네트워크 칸은
    # 왼쪽이고 그 폭은 네트워크 줄(아이콘 9 + NET 13 + 화살표·속도 19 둘 + 3 = 63)이라 CPU·MEM 칸은 2 + 63 + 5
    for rows, stack, origins in ((base, 2, [(2, 2), (2, 10)]), (base, 1, [(2, 2), (2 + row_width(base[0]) + ROW_GAP, 2)]),
                                 (with_io, 2, [(2, 2), (2, 10), (70, 2), (70, 10)])):
        f = Buffer(400, 48)
        paint_pixel(f, rows, 2, stack)
        for (ox, oy), (_, label, p, texts) in zip(origins, rows):
            bar = ox + 9 + text_width(label) + 2
            if p is None:  # 막대 없는 줄은 그 자리에 첫 글이 옴
                dx, dy = list(text_pixels(texts[0][0]))[0]
                assert at(f, rows, 2, stack, bar + dx, oy + 1 + dy) == PIX[texts[0][1]][::-1], ("막대 없는 줄의 글 자리", label)
            else:
                lit = sum(at(f, rows, 2, stack, bar + 3 * k, oy + 1) == PIX["good"][::-1] for k in range(SEGMENTS))
                assert lit == round(p / 100 * SEGMENTS), ("줄마다 막대 자리", stack, label, lit)
            dx, dy = list(text_pixels(label))[0]
            assert at(f, rows, 2, stack, ox + 9 + dx, oy + 1 + dy) == PIX["text"][::-1], ("이름 자리", stack, label)
    w, h = pixel_size(with_io)
    assert h == 19 and w == 2 + 63 + ROW_GAP + max(map(row_width, base)) + 2, "두 칸 상자 폭"
    assert pixel_size(base, 1)[1] == 11, "한 줄로 늘어놓으면 높이 11"
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
    if MAC and overlay.running_pid(PID_FILE) is not None:  # 맥은 소스로만 돌아 갈아 끼울 exe 가 없음
        if args.toggle:
            overlay.stop(PID_FILE, TRAY_CLASS)
        return
    if not MAC and overlay.already_running(PID_FILE, TRAY_CLASS, __file__, args.toggle):
        return
    if args.toggle and Path(sys.executable).name.lower() == "python.exe":
        # sysmon.bat 에서 콘솔 창이 남지 않게 pythonw 로 다시 띄움
        pythonw = Path(sys.executable).with_name("pythonw.exe")
        if pythonw.exists():
            subprocess.Popen([str(pythonw), str(Path(__file__).resolve())], close_fds=True)
            return
    if args.toggle and MAC:
        # 터미널을 닫아도 안 꺼지게 떼어서 다시 띄움
        subprocess.Popen([sys.executable, str(Path(__file__).resolve())], start_new_session=True,
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return
    if not MAC:
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)  # 배율 높은 화면에서 흐려지지 않게
        except (AttributeError, OSError):
            pass
        startup.follow(RUN_NAME, __file__)
    overlay.claim(PID_FILE, __file__)
    try:
        (MacMonitor if MAC else Monitor)().run()
    finally:
        if overlay.running_pid(PID_FILE) == os.getpid():
            PID_FILE.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
