# SPDX-License-Identifier: Apache-2.0
"""모든 창 위에 내리는 눈·비·뇌우와 떠다니는 반딧불이, 어항. 보이기만 하고 클릭은 그대로 아래 창으로 간다.

  pythonw weather.py            띄우기 (창 없이 뒤에서 돎)
  python weather.py --toggle    떠 있으면 치우고, 없으면 띄움 (weather.bat 이 이걸 부름)
  python weather.py --stop      치우기
  python weather.py --kind rain --amount 80   양은 0–100% (예전 few·normal·many 도 받음)
  python weather.py --check     자체 점검

작업 영역(작업 표시줄 뺀 주 모니터)과 그 아래 작업 표시줄까지 덮는 픽셀 알파 창(shared/surface.py)에 기본 60fps 로
그린다(메뉴에서 30–180). 바닥은 작업 표시줄에 보이는 틀(단추 묶음·알림 영역·HUD·sysmon, taskbar.frames)의 윗변이고
그 사이 틈은 화면 맨 아래. 눈은 원근 세 층으로 바람에 흔들리며 내리고 그 바닥 위에 쌓였다 천천히 녹는다.
비는 세 겹 깊이의 빗줄기가 돌풍에 기울며 내리고 바닥에서 튀며, 뇌우는 거기에 번개와 빗발의 물결을 더한다.
반딧불이는 화면 아래쪽을 떠다니며 깜빡인다. 어항은 화면을 옅은 물빛으로 덮고 빛줄기·거품·물고기·모래·해초를 그린다. 고양이(pet.py)를 켜면 바닥이나 쌓인 더미 위를 돌아다닌다.
트레이의 눈송이 메뉴에서 종류·양·고양이·숨기기·끝내기를 하고(양은 10% 칸으로 0–100%),
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
import threading
import time
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "shared"))
MAC = sys.platform == "darwin"
if MAC:  # 같은 이름의 맥판(surface·overlay·tray·startup)이 앞에 잡히게
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "shared" / "mac"))
import overlay
import startup
from surface import Surface
import pet
from tray import Tray, write_ico
if not MAC:
    import taskbar

PID_FILE = Path(tempfile.gettempdir()) / "playroom-weather.pid"
ICON_FILE = Path(tempfile.gettempdir()) / "playroom-weather.ico"
SETTINGS = (Path.home() / "Library" / "Application Support" if MAC else
            Path(os.environ.get("LOCALAPPDATA", Path.home()))) / "playroom" / "weather.json"
TRAY_CLASS = "PlayroomWeatherTray"
SURFACE_CLASS = "PlayroomWeatherSurface"

FPS = 60           # 기본. 13fps 는 끊겨 보였음. 타이머 해상도를 1ms 로 올려야 청한 만큼 나옴
# 메뉴 id → 초당 그리는 횟수. 2560×1392 에서 잰 한 코어 대비 CPU: 눈 100% 9·16·46%(30·60·180), 비 100% 13·27·77%
FPS_IDS = {40: 30, 41: 60, 42: 120, 43: 180}
SNOW_COLOR, SNOW_RIM = (248, 250, 255), (165, 176, 198)  # 테두리를 옅은 회청색으로 — 흰 창 위에서도 보이게
RAIN_COLOR = (200, 214, 236)
RAIN_LIT, RAIN_LIT_COLOR = 1.7, (236, 242, 255)  # 번개가 번쩍일 때 빗줄기 — 알파 배수, 색

# 눈 층: (비율, 반지름들 px, 속도 px/초, 알파, 번짐 px, 흔들림 px, 바람을 받는 정도, 바닥에 쌓이나)
SNOW_LAYERS = ((0.45, (0.7, 0.9, 1.1), (16, 28), 150, 0.8, 4, 0.4, False),   # 멀리
               (0.42, (1.3, 1.6, 2.0), (32, 52), 225, 0.9, 10, 0.7, True),   # 가운데
               (0.13, (2.4, 3.0, 3.6), (58, 88), 235, 1.8, 18, 1.0, True))   # 가까이 — 크고 번짐
# 비 층: (비율, 길이 px, 속도 px/초, 알파, 굵기 px)
RAIN_LAYERS = ((0.45, (9, 15), (460, 580), 75, 0.8),       # 멀리 — 가늘고 흐리고 느림, 안 튐
               (0.35, (16, 26), (650, 820), 120, 1.0),
               (0.25, (30, 44), (900, 1150), 190, 1.6))
SLANT = 0.12       # 빗줄기 기본 기울기 (가로 / 세로)
SLANTS = tuple(i * 0.05 for i in range(8))  # 미리 그려 두는 기울기들. 돌풍은 이 사이를 오감
GUST = {"rain": (0.06, 0.10), "storm": (0.16, 0.20)}  # 종류 → (기본에 더함, 출렁임 폭)
CROWN_SEC = 0.09   # 빗방울이 바닥에 닿는 순간 ㅅ자 튐을 보여 주는 시간
RAIN_MULT = 2      # 비는 빨리 지나가 같은 개수면 듬성듬성해 보여서 눈의 두 배

PILE_CAP = 16      # 쌓인 눈의 최대 높이 px. 군데군데 솟는 둔덕이 화면을 덜 가리게
PILE_STRIP = PILE_CAP + 2
PILE_PER_FLAKE = 10.0  # 눈송이 하나가 보태는 부피 = 이 값 × 반지름. 실제보다 부풀려 몇 분 안에 쌓이게.
                       # 멈추는 높이가 이 값에 비례함 (21 이면 보통 11px·많이 21px, 10 이면 그 절반쯤)
                       # 반지름²에 비례시키면 큰 눈송이 하나에 둔덕이 툭 솟음
SLOPE = 0.8        # 이웃 열과의 높이 차가 이보다 크면 흘러내림 (안식각)
DIFFUSE = 0.12     # 표면을 매끈하게 퍼뜨리는 정도
DRIFT, LOOSE, LIFT = 0.12, 3.0, 2.0  # 바람에 날리는 눈: 바람 px/초 × 초당 옮기는 비율 · 겉의 날리는 두께 px · 넘는 턱 px
MELT_PER_SEC = 0.0045  # 높이에 비례해 녹는 비율. 넣는 양 ÷ 이 값에서 높이가 멈춤 ('보통' 이면 5px 쯤)
SETTLE_SEC = 0.25
FRAMES_EVERY = 3   # 작업 표시줄 틀을 다시 읽는 간격 초. 한 번 55ms(UI 자동화)라 다른 스레드에서

STORM_MULT = 1.5   # 뇌우는 비보다 굵게
BOLT_EVERY = (5, 14)  # '보통' 일 때 번개 간격 초. 양에 반비례
BOLT_CORE, BOLT_GLOW = (244, 246, 255), (140, 160, 255)
BOLT_LEVELS = (1.0, 0.55, 0.25)
BOLT_FLICKER = ((0.0, 0.07, 0), (0.12, 0.24, 0), (0.24, 0.42, 1), (0.42, 0.6, 2))  # (시작 초, 끝 초, 밝기 단계)
BOLT_PAD = 4       # 줄기 둘레 번짐 px

FLY_SHARE = 0.17   # 양 → 반딧불 마리 수 ('보통' 25마리)
FLY_CORE, FLY_HALO = (246, 255, 184), (172, 236, 70)
FLY_LEVELS = 8
FLY_SIZES = ((1.3, 6.0), (2.0, 9.0))  # (빛 알갱이 반지름, 번짐 반지름) — 멀리, 가까이

HAIL_SHARE = 0.4   # 양 → 우박 알 수 ('보통' 60개)
HAIL_SIZES = ((1.2, 0.8, 225), (2.1, 0.9, 245))  # (반지름, 가장자리 흐림, 알파) — 작은 알, 큰 알
HAIL_COLOR, HAIL_RIM = (250, 252, 255), (186, 212, 238)
HAIL_SPEED = (820, 1050)  # 떨어지는 빠르기 px/초. 튀어 오른 뒤엔 중력으로 다시 이 빠르기까지
HAIL_BOUNCES = 2   # 바닥·더미에서 튀는 최대 횟수. 그다음 더미에 보탬
HAIL_MELT = 4      # 더미가 눈보다 몇 배 빨리 녹나
HAIL_SCARE = (24, 0.25, 5.0)  # 동물 발에서 이 px 안에 떨어지면 이 확률로 놀람, 한 번 놀라면 이 초 동안은 안 놀람
BANG_NEAR = 700  # 불꽃이 이 px 안에서 터지면 동물이 멈춰 서서 봄

FW_RATE = 1.3      # 양 100% 에서 초당 쏘아 올리는 수
FW_BURST_AT = (0.20, 0.55)  # 터지는 높이 (화면 위에서 비율)
FW_SPARKS = (60, 110)
FW_LIFE = (1.0, 1.7)
FW_LEVELS = 6
FW_GOLD = 1        # 로켓 꼬리 색 (FW_COLORS 번호)
FW_COLORS = (((255, 222, 212), (255, 62, 52)),    # (알갱이, 번짐) 빨강
             ((255, 242, 196), (255, 172, 40)),   # 금
             ((222, 255, 222), (60, 232, 92)),    # 초록
             ((222, 236, 255), (72, 132, 255)),   # 파랑
             ((246, 222, 255), (192, 82, 255)),   # 보라
             ((255, 255, 255), (204, 212, 232)))  # 흰

# 어항. 물빛은 행마다 색 하나로 화면 전체를 덮음 — 위는 옅은 하늘색, 아래로 갈수록 짙은 파랑
AQ_TOP, AQ_DEEP = (96, 178, 226), (26, 92, 178)
AQ_ALPHA = (0.05, 0.08)  # 양 50% 일 때 (맨 위, 맨 아래) 불투명도. 양에 비례 — 100% 면 두 배, 0% 면 투명
AQ_BANDS = 4       # 거품 그림에 미리 섞어 두는 물빛 높이 띠 수. 띠 안의 물빛 차이는 알파 1/255 안팎
RAY_COUNT, RAY_REACH = 5, 0.45  # 빛줄기 수 · 화면 위에서 닿는 깊이(높이 비율). 행마다 한 번 찍어서 위쪽에만
RAY_WIDTHS = (36, 64)  # 빛줄기 위쪽 폭 px. 내려가며 두 배로 퍼짐
RAY_SLANT, RAY_SWAY = 0.22, 0.05  # 기울기 (가로 / 세로) · 흔들리는 폭 — 위 끝을 축으로 아래가 좌우로 흔들림
RAY_COLOR, RAY_ALPHA = (226, 246, 255), 0.16
RAY_LEVELS = (1.0, 0.75, 0.5)  # 밝기 단계. 천천히 오감
# 거품 층: 눈 층(SNOW_LAYERS)과 같은 꼴 — (비율, 반지름들, 오르는 빠르기 px/초, 알파, 안 씀, 흔들림 px, 안 씀, 안 씀)
BUBBLE_LAYERS = ((0.6, (1.2, 1.7), (24, 42), 150, 0, 3, 0, False),
                 (0.4, (2.3, 3.2), (42, 74), 205, 0, 6, 0, False))
BUBBLE_SHARE = 0.2  # 양 → 거품 수 ('보통' 30개)
BUBBLE_COLOR = (236, 250, 255)
SAND_H = (3, 7)    # 모래 두께 px
SAND_COLORS = ((238, 222, 176), (224, 204, 150), (210, 188, 134), (232, 214, 164), (196, 172, 120))
WEED_EVERY, WEED_H, WEED_SWAY = 160, (24, 64), 7  # 해초 사이 평균 px · 키 px · 꼭대기가 흔들리는 px
WEED_COLORS = ((34, 112, 64), (52, 146, 78), (92, 190, 98))  # 아래 → 위
FISH_N, FISH_SPEED, FISH_TURN = 6, (22, 58), 0.04  # 물고기 수 · px/초 · 1초에 돌아설 확률
FISH_COLORS = {"k": (38, 43, 68), "e": (24, 20, 37), "w": (255, 255, 255), "o": (247, 118, 34),
               "b": (52, 110, 230), "n": (24, 40, 110), "y": (250, 214, 60),
               "c": (64, 224, 255), "s": (206, 214, 230), "r": (232, 58, 70)}
# 물고기: (오른쪽을 보는 그림, 꼬리를 친 그림의 각 행 앞부분). 흰동가리 · 블루탱 · 네온테트라
FISH_ART = ((("......kkkk...",
              "k..kkowwokk..",
              "kk.koowwowwek",
              "kokoowwoowwok",
              "kk.koowwowwok",
              "k..kkowwokk..",
              "......kkkk..."), ("", "...", "k..", "kok", "k..", "...", "")),
            (("....kkkkk....",
              "y.kkbbbbbkk..",
              "yykbbnnnbbek.",
              "yykbbbbnnnbbk",
              "yykbnnnbbbbk.",
              "y.kkbbbbbkk..",
              "....kkkkk...."), ("", "..", "y.", "yy", "y.", "..", "")),
            (("...kkkkk..",
              "k.kcccccek",
              "kkksssssk.",
              "k.krrrrrk.",
              "...kkkkk.."), ("", "..", "kk", "..", "")))

KINDS = {1: ("snow", "눈"), 2: ("rain", "비"), 3: ("storm", "뇌우"), 4: ("hail", "우박"), 6: ("fireflies", "반딧불이"),
         5: ("fireworks", "불꽃놀이"), 8: ("aquarium", "어항"), 7: ("none", "날씨 없음")}  # 없음은 동물만. id 는 설정 파일과 무관해 순서만 바꿔도 됨
KIND_NAMES = tuple(k for k, _ in KINDS.values())
SHOW, PANEL, AUTOSTART, EXIT = 20, 30, 50, 99
PETS = {22: "cat", 23: "bird", 24: "dog", 25: "rabbit", 26: "penguin"}  # 메뉴 id → 설정 파일 pet 목록의 이름
PET_NAMES = {"cat": "고양이", "bird": "새", "dog": "강아지", "rabbit": "토끼", "penguin": "펭귄"}
PET_CLASS = {"cat": pet.Cat, "bird": pet.Bird, "dog": pet.Dog, "rabbit": pet.Rabbit, "penguin": pet.Penguin}
RUN_NAME = "PlayroomWeather"  # 시작할 때는 인자 없이 떠서 저장된 종류·양을 따름
AMOUNTS = {10 + i: p for i, p in enumerate(range(10, 101, 10))}  # 메뉴 id → %. 트레이 메뉴엔 막대를 못 넣어 칸으로
FULL = 300       # 양 100% 의 눈송이·빗방울 수 (꽃잎·반딧불이는 이 수에 종류별 비율을 곱함)
OLD_AMOUNTS = {"few": 20, "normal": 50, "many": 100}  # 예전 세 단계. 설정 파일·--amount 에서 아직 읽음


def count(amount):
    return round(FULL * amount / 100)


def parse_amount(a):
    """0–100 정수, 또는 예전 이름. 아니면 None."""
    a = OLD_AMOUNTS.get(a) if isinstance(a, str) else a
    return a if type(a) is int and 0 <= a <= 100 else None


def amount_arg(s):
    a = parse_amount(int(s) if s.isdigit() else s)
    if a is None:
        raise argparse.ArgumentTypeError("0–100 이나 few·normal·many")
    return a

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


def streak(length, alpha, width, slant=SLANT, color=RAIN_COLOR):
    """slant 만큼 기운 빗줄기. 셔터가 열린 동안 떨어진 자국처럼 고른 선 — 양끝만 부드럽고 아래가 조금 진함."""
    sw = int(length * slant) + 4
    rows = []
    for j in range(length):
        u = (j + 0.5) / length
        a = alpha * (0.6 + 0.4 * u) * min(1.0, u / 0.3, (1 - u) / 0.12)
        xc = j * slant + 1.5
        row = b"".join(pixel(color, a * min(1.0, max(0.0, width / 2 + 0.5 - abs(x - xc))))
                       for x in range(sw))
        rows.append(trim(row))
    return sw, rows


def crown(k):
    """빗방울이 바닥에 닿는 순간의 ㅅ자 튐, k 번째 단계(0..2). 가지가 자라며 옅어짐. 맨 아래 가운데가 닿은 자리."""
    n, c = 9, 4
    grid = [[0.0] * n for _ in range(n)]
    for i in range(1, k + 3):
        for side in (-1, 1):
            x, y = c + side * i * 0.8, n - 1 - i * 0.9
            for gy in range(max(0, int(y)), min(n, int(y) + 2)):  # 점 하나를 둘레 네 칸에 나눠 칠함
                for gx in range(max(0, int(x)), min(n, int(x) + 2)):
                    grid[gy][gx] = max(grid[gy][gx], (1 - abs(gx - x)) * (1 - abs(gy - y)))
    return n, [trim(b"".join(pixel(RAIN_COLOR, 200 * (1 - k / 3) * v) for v in row)) for row in grid]


def place(sprite, stride):
    """(크기, [(건너뜀, 데이터) 행…]) → (크기, [(시작, 끝, 데이터)…]). 화면 폭이 정해진 뒤 한 번 셈해 두면 stamp 가
    행마다 자리를 다시 셈하지 않음(비 100% 한 프레임 2.4 → 1.7ms). 다 투명한 행은 뺌."""
    n, rows = sprite
    return n, [(j * stride + skip, j * stride + skip + len(d), d) for j, (skip, d) in enumerate(rows) if d]


def stamp(px, stride, x, y, rows):
    """place 로 셈해 둔 행들을 (x, y) 에 찍음."""
    off = y * stride + x * 4
    for a, e, data in rows:
        px[off + a:off + e] = data


def glow(core_r, halo_r, level, fx, fy, core_color=FLY_CORE, halo_color=FLY_HALO):
    """반딧불·불꽃 빛: 또렷한 알갱이에 넓고 옅은 번짐. level 은 0..1 밝기."""
    n = int(math.ceil(2 * halo_r)) + 2
    c = n / 2 - 0.5
    rows = []
    for y in range(n):
        row = b""
        for x in range(n):
            d = math.hypot(x - c - fx, y - c - fy)
            core = min(1.0, max(0.0, core_r + 0.5 - d))
            halo = 0.6 * math.exp(-(d / (halo_r * 0.6)) ** 2)
            color = tuple(int(halo_color[i] + (core_color[i] - halo_color[i]) * core) for i in range(3))
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

    def __init__(self, width, base=None):
        self.h = [0.0] * width
        self.flip = False
        # 열마다 바닥 높이. 흘러내림은 바닥+더미 표면으로 셈 — 틀 위 눈이 모서리에서 옆 틈으로 흘러 옆면에 붙고,
        # 많이 쌓이면 틀까지 언덕으로 이어짐. 틈의 눈은 표면이 틀 윗변을 넘어야 틀 위로 감
        self.base = base or [0] * width

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
        h, n, base = self.h, len(self.h), self.base
        # 안식각: 넘친 높이 차의 반을 낮은 쪽으로(가진 눈만큼만). 한 방향으로만 훑으면 한쪽으로 쏠리므로 번갈아 훑음
        order = range(n - 1) if self.flip else range(n - 2, -1, -1)
        self.flip = not self.flip
        for i in order:
            d = h[i] + base[i] - h[i + 1] - base[i + 1]
            if d > SLOPE:
                m = min((d - SLOPE) / 2, h[i])
                h[i] -= m
                h[i + 1] += m
            elif d < -SLOPE:
                m = min((-d - SLOPE) / 2, h[i + 1])
                h[i] += m
                h[i + 1] -= m
        # 이웃끼리 조금씩 주고받아 표면을 매끈하게. 주고받기라 부피는 그대로. 양옆으로 반씩까지만 내줌.
        # 흐름은 옛 높이로 한꺼번에 셈 — 차례로 고치면 훑는 방향으로 조금씩 쏠림
        s = [a + b for a, b in zip(h, base)]
        flow = [max(-h[i] / 2, min(h[i + 1] / 2, DIFFUSE * (s[i + 1] - s[i]))) for i in range(n - 1)]
        for i, f in enumerate(flow):
            h[i] += f
            h[i + 1] -= f
        if melt:
            k = 1 - melt
            self.h = [v * k if v > 0.01 else 0.0 for v in h]

    def blow(self, f):
        """바람: 겉의 날리는 눈(LOOSE px 까지)의 |f| 만큼을 바람 아래(f 부호 쪽) 옆 열로 옮김. 옆 표면이 LIFT 넘게
        높으면(틀 옆면) 못 넘고 그 앞에 쌓여 언덕이 되고, 언덕이 틀 윗변 가까이 차면 넘어감. 틀 위 눈은 바람 아래
        모서리로 날려 떨어짐. 화면 끝으로 날린 눈은 사라짐. 옮길 양은 옛 높이로 한꺼번에 셈."""
        h, base, n = self.h, self.base, len(self.h)
        s, k = (1 if f > 0 else -1), min(abs(f), 0.9)
        move = [0.0 if 0 <= i + s < n and h[i + s] + base[i + s] > v + b + LIFT else k * min(v, LOOSE)
                for i, (v, b) in enumerate(zip(h, base))]
        for i, m in enumerate(move):
            if m:
                h[i] -= m
                if 0 <= i + s < n:
                    h[i + s] += m


def floor_heights(w, bottom, left, rise, frames):
    """열마다 바닥 높이 px(창 밑변에서 위로). frames: taskbar.frames() 의 [(왼, 위, 오른)] 화면 좌표 — 밑에서
    rise 안(작업 표시줄 띠)에 윗변이 있는 것만 셈. None 이면 모양을 모르니 띠 윗변 전체가 바닥."""
    if frames is None:
        return [rise] * w
    base = [0] * w
    for l, t, r in frames:
        b = bottom - t
        if 0 < b <= rise:
            for x in range(max(0, l - left), min(w, r - left)):
                base[x] = max(base[x], b)
    return base


def pile_column_parts(depth=PILE_STRIP):
    """열 하나를 그릴 조각: 윗면 가장자리(높이의 소수부 16단계 알파)와 위에서 아래로 몸통(depth px)."""
    top, deep = (240, 244, 252), (212, 221, 238)
    edges = [pixel(SNOW_RIM, 255 * q / 16) for q in range(16)]
    body = b"".join(pixel(tuple(int(a + (b - a) * min(1.0, d / 14)) for a, b in zip(top, deep)), 255)
                    for d in range(depth))
    return edges, body


def pile_column(v, edges, body, zero, room=PILE_STRIP):
    """room px 짜리 열: 위는 비우고 높이 v 의 더미. 틀 옆 언덕은 틀 높이까지 자라므로 room 은 그 열 바닥 위 띠 전체."""
    n = min(int(v), room - 1)
    q = int((v - int(v)) * 16)
    return zero[:(room - n - 1) * 4] + edges[q] + body[:n * 4]


# ── 어항 ── 물빛 위에 덮어 찍는 반투명 그림은 물빛을 미리 섞어 둠. 안 섞으면 옅은 가장자리가 물빛에 구멍을 냄
def water_rows(h, amount):
    """행마다 물빛 픽셀 4바이트. 아래로 갈수록 짙고 푸름. 양 50% 에 AQ_ALPHA, 양에 비례."""
    k, rows = amount / 50, []
    for y in range(h):
        u = y / max(1, h - 1)
        rows.append(pixel(tuple(int(t + (d - t) * u) for t, d in zip(AQ_TOP, AQ_DEEP)),
                          255 * k * (AQ_ALPHA[0] + (AQ_ALPHA[1] - AQ_ALPHA[0]) * u)))
    return rows


def over(sprite, under):
    """(크기, [(건너뜀, 데이터) 행…]) 그림을 픽셀 under 위에 섞음 (premultiplied: 위 + 아래 × (1 − 위 알파))."""
    n, rows = sprite
    out = []
    for skip, d in rows:
        b = bytearray(d)
        for i in range(0, len(d), 4):
            k = 255 - d[i + 3]
            for c in range(4):
                b[i + c] = d[i + c] + under[c] * k // 255
        out.append((skip, bytes(b)))
    return n, out


def bubble(r, alpha, fx=0.0, fy=0.0):
    """거품: 거의 투명한 속에 밝은 테두리, 왼쪽 위에 반짝이는 점. fx, fy 는 disc 처럼 픽셀 아래 중심 이동."""
    n = int(math.ceil(2 * r)) + 3
    c = n / 2 - 0.5
    rows = []
    for y in range(n):
        row = b""
        for x in range(n):
            dx, dy = x - c - fx, y - c - fy
            d = math.hypot(dx, dy)
            cov = min(1.0, max(0.0, r + 0.5 - d))
            rim = max(0.0, 1 - abs(d - r + 0.5) / 0.9)
            shine = max(0.0, 1 - math.hypot(dx + r * 0.4, dy + r * 0.4) / max(0.7, r * 0.35))
            row += pixel(BUBBLE_COLOR, alpha * cov * max(0.15, rim, shine))
        rows.append(trim(row))
    return n, rows


def ray_shape(top_w, length):
    """빛줄기 한 줄기: 행마다 (가운데에서 왼쪽 끝까지 px, 알파 바이트). 내려가며 폭은 두 배로 퍼지고 옅어짐,
    가로로는 가운데가 밝은 sin² 꼴. 위 몇 줄은 물 위에서 들어오듯 빠르게 밝아짐."""
    rows = []
    for j in range(length):
        u = j / length
        wj = max(2, int(top_w * (1 + u)))
        a = 255 * RAY_ALPHA * (1 - u) ** 1.6 * min(1.0, (j + 1) / 24)
        rows.append((-(wj // 2), bytes(int(a * math.sin(math.pi * (x + 0.5) / wj) ** 2) for x in range(wj))))
    return rows


def tint_ray(shape, tints, level):
    """ray_shape 의 알파 행들에 RAY_COLOR 를 입혀 행마다 그 행의 물빛 위에 섞음 → [(왼쪽 끝 px, 픽셀 바이트)…].
    픽셀마다 파이썬을 돌면 느려서 bolt_sprite 처럼 채널마다 bytes.translate 표로 함. 물빛이 같은 행끼리 표를 같이 씀."""
    tables, out = {}, []
    for (lead, alphas), under in zip(shape, tints):
        tab = tables.get(under)
        if tab is None:
            a_tab = [int(v * level) for v in range(256)]
            tab = tables[under] = [bytes(min(255, (a * col) // 255 + under[c] * (255 - a) // 255) for a in a_tab)
                                   for c, col in enumerate((*RAY_COLOR[::-1], 255))]
        px = bytearray(len(alphas) * 4)
        px[0::4], px[1::4], px[2::4], px[3::4] = (alphas.translate(t) for t in tab)
        out.append((lead, bytes(px)))
    return out


def sand_columns(n, rng):
    """모래 열 그림 n 벌: 위에서 아래로 SAND_H[1] px. 맨 위는 밝은 알갱이, 그 아래는 알갱이 색이 섞임."""
    return [pixel(SAND_COLORS[0], 255) + b"".join(pixel(rng.choice(SAND_COLORS[1:]), 255) for _ in range(SAND_H[1] - 1))
            for _ in range(n)]


def sand_heights(w, rng):
    """열마다 모래 두께 px. 사인 둘로 완만하게 오르내림."""
    lo, hi = SAND_H
    p = rng.uniform(0, math.tau)
    return [round(lo + (hi - lo) * (0.5 + 0.32 * math.sin(x * 0.021 + p) + 0.18 * math.sin(x * 0.11 + 2 * p)))
            for x in range(w)]


def weed(height, rng):
    """해초 한 포기: 아래에서 위로 행마다 불투명 픽셀 바이트. 폭 2–3px 에 몇 줄마다 잎이 양옆으로 돋음."""
    rows, wide = [], rng.random() < 0.5
    for j in range(height):
        u = j / height
        col = pixel(WEED_COLORS[min(2, int(u * 3))], 255)
        n = (3 if wide and u < 0.7 else 2) if u < 0.9 else 1
        leaf = j % 9 in (4, 5) and u < 0.85
        rows.append(col * (n + leaf * 2))
    return rows


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
    if parse_amount(data.get("amount")) is not None:
        ok["amount"] = parse_amount(data["amount"])
    p = data.get("pet")  # 예전 파일은 true/false, 그다음은 동물 이름 하나("" 는 없음)
    p = ["cat"] if p is True else [] if p is False else [p] if isinstance(p, str) else p
    if isinstance(p, list):
        ok["pet"] = [a for a in PET_CLASS if a in p]  # 모르는 이름·겹친 이름은 버림
    if data.get("fps") in FPS_IDS.values():
        ok["fps"] = data["fps"]
    return ok


class Weather:
    def __init__(self, kind, amount, animals=(), fps=FPS):
        self.kind, self.amount, self.visible, self.fps = kind, amount, True, fps
        # ponytail: 시작할 때의 주 모니터 작업 영역에 고정. 해상도·작업 표시줄이 바뀌면 다시 켜야 함
        l, t, r, b = overlay.work_area()
        spot = None if MAC else taskbar.spot()
        # 작업 표시줄이 바로 아래 있으면 그 밑변까지 덮음 — 바탕이 투명한 작업 표시줄이면 틀(알약) 사이로는
        # 화면 맨 아래까지 떨어지게. 바닥은 열마다 self.base(밑변에서 위로 px), 틀을 읽기 전엔 띠 윗변 전체
        self.rise = spot[2] if spot and spot[1] == b else 0
        # 모니터를 꽉 채우면 윈도우가 전체 화면 앱으로 봐서(QUNS_BUSY) 알림이 막히고 HUD·sysmon 이 숨음 — 위 1px 을 비움
        t += 1 if self.rise and t == 0 else 0
        self.w, self.h, self.left, self.top = r - l, b - t + self.rise, l, t
        self.base, self.next_base = [self.rise] * self.w, None
        self.strip_h = PILE_STRIP + self.rise
        self.surface = Surface(l, t, self.w, self.h, SURFACE_CLASS)
        self.on_top = MAC or overlay.on_top("weather")  # 런처의 '항상 위'. 맥은 런처가 없음
        if not self.on_top:
            self.surface.topmost(False)
        self.stride = self.w * 4
        s = self.stride
        self.snow_sprites = [[[place(disc(rad, layer[4], layer[3], SNOW_COLOR, SNOW_RIM, fx / 4, fy / 4), s)
                               for fy in range(4) for fx in range(4)] for rad in layer[1]]
                             for layer in SNOW_LAYERS]
        self.droplet = place(disc(0.8, 0.8, 190, RAIN_COLOR, RAIN_COLOR), s)
        self.crown = [place(crown(k), s) for k in range(3)]
        self.full_clear, self.blank = True, False  # 다음 프레임은 화면 전체를 지움 · 빈 화면이라 쉬는 중
        self.snow_pile = pile_column_parts(self.strip_h)
        self.pile_zero = bytes(self.strip_h * 4)
        self.sprite_cache = {}  # 비·반딧불 그림은 그 종류를 처음 고를 때 그림
        self.aq_tint = None  # (양, 어항 물빛과 물빛을 섞은 그림들)
        self.pet_sprites = pet.sprites()
        # 이름 → 동물, PET_CLASS 순. 종류를 바꿔도 그대로 — 동물은 날씨와 따로 삶
        self.pets = {a: PET_CLASS[a](self.w) for a in PET_CLASS if a in (animals or ())}
        self.bolt_seen, self.pet_startled = None, {}  # 이름 → 우박에 다시 놀랄 수 있는 시각
        self.bangs = []  # 이번 프레임에 터진 불꽃의 x — 동물들이 돌아봄
        self.commands = queue.Queue()  # 트레이 스레드 → 그리는 스레드
        write_ico(ICON_FILE, ICON, ICON_COLORS)
        self.panel = None  # 왼쪽 클릭으로 띄운 설정 창 프로세스
        # 맥은 메뉴 막대를 누르면 메뉴가 뜨는 게 기본이라 메뉴만
        left = {} if MAC else {"on_left": lambda: self.commands.put(PANEL)}
        self.tray = Tray(TRAY_CLASS, ICON_FILE, "날씨", self.menu, self.commands.put, **left)
        self.last = self.last_settle = self.last_topmost = time.perf_counter()
        self.reset()
        self.surface.show(True)
        if self.rise:
            threading.Thread(target=self.watch_frames, daemon=True).start()

    def watch_frames(self):
        """작업 표시줄 틀을 FRAMES_EVERY 초마다 읽어 그리는 스레드에 넘김 — 앱을 열고 닫으면 단추 묶음 폭이 바뀜."""
        while True:
            self.next_base = floor_heights(self.w, self.top + self.h, self.left, self.rise, taskbar.frames())
            time.sleep(FRAMES_EVERY)

    def set_base(self, base):
        """바닥 모양을 바꿈. 틀이 사라진 열의 눈은 그대로 새 바닥으로 떨어지고(HUD 를 끄거나 앱을 닫으면 위에
        쌓였던 눈이 내려앉아 옆과 섞임), 틀이 새로 솟은 열은 틀이 밀고 올라온 만큼 눈이 묻힘."""
        h = self.pile.h
        for x, (a, b) in enumerate(zip(self.base, base)):
            if b > a:
                h[x] = max(0.0, h[x] - (b - a))
        self.base = self.pile.base = base

    # ── 트레이 ──
    def menu(self):
        return [*((label, cid, key == self.kind) for cid, (key, label) in KINDS.items()),
                None,
                ("양", [("%d%%" % p, cid, p == self.amount) for cid, p in AMOUNTS.items()]),
                ("부드러움", [("%dfps" % n, cid, n == self.fps) for cid, n in FPS_IDS.items()]),
                None,
                ("동물", [(PET_NAMES[a], cid, a in self.pets) for cid, a in PETS.items()]),
                ("보이기", SHOW, self.visible),
                ("로그인 시 실행" if MAC else "Windows 시작 시 실행", AUTOSTART, startup.is_on(RUN_NAME, __file__)),
                None,
                ("끝내기", EXIT, False)]

    def handle(self, cid):
        if isinstance(cid, tuple):  # 설정 창의 양 막대에서 손을 뗀 값
            self.amount = cid[1]
        elif cid == PANEL:
            self.open_panel()
            return
        elif cid in KINDS:
            self.kind = KINDS[cid][0]
        elif cid in AMOUNTS:
            self.amount = AMOUNTS[cid]
        elif cid in FPS_IDS:  # 움직임은 시간으로 셈해 빠르기는 그대로, 다시 깔 필요 없음
            self.fps = FPS_IDS[cid]
            self.save()
            return
        elif cid in PETS:  # 켜고 끄기
            on = set(self.pets) ^ {PETS[cid]}
            self.pets = {k: self.pets.get(k) or PET_CLASS[k](self.w) for k in PET_CLASS if k in on}
            self.full_clear = True  # 끈 동물이 있던 자리까지 지움
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
            SETTINGS.write_text(json.dumps({"kind": self.kind, "amount": self.amount, "pet": list(self.pets),
                                            "fps": self.fps}), encoding="utf-8")
        except OSError:
            pass  # 못 남겨도 지금 화면은 바뀌었으니 넘어감

    def open_panel(self):
        """그리는 루프가 tk 가 아니라서 창은 따로 띄우고, 누른 것을 한 줄씩 받아 메뉴 명령처럼 처리함."""
        if self.panel and self.panel.poll() is None:
            return  # 이미 떠 있음
        state = {"kind": self.kind, "amount": self.amount, "pet": list(self.pets), "show": self.visible,
                 "auto": startup.is_on(RUN_NAME, __file__), "fps": self.fps}
        ctypes.windll.user32.AllowSetForegroundWindow(-1)  # 방금 트레이를 누른 건 이 프로세스라 앞으로 올릴 권한을 넘김
        me = [] if getattr(sys, "frozen", False) else [str(Path(__file__).resolve())]  # 릴리스 exe 는 스크립트 없이 자기 자신
        self.panel = subprocess.Popen([sys.executable, *me, "--panel", json.dumps(state)],
                                      stdout=subprocess.PIPE, text=True, encoding="utf-8")
        threading.Thread(target=self.read_panel, args=(self.panel,), daemon=True).start()

    def read_panel(self, proc):
        for line in proc.stdout:
            word, _, arg = line.partition(" ")
            if word == "amount" and arg.strip().isdigit() and parse_amount(int(arg)) is not None:
                self.commands.put(("amount", int(arg)))
            elif word.strip().isdigit() and int(word) in (*KINDS, *FPS_IDS, *PETS, SHOW, AUTOSTART, EXIT):
                self.commands.put(int(word))

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
    def new_flake(self, li, top, layers=SNOW_LAYERS):
        layer = layers[li]
        y = -random.uniform(10, 60) if top else random.uniform(0, self.h)
        # [x, y, 속도, 층, 반지름 번호, 흔들림 위상, 흔들림 빠르기]
        return [random.uniform(0, self.w), y, random.uniform(*layer[2]), li, random.randrange(len(layer[1])),
                random.uniform(0, 6.3), random.uniform(0.6, 1.4)]

    @staticmethod
    def wind(now):
        """천천히 바뀌는 바람 px/초. 사인 몇 개를 겹쳐 돌풍처럼."""
        return 14 * math.sin(now * 0.13) + 9 * math.sin(now * 0.051 + 1.3) + 6 * math.sin(now * 0.37 + 4.0)

    def snow(self, dt, now):
        px, stride, w, h, ph, base = self.surface.pixels, self.stride, self.w, self.h, self.pile.h, self.base
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
            if yi + n >= h - base[col] - ph[col]:  # 쌓인 눈이나 바닥에 닿음. 먼 층은 쌓이지 않고 그 뒤로 사라짐
                if layer[7]:
                    self.pile.add(col, layer[1][f[4]])
                f[:] = self.new_flake(f[3], True)
                continue
            if yi < 0 or xi < 0 or xi + n > w:
                continue
            stamp(px, stride, xi, yi, sprites[int((f[1] - yi) * 4) * 4 + int((x - xi) * 4)][1])

    def render_pile(self):
        strip32 = self.strip.cast("I")
        w, last, body, zero, sh = self.w, self.pile_last, self.pile_body, self.pile_zero, self.strip_h
        for x, (v, b) in enumerate(zip(self.pile.h, self.base)):
            key = int(v * 16) | b << 16
            if key != last[x]:  # 1/16 px 아래로 안 바뀐 열은 건너뜀
                last[x] = key  # 띠는 위에서부터 빈 칸 · 더미 · 틀 높이만큼 빈 칸
                strip32[x::w] = memoryview(pile_column(v, self.pile_edges, body, zero, sh - b)
                                           + zero[:b * 4]).cast("I")

    # ── 반딧불이 ──
    def fly_sprites(self):
        """[크기][밝기 단계 1..8][1/4 픽셀 위치 16벌]."""
        if "fireflies" not in self.sprite_cache:
            self.sprite_cache["fireflies"] = [
                [[place(glow(core, halo, lv / FLY_LEVELS, fx / 4, fy / 4), self.stride)
                  for fy in range(4) for fx in range(4)]
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
            self.bolt = (now, bx, by, [place((0, lv), self.stride)[1] for lv in levels])
            lo, hi = BOLT_EVERY
            k = 50 / max(1, self.amount)  # 50% 일 때 BOLT_EVERY 그대로, 양이 많을수록 잦음
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
    def rain_set(self):
        """[번쩍임 0/1][기울기][층] → {길이: 그림}. 비·뇌우를 처음 고를 때 그림."""
        if "rain" not in self.sprite_cache:
            self.sprite_cache["rain"] = [[[{n: place(streak(n, layer[3] * k, layer[4], s, color), self.stride)
                                            for n in range(layer[1][0], layer[1][1] + 1)} for layer in RAIN_LAYERS]
                                          for s in SLANTS] for k, color in ((1, RAIN_COLOR), (RAIN_LIT, RAIN_LIT_COLOR))]
        return self.sprite_cache["rain"]

    def gust(self, now):
        """지금 빗줄기 기울기. 주기가 다른 사인 둘을 섞어 몇 초 단위로 세졌다 잦아듦."""
        base, amp = GUST[self.kind]
        g = 0.6 * math.sin(now * 0.37 + self.gust_phase) + 0.4 * math.sin(now * 0.91 + 2 * self.gust_phase)
        return min(SLANTS[-1], max(0.0, base + amp * g))

    def new_drop(self, li, top):
        layer = RAIN_LAYERS[li]
        n = random.randint(*layer[1])
        y = -n - random.uniform(0, self.h * 0.4) if top else random.uniform(0, self.h)
        # [x, y, 속도, 층, 길이, 보이는 밀도 문턱]
        return [random.uniform(-self.h * SLANTS[-1], self.w), y, random.uniform(*layer[2]), li, n, random.random()]

    def rain(self, dt, now):
        px, stride, w, h = self.surface.pixels, self.stride, self.w, self.h
        slant = self.gust(now)
        lit = 0
        if self.bolt is not None:  # 번개가 제일 밝은 동안은 빗줄기도 번쩍 드러남
            t = now - self.bolt[0]
            lit = int(any(s <= t < e and lv == 0 for s, e, lv in BOLT_FLICKER))
        sprites = self.rain_sprites[lit][round(slant / SLANTS[1])]
        # 뇌우는 빗발이 물결처럼 굵어졌다 가늘어짐 — 문턱보다 큰 빗방울은 떨어지기만 하고 안 그림
        dens = 1.0 if self.kind == "rain" else 0.7 + 0.3 * math.sin(now * 0.5 + self.gust_phase)
        base = self.base
        for d in self.drops:
            d[1] += d[2] * dt
            d[0] += d[2] * slant * dt
            x = d[0] + d[4] * slant  # 빗줄기 아래 끝
            if d[1] + d[4] >= h - base[min(max(int(x), 0), w - 1)]:
                if d[5] < dens:
                    self.splash(x, d[3])
                d[:] = self.new_drop(d[3], True)
                continue
            if d[5] >= dens:
                continue
            sw, rows = sprites[d[3]][d[4]]
            xi, yi = int(d[0]), int(d[1])
            if yi >= 0 and 0 <= xi and xi + sw <= w:
                stamp(px, stride, xi, yi, rows)
        self.splatter(dt)

    def splatter(self, dt):
        """튄 물방울과 ㅅ자 튐을 움직이고 찍음."""
        px, stride, w, h = self.surface.pixels, self.stride, self.w, self.h
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
        live = []
        for c in self.crowns:  # [닿은 x, 남은 초, 바닥 y]
            c[1] -= dt
            n, rows = self.crown[min(2, int((1 - c[1] / CROWN_SEC) * 3))]
            xi = int(c[0]) - n // 2
            if c[1] > 0 and 0 <= xi <= w - n:
                stamp(px, stride, xi, c[2] - n, rows)
                live.append(c)
        self.crowns = live

    def splash(self, x, li):
        if not li:
            return  # 멀리 것은 안 튐
        floor = self.h - self.base[min(max(int(x), 0), self.w - 1)]
        self.crowns.append([x, CROWN_SEC, floor])
        for _ in range(random.randint(1, 3) if li == 2 else random.randint(0, 1)):  # 가까운 빗줄기가 더 튐
            # 물방울 그림 밑변이 바닥에 닿는 자리에서 출발. 더 아래서 뜨면 첫 프레임에 그 차이만큼 못 오른 것은
            # 화면 밖으로 보고 지워서 180fps(한 프레임 0.5–1.2px)에서는 하나도 안 보였음
            self.splashes.append([x, floor - self.droplet[0], random.uniform(-90, 90), random.uniform(-220, -90),
                                  random.uniform(0.25, 0.45)])

    # ── 우박 ──
    def new_stone(self, top):
        big = random.random() < 0.35
        v = random.uniform(*HAIL_SPEED) * (1.1 if big else 1)
        # [x, y, vx, vy, 끝 빠르기, 크기, 튄 횟수]
        return [random.uniform(0, self.w), -random.uniform(5, self.h * 0.5) if top else random.uniform(0, self.h),
                random.uniform(-15, 15), v, v, int(big), 0]

    def hail(self, dt, now):
        px, stride, w, h, ph, base = self.surface.pixels, self.stride, self.w, self.h, self.pile.h, self.base
        for s in self.stones:
            s[3] = min(s[3] + 2200 * dt, s[4])
            s[0] += s[2] * dt
            s[1] += s[3] * dt
            n, rows = self.hail_sprites[s[5]]
            col = min(max(int(s[0]) + n // 2, 0), w - 1)
            floor = h - base[col] - ph[col] - n
            if s[1] >= floor and s[3] > 0:  # 바닥이나 더미에 닿음
                if s[6] == 0:
                    self.scare_pet(col, now)
                if s[6] < HAIL_BOUNCES and s[3] > 150:
                    s[1], s[3] = floor, -s[3] * random.uniform(0.18, 0.3)
                    s[2] += random.uniform(-70, 70)
                    s[6] += 1
                else:
                    self.pile.add(col, HAIL_SIZES[s[5]][0])
                    s[:] = self.new_stone(True)
                    continue
            xi, yi = int(s[0]), int(s[1])
            if 0 <= yi and 0 <= xi <= w - n:
                stamp(px, stride, xi, yi, rows)

    def scare_pet(self, col, now):
        reach, chance, cool = HAIL_SCARE
        for name, p in self.pets.items():
            if now >= self.pet_startled.get(name, 0):
                a, b = p.feet()
                if a - reach <= col < b + reach and random.random() < chance:
                    p.startle(now)
                    self.pet_startled[name] = now + cool

    # ── 불꽃놀이 ──
    def fw_sprites(self):
        """[색][밝기 단계 1..6]."""
        if "fireworks" not in self.sprite_cache:
            self.sprite_cache["fireworks"] = [[place(glow(1.1, 3.6, lv / FW_LEVELS, 0, 0, core, halo), self.stride)
                                               for lv in range(1, FW_LEVELS + 1)] for core, halo in FW_COLORS]
        return self.sprite_cache["fireworks"]

    def launch(self, now):
        rate = FW_RATE * self.amount / 100
        if rate <= 0:
            self.next_launch = math.inf
            return
        if not self.next_launch < math.inf or now - self.next_launch > 2:  # 양을 올렸거나 숨겼다 돌아옴 — 몰아 쏘지 않게
            self.next_launch = now + random.uniform(0, 1 / rate)
        while now >= self.next_launch:
            top = random.uniform(*FW_BURST_AT) * self.h
            vy = -math.sqrt(2 * 260 * (self.h - top) + 90 ** 2)  # 터지는 높이에서도 아직 오르는 중이게
            self.rockets.append([random.uniform(0.1, 0.9) * self.w, float(self.h), random.uniform(-25, 25), vy, top])
            self.next_launch += random.expovariate(rate)

    def burst(self, x, y):
        if self.pets:  # 동물이 없으면 react 가 안 돌아서 비우는 쪽이 없음
            self.bangs.append(x)
        a, b = random.sample(range(len(FW_COLORS)), 2)
        mixed = random.random() < 0.3
        v0 = random.uniform(150, 250)
        for i in range(random.randint(*FW_SPARKS)):
            ang, v = random.uniform(0, math.tau), v0 * random.uniform(0.78, 1.0)
            # [x, y, vx, vy, 나이, 수명, 색]
            self.sparks.append([x, y, math.cos(ang) * v, math.sin(ang) * v, 0.0, random.uniform(*FW_LIFE),
                                b if mixed and i % 2 else a])

    def fireworks(self, dt, now):
        px, stride, w, h, sprites = self.surface.pixels, self.stride, self.w, self.h, self.fw
        self.launch(now)
        gold = sprites[FW_GOLD]
        n = gold[0][0]
        live = []
        for r in self.rockets:  # [x, y, vx, vy, 터질 높이]
            r[3] += 260 * dt
            r[0] += r[2] * dt
            r[1] += r[3] * dt
            if r[1] <= r[4]:
                self.burst(r[0], r[1])
                continue
            live.append(r)
            for k in range(6):  # 머리가 제일 밝고 아래로 꼬리
                xi, yi = int(r[0] - r[2] * k * 0.012) - n // 2, int(r[1] + k * 5) - n // 2
                if 0 <= xi <= w - n and 0 <= yi <= h - n:
                    stamp(px, stride, xi, yi, gold[max(0, FW_LEVELS - 1 - k)][1])
        self.rockets = live
        drag = math.exp(-1.7 * dt)
        live = []
        for s in self.sparks:
            s[4] += dt
            if s[4] >= s[5]:
                continue
            live.append(s)
            s[2] *= drag
            s[3] = s[3] * drag + 95 * dt
            s[0] += s[2] * dt
            s[1] += s[3] * dt
            k = s[4] / s[5]
            if k > 0.7 and random.random() < 0.45:  # 사그라들며 반짝임
                continue
            lv = FW_LEVELS if k < 0.5 else max(1, round(FW_LEVELS * (1 - k) / 0.5))
            n, rows = sprites[s[6]][lv - 1]
            xi, yi = int(s[0]) - n // 2, int(s[1]) - n // 2
            if 0 <= xi <= w - n and 0 <= yi <= h - n:
                stamp(px, stride, xi, yi, rows)
        self.sparks = live

    # ── 어항 ──
    def aquarium(self):
        """어항을 깜. 그림과 모래·해초 자리는 처음 고를 때 한 번(sprite_cache), 물빛을 섞은 것은 양이 바뀔 때만
        다시, 물고기·거품·빛줄기 자리는 고를 때마다 새로."""
        w, h, s = self.w, self.h, self.stride
        if "aquarium" not in self.sprite_cache:
            rng, spots = random.Random(), []
            x = rng.uniform(10, WEED_EVERY)
            while x < w - 10:
                spots.append(int(x))
                x += rng.uniform(0.4, 1.6) * WEED_EVERY
            frames = [(rows, tuple(a + r[len(a):] for r, a in zip(rows, alt))) for rows, alt in FISH_ART]
            self.sprite_cache["aquarium"] = {
                "bubbles": [[[bubble(r, layer[3], fx / 4, fy / 4) for fy in range(4) for fx in range(4)]
                             for r in layer[1]] for layer in BUBBLE_LAYERS],
                "rays": [ray_shape(tw, int(h * RAY_REACH)) for tw in RAY_WIDTHS],
                "fish": [[{right: pet.segments(rows, not right, FISH_COLORS) for right in (True, False)} for rows in pair]
                         for pair in frames],
                "fish_size": [(len(rows[0]) * pet.SCALE, len(rows) * pet.SCALE) for rows, _ in FISH_ART],
                "sand": sand_columns(16, rng), "sand_h": sand_heights(w, rng), "sand_pick": [rng.randrange(16) for _ in range(w)],
                "weeds": [(x, weed(rng.randint(*WEED_H), rng), rng.uniform(0, math.tau), rng.uniform(0.6, 1.3))
                          for x in spots]}
        aq = self.aq = self.sprite_cache["aquarium"]
        if self.aq_tint is None or self.aq_tint[0] != self.amount:  # 화면 크기 버퍼 하나라 지난 양 것은 안 남김
            rows = water_rows(h, self.amount)
            bands = [rows[int((b + 0.5) * h / AQ_BANDS)] for b in range(AQ_BANDS)]
            self.aq_tint = (self.amount, {
                "water": b"".join(p * w for p in rows), "strip": b"".join(rows[h - self.strip_h:]),
                "bubbles": [[[[place(over(sp, under), s) for sp in subs] for subs in radii] for radii in aq["bubbles"]]
                            for under in bands],
                "rays": [[tint_ray(shape, rows, lv) for lv in RAY_LEVELS] for shape in aq["rays"]]})
        t = self.aq_tint[1]
        self.water, self.bubble_sprites, self.ray_rows = t["water"], t["bubbles"], t["rays"]
        self.sand = aq["sand_h"]
        self.pile.h = list(self.sand)  # 모래는 안 녹는 더미 — 동물이 그 위를 걷고 거품이 거기서 나옴
        self.sand_base = None  # 다음 프레임에 모래 띠를 그림
        self.vents = [x for x, *_ in random.sample(aq["weeds"], min(3, len(aq["weeds"])))]  # 거품 줄기가 나오는 해초 밑
        n = count(self.amount)
        self.flakes = [self.new_bubble(li, False) for li, layer in enumerate(BUBBLE_LAYERS)
                       for _ in range(round(n * BUBBLE_SHARE * layer[0]))]
        reach = int(h * RAY_REACH)
        lo, hi = RAY_WIDTHS[-1], w - RAY_WIDTHS[-1] - (RAY_SLANT + RAY_SWAY) * reach  # 퍼진 아래 끝까지 화면 안
        # [위 끝 가운데 x, 모양, 위상, 빠르기]
        self.rays_at = [] if hi <= lo else [[lo + (i + random.uniform(0.15, 0.85)) * (hi - lo) / RAY_COUNT,
                                             random.randrange(len(RAY_WIDTHS)), random.uniform(0, math.tau),
                                             random.uniform(0.08, 0.16)] for i in range(RAY_COUNT)]
        self.fish = [self.new_fish() for _ in range(FISH_N)]

    def rays(self, now):
        """빛줄기: 위 끝을 축으로 아래가 천천히 좌우로 흔들리고 밝기가 오감. 행마다 그 행 물빛이 섞인 조각을 덮어씀."""
        px, stride = self.surface.pixels, self.stride
        for x0, shape, ph, sp in self.rays_at:
            slant = RAY_SLANT + RAY_SWAY * math.sin(now * sp * 3 + ph)
            lv = int((0.5 + 0.5 * math.sin(now * sp * 2 + 2 * ph)) * (len(RAY_LEVELS) - 0.001))
            o = 0
            for j, (lead, data) in enumerate(self.ray_rows[shape][lv]):
                a = o + (int(x0 + j * slant) + lead) * 4
                px[a:a + len(data)] = data
                o += stride

    def render_sand(self):
        """모래 띠: 띠 높이의 물빛 위에, 열마다 그 열 바닥(틀 윗변) 바로 위로 모래. 틀 모양이 바뀔 때만 다시 그림."""
        strip32 = self.strip.cast("I")
        w, sh, tint, cols, pick = self.w, self.strip_h, self.aq_tint[1]["strip"], self.aq["sand"], self.aq["sand_pick"]
        for x, (v, b) in enumerate(zip(self.sand, self.base)):
            strip32[x::w] = memoryview(tint[:(sh - b - v) * 4] + cols[pick[x]][:v * 4] + tint[(sh - b) * 4:]).cast("I")
        self.sand_base = self.base

    def weeds(self, now):
        """해초: 뿌리는 그 열의 바닥(틀 윗변) + 모래 위. 위로 갈수록 크게, 물결처럼 조금씩 늦게 흔들림."""
        px, stride, h, base, ph = self.surface.pixels, self.stride, self.h, self.base, self.pile.h
        for x, rows, phase, speed in self.aq["weeds"]:
            y, n = h - base[x] - int(ph[x]), len(rows)
            for j, data in enumerate(rows):
                u = j / n
                xx = x + int(WEED_SWAY * u * u * math.sin(now * speed + phase - u * 2.4)) - len(data) // 8
                y -= 1
                if 0 <= xx and xx * 4 + len(data) <= stride and y >= 0:
                    o = y * stride + xx * 4
                    px[o:o + len(data)] = data

    def new_bubble(self, li, bottom):
        """눈송이(new_flake)와 같은 꼴. bottom 이면 바닥(모래 위)에서 — 반은 해초 밑 숨구멍 줄기에서 — 아니면 아무 높이."""
        f = self.new_flake(li, False, BUBBLE_LAYERS)
        if bottom:
            if self.vents and random.random() < 0.5:
                f[0] = random.choice(self.vents) + random.uniform(-2, 2)
            col = min(max(int(f[0]), 0), self.w - 1)
            n = int(math.ceil(2 * BUBBLE_LAYERS[li][1][f[4]])) + 3  # bubble() 그림 크기
            f[1] = self.h - self.base[col] - self.pile.h[col] - n - random.uniform(0, 4)
        return f

    def bubbles(self, dt, now):
        """거품: 눈송이(snow)를 거꾸로 — 같은 꼴로 흔들리며 오르다 수면(화면 위)을 넘으면 바닥에서 다시 나옴."""
        px, stride, w, h = self.surface.pixels, self.stride, self.w, self.h
        for f in self.flakes:
            layer = BUBBLE_LAYERS[f[3]]
            f[1] -= f[2] * dt
            sprites = self.bubble_sprites[min(AQ_BANDS - 1, max(0, int(f[1] * AQ_BANDS / h)))][f[3]][f[4]]
            n = sprites[0][0]
            if f[1] + n < 0:
                f[:] = self.new_bubble(f[3], True)
                continue
            x = f[0] + math.sin(f[5] + now * f[6] * 2) * layer[5]
            xi, yi = int(x), int(f[1])
            if yi < 0 or xi < 0 or xi + n > w or yi + n > h:
                continue
            stamp(px, stride, xi, yi, sprites[int((f[1] - yi) * 4) * 4 + int((x - xi) * 4)][1])

    def fish_band(self, fh):
        """키 fh 인 물고기가 오가는 높이 (위, 아래) — 위 12% 아래부터 모래·작업 표시줄 위까지."""
        lo = self.h * 0.12
        return lo, max(lo, self.h - self.rise - SAND_H[1] - fh - 20)

    def new_fish(self):
        sp = random.randrange(len(FISH_ART))
        fw, fh = self.aq["fish_size"][sp]
        lo, hi = self.fish_band(fh)
        # [x, y, 오른쪽이면 1 왼쪽이면 -1, 빠르기, 종류, 위상, 가려는 높이]
        return [random.uniform(0, max(0, self.w - fw)), random.uniform(lo, hi), random.choice((1, -1)),
                random.uniform(*FISH_SPEED), sp, random.uniform(0, math.tau), random.uniform(lo, hi)]

    def fishes(self, dt, now):
        """물고기: 좌우로 헤엄치다 화면 끝이나 가끔 돌아서고, 돌아설 때 고른 새 높이로 천천히 옮겨 감."""
        px, stride, w, h = self.surface.pixels, self.stride, self.w, self.h
        for f in self.fish:
            fw, fh = self.aq["fish_size"][f[4]]
            f[0] += f[2] * f[3] * dt
            if f[0] <= 0 or f[0] >= w - fw or random.random() < FISH_TURN * dt:
                f[2] = 1 if f[0] <= 0 else -1 if f[0] >= w - fw else -f[2]
                f[0] = min(max(f[0], 0), max(0, w - fw))
                f[6] = random.uniform(*self.fish_band(fh))
            f[1] += max(-12 * dt, min(12 * dt, f[6] - f[1]))
            y = min(max(int(f[1] + 4 * math.sin(now * 1.7 + f[5])), 0), h - fh)
            frame = int(now * (2 + f[3] / 15) + f[5]) % 2  # 빠른 물고기가 꼬리를 자주 침
            pet.stamp(px, stride, int(f[0]), y, self.aq["fish"][f[4]][frame][f[2] > 0], w, h)

    # ── 돌리기 ──
    def reset(self):
        n, kind = count(self.amount), self.kind
        self.full_clear = True
        self.flakes, self.drops, self.splashes, self.flies = [], [], [], []
        self.crowns, self.gust_phase = [], random.uniform(0, math.tau)
        self.bolt, self.next_bolt = None, time.perf_counter() + random.uniform(2, 5)
        self.pile = Pile(self.w, self.base)
        self.strip = memoryview(bytearray(self.stride * self.strip_h))
        self.pile_last = [-1] * self.w  # 처음엔 모든 열을 그림 — 빈 열이어도 틀 높이가 들어감
        self.pile_edges, self.pile_body = self.snow_pile
        if kind == "snow":
            self.flakes = [self.new_flake(li, False) for li, layer in enumerate(SNOW_LAYERS)
                           for _ in range(round(n * layer[0]))]
        elif kind in ("rain", "storm"):
            mult = RAIN_MULT * (STORM_MULT if kind == "storm" else 1)
            self.rain_sprites = self.rain_set()
            self.drops = [self.new_drop(li, False) for li, layer in enumerate(RAIN_LAYERS)
                          for _ in range(round(n * mult * layer[0]))]
        elif kind == "fireflies":
            self.flies_sprites = self.fly_sprites()
            self.flies = [self.new_fly() for _ in range(round(n * FLY_SHARE))]
        elif kind == "hail":
            if "hail" not in self.sprite_cache:
                self.sprite_cache["hail"] = [place(disc(r, soft, a, HAIL_COLOR, HAIL_RIM), self.stride)
                                             for r, soft, a in HAIL_SIZES]
            self.hail_sprites = self.sprite_cache["hail"]
            self.stones = [self.new_stone(False) for _ in range(round(n * HAIL_SHARE))]
        elif kind == "fireworks":
            self.fw = self.fw_sprites()
        elif kind == "aquarium":
            self.aquarium()
        self.rockets, self.sparks, self.next_launch = [], [], math.inf

    # ── 동물 ──
    def react(self, now):
        """날씨에서 일어난 일을 동물들에게 알림 — 번개, 가까이 터진 불꽃, 낮게 나는 반딧불이."""
        bolt = self.bolt and self.bolt[0] != self.bolt_seen
        if bolt:
            self.bolt_seen = self.bolt[0]
        base, w = self.base, self.w  # 높이는 그 자리 바닥에서 셈. 거르는 건 동물이
        low = [(f[0], self.h - f[1] - base[min(int(f[0]), w - 1)]) for f in self.flies] if self.kind == "fireflies" else []
        for p in self.pets.values():
            p.kind, p.snowy = self.kind, self.kind in ("snow", "hail")
            if bolt:
                p.startle(now)
            for x in self.bangs:
                if abs(x - p.x) < BANG_NEAR:
                    p.watch(now, x)
            if low:
                p.chase(now, low)
        self.bangs = []

    def walk_pet(self, dt, now):
        rainy = self.kind in ("rain", "storm")
        self.react(now)
        for p in self.pets.values():
            p.update(dt, now, rainy)
            a, b = p.feet()
            g = p.follow(max(v + f for v, f in zip(self.pile.h[a:b], self.base[a:b])), dt, now)  # 틀 단은 뛰어 오르내림
            p.draw(self.surface.pixels, self.stride, self.h, self.pet_sprites, g, now, rainy)

    def frame(self, dt, now):
        kind = self.kind
        # 날씨 없이 고양이만이면 고양이가 닿는 맨 아래 띠만 지우고 그만큼만 내보냄(180fps 에서 한 코어 43% → 아래 참고).
        # 종류를 바꾼 첫 프레임은 위에 남은 것까지 통째로. 맥 Surface 는 버퍼 둘을 번갈아 써서 늘 통째로
        nb = self.next_base
        if nb is not None:
            self.next_base = None
            if nb != self.base:
                self.set_base(nb)
                self.full_clear = True  # 동물이 있던 띠 위쪽까지 한 번 지움
        top = 0 if MAC or self.full_clear or kind != "none" else self.h - pet.BAND - self.rise
        self.full_clear = False
        if kind == "aquarium":  # 지우는 대신 미리 칠한 물빛으로 덮음 (2560×1440 memset 0.89 · memmove 1.15ms)
            self.surface.fill(self.water)
        elif top:
            self.surface.clear(top)
        else:
            self.surface.clear()
        piled = kind in ("snow", "hail")
        if piled:
            if now - self.last_settle >= SETTLE_SEC:
                melt, el = MELT_PER_SEC * (HAIL_MELT if kind == "hail" else 1), now - self.last_settle
                self.pile.settle(melt * el)
                if kind == "snow":  # 우박 알은 무거워 안 날림
                    self.pile.blow(DRIFT * self.wind(now) * el)
                self.last_settle = now
                self.render_pile()
            self.surface.pixels[(self.h - self.strip_h) * self.stride:] = self.strip
        elif kind == "aquarium":
            if self.sand_base is not self.base:  # 처음이거나 틀이 바뀜
                self.pile.h = list(self.sand)  # set_base 가 솟은 틀만큼 묻은 모래를 되살림
                self.render_sand()
            self.rays(now)
            self.surface.pixels[(self.h - self.strip_h) * self.stride:] = self.strip
            self.weeds(now)
        if self.pets:  # 더미 위, 내리는 것 아래
            self.walk_pet(dt, now)
        if kind == "snow":
            self.snow(dt, now)
        elif kind == "hail":
            self.hail(dt, now)
        elif kind == "fireworks":
            self.fireworks(dt, now)
        elif kind == "fireflies":
            self.fireflies(dt, now)
        elif kind == "aquarium":
            self.bubbles(dt, now)
            self.fishes(dt, now)
        elif kind in ("rain", "storm"):
            self.rain(dt, now)
            if kind == "storm":
                self.lightning(now)
        self.surface.present(top) if top else self.surface.present()
        if self.on_top and now - self.last_topmost > 2:
            self.surface.topmost()
            self.last_topmost = now

    def step(self):
        """한 프레임 진행. 숨겨져 있으면 안 그리고 False."""
        now = time.perf_counter()
        dt = min(now - self.last, 0.1)  # 멈췄다 돌아와도 한 번에 순간 이동하지 않게
        self.last = now
        if not self.visible:
            return False
        if self.kind == "none" and not self.pets:  # 그릴 게 없으면 한 번 지우고 숨겼을 때처럼 쉼(180fps 에서 29% 를 쓰던 자리)
            if not self.blank:
                self.surface.clear()
                self.surface.present()
                self.blank = True
            return False
        self.blank = False
        self.frame(dt, now)
        return True

    def run(self):
        if MAC:  # 메뉴 막대 메뉴를 연 동안엔 아래 루프가 pump 에 묶이므로 런 루프 타이머가 대신 그림
            from cocoa import while_tracking
            while_tracking(self.step, 1 / self.fps)  # ponytail: 시작할 때 값에 고정. 메뉴를 연 동안만 쓰임
        nxt = time.perf_counter()
        while True:
            period = 1 / self.fps  # 메뉴에서 바꾸면 다음 프레임부터
            self.surface.pump()
            if self.poll():
                break
            if not self.step():
                time.sleep(0.2)
                nxt = time.perf_counter()
                continue
            nxt += period
            delay = nxt - time.perf_counter()
            if delay < -period:  # 많이 밀렸으면 따라잡으려 몰아 그리지 말고 다시 맞춤
                nxt, delay = time.perf_counter(), 0
            time.sleep(max(0.0, delay))
        self.surface.close()


def check():
    fake = types.SimpleNamespace(surface=types.SimpleNamespace(pixels=bytearray(40 * 40 * 4)), stride=40 * 4, w=40, h=40,
                                 base=[0] * 40, splashes=[], crowns=[],
                                 droplet=place(disc(0.8, 0.8, 190, RAIN_COLOR, RAIN_COLOR), 40 * 4),
                                 crown=[place(crown(k), 40 * 4) for k in range(3)])
    for fps in (30, 60, 180):
        fake.splashes, fake.crowns = [], []
        for _ in range(20):
            Weather.splash(fake, 20, 2)
        n = len(fake.splashes)
        Weather.splatter(fake, 1 / fps)
        assert len(fake.splashes) == n > 0, "튄 물방울이 첫 프레임에 사라지면 안 됨 (%dfps)" % fps
        assert len(fake.crowns) == 20, "ㅅ자 튐도 첫 프레임에 보임 (%dfps)" % fps
    Weather.splash(fake, 20, 0)
    assert len(fake.crowns) == 20, "먼 층은 안 튐"
    fake.base = [0] * 20 + [12] * 20
    Weather.splash(fake, 25, 2)
    assert fake.crowns[-1][2] == 40 - 12 and fake.splashes[-1][1] == 28 - fake.droplet[0], "틀 위에 떨어지면 틀 윗변에서 튐"
    big = lambda **kw: types.SimpleNamespace(**{"surface": types.SimpleNamespace(pixels=bytearray(200 * 200 * 4)),
                                                "stride": 800, "w": 200, "h": 200, "amount": 100, "base": [0] * 200, **kw})
    hf = big(pile=Pile(200), pets={"cat": pet.Cat(200, random.Random(2)), "rabbit": pet.Rabbit(200, random.Random(2))},
             pet_startled={},
             hail_sprites=[place(disc(r, s, a, HAIL_COLOR, HAIL_RIM), 800) for r, s, a in HAIL_SIZES])
    hf.new_stone = lambda top: Weather.new_stone(hf, top)
    hf.scare_pet = lambda col, now: Weather.scare_pet(hf, col, now)
    hf.stones = [hf.new_stone(True) for _ in range(30)]
    most, scares = 0, {"cat": 0, "rabbit": 0}
    for i in range(180 * 6):
        before = dict(hf.pet_startled)
        Weather.hail(hf, 1 / 180, i / 180)
        for name in scares:
            scares[name] += hf.pet_startled.get(name) != before.get(name)
        most = max(most, *(s[6] for s in hf.stones))
    assert most == HAIL_BOUNCES and sum(hf.pile.h) > 0, "우박은 두 번까지 튀고 더미에 보탬"
    hf.stones = [[100, 199, 0, 900, 900, 1, HAIL_BOUNCES]]  # 이미 두 번 튄 알이 아직 빠르게 닿아도
    Weather.hail(hf, 1 / 180, 99)
    assert hf.stones[0][6] == 0 and hf.stones[0][1] < 0, "세 번째는 안 튀고 더미로"
    hf.base, hf.pile = [0] * 100 + [48] * 100, Pile(200)
    hf.stones = [[150, 200 - 48 - 30, 0, 900, 900, 1, HAIL_BOUNCES], [50, 200 - 48 - 30, 0, 900, 900, 1, HAIL_BOUNCES]]
    for _ in range(10):  # 프레임에 5px — 30px 밑 틀 윗변은 지나고, 화면 밑변에는 아직
        Weather.hail(hf, 1 / 180, 99)
    assert hf.stones[0][6] == 0 and sum(hf.pile.h[100:]) > 0, "틀 위의 알은 틀 윗변에 닿아 더미로(새 알로 바뀜)"
    assert hf.stones[1][1] > 200 - 48 - 30 and not any(hf.pile.h[:100]), "틈의 알은 그 높이를 지나 계속 떨어짐"
    sf = big(base=[0] * 100 + [48] * 100, pile=Pile(200), wind=Weather.wind,
             snow_sprites=[[[place(disc(rad, layer[4], layer[3], SNOW_COLOR, SNOW_RIM, fx / 4, fy / 4), 800)
                             for fy in range(4) for fx in range(4)] for rad in layer[1]] for layer in SNOW_LAYERS])
    li = next(i for i, layer in enumerate(SNOW_LAYERS) if layer[7])  # 쌓이는 층
    sf.new_flake = lambda li, top: [0.0, -1000.0, 0.0, li, 0, 0.0, 1.0]
    n = sf.snow_sprites[li][0][0][0]
    sf.flakes = [[x, 200 - 48 - n - 2, 300.0, li, 0, 0.0, 1.0] for x in (150.0, 50.0)]
    Weather.snow(sf, 1 / 60, 0.0)
    assert sf.flakes[0][1] == -1000 and sf.flakes[1][1] > 0 and sum(sf.pile.h[100:]) > 0 and not any(sf.pile.h[:100]), \
        "눈송이도 틀 위에서는 틀 윗변에, 틈에서는 계속 떨어짐"
    n = RAIN_LAYERS[1][1][0]
    wf = big(base=[0] * 100 + [48] * 100, kind="rain", gust_phase=0.0, bolt=None, sprite_cache={}, splashes=[], crowns=[],
             droplet=place(disc(0.8, 0.8, 190, RAIN_COLOR, RAIN_COLOR), 800), crown=[place(crown(k), 800) for k in range(3)],
             drops=[[x, 200 - 48 - n - 2, 300.0, 1, n, 0.0] for x in (150.0, 50.0)])
    for m in ("gust", "rain_set", "splash", "splatter"):
        setattr(wf, m, getattr(Weather, m).__get__(wf))
    wf.rain_sprites = wf.rain_set()
    wf.new_drop = lambda li, top: [0.0, -1000.0, 0.0, li, n, 0.0]
    Weather.rain(wf, 1 / 60, 0.0)
    assert [c[2] for c in wf.crowns] == [152] and wf.drops[1][1] > 0, "빗방울도 틀 위에선 틀 윗변에서 튀고, 틈에선 계속"
    zf = big(kind="none", amount=0, strip_h=PILE_STRIP + 48, snow_pile=pile_column_parts(PILE_STRIP + 48),
             base=[0] * 100 + [48] * 100)
    Weather.reset(zf)
    assert zf.pile.base is zf.base, "종류를 바꿔 더미를 새로 깔아도 틀 모양을 앎"
    zf.pile.h = [5.0] * 90 + [50.0] * 10 + [5.0] * 100  # 틈 90..99 엔 틀 높이를 넘는 언덕
    Weather.set_base(zf, [0] * 90 + [48] * 110)  # 앱을 열어 단추 묶음이 왼쪽으로 10px 넓어짐
    assert zf.pile.h[88:101] == [5.0] * 2 + [2.0] * 10 + [5.0] and zf.pile.base is zf.base, \
        "틀이 솟은 열은 그만큼 눈이 묻히고, 안 바뀐 열은 그대로"
    Weather.set_base(zf, [0] * 200)  # HUD 를 끔
    assert zf.pile.h[88:] == [5.0] * 2 + [2.0] * 10 + [5.0] * 100 and zf.pile.base == [0] * 200, \
        "틀이 사라지면 위에 쌓였던 눈이 그대로 바닥으로 떨어짐"
    assert all(0 < n <= 6 / HAIL_SCARE[2] + 1 for n in scares.values()), ("동물마다 가끔 놀라고 따로 쉼", scares)
    ff = big(rockets=[], sparks=[], next_launch=math.inf, pets={}, bangs=[],
             fw=[[place(glow(1.1, 3.6, lv / FW_LEVELS, 0, 0, c, hc), 800) for lv in range(1, FW_LEVELS + 1)]
                 for c, hc in FW_COLORS])
    ff.launch = lambda now: Weather.launch(ff, now)
    ff.burst = lambda x, y: Weather.burst(ff, x, y)
    peak = 0
    for i in range(180 * 20):
        Weather.fireworks(ff, 1 / 180, i / 180)
        peak = max(peak, len(ff.sparks))
    assert peak >= FW_SPARKS[0], "터짐"
    ff.amount = 0
    for i in range(180 * 4):  # 떠 있던 로켓이 오르는 1초 남짓 + 불꽃 수명
        Weather.fireworks(ff, 1 / 180, 20 + i / 180)
    assert not ff.sparks and not ff.rockets, "불꽃은 수명이 다하면 사라지고 0% 면 더 안 쏨"
    assert not ff.bangs, "동물이 없으면 터진 자리를 쌓아 두지 않음"
    # 불꽃이 가까이 터지면 서서 그쪽을 봄, 멀면 하던 걸 함. 낮게 나는 반딧불이는 쫓음
    cat, dog = pet.Cat(2000, random.Random(3)), pet.Dog(2000, random.Random(3))
    cat.x, dog.x = 100, 1500
    for a in (cat, dog):
        a.go("walk", 0.0)
        a.right = False
    rf = big(pets={"cat": cat, "dog": dog}, bangs=[], sparks=[], bolt=None, bolt_seen=None, kind="fireworks", flies=[])
    rf.burst = lambda x, y: Weather.burst(rf, x, y)
    rf.burst(600, 50)
    Weather.react(rf, 0.0)
    assert cat.state == "stand" and cat.right and cat.mood[0] == "!", "가까운 불꽃 쪽을 봄"
    assert dog.state == "walk" and not dog.mood and not rf.bangs, "먼 불꽃은 모름, 알린 건 비움"
    rf.kind, rf.flies = "fireflies", [[cat.x + 140, 200 - 40], [cat.x + 140, 200 - 150]]
    cat.go("walk", 0.0)
    Weather.react(rf, cat.calm)
    assert cat.state == "hop" and cat.pounce and cat.kind == "fireflies", "낮은 반딧불이로 폴짝"
    # 틀 단을 만나면 순간 이동하지 않고 뛰어 내려옴 (뛰는 모양은 pet.check 가 봄)
    walker = pet.Cat(200, random.Random(4))
    gf = big(pets={"cat": walker}, pile=Pile(200), base=[48] * 200, pet_sprites=pet.sprites(),
             kind="none", flies=[], bangs=[], bolt=None, bolt_seen=None)
    gf.react = lambda now: Weather.react(gf, now)
    Weather.walk_pet(gf, 1 / 60, 0.0)
    assert walker.ground == 48, "처음엔 발밑 높이에 바로 섬"
    gf.base = [0] * 200  # HUD 를 끔
    Weather.walk_pet(gf, 1 / 60, 1 / 60)
    Weather.walk_pet(gf, 1 / 60, 2 / 60)
    assert walker.leap and walker.ground > 48, "발밑 틀이 사라지면 뛰어내림(살짝 뜨며 시작)"
    assert floor_heights(5, 100, 0, 48, None) == [48] * 5, "틀을 모르면 작업 표시줄 윗변 전체가 바닥"
    assert floor_heights(10, 100, 10, 48, [(12, 52, 15), (16, 57, 30), (11, 20, 13), (0, 100, 20)]) == \
        [0, 0, 48, 48, 48, 0, 43, 43, 43, 43], "틀마다 그 윗변 높이, 띠 위의 창·높이 0 인 것은 안 셈"
    for kind in GUST:
        for phase in (0, 1.3, 4):
            fake.kind, fake.gust_phase = kind, phase
            for now in range(0, 60, 3):
                assert round(Weather.gust(fake, now) / SLANTS[1]) < len(SLANTS), "돌풍 기울기는 미리 그린 범위 안"
    alphas = [max(d[3::4]) for _, d in streak(30, 190, 1.0)[1]]
    assert alphas[0] < alphas[15] > alphas[-1] and alphas[-2] > alphas[2], "빗줄기는 양끝이 옅고 아래가 조금 진함"
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
    step = [0] * 10 + [20] * 10  # 왼쪽 틈 · 오른쪽 틀
    low = Pile(20, step)
    low.h[:10] = [10.0] * 10
    for _ in range(100):
        low.settle(0)
    assert low.h[10:] == [0.0] * 10, "틈의 눈은 표면이 틀 윗변보다 낮으면 틀 위로 안 오름"
    for flip in (False, True):  # 틀이 오른쪽 · 왼쪽
        high = Pile(20, step[::-1] if flip else step)
        high.h = [10.0] * 10 + [0.0] * 10 if flip else [0.0] * 10 + [10.0] * 10
        for _ in range(300):
            high.settle(0)
        g = high.h[::-1] if flip else high.h
        assert abs(sum(g) - 100) < 1e-6 and min(g) >= 0, "틀에서 흘러내려도 부피 그대로, 음수 없음"
        assert g[9] > g[5] > 0 and g[9] > SLOPE * 4, "틀 위 눈이 모서리에서 틈으로 흘러 옆면에 언덕으로 붙음"
    for f in (0.5, -0.5):  # 바람이 틀 쪽으로 붊 → 틀 옆면 앞에 언덕, 틀 위로는 못 넘음
        windward = Pile(20, step if f > 0 else step[::-1])
        windward.h = [5.0] * 10 + [0.0] * 10 if f > 0 else [0.0] * 10 + [5.0] * 10
        for _ in range(60):
            windward.blow(f)
            windward.settle(0)
        g = windward.h if f > 0 else windward.h[::-1]
        assert g[10:] == [0.0] * 10 and abs(sum(g) - 50) < 1e-6, ("벽은 못 넘고 부피 그대로", f)
        assert g[9] > g[0] + 5, ("바람 아래 벽 앞에 언덕", f, g[:10])
    lee = Pile(20, step[::-1])
    lee.h[:10] = [5.0] * 10
    lee.blow(0.5)
    assert lee.h[10] > 0 and lee.h[11] == 0, "틀 위 눈은 바람 아래 모서리로 날려 떨어짐"
    spill = Pile(10, [0] * 5 + [10] * 5)
    spill.h[:5] = [9.0] * 5
    spill.blow(0.5)
    assert spill.h[5] > 0, "언덕이 틀 윗변 가까이 차면 넘어감"
    edge = Pile(5)
    edge.h = [10.0] * 5
    edge.blow(0.5)
    assert edge.h == [8.5] + [10.0] * 4, "겉 LOOSE px 만 날림. 평평하면 그대로, 화면 끝으로 날린 눈은 사라지고 바람 위 끝은 받을 데가 없음"
    rise = PILE_STRIP + 4
    edges, body = pile_column_parts(rise + PILE_STRIP)
    rf = types.SimpleNamespace(w=4, strip_h=PILE_STRIP + rise, base=[0, rise, 1, 0],
                               pile=types.SimpleNamespace(h=[0.0, 0.0, 3.5, PILE_STRIP + 10.5]),
                               pile_last=[-1] * 4, pile_edges=edges, pile_body=body,
                               pile_zero=bytes((PILE_STRIP + rise) * 4),
                               strip=memoryview(bytearray(4 * 4 * (PILE_STRIP + rise))))
    Weather.render_pile(rf)
    strip = rf.strip.cast("I")
    col = [strip[r * 4 + 2] for r in range(PILE_STRIP + rise)]
    assert col[-2] and not col[-1], "더미 밑변이 그 열의 틀 윗변(밑에서 1px)에 앉음"
    assert sum(map(bool, col)) == 4 and not any(strip[1::4]), "몸통 3px + 가장자리 1px, 빈 열은 비움"
    assert sum(map(bool, strip[3::4])) == PILE_STRIP + 11, "틀 옆 언덕은 옛 띠 높이(PILE_STRIP)보다 높게도 그림"
    for v in (0.0, 0.5, 7.3, PILE_CAP):
        assert len(pile_column(v, edges, body, bytes(PILE_STRIP * 4))) == PILE_STRIP * 4, "열 길이가 띠 높이"
    stride = 40 * 4
    for sp in (disc(2.4, 1.8, 235, SNOW_COLOR, SNOW_RIM, 0.25, 0.5), streak(30, 190, 1.6)):
        want, got = bytearray(stride * 40), bytearray(stride * 40)
        off = 3 * stride + 5 * 4
        for skip, d in sp[1]:  # 미리 셈하기 전의 찍기
            want[off + skip:off + skip + len(d)] = d
            off += stride
        stamp(memoryview(got), stride, 5, 3, place(sp, stride)[1])
        assert want == got and any(got), "미리 셈해 찍어도 같은 바이트"
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
    assert [round(blink(t, 4), 6) for t in (0, 0.15, 0.5, 1.4, 2, 3.9)] == [0, 0.5, 1, 0.5, 0, 0], "깜빡임 곡선"
    sprites = [disc(3.0, 1.8, 235, SNOW_COLOR, SNOW_RIM, 0.5, 0.25)[1], streak(30, 165, 1.6)[1], glow(1.5, 6.5, 0.6, 0.25, 0.5)[1],
               levels[0], crown(0)[1], crown(2)[1], streak(20, 190 * RAIN_LIT, 1.6, 0.35, RAIN_LIT_COLOR)[1]]
    for rows in sprites + levels[1:]:
        for skip, data in rows:
            assert skip % 4 == 0 and len(data) % 4 == 0
            for i in range(0, len(data), 4):
                assert max(data[i:i + 3]) <= data[i + 3], "premultiplied 는 색이 알파를 못 넘음"
    for rows in sprites:  # 어둡게 낮춘 번개 단계는 끝 픽셀 알파가 0 으로 떨어질 수 있어 뺌
        for skip, data in rows:
            assert not data or (data[3] and data[-1]), "앞뒤 투명 픽셀은 잘려 있어야 함"
    assert count(50) == 150 and count(20) == 60 and count(100) == 300, "예전 보통·적게·많이와 같은 수"
    tint = water_rows(300, 50)
    alphas = [p[3] for p in tint]
    assert alphas == sorted(alphas) and alphas[0] < alphas[-1] and tint[0][0] < tint[-1][0], "물빛은 아래로 갈수록 짙고 푸름"
    assert 0.04 * 255 <= alphas[0] and alphas[-1] <= 0.09 * 255, ("기본 양에선 아주 옅게", alphas[0], alphas[-1])
    assert set(water_rows(10, 0)) == {bytes(4)}, "양 0% 면 투명"
    assert over((1, [(0, bytes(4))]), tint[-1]) == (1, [(0, tint[-1])]), "투명한 자리는 아래 물빛이 그대로"
    random.seed(3)
    aw, ah, rise = 400, 300, 20
    a = Weather.__new__(Weather)
    a.w, a.h, a.stride, a.rise, a.amount, a.kind, a.strip_h = aw, ah, aw * 4, rise, 50, "aquarium", PILE_STRIP + rise
    a.base, a.snow_pile, a.sprite_cache, a.aq_tint = [0] * 200 + [rise] * 200, pile_column_parts(PILE_STRIP + rise), {}, None
    a.next_base, a.full_clear, a.pets, a.on_top, a.last_settle = None, False, {}, False, 0
    a.surface = types.SimpleNamespace(pixels=bytearray(aw * ah * 4), clear=lambda top=0: None, present=lambda top=0: None)
    a.surface.fill = lambda src: a.surface.pixels.__setitem__(slice(None), src)
    a.reset()
    a.flakes = []  # 해초 뿌리 밑을 거품이 가리지 않게
    a.frame(1 / 60, 0.0)
    px, st = a.surface.pixels, a.stride
    at = lambda x, y: bytes(px[y * st + x * 4:y * st + x * 4 + 4])
    assert at(0, 0) == tint[0] and at(0, 150) == tint[150], "지우는 대신 물빛으로 덮음"
    assert any(at(x, 40) != tint[40] for x in range(aw)), "위쪽에 빛줄기"
    assert all(all(d[i + c] <= d[i + 3] for i in range(0, len(d), 4) for c in range(3))
               for rows in a.ray_rows for lv in rows for _, d in lv), "빛줄기는 premultiplied"
    sand_top = pixel(SAND_COLORS[0], 255)
    for nb in (None, [rise] * aw):  # 틀이 왼쪽까지 넓어져도
        if nb:
            a.next_base = nb
            a.frame(1 / 60, 0.0)
        for x, rows, *_ in a.aq["weeds"]:
            xx, y = x - len(rows[0]) // 8, ah - a.base[x] - a.sand[x]
            assert at(xx, y - 1) == rows[0][:4] and at(xx, y) == sand_top, ("해초 뿌리는 틀 윗변의 모래 위", x, nb)
        assert at(5, ah - a.base[5] - a.sand[5]) == sand_top and at(5, ah - a.base[5]) != sand_top, "모래는 틀 위"
    a.flakes = [a.new_bubble(li, False) for li in (0, 1) for _ in range(10)]
    for f in a.flakes:
        f[1] = ah / 2
    a.bubbles(0.05, 1.0)
    assert all(f[1] < ah / 2 for f in a.flakes), "거품은 위로"
    a.flakes[0][1] = -50
    a.bubbles(0.05, 1.1)
    assert a.flakes[0][1] > ah * 0.8, "수면을 넘은 거품은 바닥에서 다시 나옴"
    pinned, seen = [0] * len(a.fish), set()
    for i in range(60 * 120):
        a.fishes(1 / 60, i / 60)
        for k, f in enumerate(a.fish):
            fw, fh = a.aq["fish_size"][f[4]]
            lo, hi = a.fish_band(fh)
            assert 0 <= f[0] <= aw - fw and lo - 1 <= f[1] <= hi + 1, ("물고기는 화면 안", f)
            pinned[k] += f[0] in (0, aw - fw)
            seen.add(f[2])
    assert max(pinned) < 60 * 120 * 0.05 and seen == {1, -1}, ("끝에 닿으면 돌아섬", pinned)
    assert parse_amount("many") == 100 and parse_amount(0) == 0 and parse_amount(35) == 35
    assert all(parse_amount(a) is None for a in (101, -1, True, "x", [1], None, 2.5))
    assert amount_arg("normal") == 50 and amount_arg("7") == 7
    assert {20, 50, 100} <= set(AMOUNTS.values()), "예전 세 단계가 메뉴 칸에 있음"
    ids = [*AMOUNTS, *FPS_IDS, SHOW, *PETS, PANEL, AUTOSTART, EXIT, *KINDS]
    assert len(ids) == len(set(ids)), "메뉴 id 가 겹치지 않음"
    assert FPS in FPS_IDS.values()
    assert list(PETS.values()) == list(PET_CLASS) == list(PET_NAMES)
    global SETTINGS
    real, SETTINGS = SETTINGS, Path(tempfile.mkdtemp()) / "weather.json"
    try:
        for saved, want in ((True, ["cat"]), (False, []), ("bird", ["bird"]), ("", []), ("fox", []), (1, None),
                            (["penguin", "cat", "fox", "cat", [1]], ["cat", "penguin"])):
            SETTINGS.write_text(json.dumps({"pet": saved}), encoding="utf-8")
            assert load_settings().get("pet") == want, (saved, "예전 true 는 고양이, 모르는 이름은 버림")
    finally:
        SETTINGS = real
    from types import SimpleNamespace
    z = SimpleNamespace(pets={}, w=300, save=lambda: None)
    Weather.handle(z, 24)
    dog = z.pets["dog"]
    Weather.handle(z, 22)
    assert list(z.pets) == ["cat", "dog"] and z.pets["dog"] is dog, "여럿 켜지고, 켜 둔 동물은 그대로"
    Weather.handle(z, 24)
    assert list(z.pets) == ["cat"], "다시 누르면 꺼짐"
    q = SimpleNamespace(commands=queue.Queue())
    Weather.read_panel(q, SimpleNamespace(stdout=["amount 30\n", "amount x\n", "amount 150\n", "2\n",
                                                        "43\n", "23\n", "77\n", "hi\n"]))
    assert list(q.commands.queue) == [("amount", 30), 2, 43, 23], "설정 창이 보낸 줄 중 아는 것만"
    print("자체 점검 통과")


def panel(state):
    """트레이 왼쪽 클릭이 띄우는 설정 창. 누른 것을 한 줄씩 찍고(read_panel 이 받음), 바깥을 누르거나 Esc 면 닫힘."""
    import tkinter as tk
    from tkinter import ttk
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except (AttributeError, OSError):
        pass
    root = tk.Tk()
    root.title("날씨 설정")
    root.overrideredirect(True)
    root.attributes("-topmost", True)
    root.configure(bg="#c8c8c8")  # 1px 테두리로 보임
    px = lambda n: round(n * float(root.tk.call("tk", "scaling")) * 0.75)  # 96dpi 기준 px → 지금 화면 px
    style = ttk.Style(root)
    style.configure(".", background="white", font=("Segoe UI", 10))
    style.configure("Title.TLabel", font=("Segoe UI Semibold", 11))
    style.configure("Toolbutton", padding=(px(10), px(4)))
    f = ttk.Frame(root, padding=px(14))
    f.pack(padx=1, pady=1)

    def send(*words):
        try:
            print(*words, flush=True)
        except OSError:  # weather 가 먼저 꺼짐
            root.destroy()

    ttk.Label(f, text="날씨", style="Title.TLabel").grid(row=0, column=0, columnspan=4, sticky="w")
    kind = tk.StringVar(value=state["kind"])
    for i, (cid, (key, label)) in enumerate(KINDS.items()):
        ttk.Radiobutton(f, text=label, value=key, variable=kind, style="Toolbutton",
                        command=lambda cid=cid: send(cid)).grid(row=1 + i // 4, column=i % 4, sticky="ew",
                                                                padx=px(2), pady=px(2))

    row = ttk.Frame(f)
    row.grid(row=3, column=0, columnspan=4, sticky="ew", pady=(px(12), px(6)))
    ttk.Label(row, text="양").pack(side="left")
    val = tk.DoubleVar(value=state["amount"])
    pct = ttk.Label(row, width=5, anchor="e", text="%d%%" % state["amount"])
    show = lambda *_: pct.configure(text="%d%%" % round(val.get()))
    scale = ttk.Scale(row, from_=0, to=100, variable=val, command=show)
    pct.pack(side="right")
    scale.pack(side="left", fill="x", expand=True, padx=(px(10), px(4)))

    def jump(e):  # 볼륨 막대처럼 누른 자리로 바로 감 (ttk 기본은 한 칸씩)
        val.set(max(0.0, min(100.0, e.x / max(1, scale.winfo_width()) * 100)))
        show()

    scale.bind("<Button-1>", jump, add="+")
    scale.bind("<ButtonRelease-1>", lambda _: send("amount", round(val.get())))  # 끄는 동안 매번 다시 뿌리지 않게
    scale.bind("<KeyRelease>", lambda _: send("amount", round(val.get())))

    smooth = ttk.Frame(f)
    smooth.grid(row=4, column=0, columnspan=4, sticky="ew", pady=(0, px(8)))
    ttk.Label(smooth, text="부드러움").pack(side="left", padx=(0, px(8)))
    fps = tk.IntVar(value=state["fps"])
    for cid, n in FPS_IDS.items():
        ttk.Radiobutton(smooth, text=str(n), value=n, variable=fps, style="Toolbutton",
                        command=lambda cid=cid: send(cid)).pack(side="left", padx=px(2))
    ttk.Label(smooth, text="fps").pack(side="left", padx=(px(4), 0))

    animals = ttk.Frame(f)
    animals.grid(row=5, column=0, columnspan=4, sticky="ew", pady=(0, px(8)))
    ttk.Label(animals, text="동물").pack(side="left", padx=(0, px(8)))
    keep = []  # tk 변수는 파이썬 쪽 참조가 없어지면 체크 표시가 풀림
    for cid, a in PETS.items():  # 여럿 켤 수 있음
        keep.append(tk.BooleanVar(value=a in state["pet"]))
        ttk.Checkbutton(animals, text=PET_NAMES[a], variable=keep[-1], style="Toolbutton",
                        command=lambda cid=cid: send(cid)).pack(side="left", padx=px(2))

    for r, (key, cid, label) in enumerate((("show", SHOW, "보이기"),
                                          ("auto", AUTOSTART, "Windows 시작 시 실행")), start=6):
        keep.append(tk.BooleanVar(value=state[key]))
        ttk.Checkbutton(f, text=label, variable=keep[-1], command=lambda cid=cid: send(cid)).grid(
            row=r, column=0, columnspan=4, sticky="w", pady=px(1))
    ttk.Button(f, text="끝내기", command=lambda: (send(EXIT), root.destroy())).grid(
        row=8, column=3, sticky="e", pady=(px(10), 0))

    f.columnconfigure((0, 1, 2, 3), uniform="kind")
    root.bind("<Escape>", lambda _: root.destroy())
    u = ctypes.windll.user32

    # 바깥을 누르면 닫음. 앞에 왔던 창이면 앞자리를 잃는 것으로 알고, 못 왔으면(FocusOut 도 안 옴) 창 밖에서
    # 단추가 새로 눌리는 순간을 봄. GetAsyncKeyState 의 '눌린 적 있음' 비트는 다른 프로그램이 지워 버려 안 씀.
    # 트레이를 누른 단추가 아직 눌려 있을 수 있어 눌림에서 시작. 막대를 끌다 밖으로 나가는 건 새로 누른 게 아님
    was = {"front": False, "down": True}

    def outside():
        pid = ctypes.c_ulong()  # tk 의 바깥 창 핸들을 집기가 까다로워 앞 창이 이 프로세스 것인지로 봄
        u.GetWindowThreadProcessId(u.GetForegroundWindow(), ctypes.byref(pid))
        front = pid.value == os.getpid()
        down = bool(u.GetAsyncKeyState(1) & 0x8000 or u.GetAsyncKeyState(2) & 0x8000)
        x, y = root.winfo_pointerxy()
        x0, y0 = root.winfo_rootx(), root.winfo_rooty()
        out = not (x0 <= x < x0 + root.winfo_width() and y0 <= y < y0 + root.winfo_height())
        if was["front"] and not front or down and not was["down"] and out:
            root.destroy()
            return
        was["front"] |= front
        was["down"] = down
        root.after(50, outside)

    root.update_idletasks()
    w, h = root.winfo_reqwidth(), root.winfo_reqheight()
    l, t, r, b = overlay.work_area()
    x, _ = root.winfo_pointerxy()  # 트레이를 누른 자리 위, 작업 표시줄 바로 위
    root.geometry("+%d+%d" % (max(l, min(x - w // 2, r - w - px(12))), b - h - px(12)))
    root.focus_force()  # Esc 가 먹게. weather 가 AllowSetForegroundWindow 로 허락해 둠
    root.after(50, outside)
    root.mainloop()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--stop", action="store_true", help="떠 있는 날씨를 치움")
    ap.add_argument("--toggle", action="store_true", help="떠 있으면 치우고, 없으면 띄움")
    ap.add_argument("--check", action="store_true", help="자체 점검")
    saved = load_settings()  # 안 주면 트레이 메뉴에서 마지막으로 고른 값
    ap.add_argument("--kind", default=saved.get("kind", "snow"), choices=KIND_NAMES)
    ap.add_argument("--amount", default=saved.get("amount", 50), type=amount_arg, help="0–100 (기본 50)")
    ap.add_argument("--panel", help=argparse.SUPPRESS)  # 트레이 왼쪽 클릭의 설정 창. 지금 상태 JSON
    args = ap.parse_args()

    if args.check:
        check()
        return
    if args.panel:
        panel(json.loads(args.panel))
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
                              "--kind", args.kind, "--amount", str(args.amount)], close_fds=True)
            return
    if args.toggle and MAC:
        # 터미널을 닫아도 안 꺼지게 떼어서 다시 띄움
        subprocess.Popen([sys.executable, str(Path(__file__).resolve()), "--kind", args.kind, "--amount", str(args.amount)],
                         start_new_session=True, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL)
        return

    if not MAC:
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)  # 배율 높은 화면에서 흐려지지 않게
        except (AttributeError, OSError):
            pass
        ctypes.windll.winmm.timeBeginPeriod(1)  # 기본 타이머 간격(15.6ms)이면 30fps 를 청해도 21fps 에서 멈춤
    PID_FILE.write_text(str(os.getpid()))
    try:
        Weather(args.kind, args.amount, saved.get("pet", []), saved.get("fps", FPS)).run()
    finally:
        if not MAC:
            ctypes.windll.winmm.timeEndPeriod(1)
        if overlay.running_pid(PID_FILE) == os.getpid():
            PID_FILE.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
