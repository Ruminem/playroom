# SPDX-License-Identifier: Apache-2.0
"""모든 창 위에 내리는 눈·비·뇌우·벚꽃·낙엽과 떠다니는 반딧불이. 보이기만 하고 클릭은 그대로 아래 창으로 간다.

  pythonw weather.py            띄우기 (창 없이 뒤에서 돎)
  python weather.py --toggle    떠 있으면 치우고, 없으면 띄움 (weather.bat 이 이걸 부름)
  python weather.py --stop      치우기
  python weather.py --kind rain --amount many
  python weather.py --check     자체 점검

작업 영역(작업 표시줄 뺀 주 모니터) 전체를 덮는 픽셀 알파 창(shared/surface.py)에 30fps 로 그린다.
눈은 원근 세 층으로 바람에 흔들리며 내리고 작업 표시줄 위에 쌓였다 천천히 녹는다. 꽃잎·낙엽도 같은 층과
더미를 쓰되 빙글빙글 돌며 팔랑인다. 비는 기운 빗줄기로 내리고 바닥에서 튀며, 뇌우는 거기에 번개를 더한다.
반딧불이는 화면 아래쪽을 떠다니며 깜빡인다. 고양이(pet.py)를 켜면 바닥이나 쌓인 더미 위를 돌아다닌다.
트레이의 눈송이 메뉴에서 종류·양·고양이·숨기기·끝내기를 하고,
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
import startup
from surface import Surface
import pet
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

PILE_CAP = 16      # 쌓인 눈의 최대 높이 px. 군데군데 솟는 둔덕이 화면을 덜 가리게
PILE_STRIP = PILE_CAP + 2
PILE_PER_FLAKE = 10.0  # 눈송이 하나가 보태는 부피 = 이 값 × 반지름. 실제보다 부풀려 몇 분 안에 쌓이게.
                       # 멈추는 높이가 이 값에 비례함 (21 이면 보통 11px·많이 21px, 10 이면 그 절반쯤)
                       # 반지름²에 비례시키면 큰 눈송이 하나에 둔덕이 툭 솟음
SLOPE = 0.8        # 이웃 열과의 높이 차가 이보다 크면 흘러내림 (안식각)
DIFFUSE = 0.12     # 표면을 매끈하게 퍼뜨리는 정도
MELT_PER_SEC = 0.0045  # 높이에 비례해 녹는 비율. 넣는 양 ÷ 이 값에서 높이가 멈춤 ('보통' 이면 5px 쯤)
SETTLE_SEC = 0.25

STORM_MULT = 1.5   # 뇌우는 비보다 굵게
BOLT_EVERY = (5, 14)  # '보통' 일 때 번개 간격 초. 양에 반비례
BOLT_CORE, BOLT_GLOW = (244, 246, 255), (140, 160, 255)
BOLT_LEVELS = (1.0, 0.55, 0.25)
BOLT_FLICKER = ((0.0, 0.07, 0), (0.12, 0.24, 0), (0.24, 0.42, 1), (0.42, 0.6, 2))  # (시작 초, 끝 초, 밝기 단계)
BOLT_PAD = 4       # 줄기 둘레 번짐 px

# 잎 층: (비율, 길이 px 들, 속도 px/초, 알파, 흔들림 px, 바람을 받는 정도, 쌓일 때 부피 — 0 이면 안 쌓임)
LEAF_LAYERS = ((0.4, (6,), (18, 30), 160, 10, 0.8, 0),
               (0.45, (10, 12), (30, 48), 230, 22, 1.1, 1.9),  # 부피는 PILE_PER_FLAKE 를 곱함 — 눈을
               (0.15, (17,), (45, 70), 245, 36, 1.4, 2.9))     # 낮추며 21→10 일 때 잎 더미 높이는 그대로 두려고 2.1배
LEAF_ANGLES = 12
LEAF_FLIPS = (0.9, 0.6, 0.3, -0.3, -0.6, -0.9)  # 앞에서 본 너비 비율. 음수는 뒷면 — 조금 어둡게
LEAF_KINDS = {  # 비율: 양 → 개수, ratio: 너비/길이, notch: 끝에 홈(벚꽃잎)
    "petals": {"palette": ((255, 196, 212), (250, 172, 194), (255, 224, 232)), "ratio": 0.62, "notch": True,
               "share": 0.6},
    "leaves": {"palette": ((216, 98, 36), (232, 146, 40), (186, 58, 38), (204, 164, 52)), "ratio": 0.5,
               "notch": False, "share": 0.45}}

FLY_SHARE = 0.17   # 양 → 반딧불 마리 수 ('보통' 25마리)
FLY_CORE, FLY_HALO = (246, 255, 184), (172, 236, 70)
FLY_LEVELS = 8
FLY_SIZES = ((1.3, 6.0), (2.0, 9.0))  # (빛 알갱이 반지름, 번짐 반지름) — 멀리, 가까이

KINDS = {1: ("snow", "눈"), 2: ("rain", "비"), 3: ("storm", "뇌우"), 4: ("petals", "벚꽃"),
         5: ("leaves", "낙엽"), 6: ("fireflies", "반딧불이"), 7: ("none", "날씨 없음")}  # 없음은 고양이만
KIND_NAMES = tuple(k for k, _ in KINDS.values())
SHOW, PET, AUTOSTART, EXIT = 20, 21, 50, 99
RUN_NAME = "PlayroomWeather"  # 시작할 때는 인자 없이 떠서 저장된 종류·양을 따름
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


def leaf_shape(length, ratio, angle, flip, notch):
    """돌고 뒤집힌 꽃잎·잎 모양: 행마다 (덮인 정도, 밝기) 목록. 2×2 로 나눠 덮인 정도를 센다.
    꽃잎은 둥근 타원에 끝 홈, 잎은 양끝이 뾰족한 렌즈. 뒷면(flip < 0)은 어둡고, 밑동 쪽도 조금 어둡다."""
    a = length / 2
    b = a * ratio * abs(flip)
    n = int(math.ceil(length)) + 2
    c = n / 2 - 0.5
    ca, sa = math.cos(angle), math.sin(angle)
    shade = 1.0 if flip > 0 else 0.76
    power = 0.5 if notch else 0.9
    out = []
    for y in range(n):
        row = []
        for x in range(n):
            cov = 0
            for sx, sy in ((-0.25, -0.25), (0.25, -0.25), (-0.25, 0.25), (0.25, 0.25)):
                dx, dy = x + sx - c, y + sy - c
                u, v = dx * ca + dy * sa, dy * ca - dx * sa
                if abs(u) < a and abs(v) <= b * (1 - (u / a) ** 2) ** power + 0.15 \
                        and not (notch and u > a * 0.7 and abs(v) < b * 0.25):
                    cov += 1
            u0 = (x - c) * ca + (y - c) * sa
            row.append((cov / 4, shade * (0.86 + 0.14 * max(-1.0, min(1.0, u0 / a)))))
        out.append(row)
    return n, out


def paint(shape, color, alpha):
    n, rows = shape
    return n, [trim(b"".join(pixel(tuple(int(ch * k) for ch in color), alpha * cov) for cov, k in row))
               for row in rows]


def glow(core_r, halo_r, level, fx, fy):
    """반딧불 빛: 또렷한 알갱이에 넓고 옅은 번짐. level 은 0..1 밝기."""
    n = int(math.ceil(2 * halo_r)) + 2
    c = n / 2 - 0.5
    rows = []
    for y in range(n):
        row = b""
        for x in range(n):
            d = math.hypot(x - c - fx, y - c - fy)
            core = min(1.0, max(0.0, core_r + 0.5 - d))
            halo = 0.6 * math.exp(-(d / (halo_r * 0.6)) ** 2)
            color = tuple(int(FLY_HALO[i] + (FLY_CORE[i] - FLY_HALO[i]) * core) for i in range(3))
            row += pixel(color, 255 * level * min(1.0, core + halo))
        rows.append(trim(row))
    return n, rows


def blink(t, period):
    """반딧불 한 마리의 밝기 0..1. 주기 안에서 0.3초 켜지고 0.7초 머물고 0.8초 꺼지며, 나머지는 어둠."""
    t %= period
    if t < 0.3:
        return t / 0.3
    if t < 1.0:
        return 1.0
    if t < 1.8:
        return 1 - (t - 1.0) / 0.8
    return 0.0


def bolt_segments(w, h, rng):
    """번개 줄기: (x0, y0, x1, y1, 굵기) 목록. 본줄기는 위에서 아래로 지그재그, 곁가지는 비스듬히 짧게."""
    end = rng.uniform(0.35, 0.75) * h
    segs = []
    lo, hi = BOLT_PAD + 2, w - BOLT_PAD - 3

    def walk(x, y, drift, steps, width, branches):
        for _ in range(steps):
            nx = min(hi, max(lo, x + rng.gauss(drift, 7)))
            ny = min(h - BOLT_PAD - 3, y + rng.uniform(8, 18))
            segs.append((x, y, nx, ny, width))
            if branches and rng.random() < 0.12:
                walk(nx, ny, rng.choice((-1, 1)) * rng.uniform(6, 12), rng.randint(4, 14), width * 0.55, False)
            x, y = nx, ny
            if y >= end:
                break

    x0 = min(hi, max(lo, rng.uniform(w * 0.1, w * 0.9)))
    walk(x0, float(BOLT_PAD), rng.uniform(-3, 3), 10 ** 6, 1.0, True)  # BOLT_PAD 부터 — 번짐이 위로 안 넘치게
    return segs


def dab(width):
    """줄기의 한 점: (dx, dy, 밝기 0..255) 목록. 가운데는 하얗게 차고 둘레는 옅게 번짐."""
    out = []
    for dy in range(-BOLT_PAD, BOLT_PAD + 1):
        for dx in range(-BOLT_PAD, BOLT_PAD + 1):
            d = math.hypot(dx, dy)
            v = 255 * max(min(1.0, max(0.0, width + 0.6 - d)), 0.35 * math.exp(-(d / (1.2 + width * 1.6)) ** 2))
            if v >= 4:
                out.append((dx, dy, int(v)))
    return out


def bolt_sprite(segs):
    """줄기를 밝기 판(bytearray) 하나에 최댓값으로 찍고, 밝기 단계마다 색을 입혀 그림 조각으로.
    픽셀마다 파이썬을 돌면 수십만 번이라, 색 입히기와 단계 낮추기는 bytes.translate 표로 한다."""
    xs = [v for s in segs for v in (s[0], s[2])]
    ys = [v for s in segs for v in (s[1], s[3])]
    bx, by = int(min(xs)) - BOLT_PAD, int(min(ys)) - BOLT_PAD
    bw, bh = int(max(xs)) - bx + BOLT_PAD + 2, int(max(ys)) - by + BOLT_PAD + 2
    lum = bytearray(bw * bh)
    dabs = {}
    for x0, y0, x1, y1, width in segs:
        pts = dabs.setdefault(width, dab(width))
        steps = int(math.hypot(x1 - x0, y1 - y0)) + 1
        for i in range(steps):
            cx, cy = int(x0 + (x1 - x0) * i / steps) - bx, int(y0 + (y1 - y0) * i / steps) - by
            for dx, dy, v in pts:
                o = (cy + dy) * bw + cx + dx
                if v > lum[o]:
                    lum[o] = v
    lum = bytes(lum)
    levels = []
    for k in BOLT_LEVELS:
        a_tab = bytes(int(v * k) for v in range(256))
        # 밝을수록 하얀 가운데 색, 옅을수록 푸른 번짐 색. premultiplied 라 색 = 색 × 알파
        chans = [bytes(int(a * (BOLT_GLOW[i] + (BOLT_CORE[i] - BOLT_GLOW[i]) * (v / 255) ** 2) / 255)
                       for v, a in enumerate(a_tab)) for i in (2, 1, 0)]
        rows = []
        for y in range(bh):
            line = lum[y * bw:(y + 1) * bw]
            lead = bw - len(line.lstrip(b"\0"))
            line = line.strip(b"\0")
            px = bytearray(len(line) * 4)
            px[0::4], px[1::4], px[2::4], px[3::4] = (line.translate(t) for t in (*chans, a_tab))
            rows.append((lead * 4, bytes(px)))
        levels.append(rows)
    return bx, by, levels


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


def pile_parts_mixed(palette):
    """꽃잎·낙엽 더미: 색 덩어리를 섞은 몸통 여러 벌. 열마다 하나씩 골라 무더기처럼 보이게."""
    rng = random.Random(7)
    rim = tuple(int(ch * 0.72) for ch in palette[0])
    edges = [pixel(rim, 255 * q / 16) for q in range(16)]
    bodies = []
    for _ in range(16):
        col = []
        while len(col) < PILE_STRIP:
            color = rng.choice(palette)
            for _ in range(rng.randint(2, 4)):
                k = 1 - 0.3 * min(1.0, len(col) / 14)  # 깊을수록 그늘
                col.append(pixel(tuple(int(ch * k) for ch in color), 255))
        bodies.append(b"".join(col[:PILE_STRIP]))
    return edges, bodies


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
    if data.get("kind") in KIND_NAMES:
        ok["kind"] = data["kind"]
    if data.get("amount") in COUNT:
        ok["amount"] = data["amount"]
    if isinstance(data.get("pet"), bool):
        ok["pet"] = data["pet"]
    return ok


class Weather:
    def __init__(self, kind, amount, cat=False):
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
        self.snow_pile = pile_column_parts()
        self.pile_zero = bytes(PILE_STRIP * 4)
        self.sprite_cache = {}  # 꽃잎·낙엽·반딧불 그림은 그 종류를 처음 고를 때 그림
        self.cat_sprites = pet.sprites()
        self.cat = pet.Cat(self.w) if cat else None  # 종류를 바꿔도 그대로 — 고양이는 날씨와 따로 삶
        self.bolt_seen = None
        self.commands = queue.Queue()  # 트레이 스레드 → 그리는 스레드
        write_ico(ICON_FILE, ICON, ICON_COLORS)
        self.tray = Tray(TRAY_CLASS, ICON_FILE, "날씨", self.menu, self.commands.put)
        self.last = self.last_settle = self.last_topmost = time.perf_counter()
        self.reset()
        self.surface.show(True)

    # ── 트레이 ──
    def menu(self):
        return [*((label, cid, key == self.kind) for cid, (key, label) in KINDS.items()),
                None,
                ("양", [(label, cid, key == self.amount) for cid, (key, label, _) in AMOUNTS.items()]),
                None,
                ("고양이", PET, self.cat is not None),
                ("보이기", SHOW, self.visible),
                ("Windows 시작 시 실행", AUTOSTART, startup.is_on(RUN_NAME, __file__)),
                None,
                ("끝내기", EXIT, False)]

    def handle(self, cid):
        if cid in KINDS:
            self.kind = KINDS[cid][0]
        elif cid in AMOUNTS:
            self.amount = AMOUNTS[cid][0]
        elif cid == PET:
            self.cat = None if self.cat else pet.Cat(self.w)
            self.save()
            return
        elif cid == SHOW:
            self.visible = not self.visible
            self.surface.show(self.visible)
            return
        elif cid == AUTOSTART:
            startup.toggle(RUN_NAME, __file__)
            return
        elif cid == EXIT:
            self.tray.close()  # 트레이가 닫히면 None 이 와서 poll 이 끝냄
            return
        self.reset()
        self.save()

    def save(self):
        try:
            SETTINGS.parent.mkdir(parents=True, exist_ok=True)
            SETTINGS.write_text(json.dumps({"kind": self.kind, "amount": self.amount, "pet": self.cat is not None}),
                                encoding="utf-8")
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
        w, last, bodies, pick = self.w, self.pile_last, self.pile_bodies, self.pile_pick
        for x, v in enumerate(self.pile.h):
            key = int(v * 16)
            if key != last[x]:  # 1/16 px 아래로 안 바뀐 열은 건너뜀
                last[x] = key
                strip32[x::w] = memoryview(pile_column(v, self.pile_edges, bodies[pick[x]],
                                                       self.pile_zero)).cast("I")

    # ── 꽃잎·낙엽 ──
    def leaf_sprites(self, kind):
        """[층][크기][색] → 각도 × 뒤집힘 그림 목록. 모양은 크기마다 한 번 재고 색만 바꿔 칠함."""
        if kind not in self.sprite_cache:
            spec = LEAF_KINDS[kind]
            out = []
            for layer in LEAF_LAYERS:
                sizes = []
                for length in layer[1]:
                    shapes = [leaf_shape(length, spec["ratio"], math.tau * ai / LEAF_ANGLES, flip, spec["notch"])
                              for ai in range(LEAF_ANGLES) for flip in LEAF_FLIPS]
                    sizes.append([[paint(s, color, layer[3]) for s in shapes] for color in spec["palette"]])
                out.append(sizes)
            self.sprite_cache[kind] = out
        return self.sprite_cache[kind]

    def new_leaf(self, li, top):
        layer = LEAF_LAYERS[li]
        y = -random.uniform(15, 80) if top else random.uniform(0, self.h)
        # [x, y, 속도, 층, 크기, 색, 흔들림 위상, 흔들림 빠르기, 각도, 도는 빠르기, 뒤집힘 위상, 뒤집힘 빠르기]
        return [random.uniform(0, self.w), y, random.uniform(*layer[2]), li, random.randrange(len(layer[1])),
                random.randrange(len(LEAF_KINDS[self.kind]["palette"])), random.uniform(0, 6.3),
                random.uniform(0.3, 0.8), random.uniform(0, math.tau), random.uniform(-2.5, 2.5),
                random.uniform(0, math.tau), random.uniform(1.5, 4.0)]

    def flutter(self, dt, now):
        px, stride, w, h, ph = self.surface.pixels, self.stride, self.w, self.h, self.pile.h
        wind, sprites, nflip = self.wind(now), self.leaves_sprites, len(LEAF_FLIPS)
        for f in self.leaves:
            layer = LEAF_LAYERS[f[3]]
            f[10] += f[11] * dt
            c = math.cos(f[10])
            f[1] += f[2] * (1.35 - 0.6 * abs(c)) * dt  # 옆으로 선 잎은 빨리, 넓게 누운 잎은 천천히 떨어짐
            f[0] = (f[0] + wind * layer[5] * dt) % w
            f[8] += f[9] * dt
            x = f[0] + math.sin(f[6] + now * f[7]) * layer[4]
            frames = sprites[f[3]][f[4]][f[5]]
            n = frames[0][0]
            xi, yi = int(x), int(f[1])
            col = min(max(xi + n // 2, 0), w - 1)
            if yi + n >= h - ph[col]:
                if layer[6]:
                    self.pile.add(col, layer[6])
                f[:] = self.new_leaf(f[3], True)
                continue
            if yi < 0 or xi < 0 or xi + n > w:
                continue
            ai = int(f[8] / math.tau * LEAF_ANGLES) % LEAF_ANGLES
            stamp(px, stride, xi, yi, frames[ai * nflip + min(nflip - 1, int((1 - c) * nflip / 2))][1])

    # ── 반딧불이 ──
    def fly_sprites(self):
        """[크기][밝기 단계 1..8][1/4 픽셀 위치 16벌]."""
        if "fireflies" not in self.sprite_cache:
            self.sprite_cache["fireflies"] = [
                [[glow(core, halo, lv / FLY_LEVELS, fx / 4, fy / 4) for fy in range(4) for fx in range(4)]
                 for lv in range(1, FLY_LEVELS + 1)] for core, halo in FLY_SIZES]
        return self.sprite_cache["fireflies"]

    def new_fly(self):
        # [x, y, 방향, 빠르기, 크기, 깜빡임 주기, 주기 어긋남, 방향이 틀어지는 빠르기]
        return [random.uniform(0, self.w), random.uniform(self.h * 0.35, self.h - 12), random.uniform(0, math.tau),
                random.uniform(8, 26), 1 if random.random() < 0.35 else 0, random.uniform(2.5, 5.5),
                random.uniform(0, 6), 0.0]

    def fireflies(self, dt, now):
        px, stride, w, h, sprites = self.surface.pixels, self.stride, self.w, self.h, self.flies_sprites
        for f in self.flies:
            f[7] = max(-1.2, min(1.2, f[7] + random.gauss(0, 1.5) * dt))
            f[2] += f[7] * dt
            f[0] = (f[0] + math.cos(f[2]) * f[3] * dt) % w
            f[1] += math.sin(f[2]) * f[3] * 0.6 * dt
            if (f[1] < h * 0.3 and math.sin(f[2]) < 0) or (f[1] > h - 12 and math.sin(f[2]) > 0):
                f[2] = -f[2]  # 화면 아래쪽 2/3 안에서 위아래로 튕김
            lv = round(blink(now + f[6], f[5]) * FLY_LEVELS)
            if not lv:
                continue
            frames = sprites[f[4]][lv - 1]
            n = frames[0][0]
            x, y = f[0] - n / 2, f[1] - n / 2
            xi, yi = int(x), int(y)
            if 0 <= xi and xi + n <= w and 0 <= yi and yi + n <= h:
                stamp(px, stride, xi, yi, frames[int((y - yi) * 4) * 4 + int((x - xi) * 4)][1])

    # ── 번개 ──
    def lightning(self, now):
        if self.bolt is None and now >= self.next_bolt:
            bx, by, levels = bolt_sprite(bolt_segments(self.w, self.h, random))
            self.bolt = (now, bx, by, levels)
            lo, hi = BOLT_EVERY
            k = COUNT["normal"] / COUNT[self.amount]
            self.next_bolt = now + random.uniform(lo * k, hi * k)
        if self.bolt is None:
            return
        t0, bx, by, levels = self.bolt
        t = now - t0
        if t > BOLT_FLICKER[-1][1]:
            self.bolt = None
            return
        for start, end, lv in BOLT_FLICKER:
            if start <= t < end:
                stamp(self.surface.pixels, self.stride, bx, by, levels[lv])

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
        n, kind = COUNT[self.amount], self.kind
        self.flakes, self.drops, self.splashes, self.leaves, self.flies = [], [], [], [], []
        self.bolt, self.next_bolt = None, time.perf_counter() + random.uniform(2, 5)
        self.pile = Pile(self.w)
        self.strip = memoryview(bytearray(self.stride * PILE_STRIP))
        self.pile_last = [0] * self.w
        self.pile_edges, body = self.snow_pile
        self.pile_bodies, self.pile_pick = [body], [0] * self.w
        if kind == "snow":
            self.flakes = [self.new_flake(li, False) for li, layer in enumerate(SNOW_LAYERS)
                           for _ in range(round(n * layer[0]))]
        elif kind in ("rain", "storm"):
            mult = RAIN_MULT * (STORM_MULT if kind == "storm" else 1)
            self.drops = [self.new_drop(li, False) for li, layer in enumerate(RAIN_LAYERS)
                          for _ in range(round(n * mult * layer[0]))]
        elif kind in LEAF_KINDS:
            spec = LEAF_KINDS[kind]
            self.leaves_sprites = self.leaf_sprites(kind)
            self.pile_edges, self.pile_bodies = pile_parts_mixed(spec["palette"])
            self.pile_pick = []
            while len(self.pile_pick) < self.w:  # 3–7열씩 같은 몸통 — 열마다 고르면 세로 줄무늬가 됨
                self.pile_pick += [random.randrange(len(self.pile_bodies))] * random.randint(3, 7)
            self.leaves = [self.new_leaf(li, False) for li, layer in enumerate(LEAF_LAYERS)
                           for _ in range(round(n * spec["share"] * layer[0]))]
        elif kind == "fireflies":
            self.flies_sprites = self.fly_sprites()
            self.flies = [self.new_fly() for _ in range(round(n * FLY_SHARE))]

    # ── 고양이 ──
    def walk_cat(self, dt, now):
        cat, rainy = self.cat, self.kind in ("rain", "storm")
        if self.bolt and self.bolt[0] != self.bolt_seen:
            self.bolt_seen = self.bolt[0]
            cat.startle(now)
        cat.update(dt, now, rainy)
        a, b = cat.feet()
        cat.draw(self.surface.pixels, self.stride, self.h, self.cat_sprites, max(self.pile.h[a:b]), now, rainy)

    def frame(self, dt, now):
        self.surface.clear()
        kind = self.kind
        piled = kind == "snow" or kind in LEAF_KINDS
        if piled:
            if now - self.last_settle >= SETTLE_SEC:
                self.pile.settle(MELT_PER_SEC * (now - self.last_settle))
                self.last_settle = now
                self.render_pile()
            self.surface.pixels[(self.h - PILE_STRIP) * self.stride:] = self.strip
        if self.cat:  # 더미 위, 내리는 것 아래
            self.walk_cat(dt, now)
        if piled:
            self.snow(dt, now) if kind == "snow" else self.flutter(dt, now)
        elif kind == "fireflies":
            self.fireflies(dt, now)
        elif kind in ("rain", "storm"):
            self.rain(dt)
            if kind == "storm":
                self.lightning(now)
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
    rng = random.Random(3)
    segs = bolt_segments(400, 300, rng)
    assert all(0 <= v[0] < 400 and 0 <= v[2] < 400 and 0 <= v[1] < 300 and 0 <= v[3] < 300 for v in segs), \
        "번개는 화면 안에"
    assert any(s[4] < 1 for s in segs) and segs[0][1] == BOLT_PAD, "위에서 시작하고 곁가지가 있음 (씨앗 3)"
    bx, by, levels = bolt_sprite(segs)
    assert bx >= 0 and by >= 0 and by + len(levels[0]) <= 300, "그림 조각이 화면 밖으로 안 나감"
    assert bx + max(skip // 4 + len(d) // 4 for skip, d in levels[0]) <= 400
    for seed in range(5):  # 좁은 폭이면 지그재그가 반드시 가장자리에 닿음
        nx, _, narrow = bolt_sprite(bolt_segments(30, 300, random.Random(seed)))
        assert nx >= 0 and nx + max(skip // 4 + len(d) // 4 for skip, d in narrow[0]) <= 30, "가장자리에서 막힘"
    assert sum(len(d) for sk, d in levels[0]) > 4 * 200, "줄기가 그려져 있음"
    petal = paint(leaf_shape(13, 0.62, 0.7, -0.55, True), (255, 196, 212), 240)
    edge_on = paint(leaf_shape(13, 0.62, 0.7, 0.3, True), (255, 196, 212), 240)
    assert sum(len(d) for _, d in petal[1]) > sum(len(d) for _, d in edge_on[1]), "옆으로 서면 좁아 보임"
    assert [round(blink(t, 4), 6) for t in (0, 0.15, 0.5, 1.4, 2, 3.9)] == [0, 0.5, 1, 0.5, 0, 0], "깜빡임 곡선"
    sprites = [disc(3.0, 1.8, 235, SNOW_COLOR, SNOW_RIM, 0.5, 0.25)[1], streak(30, 165, 1.6)[1], petal[1],
               paint(leaf_shape(9, 0.5, 2.0, 0.9, False), (216, 98, 36), 225)[1], glow(1.5, 6.5, 0.6, 0.25, 0.5)[1],
               levels[0]]
    for rows in sprites + levels[1:]:
        for skip, data in rows:
            assert skip % 4 == 0 and len(data) % 4 == 0
            for i in range(0, len(data), 4):
                assert max(data[i:i + 3]) <= data[i + 3], "premultiplied 는 색이 알파를 못 넘음"
    for rows in sprites:  # 어둡게 낮춘 번개 단계는 끝 픽셀 알파가 0 으로 떨어질 수 있어 뺌
        for skip, data in rows:
            assert not data or (data[3] and data[-1]), "앞뒤 투명 픽셀은 잘려 있어야 함"
    print("자체 점검 통과")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--stop", action="store_true", help="떠 있는 날씨를 치움")
    ap.add_argument("--toggle", action="store_true", help="떠 있으면 치우고, 없으면 띄움")
    ap.add_argument("--check", action="store_true", help="자체 점검")
    saved = load_settings()  # 안 주면 트레이 메뉴에서 마지막으로 고른 값
    ap.add_argument("--kind", default=saved.get("kind", "snow"), choices=KIND_NAMES)
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
        Weather(args.kind, args.amount, saved.get("pet", False)).run()
    finally:
        ctypes.windll.winmm.timeEndPeriod(1)
        if overlay.running_pid(PID_FILE) == os.getpid():
            PID_FILE.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
