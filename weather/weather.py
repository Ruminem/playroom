# SPDX-License-Identifier: Apache-2.0
"""모든 창 위에 내리는 눈과 비. 보이기만 하고 클릭은 그대로 아래 창으로 간다.

  pythonw weather.py            띄우기 (창 없이 뒤에서 돎)
  python weather.py --toggle    떠 있으면 치우고, 없으면 띄움 (weather.bat 이 이걸 부름)
  python weather.py --stop      치우기
  python weather.py --kind rain --amount many
  python weather.py --check     자체 점검

작업 영역(작업 표시줄 뺀 주 모니터) 전체를 덮는 픽셀 알파 창(shared/surface.py)에 30fps 로 그린다.
눈은 원근 세 층으로 바람에 흔들리며 내리고 작업 표시줄 위에 쌓였다 천천히 녹는다. 비는 기운
빗줄기로 내리고 바닥에서 튄다. 트레이의 눈송이 메뉴에서 눈·비·양·숨기기·끝내기를 하고,
고른 것은 SETTINGS 에 남는다.
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
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "shared"))
import overlay
from surface import Surface
from tray import Tray, write_ico

PID_FILE = Path(tempfile.gettempdir()) / "playroom-weather.pid"
ICON_FILE = Path(tempfile.gettempdir()) / "playroom-weather.ico"
SETTINGS = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "playroom" / "weather.json"
TRAY_CLASS = "PlayroomWeatherTray"
SURFACE_CLASS = "PlayroomWeatherSurface"

FPS = 30           # 13fps 는 끊겨 보였음. 타이머 해상도를 1ms 로 올려야 실제로 30 이 나옴
SNOW_COLOR, SNOW_RIM = (248, 250, 255), (165, 176, 198)  # 테두리를 옅은 회청색으로 — 흰 창 위에서도 보이게
RAIN_COLOR = (200, 214, 236)

# 눈 층: (비율, 반지름들 px, 속도 px/초, 알파, 번짐 px, 흔들림 px, 바람을 받는 정도, 바닥에 쌓이나)
SNOW_LAYERS = ((0.45, (0.7, 0.9, 1.1), (16, 28), 150, 0.8, 4, 0.4, False),   # 멀리
               (0.42, (1.3, 1.6, 2.0), (32, 52), 225, 0.9, 10, 0.7, True),   # 가운데
               (0.13, (2.4, 3.0, 3.6), (58, 88), 235, 1.8, 18, 1.0, True))   # 가까이 — 크고 번짐
# 비 층: (비율, 길이 px, 속도 px/초, 알파, 굵기 px)
RAIN_LAYERS = ((0.6, (16, 26), (650, 820), 120, 1.0),
               (0.4, (30, 44), (900, 1150), 190, 1.6))
SLANT = 0.12       # 빗줄기 기울기 (가로 / 세로)
RAIN_MULT = 2      # 비는 빨리 지나가 같은 개수면 듬성듬성해 보여서 눈의 두 배

PILE_CAP = 28      # 쌓인 눈의 최대 높이 px
PILE_STRIP = PILE_CAP + 2
PILE_PER_FLAKE = 21.0  # 눈송이 하나가 보태는 부피 = 이 값 × 반지름. 실제보다 부풀려 몇 분 안에 쌓이게.
                       # 반지름²에 비례시키면 큰 눈송이 하나에 둔덕이 툭 솟음
SLOPE = 0.8        # 이웃 열과의 높이 차가 이보다 크면 흘러내림 (안식각)
DIFFUSE = 0.12     # 표면을 매끈하게 퍼뜨리는 정도
MELT_PER_SEC = 0.0045  # 높이에 비례해 녹는 비율. 넣는 양 ÷ 이 값에서 높이가 멈춤 ('보통' 이면 10px 쯤)
SETTLE_SEC = 0.25

SNOW, RAIN, SHOW, EXIT = 1, 2, 3, 99
AMOUNTS = {10: ("few", "적게", 60), 11: ("normal", "보통", 150), 12: ("many", "많이", 300)}
COUNT = {key: n for key, _, n in AMOUNTS.values()}

ICON_COLORS = {"b": "#0099db", "w": "#ffffff"}
ICON = ("...b...",
        ".b.b.b.",
        "..bbb..",
        "bbbwbbb",
        "..bbb..",
        ".b.b.b.",
        "...b...")


# ── 그림 조각 ── premultiplied BGRA. 행마다 (앞에서 건너뛸 바이트, 바이트) 로, 투명한 앞뒤는 잘라 둔다.
# 겹친 그림을 섞지 않고 덮어쓰므로, 잘라 두면 둥근 모서리가 밑의 것을 지우지 않는다
def pixel(color, a):
    a = max(0, min(255, int(a)))
    r, g, b = color
    return bytes((b * a // 255, g * a // 255, r * a // 255, a))


def trim(row):
    """한 행의 픽셀 바이트에서 투명한 앞뒤를 잘라 (건너뛸 바이트, 남은 바이트)."""
    px = [row[i:i + 4] for i in range(0, len(row), 4)]
    lead = 0
    while lead < len(px) and px[lead][3] == 0:
        lead += 1
    end = len(px)
    while end > lead and px[end - 1][3] == 0:
        end -= 1
    return lead * 4, b"".join(px[lead:end])


def disc(r, soft, alpha, core, rim, fx=0.0, fy=0.0):
    """부드러운 원판. fx, fy 는 픽셀 아래 단위의 중심 이동 — 느린 눈송이가 1px 씩 덜컥거리지 않게."""
    n = int(math.ceil(2 * (r + soft))) + 2
    c = n / 2 - 0.5
    rows = []
    for y in range(n):
        row = b""
        for x in range(n):
            d = math.hypot(x - c - fx, y - c - fy)
            cov = min(1.0, max(0.0, (r + soft / 2 - d) / soft))
            cov = cov * cov * (3 - 2 * cov)
            t = min(1.0, d / max(r, 0.5)) ** 2
            color = tuple(int(core[i] + (rim[i] - core[i]) * t) for i in range(3))
            row += pixel(color, alpha * cov)
        rows.append(trim(row))
    return n, rows


def streak(length, alpha, width):
    """SLANT 만큼 기운 빗줄기. 꼬리(위)는 투명하고 머리(아래)로 갈수록 진함."""
    sw = int(length * SLANT) + 4
    rows = []
    for j in range(length):
        a = alpha * ((j + 1) / length) ** 1.6
        xc = j * SLANT + 1.5
        row = b"".join(pixel(RAIN_COLOR, a * min(1.0, max(0.0, width / 2 + 0.5 - abs(x - xc))))
                       for x in range(sw))
        rows.append(trim(row))
    return sw, rows


def stamp(px, stride, x, y, rows):
    off = y * stride + x * 4
    for skip, data in rows:
        if data:
            px[off + skip:off + skip + len(data)] = data
        off += stride


# ── 쌓인 눈 ──
class Pile:
    """픽셀 열마다 높이(실수 px). 떨어진 자리에 둔덕을 보태고, settle() 이 흘러내림·퍼짐·녹음을 한다."""

    def __init__(self, width):
        self.h = [0.0] * width
        self.flip = False

    def add(self, x, r):
        h = self.h
        spread = int(r * 5) + 6  # 넓게 펴서 넣어야 떨어질 때마다 뾰족하게 안 솟음
        weights = [(i, spread + 1 - abs(i - x)) for i in range(x - spread, x + spread + 1)
                   if 0 <= i < len(h) and h[i] < PILE_CAP]
        total = sum(w for _, w in weights)
        vol = PILE_PER_FLAKE * r
        for i, w in weights:
            h[i] = min(PILE_CAP, h[i] + vol * w / total)

    def settle(self, melt):
        h, n = self.h, len(self.h)
        # 안식각: 넘친 높이 차의 반을 낮은 쪽으로. 한 방향으로만 훑으면 한쪽으로 쏠리므로 번갈아 훑음
        order = range(n - 1) if self.flip else range(n - 2, -1, -1)
        self.flip = not self.flip
        for i in order:
            d = h[i] - h[i + 1]
            if d > SLOPE:
                m = (d - SLOPE) / 2
                h[i] -= m
                h[i + 1] += m
            elif d < -SLOPE:
                m = (-d - SLOPE) / 2
                h[i] += m
                h[i + 1] -= m
        # 이웃끼리 조금씩 주고받아 표면을 매끈하게. 주고받기라 부피는 그대로.
        # 흐름은 옛 높이로 한꺼번에 셈 — 차례로 고치면 훑는 방향으로 조금씩 쏠림
        flow = [DIFFUSE * (b - a) for a, b in zip(h, h[1:])]
        for i, f in enumerate(flow):
            h[i] += f
            h[i + 1] -= f
        if melt:
            k = 1 - melt
            self.h = [v * k if v > 0.01 else 0.0 for v in h]


def pile_column_parts():
    """열 하나를 그릴 조각: 윗면 가장자리(높이의 소수부 16단계 알파)와 위에서 아래로 몸통."""
    top, deep = (240, 244, 252), (212, 221, 238)
    edges = [pixel(SNOW_RIM, 255 * q / 16) for q in range(16)]
    body = b"".join(pixel(tuple(int(a + (b - a) * min(1.0, d / 14)) for a, b in zip(top, deep)), 255)
                    for d in range(PILE_STRIP))
    return edges, body


def pile_column(v, edges, body, zero):
    n = min(int(v), PILE_STRIP - 1)
    q = int((v - int(v)) * 16)
    return zero[:(PILE_STRIP - n - 1) * 4] + edges[q] + body[:n * 4]


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
        # ponytail: 시작할 때의 주 모니터 작업 영역에 고정. 해상도·작업 표시줄이 바뀌면 다시 켜야 함
        l, t, r, b = overlay.work_area()
        self.w, self.h = r - l, b - t
        self.surface = Surface(l, t, self.w, self.h, SURFACE_CLASS)
        self.stride = self.w * 4
        self.snow_sprites = [[[disc(rad, layer[4], layer[3], SNOW_COLOR, SNOW_RIM, fx / 4, fy / 4)
                               for fy in range(4) for fx in range(4)] for rad in layer[1]]
                             for layer in SNOW_LAYERS]
        self.rain_sprites = [{n: streak(n, layer[3], layer[4]) for n in range(layer[1][0], layer[1][1] + 1)}
                             for layer in RAIN_LAYERS]
        self.droplet = disc(0.8, 0.8, 190, RAIN_COLOR, RAIN_COLOR)
        self.pile_edges, self.pile_body = pile_column_parts()
        self.pile_zero = bytes(PILE_STRIP * 4)
        self.commands = queue.Queue()  # 트레이 스레드 → 그리는 스레드
        write_ico(ICON_FILE, ICON, ICON_COLORS)
        self.tray = Tray(TRAY_CLASS, ICON_FILE, "날씨", self.menu, self.commands.put)
        self.last = self.last_settle = self.last_topmost = time.perf_counter()
        self.reset()
        self.surface.show(True)

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
            self.surface.show(self.visible)
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
        """트레이에서 온 명령을 처리. None 이면 트레이가 닫힌 것. 끝내야 하면 True."""
        try:
            while True:
                cid = self.commands.get_nowait()
                if cid is None:
                    return True
                self.handle(cid)
        except queue.Empty:
            return False

    # ── 눈 ──
    def new_flake(self, li, top):
        layer = SNOW_LAYERS[li]
        y = -random.uniform(10, 60) if top else random.uniform(0, self.h)
        # [x, y, 속도, 층, 반지름 번호, 흔들림 위상, 흔들림 빠르기]
        return [random.uniform(0, self.w), y, random.uniform(*layer[2]), li, random.randrange(len(layer[1])),
                random.uniform(0, 6.3), random.uniform(0.6, 1.4)]

    @staticmethod
    def wind(now):
        """천천히 바뀌는 바람 px/초. 사인 몇 개를 겹쳐 돌풍처럼."""
        return 14 * math.sin(now * 0.13) + 9 * math.sin(now * 0.051 + 1.3) + 6 * math.sin(now * 0.37 + 4.0)

    def snow(self, dt, now):
        px, stride, w, h, ph = self.surface.pixels, self.stride, self.w, self.h, self.pile.h
        wind = self.wind(now)
        for f in self.flakes:
            layer = SNOW_LAYERS[f[3]]
            sprites = self.snow_sprites[f[3]][f[4]]
            n = sprites[0][0]
            f[1] += f[2] * dt
            f[0] = (f[0] + wind * layer[6] * dt) % w
            x = f[0] + math.sin(f[5] + now * f[6]) * layer[5]
            xi, yi = int(x), int(f[1])
            col = min(max(xi + n // 2, 0), w - 1)
            if yi + n >= h - ph[col]:  # 쌓인 눈에 닿음. 먼 층은 쌓이지 않고 그 뒤로 사라짐
                if layer[7]:
                    self.pile.add(col, layer[1][f[4]])
                f[:] = self.new_flake(f[3], True)
                continue
            if yi < 0 or xi < 0 or xi + n > w:
                continue
            stamp(px, stride, xi, yi, sprites[int((f[1] - yi) * 4) * 4 + int((x - xi) * 4)][1])

    def render_pile(self):
        strip32 = self.strip.cast("I")
        w, last = self.w, self.pile_last
        for x, v in enumerate(self.pile.h):
            key = int(v * 16)
            if key != last[x]:  # 1/16 px 아래로 안 바뀐 열은 건너뜀
                last[x] = key
                strip32[x::w] = memoryview(pile_column(v, self.pile_edges, self.pile_body,
                                                       self.pile_zero)).cast("I")

    # ── 비 ──
    def new_drop(self, li, top):
        layer = RAIN_LAYERS[li]
        n = random.randint(*layer[1])
        y = -n - random.uniform(0, self.h * 0.4) if top else random.uniform(0, self.h)
        # [x, y, 속도, 층, 길이]
        return [random.uniform(-self.h * SLANT, self.w), y, random.uniform(*layer[2]), li, n]

    def rain(self, dt):
        px, stride, w, h = self.surface.pixels, self.stride, self.w, self.h
        for d in self.drops:
            d[1] += d[2] * dt
            d[0] += d[2] * SLANT * dt
            if d[1] + d[4] >= h:
                self.splash(d[0] + d[4] * SLANT, d[3])
                d[:] = self.new_drop(d[3], True)
                continue
            sw, rows = self.rain_sprites[d[3]][d[4]]
            xi, yi = int(d[0]), int(d[1])
            if yi >= 0 and 0 <= xi and xi + sw <= w:
                stamp(px, stride, xi, yi, rows)
        n, rows = self.droplet
        live = []
        for s in self.splashes:  # [x, y, vx, vy, 남은 초]
            s[4] -= dt
            s[3] += 1100 * dt  # 중력
            s[0] += s[2] * dt
            s[1] += s[3] * dt
            xi, yi = int(s[0]), int(s[1])
            if s[4] > 0 and 0 <= yi <= h - n and 0 <= xi <= w - n:
                stamp(px, stride, xi, yi, rows)
                live.append(s)
        self.splashes = live

    def splash(self, x, li):
        for _ in range(random.randint(1, 3) if li else random.randint(0, 1)):  # 먼 빗줄기는 덜 튐
            self.splashes.append([x, self.h - 3, random.uniform(-90, 90), random.uniform(-220, -90),
                                  random.uniform(0.25, 0.45)])

    # ── 돌리기 ──
    def reset(self):
        n = COUNT[self.amount]
        self.flakes, self.drops, self.splashes = [], [], []
        self.pile = Pile(self.w)
        self.strip = memoryview(bytearray(self.stride * PILE_STRIP))
        self.pile_last = [0] * self.w
        if self.kind == "snow":
            self.flakes = [self.new_flake(li, False) for li, layer in enumerate(SNOW_LAYERS)
                           for _ in range(round(n * layer[0]))]
        else:
            self.drops = [self.new_drop(li, False) for li, layer in enumerate(RAIN_LAYERS)
                          for _ in range(round(n * RAIN_MULT * layer[0]))]

    def frame(self, dt, now):
        self.surface.clear()
        if self.kind == "snow":
            if now - self.last_settle >= SETTLE_SEC:
                self.pile.settle(MELT_PER_SEC * (now - self.last_settle))
                self.last_settle = now
                self.render_pile()
            self.surface.pixels[(self.h - PILE_STRIP) * self.stride:] = self.strip
            self.snow(dt, now)
        else:
            self.rain(dt)
        self.surface.present()
        if now - self.last_topmost > 2:
            self.surface.topmost()
            self.last_topmost = now

    def run(self):
        period = 1 / FPS
        nxt = time.perf_counter()
        while True:
            self.surface.pump()
            if self.poll():
                break
            now = time.perf_counter()
            dt = min(now - self.last, 0.1)  # 멈췄다 돌아와도 한 번에 순간 이동하지 않게
            self.last = now
            if not self.visible:
                time.sleep(0.2)
                nxt = time.perf_counter()
                continue
            self.frame(dt, now)
            nxt += period
            delay = nxt - time.perf_counter()
            if delay < -period:  # 많이 밀렸으면 따라잡으려 몰아 그리지 말고 다시 맞춤
                nxt, delay = time.perf_counter(), 0
            time.sleep(max(0.0, delay))
        self.surface.close()


def check():
    p = Pile(40)
    p.add(20, 2.0)
    vol = PILE_PER_FLAKE * 2.0
    assert abs(sum(p.h) - vol) < 1e-9, "보탠 부피가 그대로여야 함"
    assert p.h[20] == max(p.h), "떨어진 자리가 제일 높음"
    for _ in range(200):
        p.settle(0)
    assert abs(sum(p.h) - vol) < 1e-6, "흘러내림·퍼짐은 부피를 안 바꿈"
    assert max(abs(a - b) for a, b in zip(p.h, p.h[1:])) <= SLOPE + 1e-6, "안식각보다 가파르면 안 됨"
    assert abs(p.h[10] - p.h[30]) < 0.01, "한쪽으로 쏠리지 않음"
    p.settle(0.5)
    assert abs(sum(p.h) - vol / 2) < 0.1, "녹는 양은 높이에 비례"
    spike = Pile(11)
    spike.h[5] = 20.0
    spike.settle(0)
    assert max(spike.h) < 12, "뾰족한 기둥은 한 번에 무너져야 함 (퍼짐만으로는 15 쯤 남음)"
    q = Pile(5)
    q.h = [PILE_CAP] * 5
    q.add(2, 3.0)
    assert q.h == [PILE_CAP] * 5, "다 차면 더 안 쌓임"
    edges, body = pile_column_parts()
    for v in (0.0, 0.5, 7.3, PILE_CAP):
        assert len(pile_column(v, edges, body, bytes(PILE_STRIP * 4))) == PILE_STRIP * 4, "열 길이가 띠 높이"
    for rows in (disc(3.0, 1.8, 235, SNOW_COLOR, SNOW_RIM, 0.5, 0.25)[1], streak(30, 165, 1.6)[1]):
        for skip, data in rows:
            assert skip % 4 == 0 and len(data) % 4 == 0
            for i in range(0, len(data), 4):
                assert max(data[i:i + 3]) <= data[i + 3], "premultiplied 는 색이 알파를 못 넘음"
            assert not data or (data[3] and data[-1]), "앞뒤 투명 픽셀은 잘려 있어야 함"
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
    ctypes.windll.winmm.timeBeginPeriod(1)  # 기본 타이머 간격(15.6ms)이면 30fps 를 청해도 21fps 에서 멈춤
    PID_FILE.write_text(str(os.getpid()))
    try:
        Weather(args.kind, args.amount).run()
    finally:
        ctypes.windll.winmm.timeEndPeriod(1)
        if overlay.running_pid(PID_FILE) == os.getpid():
            PID_FILE.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
