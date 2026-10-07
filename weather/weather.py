# SPDX-License-Identifier: Apache-2.0
"""모든 창 위에 내리는 눈·비·뇌우·우박, 유리창에 맺히는 빗방울, 안개·오로라, 떠다니는 반딧불이·나비·잠자리·비눗방울, 불꽃놀이, 어항. 보이기만 하고 클릭은 그대로 아래 창으로 간다.

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
트레이의 눈송이 메뉴에서 종류·양·고양이·숨기기·끝내기를 하고(양은 10% 칸으로 0–100%), 왼쪽 클릭 설정 창에서는
어항의 물고기·거품·빛줄기 수도 막대로 고른다. 빗소리(rain_sound.py)를 켜면 비·뇌우일 때 창밖 빗소리가 난다.
고른 것은 SETTINGS 에 남는다.
"""
import argparse
import array
import colorsys
import ctypes
import itertools
import json
import math
import os
import queue
import random
import re
import shutil
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
import rain_sound
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
# 180(id 43)은 0.2.7 에서 뺐음 — 어항 98%, 뇌우 100% 에 동물 다섯이 한 코어를 다 썼음. 저장된 180 은 120 으로 읽음
FPS_IDS = {40: 30, 41: 60, 42: 120}
SNOW_COLOR, SNOW_RIM = (248, 250, 255), (165, 176, 198)  # 테두리를 옅은 회청색으로 — 흰 창 위에서도 보이게
RAIN_COLOR = (200, 214, 236)
RAIN_LIT, RAIN_LIT_COLOR = 1.7, (236, 242, 255)  # 번개가 번쩍일 때 빗줄기 — 알파 배수, 색
# 밝은 알갱이(눈·비·우박·거품·반딧불) 둘레의 그림자 색 · 알갱이 알파에 곱하는 비율. 흰 웹 페이지 위에서도 보이게 하는 것이고
# 어두운 창 위에선 어둠에 묻힘. 밝기를 화면에서 재 바꾸는 방식은 프레임마다 캡처가 비싸서 안 함
SHADE, SHADE_K = (22, 32, 64), 0.4
SHADES = {}  # k 별 알파 → 그림자 픽셀 표

# 눈 층: (비율, 반지름들 px, 속도 px/초, 알파, 번짐 px, 흔들림 px, 바람을 받는 정도, 바닥에 쌓이나)
SNOW_LAYERS = ((0.45, (0.7, 0.9, 1.1), (16, 28), 150, 0.8, 4, 0.4, False),   # 멀리
               (0.42, (1.3, 1.6, 2.0), (32, 52), 225, 0.9, 10, 0.7, True),   # 가운데
               (0.13, (2.4, 3.0, 3.6), (58, 88), 235, 1.8, 18, 1.0, True),   # 가까이 — 크고 번짐
               (0.03, (5.0, 6.5, 8.0), (110, 160), 120, 6.0, 30, 1.3, False))  # 눈앞 — 초점 밖처럼 크고 흐림
SNOW_NEAR = 3      # 눈앞 층 번호. 쌓인 눈 앞을 지나 화면 밑으로 빠짐
SNOW_FLUTTER = 0.25  # 낙하 빠르기가 송이마다 이 비율만큼 오르내림 — 팔랑임
LAND_T = (0.5, 1.1)  # 쌓인 눈에 닿은 송이가 표면에 얹혀 보이는 초. 그동안 작아지며 스밈
GLINT_RATE, GLINT_T, GLINT_LEVELS = 40, (0.3, 0.8), 4  # 쌓인 눈 반짝임: 2560 폭에 초당 시도 수(눈 1.5px 아래 열이면 거름) · 깜빡이는 초 · 밝기 단계
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
# 쌓인 눈 윗면: 맨 위 1px 테두리 색(어두운 창에서 회색 띠로 안 보이고 밝은 창에서 안 끊기게 둘 사이) · 왼쪽 위 빛을 받는
# 비탈 · 등진 비탈의 색 · 비탈 단계(−3..3) · 양옆 열 높이 차 → 단계 배수
PILE_RIM, PILE_LIT, PILE_SHADOW, PILE_SLOPES, PILE_LIGHT = (205, 213, 230), (255, 255, 255), (196, 208, 234), 3, 2.0
PILE_PER_FLAKE = 10.0  # 눈송이 하나가 보태는 부피 = 이 값 × 반지름. 실제보다 부풀려 몇 분 안에 쌓이게.
                       # 멈추는 높이가 이 값에 비례함 (21 이면 보통 11px·많이 21px, 10 이면 그 절반쯤)
                       # 반지름²에 비례시키면 큰 눈송이 하나에 둔덕이 툭 솟음
SLOPE = 0.8        # 이웃 열과의 높이 차가 이보다 크면 흘러내림 (안식각)
DIFFUSE = 0.12     # 표면을 매끈하게 퍼뜨리는 정도
DRIFT, LOOSE, LIFT = 0.12, 3.0, 2.0  # 바람에 날리는 눈: 바람 px/초 × 초당 옮기는 비율 · 겉의 날리는 두께 px · 넘는 턱 px
MELT_PER_SEC = 0.0045  # 높이에 비례해 녹는 비율. 넣는 양 ÷ 이 값에서 높이가 멈춤 ('보통' 이면 5px 쯤)
SETTLE_SEC = 0.25
FRAMES_EVERY = 3   # 작업 표시줄 틀을 다시 읽는 간격 초. 한 번 55ms(UI 자동화)라 다른 스레드에서
FULLSCREEN_EVERY = 0.25  # 전체 화면 앱이 떴는지 보는 간격 초. 한 번 0.1ms
SINK_G, SINK_CRUMBLE = 900, 0.12  # 틀이 사라져 바닥이 내려앉는 가속 px/초² · 4px 묶음마다 늦게 떨어지는 최대 초
SINK_WATER_G, SINK_WATER_V = 600, 70  # 어항은 물속이라 덜 가속하고 이 px/초(종단 속도)를 안 넘음 — 모래가 천천히 가라앉음

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
FW_WHITE = 5
# 터지는 모양: 이름 → (뽑힐 무게, 끌림 1/초, 중력 px/초², 꼬리 점 수 범위 — 불꽃마다 뽑음).
# 꼬리는 FW_TRAIL_DT 초마다 지나온 자리를 남김
FW_KINDS = {"peony": (3, 1.7, 95, (0, 0)),         # 모란 — 색 점이 공 모양으로
            "chrysanthemum": (3, 1.7, 95, (5, 5)),  # 국화 — 모란에 꼬리
            "willow": (2, 1.6, 150, (8, 20)),       # 버들 — 금빛 꼬리가 제각각 길게 처지며 오래 머묾
            "palm": (2, 1.2, 95, (12, 12)),         # 야자 — 굵은 팔 몇 개
            "ring": (2, 1.7, 95, (0, 0)),           # 고리 — 기울어진 원
            "crossette": (2, 1.5, 95, (4, 4)),      # 갈라지기 — 별이 날다 넷으로 쪼개짐
            "strobe": (2, 1.5, 50, (0, 0)),         # 반짝이 — 흰 점이 깜빡이며 오래
            "heart": (1, 1.7, 70, (0, 0))}          # 하트
FW_TRAIL_DT = 0.035
FW_SPLIT = (0.35, 0.5)  # 갈라지기 별이 쪼개지는 나이(초)
FW_SHIFT = 0.25         # 모란·국화가 중간에 색이 바뀔 확률

RAINY = ("rain", "storm")  # 빗줄기가 내리고 동물이 비 맞는 날처럼 구는 종류
SOUNDY = (*RAINY, "window")  # 빗소리가 나는 종류 — 창문 빗방울은 실내라 동물은 안 젖음

# 안개: 화면 아래에서 닿는 높이(비율) · 양 50% 의 맨 아래 불투명도 · 색 · 흐르는 빠르기 px/초
# 행마다 같은 빠르기에, 높이를 따라 위상이 밀리는 출렁임(폭 px · 빠르기 rad/초 · 행당 위상)을 더함 — 행마다 빠르기가
# 다르면 오래 둘수록 이웃 행이 벌어져 가로 줄무늬가 됨
FOG_REACH, FOG_ALPHA, FOG_COLOR, FOG_DRIFT = 0.42, 0.30, (218, 224, 236), 9
FOG_SWAY, FOG_SWAY_V, FOG_SWAY_K = 40, 0.12, 0.012
FOG_KNOT = 90      # 이 행마다 가로 무늬를 하나씩 새로 뽑고 그 사이 행은 섞음
FOG_MIX = 16       # 섞는 비율 단계 수 — 단계마다 한 번만 셈

# 오로라: 화면 위에서 닿는 깊이(비율) · 양 50% 의 가장 짙은 불투명도 · 옆 흐름(px/초) · 출렁임 물결들(폭 px, 빠르기,
# 행마다 밀리는 위상) — 폭과 빠르기가 다른 둘을 섞어 빛살이 모두 같은 S 자로 휘지 않음
AURORA_REACH, AURORA_ALPHA, AURORA_DRIFT = 0.6, 0.5, 6
AURORA_SWAY = ((50, 0.11, 0.004), (14, 0.23, 0.011))
AURORA_PHASES = 2   # 행을 1/이만큼 px 씩 옮겨 본 벌 수 — 정수 px 로 밀면 기운 빛살에 1px 계단이 보임. 넷이면 35MB 라
#                     캐시를 넘쳐 프레임이 1ms 늘었음(둘은 18MB, 이웃 행 차가 0.35px 아래라 반 px 계단은 안 보임)
AURORA_RAYQ = 16    # 빛살 높이 단계 수 — 단계마다 본 하나(2560×1440 에 54KB)
# 커튼마다 (아랫단 깊이 비율, 세기, 빛살 높이) — 앞(아래) 커튼이 밝고 빛살이 김
AURORA_RIBBONS = ((0.82, 1.0, 0.45), (0.64, 0.7, 0.32), (0.46, 0.45, 0.22))  # 빛살 높이 2배면 위가 보라로 꽉 참
# 아랫단에서 잰 높이(비율) → 색: 밑은 분홍 술, 아랫단은 흰빛 초록, 위로 초록 · 청록 · 보라
AURORA_COLORS = ((-0.03, (255, 70, 160)), (0.0, (200, 255, 220)), (0.04, (80, 255, 140)), (0.15, (40, 225, 170)),
                 (0.3, (120, 110, 255)), (0.5, (190, 80, 255)))
# 오로라에 곁들인 유성: 양 50% 에서 초당 오는 수 · 그중 유성우(한 복사점에서 몰아 떨어짐)인 몫 · 유성우 개수 · 그 사이 초
METEOR_RATE, METEOR_SHOWER, METEOR_BURST, METEOR_GAP = 1 / 6, 0.15, (5, 9), (0.15, 0.6)
METEOR_LIFE, METEOR_SPEED, METEOR_TAIL_SEC = (0.4, 1.0), (900, 1600), 0.17  # 꼬리 길이 = 빠르기 × 이 초
FIREBALL = 0.1     # 불덩이 비율 — 밝아 심이 굵어 보이고, 느리고 오래 가며 끝에서 번쩍
# 단면: 심 σ · 번짐 σ · 번짐 세기 · 머리 빛 σ (px) · 머리 빛 세기 · 심선에서 이 px 밖은 안 셈. 머리 빛이 크면 올챙이처럼 보임
METEOR_CORE, METEOR_GLOW, METEOR_GLOW_K, METEOR_HEAD_R, METEOR_HEAD_K, METEOR_R = 0.7, 1.6, 0.25, 1.2, 0.7, 4
METEOR_HEAD, METEOR_TAIL = (235, 255, 235), (140, 185, 255)  # 머리 흰빛 초록 → 꼬리 옅은 파랑

# 비눗방울: 양 → 방울 수 ('보통' 9개) · 반지름들 px · 오르는 빠르기 px/초 · 터지기까지 초 · 무지갯빛이 도는 그림 수 · 초당 바퀴
# 그림 수 8 이면 한 번에 45° 씩 뚝뚝 넘어가 돌아가는 게 보였음. 32 면 11°
SOAP_SHARE, SOAP_R, SOAP_RISE, SOAP_LIFE = 0.06, (6, 9, 13, 18), (18, 46), (5, 14)
SOAP_HUES, SOAP_SPIN, SOAP_SWAY = 32, 0.25, 9  # 흔들림 폭 px

# 나비·잠자리: 양 → 마리 수 ('보통' 8마리) · 그중 잠자리 몫. 나비는 팔랑이는 빠르기 px/초 · 날갯짓 Hz · 초당 내려앉을
# 확률 · 앉아 쉬는 초 · 동물이 이 px 안에 오면 날아오름. 잠자리는 휙 나는 최고 px/초 · 멈춰 떠 있는 초
BUG_SHARE, BUG_DRAGON = 0.05, 0.3
FLUTTER_V, FLUTTER_HZ, BUG_LAND, BUG_REST, BUG_SHY = (30, 70), 7, 0.07, (2.5, 7), 70
DART_V, DART_HOVER = 320, (0.4, 2.2)
BUG_COLORS = ({"a": (247, 140, 30), "b": (38, 30, 30), "c": (252, 204, 126), "k": (38, 43, 68)},     # 제주왕나비 빛
              {"a": (250, 250, 244), "b": (70, 72, 84), "c": (232, 234, 214), "k": (38, 43, 68)},    # 배추흰나비
              {"a": (64, 142, 255), "b": (24, 34, 76), "c": (128, 194, 255), "k": (38, 43, 68)},     # 파랑
              {"a": (255, 218, 60), "b": (96, 74, 24), "c": (255, 240, 156), "k": (38, 43, 68)},     # 노랑
              {"b": (52, 122, 232), "g": (40, 90, 180), "e": (30, 40, 82), "w": (170, 196, 226)},   # 파란 잠자리
              {"b": (226, 62, 46), "g": (170, 52, 40), "e": (92, 32, 32), "w": (196, 186, 206)})    # 고추잠자리
BUTTERFLY_ART = (("..k...k..",  # 날개를 활짝 → 반쯤 → 접음 → 반쯤 으로 돌림
                  "...k.k...",
                  "bba.k.abb",
                  "baaakaaab",
                  "baaakaaab",
                  ".aaakaaa.",
                  "..cakac..",
                  "..cc.cc.."),
                 ("..k...k..",
                  "...k.k...",
                  ".ba.k.ab.",
                  ".baakaab.",
                  "..aakaa..",
                  "..aakaa..",
                  "..cakac..",
                  "...c.c..."),
                 ("..k...k..",
                  "...k.k...",
                  "...bkb...",
                  "...aka...",
                  "...aka...",
                  "...aka...",
                  "...ckc...",
                  "........."))
DRAGONFLY_ART = (("....w..w....",  # 위에서 본 그림, 오른쪽을 봄. 날개 두 쌍이 프레임마다 앞뒤로 젖혀짐 — 빨라서 떨려 보임
                  "...ww.ww....",
                  "bbbbbbbbggee",
                  "...ww.ww....",
                  "....w..w...."),
                 ("...w..w.....",
                  "...ww.ww....",
                  "bbbbbbbbggee",
                  "...ww.ww....",
                  "...w..w....."))

# 창문 빗방울: 양 → 유리에 맺혀 있는 방울 수 ('보통' 150개) · 양 50% 에 초당 새로 맺히는 수 · 새 방울 반지름 범위 px ·
# 이 반지름이 넘으면 초당 PANE_GO 확률로 흘러내리기 시작 · 반지름 최대 · 흐를 때 달리는 px/초 · 달리는 초 · 멈칫하는 초 ·
# 지나간 자리에 남기는 작은 방울 사이 px
PANE_SHARE, PANE_RATE, PANE_R, PANE_HEAVY, PANE_GO, PANE_RMAX = 1.0, 22, (1.5, 6), 6, 0.12, 13
PANE_RUN, PANE_RUN_T, PANE_STOP_T, PANE_TRAIL = (70, 230), (0.08, 0.35), (0.05, 0.7), (10, 22)
# 새 방울이 유리에 부딪히는 모양: 퍼졌다 오므라드는 초 · 처음 퍼진 배수 · 이 반지름 이상이면 둘레에 잔방울이 튐 (개수, 거리 배수)
PANE_SPLAT_T, PANE_SPLAT_K, PANE_SPRAY_R, PANE_SPRAY = 0.15, 1.8, 2.5, ((0, 3), (1.5, 2.8))
# 소나기: 사이 초 · 이어지는 초 · 가장 셀 때 초당 빗줄기 수(양 50%) · 빗줄기 중 유리에 부딪혀 맺는 몫 · 빗줄기 기울기(SLANTS 번호) ·
# 빗줄기가 보이는 초 · 맺힌 방울이 넘치면 마르는 수/초(넘친 수의 1/8 을 더함 — 소나기 뒤 한꺼번에 사라지지 않게)
PANE_SHOWER_EVERY, PANE_SHOWER_LEN, PANE_SHOWER_RAIN, PANE_STICK = (40, 90), (3, 6), 420, 0.3
PANE_SHOWER_SLANT, PANE_STREAK_T, PANE_DRY = 4, (0.08, 0.3), 8

# 어항. 물빛은 행마다 색 하나로 화면 전체를 덮음 — 위는 옅은 하늘색, 아래로 갈수록 짙은 파랑
AQ_TOP, AQ_DEEP = (96, 178, 226), (26, 92, 178)
AQ_ALPHA = (0.05, 0.08)  # 양 50% 일 때 (맨 위, 맨 아래) 불투명도. 양에 비례 — 100% 면 두 배, 0% 면 투명
AQ_BANDS = 4       # 거품 그림에 미리 섞어 두는 물빛 높이 띠 수. 띠 안의 물빛 차이는 알파 1/255 안팎
RAY_COUNT, RAY_REACH = 5, 0.45  # 빛줄기 수 · 화면 위에서 닿는 깊이(높이 비율). 행마다 한 번 찍어서 위쪽에만
RAY_WIDTHS, RAY_SPREAD = (0.025, 0.039, 0.055), 2.0  # 빛줄기 모양별 위쪽 폭 (화면 폭 비율, 2560 에서 64·100·140px) · 아래 끝은 (1 + SPREAD) 배로 퍼짐
RAY_SLANT, RAY_SWAY = (0.12, 0.30), 0.05  # 기울기 (가로 / 세로) 왼쪽 줄기 → 오른쪽 줄기, 부채꼴 · 흔들리는 폭
RAY_COLOR, RAY_ALPHA = (226, 246, 255), 0.16
# 밝기 단계 수 (1/8 … 1). 줄기 통째로 천천히 오감. 줄기를 따라 행마다 단계를 달리하면 단계 경계가 가로줄로 보이고,
# 행 디더는 가로 줄무늬가 보여서 안 함(2026-10-05 그려 봄)
RAY_LEVELS = 8
# 거품 층: 눈 층(SNOW_LAYERS)과 같은 꼴 — (비율, 반지름들, 오르는 빠르기 px/초, 알파, 안 씀, 흔들림 px, 안 씀, 안 씀)
BUBBLE_LAYERS = ((0.6, (1.2, 1.7), (24, 42), 150, 0, 3, 0, False),
                 (0.4, (2.3, 3.2), (42, 74), 205, 0, 6, 0, False))
BUBBLE_SHARE = 0.2  # 양 → 거품 수 ('보통' 30개)
BUBBLE_COLOR = (236, 250, 255)
BREATH_BUBBLES = (2, 4)  # 동물이 숨 한 번에 내쉬는 거품 수 (간격은 pet.BREATH)
SAND_H = (3, 7)    # 모래 두께 px
SAND_COLORS = ((238, 222, 176), (224, 204, 150), (210, 188, 134), (232, 214, 164), (196, 172, 120))
WEED_EVERY, WEED_H, WEED_SWAY = 160, (24, 64), 7  # 해초 사이 평균 px · 키 px · 꼭대기가 흔들리는 px
WEED_COLORS = ((34, 112, 64), (52, 146, 78), (92, 190, 98))  # 아래 → 위
FISH_N, FISH_SPEED, FISH_TURN = 8, (22, 58), 0.04  # 물고기 수 · px/초 · 1초에 돌아설 확률
FISH_COLORS = {"k": (38, 43, 68), "e": (24, 20, 37), "w": (255, 255, 255), "o": (247, 118, 34), "O": (206, 76, 20),
               "a": (255, 168, 86), "b": (44, 104, 226), "l": (104, 168, 250), "n": (24, 30, 72),
               "y": (250, 214, 60), "Y": (214, 156, 28), "m": (255, 244, 208), "c": (64, 230, 255),
               "r": (232, 58, 70), "g": (78, 92, 112), "s": (214, 222, 236), "S": (150, 162, 190),
               "t": (176, 204, 228), "p": (126, 84, 36)}
# 물고기: (오른쪽을 보는 그림, 꼬리를 친 그림의 각 행 앞부분). 흰동가리 · 블루탱 · 네온테트라 · 복어 · 엔젤피시
# 등은 어둡고 배는 밝게, 눈은 2×2 에 흰 반짝임. 흰동가리 띠 양옆 · 블루탱 '팔레트' 무늬 · 엔젤피시 줄은 검정 계열
FISH_ART = (
    ((".......kkkk..kkk........",
      "......kooookkoook.......",
      "..kk..koooookooookk.....",
      ".kook.koOOkwwkOOkwwkk...",
      "kooookwkOOkwwkOOkwwkOk..",
      "kooookwkOOkwwwkOkwwewOk.",
      "kooookwkookwwwkokwweeoOk",
      "kooookwkookwwwkokwwkaak.",
      "kooookwkaakwwkaakwwkak..",
      ".kook.koaakwwkaakwwkk...",
      "..kk..kooookkkoookk.....",
      ".......koook.kook.......",
      "........kkk...kk........"),
     ("", "", "...", "..k", "..k", ".k", ".k", ".k", "..k", "..k", "...", "", "")),
    ((".......kkkkkkkkkk.....",
      ".k....kbbbbbbbbbbk....",
      "kyk...kbbbbbbbbbbbk...",
      ".kyk..kbbbbbbbbbbbk...",
      ".kyykknnnnnnnnnnnnbk..",
      ".kyyynnnnbbbbbnnnnewk.",
      "..kyynnbnbbbbbnnbbeebk",
      "..kyynbbbnnnnnbbbbbblk",
      ".kyyylllbbbbbbbyylllk.",
      ".kyykklllllllllyyllk..",
      ".kyk..kblllllllllkk...",
      "kyk...kbbbbbbbbbk.....",
      ".k....kbbbbbbbbk......",
      ".......kkkkkkkk......."),
     ("", "..", "...", "...", "..k", "..k", "...k", "...k", "..k", "..k", "...", "...", "..", "")),
    (("..........kk.......",
      "..k..kkkkkttkkk....",
      ".ktkkggggggggggkk..",
      ".ktggccccccccccewk.",
      ".ktsssssssssccceegk",
      ".ktrrrrrrrrrsssssk.",
      ".ktkkrrrrrrrssskk..",
      "..k..kkkkttkkkk....",
      ".........kk........"),
     ("", "...", "...", "..k", "..k", "..k", "...", "...", "")),
    ((".........kk.......",
      "......kkkYYkkk....",
      ".....kYYYYYpYYk...",
      ".k..kYYYpYYYYYpk..",
      "kYkkYYYYYYYYYewYk.",
      "kYYYYYpYYYpYYeeYk.",
      ".kYYyyyyyyyyyyyyYk",
      ".kYmyyyypyypyyyymk",
      "kYYYmmmmmyymYmmmk.",
      "kYkkmmmmmmmmYmmmk.",
      ".k..kmmmmmmmmmmk..",
      ".....kmmmmmmmmk...",
      "......kkkmmkkk....",
      ".........kk......."),
     ("", "", "", "..", "..", ".k", "..k", "..k", ".k", "..", "..", "", "", "")),
    (("....kkk.............",
      "...kSSSkk...........",
      "...kSSSnSk..........",
      "....kSSnSSkk........",
      "....kSSnSSSnk.......",
      ".....kSnSSSnnkkk....",
      "..k..kSnSSnnSSSSk...",
      ".kSk.kSnSSnnSSSnSk..",
      ".kSSkkSnSSnnSSSewSk.",
      ".kSSSSSnssnnssseeSk.",
      "..kSSsnnssnnsssnssk.",
      ".kSSSwnsssnnsssnswk.",
      ".kSSkknwwwnnwwwnwwk.",
      ".kSk.knwwwnnwwwnwk..",
      "..k..knSwwnnwwwnk...",
      ".....knSSnnSSkkk....",
      "....kSnSSnnSSk......",
      "....kSnSSnkSk.......",
      "...kSSnSSkkSk.......",
      "...kSnSkkknSk.......",
      "....kkk...kk........"),
     ("", "", "", "", "", "", "...", "...", "..k", "..k", "...k", "..k", "..k", "...", "...", "", "", "", "", "", "")),
)
FISH_FLIP, FISH_PULSE = 0.4, 0.3  # 돌아서는 초 · 꼬리를 칠 때 빨라졌다 느려지는 몫
# 떼: 은빛 작은 물고기 몇 마리가 안 보이는 우두머리를 저마다 다른 늦음으로 따라감 (FISH_ART 와 같은 꼴)
SCHOOL_ART = (("....kkkk..",
               "kc.ksssssk",
               "kcsccccwek",
               "kc.ktttttk",
               "....kkkk.."),
              ("", "..k", ".c", "..k", ""))
SCHOOL_N, SCHOOL_BACK, SCHOOL_SIDE, SCHOOL_PULL = (6, 9), (10, 90), 26, (1.0, 2.6)  # 마릿수 · 뒤로 px · 위아래 px · 따라가는 빠르기 /초
# 바닥 장식: 해초 사이 틈마다 DECOR_SHARE 확률로 하나. 산호 둘 · 조개 · 불가사리 · 돌
DECOR_COLORS = {"k": (38, 43, 68), "p": (255, 122, 160), "q": (196, 64, 112), "v": (170, 122, 222), "u": (112, 72, 172),
                "l": (252, 222, 198), "d": (226, 160, 128), "o": (255, 150, 64), "g": (140, 150, 170), "s": (186, 196, 212),
                "y": (250, 206, 60), "Y": (196, 146, 30), "w": (255, 255, 255), "b": (156, 94, 48), "n": (100, 58, 30),
                "r": (236, 72, 56), "R": (168, 40, 36), "e": (24, 20, 37)}
DECOR_SHARE = 0.75
DECOR_ART = ((".p.....p...",
              ".p..p..p.p.",
              "pp..p.pp.p.",
              ".p.pp.p..pp",
              ".ppp..p.pp.",
              "..pp.ppp.p.",
              "..p..pp.pp.",
              "..pppp.pp..",
              "...ppppp...",
              "....qpp....",
              "....qqp....",
              "...qqqqq..."),
             ("...vvvvvv...",
              ".vvuvvuvvvv.",
              "vvuvvvuvvuvv",
              "vuvvuvvvuvvv",
              "vvvuvvuvvuvv",
              "uuuuuuuuuuuu"),
             ("...kkk...",
              "..kldlk..",
              ".kldldlk.",
              "kldldldlk",
              "kldldldlk",
              ".kkkkkkk.",
              "...kdk...",
              "...kkk..."),
             ("....k....",
              "...kok...",
              "kkkkokkkk",
              "koooooook",
              ".koodook.",
              "..koook..",
              ".kok.kok.",
              "kok...kok",
              "kk.....kk"),
             ("...kkkk...",
              ".kkgsgsgk.",
              "kgsgggsgsk",
              "kggsgggggk",
              "kkkkkkkkkk"))
# 보물상자: (닫힘, 열림). 닫혀 있는 초 · 열려 있는 초 · 열린 동안 거품 뿜는 간격 초
CHEST_ART = (("..kkkkkkkk..",
              ".knnnnnnnnk.",
              "knbbbbbbbbnk",
              "kyyyyyyyyyyk",
              "kbbbbykybbbk",
              "kbbbbyybbbbk",
              "kbbbbbbbbbbk",
              "knnnnnnnnnnk",
              ".kkkkkkkkkk."),
             (".kkkkkkkk...",
              "knnnnnnnnk..",
              ".knnnnnnnnk.",
              "kyywyywyyyyk",
              "kyyyyyyyyyyk",
              "kbbbbykybbbk",
              "kbbbbyybbbbk",
              "kbbbbbbbbbbk",
              "knnnnnnnnnnk",
              ".kkkkkkkkkk."))
CHEST_SHUT, CHEST_OPEN, CHEST_PUFF = (8, 15), 2.0, 0.07
# 게: (걸음 둘, 집게 듦). 마릿수 · px/초 · 걷는 초 · 서서 집게 드는 초
CRAB_ART = (("rr.........rr",
             "rRr..e.e..rRr",
             ".rr..k.k..rr.",
             "..rrrrrrrrr..",
             ".rrrRrrrRrrr.",
             "..r.r...r.r..",
             ".r.r.....r.r."),
            ("rr.........rr",
             "rRr..e.e..rRr",
             ".rr..k.k..rr.",
             "..rrrrrrrrr..",
             ".rrrRrrrRrrr.",
             ".r.r.....r.r.",
             "..r.r...r.r.."),
            ("r.r.......r.r",
             "rrr..e.e..rrr",
             ".rr..k.k..rr.",
             "..rrrrrrrrr..",
             ".rrrRrrrRrrr.",
             "..r.r...r.r..",
             ".r.r.....r.r."))
CRAB_N, CRAB_SPEED, CRAB_WALK, CRAB_REST = 2, 22, (2, 6), (1, 3)
# 해파리: 반투명이라 물빛 띠(AQ_BANDS)마다 미리 섞음. (편 그림, 오므린 그림), 글자 → (색, 알파)
JELLY_COLORS = {"q": ((250, 170, 235), 200), "p": ((236, 140, 220), 150), "w": ((255, 255, 255), 220),
                "t": ((240, 170, 230), 120)}
JELLY_ART = (("..qqqqq..",
              ".qwwpppq.",
              "qwppppppq",
              "qpppppppq",
              "qqqqqqqqq",
              ".t.t.t.t.",
              ".t.t.t.t.",
              ".t..t..t.",
              "..t.t.t..",
              ".t..t..t.",
              ".t.....t."),
             ("...qqq...",
              "..qwppq..",
              ".qwppppq.",
              ".qpppppq.",
              ".qqqqqqq.",
              "..t.t.t..",
              "..t.t.t..",
              "..t.t.t..",
              ".t..t..t.",
              "..t...t..",
              "........."))
# 해파리 수 · 오므려 밀어 오르는 간격 초 · 그때 오르는 빠르기 px/초 · 가라앉는 빠르기 px/초 · 오므린 그림 보이는 초
JELLY_N, JELLY_PULSE, JELLY_PUSH, JELLY_SINK, JELLY_SQUEEZE = 3, (2.0, 3.5), 42, 7, 0.35

KINDS = {1: ("snow", "눈"), 2: ("rain", "비"), 3: ("storm", "뇌우"), 4: ("hail", "우박"), 35: ("window", "창문 빗방울"),
         31: ("fog", "안개"), 33: ("aurora", "오로라"), 6: ("fireflies", "반딧불이"), 34: ("bugs", "나비·잠자리"),
         32: ("soap", "비눗방울"), 5: ("fireworks", "불꽃놀이"), 8: ("aquarium", "어항"), 7: ("none", "날씨 없음")}  # 없음은 동물만. id 는 설정 파일과 무관해 순서만 바꿔도 됨
KIND_NAMES = tuple(k for k, _ in KINDS.values())
SHOW, PANEL, AUTOSTART, EXIT = 20, 30, 50, 99
DRAG = 27  # 동물을 왼쪽 단추로 집어 옮기기. 윈도우만 — 맥은 창을 누르면 앱이 앞으로 나와 포커스를 뺏을 수 있어 아직 안 함
PETS = {22: "cat", 23: "bird", 24: "dog", 25: "rabbit", 26: "penguin"}  # 메뉴 id → 설정 파일 pet 목록의 이름
PET_NAMES = {"cat": "고양이", "bird": "새", "dog": "강아지", "rabbit": "토끼", "penguin": "펭귄"}
PET_CLASS = {"cat": pet.Cat, "bird": pet.Bird, "dog": pet.Dog, "rabbit": pet.Rabbit, "penguin": pet.Penguin}
RUN_NAME = "PlayroomWeather"  # 시작할 때는 인자 없이 떠서 저장된 종류·양을 따름
AMOUNTS = {10 + i: p for i, p in enumerate(range(10, 101, 10))}  # 메뉴 id → %. 트레이 메뉴엔 막대를 못 넣어 칸으로
SOUND = 60  # 비·뇌우에 빗소리 켜고 끄기
VOLUMES = {61 + i: p for i, p in enumerate(range(10, 101, 10))}  # 메뉴 id → 빗소리 크기 %
VOLUME = 50
FULL = 300       # 양 100% 의 눈송이·빗방울 수 (꽃잎·반딧불이는 이 수에 종류별 비율을 곱함)
OLD_AMOUNTS = {"few": 20, "normal": 50, "many": 100}  # 예전 세 단계. 설정 파일·--amount 에서 아직 읽음
# 어항 막대: 설정 파일 키 → (설정 창 이름, 기본값, 끝값, 단위). 물고기는 마릿수, 거품·빛줄기는 0–100% 이고 50% 가
# 거품 30개 · RAY_COUNT, 100% 면 두 배. 어항에서 양은 물빛 진하기만 정함
FISH_MAX = 20
TANK = {"fish": ("물고기", FISH_N, FISH_MAX, "마리"), "bubbles": ("거품", 50, 100, "%"), "rays": ("빛줄기", 50, 100, "%")}


def count(amount):
    return round(FULL * amount / 100)


def parse_tank(key, v):
    """어항 막대 key 의 0–끝값 정수. 아니면 None."""
    return v if type(v) is int and 0 <= v <= TANK[key][2] else None


def refit(items, want, make, layered=True):
    """items 를 층마다 want[층] 개로 맞춤 — 앞에서부터 남기고 모자란 것만 make(층) 으로 새로. 층은 항목의 [3].
    막대를 끄는 동안 다시 깔지 않게: 떠 있던 것은 제자리에 남음."""
    have, keep = [0] * len(want), []
    for it in items:
        li = it[3] if layered else 0
        if have[li] < want[li]:
            have[li] += 1
            keep.append(it)
    return keep + [make(li) for li, n in enumerate(want) for _ in range(n - have[li])]


def parse_amount(a):
    """0–100 정수, 또는 예전 이름. 아니면 None."""
    a = OLD_AMOUNTS.get(a) if isinstance(a, str) else a
    return a if type(a) is int and 0 <= a <= 100 else None


def amount_arg(s):
    a = parse_amount(int(s) if s.isdigit() else s)
    if a is None:
        raise argparse.ArgumentTypeError("0–100 이나 few·normal·many")
    return a


def hearing(kind, visible, sound, volume):
    """지금 울릴 빗소리 크기, 조용해야 하면 None. 비·뇌우·창문 빗방울이 보이는 동안만 — 숨기면 소리도 멈춤."""
    return volume if sound and visible and kind in SOUNDY and volume else None

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


def shade(sprite, k=SHADE_K):
    """흰 글씨에 그림자를 주듯 그림의 양옆·아래 1px 에 남색 그림자를 깔아 밝은 창 위에서도 보이게. 그림자 알파는
    둘레 픽셀 알파 × k 라 옅은 알갱이엔 옅게. 어두운 창 위에선 어둠에 묻혀 거의 그대로임.
    그림은 폭 2px·높이 1px 커지고 원래 그림은 1px 오른쪽에 앉음.
    ponytail: 픽셀마다 파이썬이라 비 그림 만들기가 106 → 212ms(종류를 처음 고를 때 한 번). 거슬리면 bytes.translate 표로"""
    n, rows = sprite
    w = n + 2
    full = [bytes(4 * w)]  # 맨 위는 그림자도 없는 빈 줄 — 아래 dilation 이 y-1 을 볼 때 씀
    for skip, d in rows:
        full.append(bytes(skip + 4) + d + bytes(4 * w - skip - 4 - len(d)))
    full.append(bytes(4 * w))
    near = []  # 행마다 양옆 1px 까지 넓힌 알파
    for row in full:
        a = row[3::4]
        near.append([max(a[max(0, x - 1):x + 2]) for x in range(w)])
    sh = SHADES.get(k) or SHADES.setdefault(k, [pixel(SHADE, v * k) for v in range(256)])  # 둘레 알파 → 그림자 픽셀
    out = []
    for y in range(1, len(full)):
        src, up, here = full[y], near[y - 1], near[y]
        px = bytearray(src)
        for x in range(w):
            s = sh[max(up[x], here[x])]
            if s[3]:
                i, keep = 4 * x, 255 - src[4 * x + 3]
                for c in range(4):
                    px[i + c] = src[i + c] + s[c] * keep // 255
        out.append(trim(bytes(px)))
    return w, out


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
    return shade((n, rows))


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
    return shade((sw, rows))


def shower_set(stride):
    """창문 소나기 빗줄기. rain_set 과 같은 꼴([번쩍임][기울기][층] → {길이: 그림})이되 PANE_SHOWER_SLANT 칸만 그림
    — 16벌을 다 그리면 200ms 걸림."""
    return [[None] * PANE_SHOWER_SLANT + [[{n: place(streak(n, ly[3], ly[4], SLANTS[PANE_SHOWER_SLANT]), stride)
                                            for n in range(ly[1][0], ly[1][1] + 1)} for ly in RAIN_LAYERS]]]


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
    return shade((n, [trim(b"".join(pixel(RAIN_COLOR, 200 * (1 - k / 3) * v) for v in row)) for row in grid]))


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


def fw_set(stride):
    """불꽃 (머리, 꼬리) — 각각 [색][밝기 단계 1..6]. 꼬리는 작고 번짐이 좁음."""
    return tuple([[place(glow(core_r, halo_r, lv / FW_LEVELS, 0, 0, core, halo), stride)
                   for lv in range(1, FW_LEVELS + 1)] for core, halo in FW_COLORS]
                 for core_r, halo_r in ((1.1, 3.6), (0.6, 2.0)))


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


def snow_set(stride):
    """눈송이 그림 [층][반지름][1/4 px 위치 16벌]. 눈앞 층은 흐려 1/4 px 가 안 보이고 그림이 커서 한 벌을 16번 가리킴."""
    return [[[place(disc(rad, ly[4], ly[3], SNOW_COLOR, SNOW_RIM, fx / 4, fy / 4), stride)
              for fy in range(4) for fx in range(4)] if li != SNOW_NEAR
             else [place(disc(rad, ly[4], ly[3], SNOW_COLOR, SNOW_RIM), stride)] * 16
             for rad in ly[1]] for li, ly in enumerate(SNOW_LAYERS)]


def settled_set():
    """쌓인 눈 위에 얹는 그림(place 안 함 — lay 가 밝은 쪽을 남기며 찍음): 내려앉은 송이 [층][반지름] 과
    반짝이 [밝기 단계]."""
    return ([[disc(rad, ly[4], ly[3], SNOW_COLOR, SNOW_RIM) for rad in ly[1]] for ly in SNOW_LAYERS],
            [glow(0.5, 1.6, (lv + 1) / GLINT_LEVELS, 0, 0, (255, 255, 255), (190, 215, 255)) for lv in range(GLINT_LEVELS)])


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


def crumble(w):
    """열마다 바닥이 늦게 떨어지는 초. 4px 묶음끼리 같아서 한 덩이씩 무너짐 — 열마다 따로면 지글거림."""
    return [d for d in (random.uniform(0, SINK_CRUMBLE) for _ in range(w // 4 + 1)) for _ in range(4)][:w]


def drop(t, g, vt=math.inf):
    """t 초 동안 떨어진 px — g px/초² 로 빨라지다 종단 속도 vt px/초 에 닿으면 그 빠르기로(물 저항)."""
    return g * t * t / 2 if g * t <= vt else vt * t - vt * vt / (2 * g)


def pile_column_parts(depth=PILE_STRIP):
    """열 하나를 그릴 조각: 윗면 가장자리(높이의 소수부 16단계 알파)와 비탈 단계(−PILE_SLOPES..PILE_SLOPES)마다 위에서
    아래로 몸통(depth px). 몸통 맨 위 1px 은 테두리 색 — 소수부 알파로만 그리면 밝은 창 위에서 테두리가 점선으로 끊김.
    그 밑 4px 은 왼쪽 위 빛을 받는 비탈이면 하얗게, 등지면 푸르스름하게."""
    top, deep = (240, 244, 252), (212, 221, 238)
    edges = [pixel(SNOW_RIM, 255 * q / 16) for q in range(16)]
    bodies = []
    for s in range(-PILE_SLOPES, PILE_SLOPES + 1):
        tint, k = (PILE_LIT if s > 0 else PILE_SHADOW), abs(s) / PILE_SLOPES
        col = [pixel(PILE_RIM, 255)]
        for d in range(1, depth):
            c = [a + (b - a) * min(1.0, d / 14) for a, b in zip(top, deep)]
            m = k * max(0.0, 1 - (d - 1) / 4)
            col.append(pixel(tuple(int(v + (t - v) * m) for v, t in zip(c, tint)), 255))
        bodies.append(b"".join(col))
    return edges, bodies


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
    return shade((n, rows))


def soap_balls(r, hues):
    """비눗방울 hues 벌: 거의 투명한 속에 무지갯빛 테두리(각도를 따라 색이 돌고, 벌마다 1/hues 바퀴씩 돌려 둠)와
    왼쪽 위 반짝임. 알파와 그림자는 색과 무관해 한 번만 셈 — 그림자는 색 없는 그림에 깔고 벌마다 색만 더함
    (그림자 픽셀 = 원래 + 그림자 × (255 − 알파) 라 색이 덧셈으로 떨어짐). 벌마다 shade 를 다 돌리면 32벌 0.3초."""
    n = int(math.ceil(2 * r)) + 3
    c = n / 2 - 0.5
    rows, dots = [], []  # dots: 색을 칠할 픽셀 (행, 바이트 자리, 각도 칸 0–255, 색 몫 a·(1−반짝임), 흰 몫 a·반짝임)
    for y in range(n):
        row = b""
        for x in range(n):
            dx, dy = x - c, y - c
            d = math.hypot(dx, dy)
            cov = min(1.0, max(0.0, r + 0.5 - d))
            rim = max(0.0, 1 - abs(d - r + 0.6) / 1.1)
            shine = max(0.0, 1 - math.hypot(dx + r * 0.45, dy + r * 0.45) / max(0.8, r * 0.28))
            a = 235 * cov * max(0.08, rim, shine)
            row += pixel((0, 0, 0), a)
            if int(a):  # 반짝임 쪽은 하얗게: 채널 = a·(f + (1−f)·반짝임) = f·a(1−반짝임) + a·반짝임
                dots.append((y, 4 * (x + 1), int(math.atan2(dy, dx) / math.tau * 256) & 255, a * (1 - shine), a * shine))
        rows.append(trim(row))
    w, base = shade((n, rows))  # 그림은 1px 오른쪽에 앉음 — dots 의 x + 1
    base = [bytes(skip) + d + bytes(4 * w - skip - len(d)) for skip, d in base]
    film = [colorsys.hsv_to_rgb(i / 256, 0.45, 1.0) for i in range(256)]
    out = []
    for k in range(hues):
        off, px = k * 256 // hues, [bytearray(b) for b in base]
        for y, i, ang, m, s in dots:
            fr, fg, fb = film[(ang + off) & 255]
            row = px[y]
            row[i] += int(fb * m + s)
            row[i + 1] += int(fg * m + s)
            row[i + 2] += int(fr * m + s)
        out.append((w, [trim(bytes(b)) for b in px]))
    return out


def aurora_field(w, rows, rng):
    """오로라 무늬: rows 행의 행마다 premultiplied BGRA 픽셀 바이트(폭 w, 끝이 처음과 이어짐). 커튼 AURORA_RIBBONS 겹이
    겹쳐 있고, 커튼마다 아랫단이 큰 굽이와 잔 굽이를 섞어 구불거림. 아랫단 둘레는 옅은 초록 빛무리, 밑은 가는 분홍
    술로 빠르게 사라지고, 위로는 무작위 자리 · 굵기 · 세기의 빛살 수백 줄이 제 높이만큼 뻗음. 아랫단이 가파르게 접힌
    곳(주름)은 더 밝고, 커튼마다 옆으로 짙어졌다 끊겼다 함. 색은 아랫단에서 잰 높이로 — 흰빛 초록 → 초록 → 청록 → 보라.
    픽셀마다 셈함: 열의 세로 모양은 커튼마다 미리 셈한 본(아랫단에서 잰 높이 → 색 · 세기)을 그 열의 아랫단 깊이만큼
    밀어 잘라 쓰고, 본은 픽셀 하나에 32비트 칸 넷(B·G·R·A)을 담은 큰 정수라 밀기 · 곱하기 · 더하기가 C 에서 한 번에
    됨 — 파이썬으로 픽셀마다 셈하면 2560×860 에 몇 초. 알파 칸은 커튼마다 세기 × 가장 센 색 채널을 더한 것이라 늘
    색 칸 이상. 넘친 칸은 255 에 멈춰 밝은 곳이 하얗게 바램."""
    def noise(ks, n, amp):  # 폭에 정수 번 도는 사인 n 개, 진폭이 1/k 로 줄어 굽이가 자연스러움
        ws = [(k, rng.uniform(0, math.tau), amp * rng.uniform(0.5, 1) / k) for k in rng.sample(ks, n)]
        return [sum(a * math.sin(math.tau * k * x / w + p) for k, p, a in ws) for x in range(w)]

    def color(d):  # 아랫단에서 잰 높이 → 색 0–1
        lo = max((s for s in AURORA_COLORS if s[0] <= d), default=AURORA_COLORS[0])
        hi = min((s for s in AURORA_COLORS if s[0] > d), default=AURORA_COLORS[-1])
        t = min(1.0, max(0.0, (d - lo[0]) / (hi[0] - lo[0]))) if hi[0] > lo[0] else 0.0
        return [(a + (b - a) * t) / 255 for a, b in zip(lo[1], hi[1])]

    span = 2 * rows  # 본의 길이(픽셀). 칸 t 는 아랫단 위 rows − t 픽셀
    glow = color(0.05)

    def pack(tones, f):  # 높이 d → (색 세기, 빛무리 세기) 를 본 하나로: 칸마다 1023 이 세기 1
        lanes = array.array("I")
        for t in range(span):
            d = (rows - t) / rows
            i, g = f(d)
            (r, gr, b), (r2, g2, b2) = tones[t], glow
            lanes.extend((round(1023 * (i * b + g * b2)), round(1023 * (i * gr + g * g2)), round(1023 * (i * r + g * r2)),
                          round(1023 * (i * max(r, gr, b) + g * max(glow)))))
        return int.from_bytes(lanes.tobytes(), "little")

    assert array.array("I").itemsize == 4
    ribbons = []
    for base, power, reach in AURORA_RIBBONS:
        # 아랫단 밑은 pw² 만큼 늘려 셈 — 뒤 커튼일수록 밑이 흐리고 분홍 술도 앞 커튼에만 짙음
        tones = [color((rows - t) / rows * (power * power if t > rows else 1)) for t in range(span)]
        fade = lambda d, pw=power: math.exp(d * pw * pw / 0.012) if d < 0 else 1.0
        hem_t = pack(tones, lambda d, pw=power: (fade(d) * 0.5 * pw * math.exp(-max(d, 0) / 0.025), 0.12 * pw * math.exp(-abs(d) / 0.05)))
        ray_t = [pack(tones, lambda d, h=reach * (0.35 + 0.65 * (q + 0.5) / AURORA_RAYQ): (fade(d) * math.exp(-max(d, 0) / h), 0))
                 for q in range(AURORA_RAYQ)]  # 빛살 높이를 AURORA_RAYQ 단계로
        hem = [min(0.9, max(0.12, base + a + b)) for a, b in zip(noise(range(1, 4), 2, 0.12), noise(range(4, 16), 4, 0.15))]
        env = [min(1.0, max(0.0, 0.6 + e)) ** 1.5 for e in noise(range(1, 7), 3, 0.8)]
        streak = [0.0] * w
        for _ in range(w // 6):  # 2560 폭에 430 줄
            c, s, a = rng.uniform(0, w), rng.uniform(0.7, 4.5), rng.uniform(0.2, 1.2)
            for x in range(int(c - 3 * s), int(c + 3 * s) + 1):
                streak[x % w] += a * math.exp(-((x - c) / s) ** 2 / 2)
        cols = []
        for x in range(w):
            k = power * env[x] * (1 + min(1.0, 0.35 * abs(hem[(x + 1) % w] - hem[x - 1]) * rows))
            ray = 0.15 + 0.85 * (1 - math.exp(-streak[x]))
            cols.append((128 * (rows - round(hem[x] * rows)), round(64 * k), round(64 * k * ray),
                         ray_t[min(AURORA_RAYQ - 1, int(ray * AURORA_RAYQ))]))
        ribbons.append((hem_t, cols))
    mask, sat = (1 << 128 * rows) - 1, bytes([0] + [255] * 255)
    out = []
    for x in range(w):
        acc = 0
        for hem_t, cols in ribbons:
            sh, kh, kr, ray_t = cols[x]
            if kh:
                acc += kh * (hem_t >> sh & mask) + kr * (ray_t >> sh & mask)
        b = acc.to_bytes(rows * 16, "little")  # 칸마다 1023 × 64 ≈ 255 · 256 이라 둘째 바이트가 0–255, 셋째는 넘친 몫
        out.append((int.from_bytes(b[1::4], "little") | int.from_bytes(b[2::4].translate(sat), "little")).to_bytes(rows * 4, "little"))
    cm, stride = b"".join(out), rows * 4  # 열마다 이어 붙인 것 → 행으로 돌려 세움
    rows_out = []
    for j in range(rows):
        px = bytearray(w * 4)
        for c in range(4):
            px[c::4] = cm[j * 4 + c::stride]
        rows_out.append(bytes(px))
    return rows_out


def subpixel(rows, n):
    """행(BGRA 바이트)마다 1/n 픽셀씩 옮겨 본 n 벌 — p 벌째는 (n − p)/n · 제 픽셀 + p/n · 오른쪽 이웃(끝은 처음과 이어짐).
    slide 가 정수 px 아래 몫으로 벌을 골라 계단 없이 밀게. 두 몫의 칸 합이 255 를 안 넘어 큰 정수 하나로 더함."""
    tabs = [(bytes(v * (n - p) // n for v in range(256)), bytes(v * p // n for v in range(256))) for p in range(1, n)]
    out = []
    for r in rows:
        right, size = r[4:] + r[:4], len(r)
        out.append((r, *((int.from_bytes(r.translate(a), "little") + int.from_bytes(right.translate(b), "little"))
                         .to_bytes(size, "little") for a, b in tabs)))
    return out


# 유성 표: 심선에서 거리(1/8 px) → 단면 세기 · 머리에서 거리²(1/4 px²) → 머리 빛 · 꼬리 32 마디 색 × 알파 → 픽셀
METEOR_CROSS = [math.exp(-(i / 8) ** 2 / (2 * METEOR_CORE ** 2)) + METEOR_GLOW_K * math.exp(-(i / 8) ** 2 / (2 * METEOR_GLOW ** 2))
                for i in range(METEOR_R * 8 + 1)]
METEOR_BLOOM = [METEOR_HEAD_K * math.exp(-(i / 4) / (2 * METEOR_HEAD_R ** 2)) for i in range(METEOR_R ** 2 * 4 + 1)]
METEOR_PX = [[pixel(tuple(int(a + (b - a) * min(1.0, c / 31 * 1.5)) for a, b in zip(METEOR_HEAD, METEOR_TAIL)), q)
              for q in range(256)] for c in range(32)]


def meteor_streak(hx, hy, ux, uy, length, k):
    """유성 한 줄: 머리 (hx, hy) 에서 (ux, uy) 반대쪽으로 length px 꼬리. 소수 좌표 그대로 픽셀마다 셈해 어느 각도 ·
    자리에서도 계단이나 떨림이 없음. 단면은 가는 심에 옅은 번짐, 꼬리 끝으로 exp(−3s) · (1 − s) 만큼 옅어지고, 머리에
    둥근 빛. 색은 머리 흰빛 초록 → 꼬리 옅은 파랑. k 는 밝기 배수(1 넘으면 심이 하얗게 차 굵어 보임).
    [(y, x, premultiplied BGRA 바이트)…] — 꼬리 250px 에 2,700–3,300px · 1.5–1.7ms."""
    R, rows, inv, ty = METEOR_R, [], 1 / length, hy - uy * length
    cross, bloom, pxs, zero = METEOR_CROSS, METEOR_BLOOM, METEOR_PX, METEOR_PX[0][0]
    for y in range(math.floor(min(hy, ty) - R), math.ceil(max(hy, ty) + R) + 1):
        ry = y - hy
        if abs(uy) > 1e-6:  # 이 행에서 심선이 R 안에 드는 꼬리 구간
            s0, s1 = sorted(((-ry - R) / uy, (-ry + R) / uy))
            s0, s1 = max(-R, s0), min(length, s1)
        else:
            s0, s1 = -R, length
        if s0 > s1:
            continue
        xa, xb = hx - ux * s0, hx - ux * s1
        x0, out = math.floor(min(xa, xb) - R), []
        for x in range(x0, math.ceil(max(xa, xb) + R) + 1):
            rx = x - hx
            d = abs(rx * uy - ry * ux)
            if d >= R:
                out.append(zero)
                continue
            s, r2 = -(rx * ux + ry * uy), rx * rx + ry * ry
            v = bloom[int(r2 * 4)] if r2 < R * R else 0.0
            c = 0
            if 0 <= s < length:
                f = s * inv
                v += math.exp(-3 * f) * (1 - f) * cross[int(d * 8)]
                c = int(f * 32)
            out.append(pxs[c][min(255, int(255 * k * v))])
        rows.append((y, x0, b"".join(out)))
    return rows


def glint(px, stride, w, h, rows):
    """meteor_streak 의 행들을 바이트마다 밝은 쪽을 남기며 찍음 — 덮어쓰면 둘레의 옅은 픽셀이 밑의 오로라를 검게 파먹음.
    premultiplied 라 채널마다 큰 쪽을 골라도 색 ≤ 알파가 지켜짐. 화면 밖으로 나간 몫은 잘라 냄.
    ponytail: map(max) 라 유성 하나에 0.5ms 쯤. 수십 개를 한꺼번에 띄우려면 큰 정수 SWAR 로"""
    for y, x, data in rows:
        if 0 <= y < h:
            a = x * 4
            lo, hi = max(a, 0), min(a + len(data), w * 4)
            if lo < hi:
                o = y * stride
                px[o + lo:o + hi] = bytes(map(max, px[o + lo:o + hi], data[lo - a:hi - a]))


def lay(px, stride, w, h, sprite, x, y):
    """(크기, [(건너뜀, 데이터) 행…]) 그림을 왼쪽 위 (x, y) 에 glint 로 찍음 — 쌓인 눈 위에 덮어 찍으면 옅은 가장자리가
    흰 몸통에 구멍을 냄."""
    glint(px, stride, w, h, [(y + j, x + skip, d) for j, (skip, d) in enumerate(sprite[1]) if d])


def pane_drop(r):
    """유리에 맺힌 물방울: 거의 투명한 몸통, 위 테두리는 남색으로 어둡고 아래는 밝은 초승달, 왼쪽 위에 반짝이는 점 —
    둥근 렌즈가 위쪽 어둠과 아래쪽 빛을 뒤집어 비추는 모양. 밝은 창 위에서는 남색 테두리가, 어두운 창 위에서는 밝은
    초승달이 보임."""
    n = int(math.ceil(2 * r)) + 3
    c = n / 2 - 0.5
    rows = []
    for y in range(n):
        row = b""
        for x in range(n):
            dx, dy = x - c, y - c
            d = math.hypot(dx, dy)
            cov = min(1.0, max(0.0, r + 0.5 - d))
            edge = max(0.0, 1 - abs(d - r + 0.7) / 1.2) if r >= 1.5 else 1.0
            up = -dy / max(r, 0.5)  # 1 위 · −1 아래
            dark, lit = edge * max(0.0, up) ** 0.7, edge * max(0.0, -up) ** 1.2
            shine = max(0.0, 1 - math.hypot(dx + r * 0.35, dy + r * 0.35) / max(0.7, r * 0.3))
            if shine > 0.05 or lit > dark:
                col, a = (255, 255, 255), 230 * max(shine, lit * 0.8, 0.12)
            else:
                col, a = (36, 44, 72), 200 * max(dark * 0.75, 0.12)
            row += pixel(col, a * cov)
        rows.append(trim(row))
    return shade((n, rows))


def fog_field(w, rows, rng):
    """안개 무늬: rows 행의 행마다 알파 0–255 바이트(폭 w, 끝이 처음과 이어짐). FOG_KNOT 행마다 사인 넷을 겹친 가로
    무늬(폭에 정수 번 돌아 이어짐)를 뽑고, 그 사이 행은 FOG_MIX 단계로 섞어 단계마다 한 번만 셈."""
    def line():  # 옅은 바탕(0.3) 위에 화면 폭의 1/2–1/9 크기 뭉치가 짙게
        waves = [(k, rng.uniform(0, math.tau), k ** -0.6) for k in rng.sample(range(2, 10), 4)]
        tot = sum(a for _, _, a in waves)
        return [0.3 + 0.7 * min(1.0, max(0.0, 0.5 + 0.9 * sum(a * math.sin(math.tau * k * x / w + p)
                                                              for k, p, a in waves) / tot)) ** 1.3 for x in range(w)]

    knots = [line() for _ in range(rows // FOG_KNOT + 2)]
    mixes, out = {}, []
    for j in range(rows):
        i, s = divmod(j * FOG_MIX // FOG_KNOT, FOG_MIX)
        if (i, s) not in mixes:
            t = s / FOG_MIX
            t = t * t * (3 - 2 * t)
            mixes[i, s] = bytes(int(255 * (p + (q - p) * t)) for p, q in zip(knots[i], knots[i + 1]))
        out.append(mixes[i, s])
    return out


def ray_shape(top_w, length, rng):
    """빛줄기 한 줄기: 행마다 (가운데에서 왼쪽 끝까지 px, 알파 바이트). 가는 빛살 3–5 가닥이 겹친 단면 — 가닥마다
    자리·굵기·세기·끝나는 깊이가 달라 결이 보이고, 자리를 폭 비율로 두어 내려가며 같이 벌어짐. 바깥은 sin² 로 사그라듦.
    위 몇 줄은 물 위에서 들어오듯 빠르게 밝아지고, 아래로 옅어져 끝에서 0. 단면은 깊이 1/32 마다 256 칸으로 한 번 셈하고
    폭이 바뀔 때만 그 폭으로 늘려 씀(폭마다 픽셀을 다 셈하면 2560×1440 에서 세 모양 0.2초, 이렇게 0.05초).
    행마다는 단면에 밝기를 bytes.translate 로 곱함."""
    strands = [(rng.uniform(0.2, 0.8), rng.uniform(0.06, 0.16), rng.uniform(0.45, 1.0), rng.uniform(0.5, 1.0))
               for _ in range(rng.randint(3, 5))]  # (가로 자리 0–1, 굵기, 세기, 끝나는 깊이 0–1)
    bases, profiles, scales, rows = {}, {}, {}, []
    for j in range(length):
        u = j / length
        wj = max(2, int(top_w * (1 + RAY_SPREAD * u)))
        prof = profiles.get(wj)
        if prof is None:
            m = int(u * 32)
            base = bases.get(m)
            if base is None:
                live = [(c, s, k * min(1.0, max(0.0, (end - m / 32) / 0.3))) for c, s, k, end in strands]
                base = bases[m] = [255 * math.sin(math.pi * t) ** 2 * min(1.0, 0.45 + 0.55 * sum(
                    k * math.exp(-((t - c) / s) ** 2) for c, s, k in live)) for t in ((i + 0.5) / 256 for i in range(256))]
            prof = profiles[wj] = bytes(int(base[(2 * x + 1) * 128 // wj]) for x in range(wj))
        # 수면 가까이 조금 더 밝고(1 + 0.4 e^-u/0.05), 아래로 길게 옅어져 끝에서 0
        q = int(255 * RAY_ALPHA * (1 - u) ** 1.3 * (1 + 0.4 * math.exp(-u / 0.05)) / 1.4 * min(1.0, (j + 1) / 14))
        tab = scales.get(q)
        if tab is None:  # 알파 2 아래는 0 — 옅은 가장자리를 잘라 겹친 줄기를 덜 지움
            tab = scales[q] = bytes(v * q // 255 if v * q // 255 >= 2 else 0 for v in range(256))
        a = prof.translate(tab)
        lead = len(a) - len(a.lstrip(b"\0"))  # 투명한 앞뒤는 자름 — 겹친 줄기를 덜 지움
        rows.append((lead - wj // 2, a.strip(b"\0") or b"\0"))
    return rows


def tint_rays(shapes, tints):
    """ray_shape 의 알파 행들에 RAY_COLOR 를 밝기 단계마다 입혀 행마다 그 행의 물빛 위에 섞음
    → [모양][단계] = [(왼쪽 끝 px, 픽셀 바이트) 행…]. 채널마다 bytes.translate 표로 하고, 물빛이 같은 행(2560×1440 에서
    위 45% 가 6 가지)은 이어 붙여 한 번에 섞어 행마다 파이썬을 덜 돎. 섞는 셈은 한 번에 반올림 — 두 번 내림하면
    가장자리가 물빛보다 1 어두운 테두리가 됨."""
    tables, out = {}, []
    for shape in shapes:
        levels = []
        for k in range(RAY_LEVELS):
            rows = []
            for under, group in itertools.groupby(zip(shape, tints), key=lambda rt: rt[1]):
                group = [r for r, _ in group]
                tab = tables.get((under, k))
                if tab is None:
                    a_tab = [v * (k + 1) // RAY_LEVELS for v in range(256)]
                    tab = tables[under, k] = [bytes((a * col + under[c] * (255 - a) + 127) // 255 for a in a_tab)
                                              for c, col in enumerate((*RAY_COLOR[::-1], 255))]
                alphas = b"".join(d for _, d in group)
                px = bytearray(len(alphas) * 4)
                px[0::4], px[1::4], px[2::4], px[3::4] = (alphas.translate(t) for t in tab)
                px, o = bytes(px), 0
                for lead, d in group:
                    rows.append((lead, px[o:o + len(d) * 4]))
                    o += len(d) * 4
            levels.append(rows)
        out.append(levels)
    return out


def ray_level(lo, hi, s):
    """밝기 비율 lo–hi 사이를 s(−1…1)로 오가는 줄기의 밝기 단계 번호 (0 … RAY_LEVELS − 1, 단계 k 의 밝기는 (k+1)/단계 수)."""
    return min(RAY_LEVELS - 1, max(0, round((lo + (hi - lo) * (0.5 + 0.5 * s)) * RAY_LEVELS) - 1))


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


def weed(height, rng, dark=1.0):
    """해초 한 포기: 아래에서 위로 행마다 불투명 픽셀 바이트. 폭 2–3px 에 몇 줄마다 잎이 양옆으로 돋음. dark 는 색 배율."""
    rows, wide = [], rng.random() < 0.5
    cols = [pixel(tuple(int(v * dark) for v in c), 255) for c in WEED_COLORS]
    for j in range(height):
        u = j / height
        col = cols[min(2, int(u * 3))]
        n = (3 if wide and u < 0.7 else 2) if u < 0.9 else 1
        leaf = j % 9 in (4, 5) and u < 0.85
        rows.append(col * (n + leaf * 2))
    return rows


def tuft(x, rng):
    """해초 덤불: 한 자리(x)에 2–3 포기 [(x, 행, 위상, 빠르기, 흔들림)]. 뒤 포기는 낮고 어둡게 먼저, 제일 큰 포기는
    마지막(맨 앞). 옆 포기는 x ± 3–7px — 자리는 화면 끝에서 10px 안쪽이라 안 넘침. 흔들림은 행마다 (p, q, 반 폭):
    WEED_SWAY·u²·sin(t − 2.4u) = sin t · p − cos t · q 라 그릴 때 포기마다 sin·cos 한 번 (행마다 부르면 덤불이 두 배 느림)."""
    top, phase, speed = rng.randint(*WEED_H), rng.uniform(0, math.tau), rng.uniform(0.6, 1.3)
    back = [(x + rng.choice((-1, 1)) * rng.randint(3, 7), weed(int(top * rng.uniform(0.45, 0.8)), rng, 0.72),
             phase + rng.uniform(0.4, 1.2), speed * rng.uniform(0.85, 1.15)) for _ in range(rng.randint(1, 2))]
    sway = lambda rows: [(WEED_SWAY * u * u * math.cos(u * 2.4), WEED_SWAY * u * u * math.sin(u * 2.4), len(d) // 8)
                         for j, d in enumerate(rows) for u in (j / len(rows),)]
    return [(*b, sway(b[1])) for b in (*back, (x, weed(top, rng), phase, speed))]


def tinted(rows, colors, under):
    """글자 판 → pet.stamp 조각 (pet.segments 꼴). colors 는 글자 → (색, 알파) — 반투명 칸은 물빛 under 위에 미리
    섞음. 행 안의 빈 칸은 끊어서 밑에 찍힌 물고기를 안 지움."""
    cell = {c: over((1, [(0, pixel(col, a))]), under)[1][0][1] * pet.SCALE for c, (col, a) in colors.items()}
    out = []
    for y, line in enumerate(rows):
        x = 0
        while x < len(line):
            if line[x] == ".":
                x += 1
                continue
            start = x
            while x < len(line) and line[x] != ".":
                x += 1
            data = b"".join(cell[c] for c in line[start:x])
            out += [(y * pet.SCALE + sy, start * pet.SCALE * 4, data) for sy in range(pet.SCALE)]
    return out


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
    fps = 120 if data.get("fps") == 180 else data.get("fps")  # 0.2.6 까지 있던 180
    if fps in FPS_IDS.values():
        ok["fps"] = fps
    for k in TANK:
        if parse_tank(k, data.get(k)) is not None:
            ok[k] = data[k]
    if isinstance(data.get("drag"), bool):
        ok["drag"] = data["drag"]
    if isinstance(data.get("sound"), bool):
        ok["sound"] = data["sound"]
    if isinstance(data.get("volume"), int) and parse_amount(data["volume"]) is not None:
        ok["volume"] = data["volume"]
    return ok


class Weather:
    def __init__(self, kind, amount, animals=(), fps=FPS, tank=None, drag=False, sound=False, volume=VOLUME):
        self.kind, self.amount, self.visible, self.fps = kind, amount, True, fps
        self.sound, self.volume, self.rain_player = sound, volume, rain_sound.Player()  # 빗소리 켰나 · 크기 % · 트는 것
        self.tank = {k: (tank or {}).get(k, TANK[k][1]) for k in TANK}  # 어항 막대. 어항이 아닐 때 바꿔도 남겨 둠
        self.drag, self.catching = drag and not MAC, False  # 동물 집기를 켰나 · 지금 창이 클릭을 받나
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
        # 바닥이 가려는 모양 · 내려앉는 중이면 (시작 모양, 시각) · 열마다 늦게 떨어지는 초(모래가 무너지듯)
        self.goal, self.fall, self.crumble = self.base, None, crumble(self.w)
        self.strip_h = PILE_STRIP + self.rise
        self.surface = Surface(l, t, self.w, self.h, SURFACE_CLASS, **({} if MAC else {"on_mouse": self.press}))
        self.on_top = MAC or overlay.on_top("weather")  # 런처의 '항상 위'. 맥은 런처가 없음
        if not self.on_top:
            self.surface.topmost(False)
        self.stride = self.w * 4
        s = self.stride
        self.snow_sprites = snow_set(s)
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
        self.panel = None  # 숨긴 채 띄워 둔 설정 창 프로세스
        # 맥은 메뉴 막대를 누르면 메뉴가 뜨는 게 기본이라 메뉴만. 윈도우는 오른쪽 클릭도 같은 설정 창 — 메뉴와 창이
        # 따로 있으면 한쪽에만 생기는 것(빗소리를 비·뇌우에서만 보이기 등)이 갈라졌음
        if MAC:
            self.tray = Tray(TRAY_CLASS, ICON_FILE, "날씨", self.menu, self.commands.put)
        else:
            self.tray = Tray(TRAY_CLASS, ICON_FILE, "날씨", None, self.commands.put, on_left=lambda: self.commands.put(PANEL))
            self.start_panel()
        self.last = self.last_settle = self.last_topmost = time.perf_counter()
        self.reset()
        self.hear()
        self.surface.show(True)
        if self.rise:
            threading.Thread(target=self.watch_frames, daemon=True).start()

    def watch_frames(self):
        """작업 표시줄 틀을 FRAMES_EVERY 초마다 읽어 그리는 스레드에 넘김 — 앱을 열고 닫으면 단추 묶음 폭이 바뀜.
        전체 화면 앱(F11 등)이 작업 표시줄을 가리면 틀이 없는 것으로 봄 — UI 자동화는 가려진 단추 자리도 그대로
        알려 줌. 전체 화면은 싸게 알 수 있어 FULLSCREEN_EVERY 마다 보고, 바뀌면 바로 다시 냄."""
        full, last = None, -math.inf
        while True:
            fs = taskbar.fullscreen_app()
            if fs != full or time.monotonic() - last >= FRAMES_EVERY:
                full, last = fs, time.monotonic()
                self.next_base = floor_heights(self.w, self.top + self.h, self.left, self.rise,
                                               [] if fs else taskbar.frames())
            time.sleep(FULLSCREEN_EVERY)

    def set_base(self, base):
        """바닥 모양을 바꿈. 틀이 사라진 열의 눈은 그대로 새 바닥으로 떨어지고(HUD 를 끄거나 앱을 닫으면 위에
        쌓였던 눈이 내려앉아 옆과 섞임), 틀이 새로 솟은 열은 틀이 밀고 올라온 만큼 눈이 묻힘. 발밑에 틀이 단보다
        높이 솟은 동물도 그 뒤에 묻혔다가 빼꼼 나옴(pet.follow) — 전체 화면을 풀 때도, 단추 묶음이 넓어질 때도."""
        h = self.pile.h
        for x, (a, b) in enumerate(zip(self.base, base)):
            if b > a:
                h[x] = max(0.0, h[x] - (b - a))
        for p in self.pets.values():
            a, b = p.feet()
            if p.ground is not None and max(base[a:b], default=0) > p.ground + pet.LEDGE and \
                    any(n > o for o, n in zip(self.base[a:b], base[a:b])):
                p.bury()
        self.base = self.pile.base = base

    def sink(self, now):
        """바닥을 goal 로 한 걸음. 솟는 열은 바로(작업 표시줄은 확 나타남), 낮아지는 열은 SINK_G 로 떨어짐 — 바닥
        위의 모래·눈·장식·동물은 base 를 따라 같이 내려옴. 어항은 물속이라 SINK_WATER_V 를 안 넘게 천천히.
        바닥이 바뀌었으면 True."""
        start, t0 = self.fall
        t, (g, vt) = now - t0, (SINK_WATER_G, SINK_WATER_V) if self.kind == "aquarium" else (SINK_G, math.inf)
        base = [n if n >= s else max(n, s - int(drop(max(0.0, t - d), g, vt)))
                for n, s, d in zip(self.goal, start, self.crumble)]
        if base == self.goal:
            base, self.fall = self.goal, None
        if base == self.base:
            return False
        self.set_base(base)
        return True

    # ── 트레이 ──
    def menu(self):
        return [*((label, cid, key == self.kind) for cid, (key, label) in KINDS.items()),
                None,
                ("양", [("%d%%" % p, cid, p == self.amount) for cid, p in AMOUNTS.items()]),
                ("부드러움", [("%dfps" % n, cid, n == self.fps) for cid, n in FPS_IDS.items()]),
                None,
                ("동물", [*((PET_NAMES[a], cid, a in self.pets) for cid, a in PETS.items()),
                          *(() if MAC else (None, ("집어서 옮기기", DRAG, self.drag)))]),
                ("빗소리", [("비·뇌우에 켜기", SOUND, self.sound), None,
                          *(("%d%%" % p, cid, p == self.volume) for cid, p in VOLUMES.items())]),
                ("보이기", SHOW, self.visible),
                ("로그인 시 실행" if MAC else "Windows 시작 시 실행", AUTOSTART, startup.is_on(RUN_NAME, __file__)),
                None,
                ("끝내기", EXIT, False)]

    def handle(self, cid):
        if isinstance(cid, tuple):  # 설정 창의 막대 값 — 양이나 어항 막대. 끄는 동안에도 0.1초마다 옴
            key, value = cid
            if key == "volume":
                self.volume = value
                self.save()
                return
            if key not in TANK:
                self.amount = value
            else:
                self.tank[key] = value
            if key not in TANK or self.kind == "aquarium":  # 어항이 아니면 어항 막대는 남기기만. 어항을 고를 때 씀
                self.retune()
            self.save()
            return
        elif cid == PANEL:
            self.open_panel()
            return
        elif cid in KINDS:
            self.kind = KINDS[cid][0]
        elif cid in AMOUNTS:
            self.amount = AMOUNTS[cid]
        elif cid in (SOUND, *VOLUMES):  # 소리는 poll 이 handle 다음에 hear 로 맞춤
            if cid == SOUND:
                self.sound = not self.sound
            else:
                self.volume = VOLUMES[cid]
            self.save()
            return
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
        elif cid == DRAG:
            self.drag = not self.drag and not MAC
            self.press(False)  # 끄면 들고 있던 동물을 놓음. 클릭 통과는 다음 프레임 aim 이 되돌림
            self.save()
            return
        elif cid == SHOW:
            self.visible = not self.visible
            self.surface.show(self.visible)
            self.press(False)
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
                                            "fps": self.fps, **self.tank, "drag": self.drag,
                                            "sound": self.sound, "volume": self.volume}), encoding="utf-8")
        except OSError:
            pass  # 못 남겨도 지금 화면은 바뀌었으니 넘어감

    def start_panel(self):
        """그리는 루프가 tk 가 아니라서 설정 창은 따로 띄우고, 누른 것을 한 줄씩 받아 메뉴 명령처럼 처리함.
        켤 때 숨긴 채 띄워 둠 — 누를 때마다 새로 띄우면 파이썬·tk 를 띄우느라 0.35–0.57초 걸렸음. 대신 54MB 를 늘 씀"""
        me = [] if getattr(sys, "frozen", False) else [str(Path(__file__).resolve())]  # 릴리스 exe 는 스크립트 없이 자기 자신
        self.panel = subprocess.Popen([sys.executable, *me, "--panel"], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                      text=True, encoding="utf-8")
        threading.Thread(target=self.read_panel, args=(self.panel,), daemon=True).start()

    def open_panel(self):
        """띄워 둔 설정 창에 지금 상태를 한 줄로 보내 보이게 함. 꺼져 있으면(끝내기 직전 등) 새로 띄움."""
        if not self.panel or self.panel.poll() is not None:
            self.start_panel()
        state = {"kind": self.kind, "amount": self.amount, "pet": list(self.pets), "show": self.visible,
                 "auto": startup.is_on(RUN_NAME, __file__), "fps": self.fps, "tank": self.tank, "drag": self.drag,
                 "sound": self.sound, "volume": self.volume}
        ctypes.windll.user32.AllowSetForegroundWindow(-1)  # 방금 트레이를 누른 건 이 프로세스라 앞으로 올릴 권한을 넘김
        try:
            self.panel.stdin.write(json.dumps(state) + "\n")
            self.panel.stdin.flush()
        except OSError:
            self.panel = None  # 막 꺼진 참 — 다음에 누르면 새로 띄움

    def read_panel(self, proc):
        for line in proc.stdout:
            word, _, arg = line.partition(" ")
            if arg.strip().isdigit() and (parse_amount(int(arg)) is not None if word in ("amount", "volume") else
                                          word in TANK and parse_tank(word, int(arg)) is not None):
                self.commands.put((word, int(arg)))
            elif word.strip().isdigit() and int(word) in (*KINDS, *FPS_IDS, *PETS, DRAG, SOUND, SHOW, AUTOSTART, EXIT):
                self.commands.put(int(word))

    def poll(self):
        """트레이에서 온 명령을 처리. None 이면 트레이가 닫힌 것. 끝내야 하면 True."""
        try:
            while True:
                cid = self.commands.get_nowait()
                if cid is None:
                    return True
                self.handle(cid)
                self.hear()
        except queue.Empty:
            return False

    def hear(self):
        """빗소리를 지금 종류·보이기·설정에 맞춤. 같으면 아무것도 안 함 — 명령마다 불러도 됨."""
        self.rain_player.set(hearing(self.kind, self.visible, self.sound, self.volume))

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
            f[1] += f[2] * (1 + SNOW_FLUTTER * math.sin(1.7 * f[5] + 2.3 * now * f[6])) * dt  # 팔랑임
            f[0] = (f[0] + wind * layer[6] * dt) % w
            x = f[0] + (math.sin(f[5] + now * f[6]) + 0.3 * math.sin(3.1 * f[5] + 2.9 * now * f[6])) * layer[5]
            xi, yi = int(x), int(f[1])
            col = min(max(xi + n // 2, 0), w - 1)
            # 쌓인 눈이나 바닥에 닿음. 먼 층은 쌓이지 않고 그 뒤로 사라지고, 눈앞 층은 그 앞을 지나 화면 밑변까지
            if yi + n >= (h if f[3] == SNOW_NEAR else h - base[col] - ph[col]):
                if layer[7]:
                    self.pile.add(col, layer[1][f[4]])
                    self.landed.append([x, col, f[3], f[4], 0.0, random.uniform(*LAND_T)])
                f[:] = self.new_flake(f[3], True)
                continue
            if yi < 0 or xi < 0 or xi + n > w:
                continue
            stamp(px, stride, xi, yi, sprites[int((f[1] - yi) * 4) * 4 + int((x - xi) * 4)][1])
        self.settled(dt)

    def settled(self, dt):
        """쌓인 눈 위: 내려앉은 송이는 표면에 얹혀 LAND_T 동안 한 단계씩 작아지다 스미고, 눈이 1.5px 넘게 쌓인 열에는
        반짝이가 GLINT_T 동안 켜졌다 꺼짐. 표면 높이를 프레임마다 다시 읽어 더미가 꺼지거나 솟아도 따라감."""
        px, stride, w, h, ph, base = self.surface.pixels, self.stride, self.w, self.h, self.pile.h, self.base
        flakes, glints = self.settled_sprites
        live = []
        for s in self.landed:  # [x, 열, 층, 반지름 번호, 나이, 수명]
            s[4] += dt
            if s[4] >= s[5]:
                continue
            live.append(s)
            ri = s[3] - int(s[4] / s[5] * (s[3] + 1))
            sp = flakes[s[2]][ri]
            r = SNOW_LAYERS[s[2]][1][ri]
            lay(px, stride, w, h, sp, int(s[0] - sp[0] / 2), int(h - base[s[1]] - ph[s[1]] - 0.4 * r - sp[0] / 2))
        self.landed = live
        self.glint_due += GLINT_RATE * w / 2560 * dt
        while self.glint_due >= 1:
            self.glint_due -= 1
            col = random.randrange(w)
            if ph[col] >= 1.5:  # [열, 표면에서 밑으로 깊이, 나이, 수명] — 흰 몸통 안이면 안 보여 테두리에 걸침
                self.glints.append([col, random.uniform(-0.5, 1.0), 0.0, random.uniform(*GLINT_T)])
        live = []
        for g in self.glints:
            g[2] += dt
            if g[2] >= g[3]:
                continue
            live.append(g)
            sp = glints[min(GLINT_LEVELS - 1, int(math.sin(math.pi * g[2] / g[3]) * GLINT_LEVELS))]
            lay(px, stride, w, h, sp, g[0] - sp[0] // 2, int(h - base[g[0]] - ph[g[0]] + g[1]) - sp[0] // 2)
        self.glints = live

    def render_pile(self):
        strip32 = self.strip.cast("I")
        w, last, bodies, zero, sh = self.w, self.pile_last, self.pile_body, self.pile_zero, self.strip_h
        ph, base, top = self.pile.h, self.base, 2 * PILE_SLOPES
        s = [v + b for v, b in zip(ph, base)]
        # 비탈 단계 0..top: 오른쪽으로 오르면(왼쪽을 봄) 빛을 받음. 2560 열에 0.6ms 더 듦(min·max·round 로 셈하면 1.1ms)
        for x, (v, b, r, l) in enumerate(zip(ph, base, s[1:] + s[-1:], s[:1] + s[:-1])):
            i = int((r - l) * PILE_LIGHT + PILE_SLOPES + 0.5)
            i = 0 if i < 0 else top if i > top else i
            key = int(v * 16) | b << 16 | i << 28
            if key != last[x]:  # 1/16 px 아래로 안 바뀐 열은 건너뜀
                last[x] = key  # 띠는 위에서부터 빈 칸 · 더미 · 틀 높이만큼 빈 칸
                strip32[x::w] = memoryview(pile_column(v, self.pile_edges, bodies[i], zero, sh - b)
                                           + zero[:b * 4]).cast("I")

    # ── 반딧불이 ──
    def fly_sprites(self):
        """[크기][밝기 단계 1..8][1/4 픽셀 위치 16벌]."""
        if "fireflies" not in self.sprite_cache:
            self.sprite_cache["fireflies"] = [
                [[place(shade(glow(core, halo, lv / FLY_LEVELS, fx / 4, fy / 4)), self.stride)
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
        dens = 1.0 if self.kind != "storm" else 0.7 + 0.3 * math.sin(now * 0.5 + self.gust_phase)
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
                stamp(px, stride, xi, c[2] - n + 1, rows)  # shade 로 높이가 폭보다 1px 작음
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
        if "fireworks" not in self.sprite_cache:
            self.sprite_cache["fireworks"] = fw_set(self.stride)
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

    def burst(self, x, y, kind=None):
        if self.pets:  # 동물이 없으면 react 가 안 돌아서 비우는 쪽이 없음
            self.bangs.append(x)
        if kind is None:
            kind = random.choices(list(FW_KINDS), [k[0] for k in FW_KINDS.values()])[0]
        a, b = random.sample(range(len(FW_COLORS)), 2)
        shift = kind in ("peony", "chrysanthemum") and random.random() < FW_SHIFT
        mixed = not shift and kind in ("peony", "chrysanthemum", "ring") and random.random() < 0.3
        v0, life = random.uniform(150, 250), FW_LIFE

        def ball(n, lo, hi):
            return [(math.cos(g) * v, math.sin(g) * v)
                    for g, v in ((random.uniform(0, math.tau), v0 * random.uniform(lo, hi)) for _ in range(n))]

        if kind == "ring":
            n, tilt, rot = random.randint(48, 64), random.uniform(0.2, 1.0), random.uniform(0, math.pi)
            c, s = math.cos(rot) * v0, math.sin(rot) * v0
            vel = [(u * c - v * s, u * s + v * c)
                   for u, v in ((math.cos(math.tau * i / n), math.sin(math.tau * i / n) * tilt) for i in range(n))]
        elif kind == "heart":
            rot, k = random.uniform(-0.3, 0.3), v0 / 17
            c, s = math.cos(rot) * k, math.sin(rot) * k
            pts = [(16 * math.sin(t) ** 3, -(13 * math.cos(t) - 5 * math.cos(2 * t) - 2 * math.cos(3 * t) - math.cos(4 * t)))
                   for t in (math.tau * i / 56 for i in range(56))]
            vel = [(u * c - v * s, u * s + v * c) for u, v in pts]
            a = b = random.choice((0, 4))  # 빨강·보라
        elif kind == "palm":
            n, v0, life = random.randint(7, 11), random.uniform(260, 330), (1.4, 1.9)
            vel = [(math.cos(g) * v, math.sin(g) * v) for g, v in
                   ((math.tau * (i + random.uniform(-0.2, 0.2)) / n, v0 * random.uniform(0.92, 1.0)) for i in range(n))]
            if random.random() < 0.6:
                a = b = FW_GOLD
        elif kind == "willow":
            v0, life, a, b = random.uniform(220, 270), (2.8, 3.8), FW_GOLD, FW_GOLD
            vel = ball(random.randint(70, 95), 0.5, 1.0)
        elif kind == "crossette":
            v0 = random.uniform(180, 230)
            vel = ball(random.randint(12, 16), 0.9, 1.0)
        elif kind == "strobe":
            life, a, b = (2.0, 2.8), FW_WHITE, FW_WHITE
            vel = ball(random.randint(60, 90), 0.3, 1.0)
        else:
            vel = ball(random.randint(*FW_SPARKS), 0.78, 1.0)
        for i, (vx, vy) in enumerate(vel):
            c = b if mixed and i % 2 else a
            # [x, y, vx, vy, 나이, 수명, 색, 모양, 반 넘어 바뀌는 색, 꼬리, 꼬리 남긴 나이, 덤(갈라지기: 쪼개질 나이 · 반짝이: 위상),
            #  꼬리 점 수]
            extra = random.uniform(*FW_SPLIT) if kind == "crossette" else random.random() if kind == "strobe" else 0
            self.sparks.append([x, y, vx, vy, 0.0, random.uniform(*life), c, kind, b if shift else c, [], 0.0, extra,
                                random.randint(*FW_KINDS[kind][3])])

    def fireworks(self, dt, now):
        px, stride, w, h, (sprites, tails) = self.surface.pixels, self.stride, self.w, self.h, self.fw
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
        moves = {k: (math.exp(-v[1] * dt), v[2] * dt) for k, v in FW_KINDS.items()}
        live, born, heads = [], [], []
        for s in self.sparks:
            s[4] += dt
            if s[4] >= s[5]:
                continue
            if s[7] == "crossette" and s[11] and s[4] >= s[11]:  # 넷으로 쪼개짐 — 새끼는 더 안 쪼개짐
                sp, g = 0.6 * math.hypot(s[2], s[3]) + 60, math.atan2(s[3], s[2]) + math.pi / 4
                born += [[s[0], s[1], math.cos(g + q * math.pi / 2) * sp, math.sin(g + q * math.pi / 2) * sp, 0.0,
                          random.uniform(0.6, 0.9), s[6], "crossette", s[8], [], 0.0, 0, s[12]] for q in range(4)]
                continue
            live.append(s)
            (drag, fall), keep = moves[s[7]], s[12]
            s[2] *= drag
            s[3] = s[3] * drag + fall
            s[0] += s[2] * dt
            s[1] += s[3] * dt
            k = s[4] / s[5]
            lv = FW_LEVELS if k < 0.5 else max(1, round(FW_LEVELS * (1 - k) / 0.5))
            c = s[6] if k < 0.5 else s[8]
            if keep:  # 꼬리: 오래된 점일수록 어두움. 머리보다 먼저 찍어 다른 불꽃 꼬리가 머리를 덮지 않게
                tr = s[9]
                if s[4] - s[10] >= FW_TRAIL_DT:
                    tr.append((s[0], s[1]))
                    s[10] = s[4]
                    if len(tr) > keep:
                        del tr[0]
                tail, m = tails[c], len(tr) + 1
                for j, (tx, ty) in enumerate(tr, 1):
                    tl = lv * j // m
                    if tl:
                        n, rows = tail[tl - 1]
                        xi, yi = int(tx) - n // 2, int(ty) - n // 2
                        if 0 <= xi <= w - n and 0 <= yi <= h - n:
                            stamp(px, stride, xi, yi, rows)
            if k > 0.7 and random.random() < 0.45:  # 사그라들며 반짝임
                continue
            if s[7] == "strobe" and (s[4] * 12 + s[11]) % 1 < 0.5:  # 깜빡임
                continue
            n, rows = sprites[c][lv - 1]
            xi, yi = int(s[0]) - n // 2, int(s[1]) - n // 2
            if 0 <= xi <= w - n and 0 <= yi <= h - n:
                heads.append((xi, yi, rows))
        for xi, yi, rows in heads:
            stamp(px, stride, xi, yi, rows)
        self.sparks = live + born

    # ── 안개 · 오로라 ──
    def tint(self, name, cur, color, alpha, ramp):
        """sprite_cache[name] 의 알파 행 무늬에 색과 높이별 진하기를 입혀 행마다 (픽셀 바이트,) 로 — slide 가 받는 꼴(옮겨 본
        벌이 하나). color(u)·ramp(u) 는 위 0 → 아래 1 인 u 의 색·진하기 배수. 양이 바뀔 때만 새로 만들고(2560 폭이면
        행 600개에 6MB) 아니면 cur 를 그대로 돌려줌."""
        if cur is not None and cur[0] == self.amount:
            return cur
        field = self.sprite_cache[name]
        k, n, scales, chans, rows = alpha * self.amount / 50, len(field), {}, {}, []
        for j, a in enumerate(field):
            u = (j + 1) / n
            q = min(255, int(255 * k * ramp(u)))
            tab = scales.get(q) or scales.setdefault(q, bytes(v * q // 255 for v in range(256)))
            c = color(round(u * 32) / 32)  # 색은 32 단계로 — 단계마다 표를 한 번만 셈
            if c not in chans:  # premultiplied B, G, R
                chans[c] = [bytes(ch * v // 255 for v in range(256)) for ch in c[::-1]]
            a = a.translate(tab)
            px = bytearray(len(a) * 4)
            px[0::4], px[1::4], px[2::4], px[3::4] = (*(a.translate(t) for t in chans[c]), a)
            rows.append((bytes(px),))
        return self.amount, rows

    def meteors(self, dt, now):
        """오로라에 곁들인 유성. 가끔 하나씩, 드물게 한 복사점에서 몇 초에 걸쳐 몰아 떨어지는 유성우. 복사점은 화면 위
        바깥이라 늘 아래쪽으로 남. 차차 밝아져 수명 70% 에서 가장 밝고 빨리 꺼짐, 불덩이는 85% 에서 한 번 번쩍. 꼬리는
        떨어지기 시작한 점 뒤로는 안 늘어남."""
        w, h = self.w, self.h
        if random.random() < METEOR_RATE * self.amount / 50 * dt:
            rad, t = (random.uniform(-0.5 * w, 1.5 * w), -random.uniform(0.3, 1.0) * h), now
            for _ in range(random.randint(*METEOR_BURST) if random.random() < METEOR_SHOWER else 1):
                self.meteor_due.append((t, rad))
                t += random.uniform(*METEOR_GAP)
        if self.meteor_due and self.meteor_due[0][0] <= now:
            due = [d for d in self.meteor_due if d[0] <= now]
            self.meteor_due = [d for d in self.meteor_due if d[0] > now]
            for _, (rx, ry) in due:
                x, y = random.uniform(0, w), random.uniform(0.03, 0.4) * h
                a, fire = math.atan2(y - ry, x - rx), random.random() < FIREBALL
                # [x, y, 방향 x, 방향 y, 빠르기, 나이, 수명, 밝기, 불덩이]
                self.shooting.append([x, y, math.cos(a), math.sin(a), random.uniform(*METEOR_SPEED) * (0.6 if fire else 1),
                                      0.0, random.uniform(*METEOR_LIFE) * (1.6 if fire else 1),
                                      1.6 if fire else random.uniform(0.45, 1.0), fire])
        px, stride, live = self.surface.pixels, self.stride, []
        for m in self.shooting:
            x, y, ux, uy, v, age, life, k, fire = m
            age += dt
            if age >= life:
                continue
            live.append(m)
            m[0], m[1], m[5], t = x + ux * v * dt, y + uy * v * dt, age, age / life
            k *= math.sin(math.pi * t ** 1.94) + (0.8 * math.exp(-((t - 0.85) / 0.04) ** 2) if fire else 0)
            tail = v * min(METEOR_TAIL_SEC, age)
            if k > 0.01 and tail > 1:
                glint(px, stride, w, h, meteor_streak(m[0], m[1], ux, uy, tail, k))
        self.shooting = live

    def fog(self, now):
        """안개는 작업 표시줄 바로 위에 깔림."""
        rows = self.fog_px[1]
        self.slide(rows, self.h - self.rise - len(rows), now, FOG_DRIFT, ((FOG_SWAY, FOG_SWAY_V, FOG_SWAY_K),))

    def slide(self, rows, y0, now, drift, sways):
        """행마다 무늬를 시간만큼 옆으로 밀어 y0 부터 잘라 붙임. 행은 subpixel 의 옮겨 본 벌들이라 정수 px 아래 몫은 벌을
        골라 맞추고, 무늬 끝에서 처음으로 감기는 자리는 두 번에 나눠 붙임. 밀리는 양은 모든 행이 같은 빠르기에 높이를 따라 위상이
        밀린 출렁임(sways 의 (폭, 빠르기, 위상) 물결들의 합)을 더한 것 — 이웃 행끼리는 늘 1px 안팎만 어긋나 무늬가 안 찢어지고, 위아래가 서로 엇갈려 흘러 보임.
        행마다 빠르기가 다르면 오래 둘수록 이웃 행이 벌어져 가로 줄무늬가 됨."""
        px, stride, w = self.surface.pixels, self.stride, self.w
        drift *= now
        n, offs = len(rows[0]), [drift] * len(rows)
        for a, v, k in sways:  # 물결마다 한 번에 — 행마다 sum(…) 이면 864행에 0.4ms 더 듦
            p = now * v
            offs = [f + a * math.sin(p + j * k) for j, f in enumerate(offs)]
        for j, (cuts, f) in enumerate(zip(rows, offs)):
            f %= w  # 0 ≤ f < w
            o = int(f)
            row = cuts[int((f - o) * n)]
            o *= 4
            s, rest = (y0 + j) * stride, stride - o
            px[s:s + rest] = row[o:]
            px[s + rest:s + stride] = row[:o]

    # ── 비눗방울 ──
    def new_soap(self, bottom):
        """bottom 이면 바닥 조금 위에서, 아니면 아무 높이에서. 작은 방울이 많음."""
        size = random.choices(range(len(SOAP_R)), (4, 3, 2, 1))[0]
        x = random.uniform(0, self.w - 2 * SOAP_R[size] - 4)
        col = min(max(int(x), 0), self.w - 1)
        y = self.h - self.base[col] - random.uniform(30, 90) if bottom else random.uniform(self.h * 0.2, self.h - 60)
        # [x, y, 오르는 빠르기, 크기, 흔들림 위상, 흔들림 빠르기, 남은 초, 무지개 위상, 흔들려 그린 x — 클릭이 봄]
        return [x, y, random.uniform(*SOAP_RISE), size, random.uniform(0, math.tau), random.uniform(0.8, 1.6),
                random.uniform(*SOAP_LIFE), random.random(), x]

    def soap(self, dt, now):
        """오르며 흔들리다 수명이 다하거나 화면 위로 나가거나 동물 몸에 닿으면 톡 — 물방울이 튀고, 닿은 동물은 ♪."""
        px, stride, w, h = self.surface.pixels, self.stride, self.w, self.h
        boxes = [(p, p.box()) for p in self.pets.values()]
        for b in self.soaps:
            b[1] -= b[2] * dt
            b[6] -= dt
            frames = self.soap_sprites[b[3]]
            n = frames[0][0]
            x = b[8] = b[0] + math.sin(b[4] + now * b[5]) * SOAP_SWAY
            cx, cy = x + n / 2, b[1] + n / 2
            hit = next((p for p, bx in boxes if bx and bx[0] <= cx < bx[0] + bx[2] and bx[1] <= cy < bx[1] + bx[3]), None)
            if hit or b[6] <= 0 or b[1] + n < 0:
                if b[1] + n >= 0:
                    self.pop(cx, cy, SOAP_R[b[3]])
                if hit:
                    hit.emote("♪", now)
                b[:] = self.new_soap(True)
                continue
            xi, yi = int(x), int(b[1])
            if 0 <= xi <= w - n and 0 <= yi <= h - n:
                stamp(px, stride, xi, yi, frames[int((now * SOAP_SPIN + b[7]) * SOAP_HUES) % SOAP_HUES][1])
        self.splatter(dt)

    def pop(self, x, y, r):
        """터진 방울 둘레에서 작은 물방울 몇 개가 바깥으로 튀어 떨어짐 — 비의 튄 물방울(splatter)을 그대로 씀."""
        d = self.droplet[0]
        for _ in range(3 + r // 3):
            ang, v = random.uniform(0, math.tau), random.uniform(50, 110)
            self.splashes.append([x + math.cos(ang) * r - d / 2, y + math.sin(ang) * r - d / 2,
                                  math.cos(ang) * v, math.sin(ang) * v - 40, random.uniform(0.18, 0.3)])

    # ── 나비 · 잠자리 ──
    def bug_sprites(self):
        """([종류][프레임][오른쪽을 보나] 조각, 종류마다 (폭, 높이)). 나비는 위에서 본 그림이라 좌우가 같음."""
        if "bugs" not in self.sprite_cache:
            fly = [[{r: pet.segments(rows, False, c) for r in (True, False)} for rows in BUTTERFLY_ART]
                   for c in BUG_COLORS[:4]]
            dragon = [[{r: pet.segments(rows, not r, c) for r in (True, False)} for rows in DRAGONFLY_ART]
                      for c in BUG_COLORS[4:]]
            size = lambda art: (len(art[0][0]) * pet.SCALE, len(art[0]) * pet.SCALE)
            self.sprite_cache["bugs"] = fly + dragon, [size(BUTTERFLY_ART)] * 4 + [size(DRAGONFLY_ART)] * 2
        return self.sprite_cache["bugs"]

    def new_bug(self):
        """화면 아래쪽 2/3 어딘가에서 날고 있음. x, y 는 가운데."""
        dragon = random.random() < BUG_DRAGON
        sp = random.randrange(4, 6) if dragon else random.randrange(4)
        x, y = random.uniform(0, self.w), random.uniform(self.h * 0.35, self.h * 0.85)
        # [x, y, 종류, 상태, 상태가 끝나는 시각, 방향(라디안), 방향이 틀어지는 빠르기, 위상, 빠르기, 가려는 x, 가려는 y]
        return [x, y, sp, "hover" if dragon else "fly", 0.0, random.uniform(0, math.tau), 0.0,
                random.uniform(0, math.tau), random.uniform(*FLUTTER_V), x, y]

    def flutter(self, dt, now):
        """나비는 이리저리 팔랑이다 가끔 바닥에 내려앉아 쉬고, 동물이 다가오면 날아오름. 잠자리는 휙 날아가 멈춰 떠
        있기를 되풀이. 둘 다 화면 아래쪽 2/3 안에서."""
        px, stride, w, h = self.surface.pixels, self.stride, self.w, self.h
        sprites, sizes = self.bug_sprites()
        near = [bx[0] + bx[2] / 2 for bx in (p.box() for p in self.pets.values() if not p.held) if bx]
        for b in self.bugs:
            bw, bh = sizes[b[2]]
            floor = h - self.base[min(max(int(b[0]), 0), w - 1)] - bh / 2
            s, right = b[3], True
            if s == "fly":
                b[6] = max(-3.0, min(3.0, b[6] + random.gauss(0, 6) * dt))
                b[5] += b[6] * dt
                b[0] = (b[0] + math.cos(b[5]) * b[8] * dt) % w
                b[1] += math.sin(b[5]) * b[8] * 0.6 * dt
                if (b[1] < h * 0.3 and math.sin(b[5]) < 0) or (b[1] > floor - 30 and math.sin(b[5]) > 0):
                    b[5] = -b[5]  # 화면 아래쪽 2/3 안에서 위아래로 튕김
                if random.random() < BUG_LAND * dt:
                    b[3] = "down"
                y, frame = b[1] + 5 * math.sin(now * 5 + b[7]), (0, 1, 2, 1)[int(now * FLUTTER_HZ * 4 + b[7]) % 4]
            elif s == "down":  # 팔랑이며 비스듬히 내려감
                b[0] = (b[0] + math.cos(b[5]) * b[8] * 0.5 * dt) % w
                b[1] = min(floor, b[1] + b[8] * dt)
                if b[1] >= floor:
                    b[3], b[4] = "rest", now + random.uniform(*BUG_REST)
                y, frame = b[1], (0, 1, 2, 1)[int(now * FLUTTER_HZ * 4 + b[7]) % 4]
            elif s == "rest":  # 바닥에 앉아 날개를 천천히 접었다 폄
                b[1] = floor
                if now >= b[4] or any(abs(cx - b[0]) < BUG_SHY for cx in near):
                    b[3], b[5], b[6] = "fly", -math.pi / 2 + random.uniform(-0.6, 0.6), 0.0
                    b[1] -= 4
                y, frame = b[1], (0, 1, 2, 1)[int(now * 1.2 + b[7]) % 4]
            else:  # 잠자리: 떠 있다(hover) 휙 날아감(dart)
                if s == "hover" and now >= b[4]:
                    b[3] = "dart"
                    b[9] = min(max(b[0] + random.uniform(-500, 500), bw), w - bw)
                    b[10] = random.uniform(h * 0.3, max(h * 0.3, floor - 40))
                if b[3] == "dart":
                    dx, dy = b[9] - b[0], b[10] - b[1]
                    d = math.hypot(dx, dy)
                    if d < 2:
                        b[3], b[4] = "hover", now + random.uniform(*DART_HOVER)
                    else:
                        v = min(DART_V, d * 5) * dt  # 가까워지며 멈춰 섬
                        b[0], b[1], b[5] = b[0] + dx / d * v, b[1] + dy / d * v, math.atan2(dy, dx)
                right = math.cos(b[5]) >= 0
                y, frame = b[1] + 1.5 * math.sin(now * 3 + b[7]), int(now * 30 + b[7]) % 2
            pet.stamp(px, stride, int(b[0] - bw / 2), int(y - bh / 2), sprites[b[2]][frame][right], w, h)

    # ── 창문 빗방울 ──
    def pane(self, dt):
        """유리창에 빗방울이 맺힘: 맺힌 방울은 가만히 있다 옆에 새 방울이 닿으면 합쳐 커지고, 커진 방울은 가끔 흘러내림.
        흐르는 방울은 달리다 멈칫하기를 되풀이하며 길 위의 방울을 삼켜 커지고, 지나간 자리에 작은 방울을 떨굼. 바닥
        (작업 표시줄 위)에 닿으면 사라짐. 맺힌 방울이 pane_cap 을 넘으면 오래된 것부터 초당 PANE_DRY 개 남짓씩 마름.
        새 방울은 splats 에서 PANE_SPLAT_T 동안 퍼졌다 오므라든 뒤 맺힘."""
        px, stride, w, h, panes, sprites = self.surface.pixels, self.stride, self.w, self.h, self.panes, self.pane_sprites
        self.pane_due += PANE_RATE * self.amount / 50 * dt
        quiet = self.pane_due > 3  # 처음 반쯤 채울 때 · 숨겼다 돌아옴 — 한꺼번에 부딪히지 않고 그냥 맺힘
        while self.pane_due >= 1:
            self.pane_due -= 1
            x, y, r = random.uniform(0, w), random.uniform(0, h - self.rise - 20), random.uniform(*PANE_R)
            if quiet:
                self.wet(x, y, r)
            else:
                self.splats.append([x, y, r, 0.0])
        live = []
        for s in self.splats:  # [x, y, r, 나이]
            s[3] += dt
            if s[3] < PANE_SPLAT_T:
                live.append(s)
                continue
            self.wet(*s[:3])
            if s[2] >= PANE_SPRAY_R:  # 큰 방울은 둘레에 잔방울을 튀김
                for _ in range(random.randint(*PANE_SPRAY[0])):
                    a, d = random.uniform(0, math.tau), s[2] * random.uniform(*PANE_SPRAY[1])
                    self.wet(s[0] + d * math.cos(a), s[1] + d * math.sin(a), random.uniform(0.7, 1.3))
        self.splats = live
        extra = len(panes) - self.pane_cap
        self.pane_dry = self.pane_dry + (PANE_DRY + extra / 8) * dt if extra > 0 else 0.0
        if self.pane_dry >= 1:
            del panes[:min(extra, int(self.pane_dry))]
            self.pane_dry -= int(self.pane_dry)
        for d in panes:
            if d[2] >= PANE_HEAVY and random.random() < PANE_GO * dt:
                panes.remove(d)  # 흐르기 시작 — 리스트를 도는 중이라 한 프레임에 한 방울만
                # [x, y, r, 이 상태가 끝나기까지 초, 달리나, 달리는 빠르기, 좌우 빠르기, 다음 자국까지 px]
                self.runs.append([d[0], d[1], d[2], 0.0, False, 0.0, 0.0, random.uniform(*PANE_TRAIL)])
                break
        for s in self.runs[:]:
            s[3] -= dt
            if s[3] <= 0:
                s[4] = not s[4]
                s[3] = random.uniform(*(PANE_RUN_T if s[4] else PANE_STOP_T))
                s[5] = random.uniform(*PANE_RUN) * min(1.5, s[2] / 7)  # 큰 방울이 빠름
                s[6] = random.uniform(-0.2, 0.2) * s[5]
            if s[4]:
                step = s[5] * dt
                s[0], s[1], s[7] = s[0] + s[6] * dt, s[1] + step, s[7] - step
                for d in [d for d in panes if d[1] > s[1] - s[2] and abs(d[0] - s[0]) < s[2] + d[2]
                          and math.hypot(d[0] - s[0], d[1] - s[1]) < s[2] + d[2]]:
                    panes.remove(d)  # 길 위의 방울을 삼킴 — 위 끝보다 아래 것만(지나온 자국은 그 위에 떨굼)
                    s[2] = min(PANE_RMAX, math.hypot(s[2], d[2]))
                if s[7] <= 0:  # 자국을 떨구며 조금 작아짐
                    t = random.uniform(1.2, 2.2)
                    panes.append([s[0] + random.uniform(-1, 1), s[1] - s[2] - t - 1, t])
                    s[2], s[7] = math.sqrt(max(9.0, s[2] ** 2 - 0.6 * t * t)), random.uniform(*PANE_TRAIL)
            if s[1] + s[2] >= h - self.base[min(max(int(s[0]), 0), w - 1)] or not 0 <= s[0] < w:
                self.runs.remove(s)
        # 부딪히는 방울은 탁 퍼졌다 오므라듦. 번지는 고리는 물웅덩이 것이라 유리엔 안 그림(그렸더니 웃는 얼굴처럼 보였음)
        splat = [(x, y, r * (1 + (PANE_SPLAT_K - 1) * (1 - t / PANE_SPLAT_T) ** 2)) for x, y, r, t in self.splats]
        for x, y, r, *_ in panes + self.runs + splat:
            n, rows = sprites[min(len(sprites) - 1, max(0, round((r - 1) * 2)))]
            xi, yi = int(x - n / 2), int(y - n / 2)
            if 0 <= xi <= w - n and 0 <= yi <= h - n:
                stamp(px, stride, xi, yi, rows)

    def shower(self, dt):
        """창문 빗방울의 소나기: PANE_SHOWER_EVERY 초에 한 번 PANE_SHOWER_LEN 초 동안 비스듬한 빗줄기가 유리 바깥으로 쏟아짐
        (동물 뒤). 빗줄기는 잠깐 보이다 사라지며 PANE_STICK 만큼은 그 자리에서 유리에 부딪혀 맺힘(splats)."""
        px, stride, w, h = self.surface.pixels, self.stride, self.w, self.h
        if self.shower_left > 0:
            self.shower_left -= dt
            f = math.sin(math.pi * max(0.0, self.shower_left) / self.shower_len)  # 차차 세졌다 잦아듦
        else:
            f = 0.0
            self.shower_in -= dt
            if self.shower_in <= 0:
                self.shower_len = self.shower_left = random.uniform(*PANE_SHOWER_LEN)
                self.shower_in = random.uniform(*PANE_SHOWER_EVERY)
        slant, floor = SLANTS[PANE_SHOWER_SLANT], h - self.rise - 20
        self.streak_due += PANE_SHOWER_RAIN * self.amount / 50 * f * dt
        while self.streak_due >= 1:
            self.streak_due -= 1
            li = 1 + (random.random() < 0.4)  # 가운데 · 가까운 층
            n = random.randint(*RAIN_LAYERS[li][1])
            # [x, y, 빠르기, 층, 길이, 남은 초]
            self.streaks.append([random.uniform(-h * slant, w), random.uniform(-n, floor - n),
                                 random.uniform(*RAIN_LAYERS[li][2]), li, n, random.uniform(*PANE_STREAK_T)])
        sprites, live = self.rain_sprites[0][PANE_SHOWER_SLANT], []
        for s in self.streaks:
            s[5] -= dt
            s[0] += s[2] * slant * dt
            s[1] += s[2] * dt
            if s[5] <= 0 or s[1] + s[4] >= floor:
                if random.random() < PANE_STICK:  # 아래 끝이 유리에 닿음
                    self.splats.append([s[0] + s[4] * slant, min(s[1] + s[4], floor), random.uniform(*PANE_R), 0.0])
                continue
            live.append(s)
            sw, rows = sprites[s[3]][s[4]]
            xi, yi = int(s[0]), int(s[1])
            if yi >= 0 and 0 <= xi and xi + sw <= w:
                stamp(px, stride, xi, yi, rows)
        self.streaks = live

    def wet(self, x, y, r):
        """(x, y) 에 반지름 r 방울이 맺힘. 닿는 맺힌 방울이 있으면 합쳐 하나로 — 물 양(넓이)을 더하고 큰 쪽으로 쏠림."""
        for d in self.panes:
            if abs(d[0] - x) < d[2] + r and math.hypot(d[0] - x, d[1] - y) < d[2] + r:
                big = d[2] * d[2] / (d[2] * d[2] + r * r)
                d[0], d[1] = d[0] * big + x * (1 - big), d[1] * big + y * (1 - big)
                d[2] = min(PANE_RMAX, math.hypot(d[2], r))
                return
        self.panes.append([x, y, r])

    # ── 어항 ──
    def aquarium(self):
        """어항을 깜. 그림과 모래·해초 자리는 처음 고를 때 한 번(sprite_cache), 물빛은 water_tint, 물고기·거품·빛줄기
        수는 retune 이 맞춤."""
        w, h = self.w, self.h
        if "aquarium" not in self.sprite_cache:
            rng, spots = random.Random(random.random()), []  # 전역 random 을 따름 — 검사(random.seed)에서 같은 자리
            x = rng.uniform(10, WEED_EVERY)
            while x < w - 10:
                spots.append(int(x))
                x += rng.uniform(0.4, 1.6) * WEED_EVERY
            tail = lambda rows, alt: (rows, tuple(a + r[len(a):] for r, a in zip(rows, alt)))  # (그대로, 꼬리 친 그림)
            frames, school = [tail(*art) for art in FISH_ART], tail(*SCHOOL_ART)
            sides = lambda rows: {right: pet.segments(rows, not right, FISH_COLORS) for right in (True, False)}
            size = lambda rows: (len(rows[0]) * pet.SCALE, len(rows) * pet.SCALE)
            # 상자는 화면 60% 자리에 제일 가까운 넉넉한 틈에, 나머지 틈엔 DECOR_SHARE 확률로 장식 하나 (해초와 6px 띄움)
            gaps, cw = list(zip([0, *spots], [*spots, w])), size(CHEST_ART[0])[0]
            chest = min((g for g in gaps if g[1] - g[0] >= cw + 16), key=lambda g: abs(sum(g) / 2 - w * 0.6), default=None)
            decor = []
            for g in gaps:
                k = rng.randrange(len(DECOR_ART))
                dw = size(DECOR_ART[k])[0]
                if g != chest and g[1] - g[0] >= dw + 12 and rng.random() < DECOR_SHARE:
                    decor.append((int(rng.uniform(g[0] + 6, g[1] - 6 - dw)), k))
            self.sprite_cache["aquarium"] = {
                "decor": [(x, size(DECOR_ART[k]), pet.segments(DECOR_ART[k], rng.random() < 0.5, DECOR_COLORS))
                          for x, k in decor],
                "chest_x": None if chest is None else (sum(chest) - cw) // 2,
                "chest": [pet.segments(rows, False, DECOR_COLORS) for rows in CHEST_ART],
                "chest_size": [size(rows) for rows in CHEST_ART],
                "crab": [pet.segments(rows, False, DECOR_COLORS) for rows in CRAB_ART], "crab_size": size(CRAB_ART[0]),
                "jelly_size": size(JELLY_ART[0]),
                "bubbles": [[[bubble(r, layer[3], fx / 4, fy / 4) for fy in range(4) for fx in range(4)]
                             for r in layer[1]] for layer in BUBBLE_LAYERS],
                "rays": [ray_shape(max(8, int(w * f)), int(h * RAY_REACH), rng) for f in RAY_WIDTHS],
                # [종류][꼬리][오른쪽] — thin 은 한 칸 건너 하나씩 뺀 반쪽 폭: 돌아서는 동안 옆모습이 좁아 보임
                "fish": [[sides(rows) for rows in pair] for pair in frames],
                "fish_thin": [[sides([r[::2] for r in rows]) for rows in pair] for pair in frames],
                "fish_size": [size(rows) for rows, _ in FISH_ART],
                "fish_thin_w": [size([r[::2] for r in rows])[0] for rows, _ in FISH_ART],
                "school": [[sides([r[::2] for r in rows] if thin else rows) for rows in school] for thin in (False, True)],
                "school_size": size(SCHOOL_ART[0]), "school_thin_w": size([r[::2] for r in SCHOOL_ART[0]])[0],
                "sand": sand_columns(16, rng), "sand_h": sand_heights(w, rng), "sand_pick": [rng.randrange(16) for _ in range(w)],
                "weeds": [blade for x in spots for blade in tuft(x, rng)]}
        aq = self.aq = self.sprite_cache["aquarium"]
        self.sand = aq["sand_h"]
        self.pile.h = list(self.sand)  # 모래는 안 녹는 더미 — 동물이 그 위를 걷고 거품이 거기서 나옴
        self.sand_base = None  # 다음 프레임에 모래 띠를 그림
        self.vents = [x for x, *_ in random.sample(aq["weeds"], min(3, len(aq["weeds"])))]  # 거품 줄기가 나오는 해초 밑
        self.fish, self.school, self.rays_at, self.rays_drawn = [], None, [], None  # 물빛과 물고기·떼·거품·빛줄기 수는 retune 이 맞춤
        cw = aq["crab_size"][0]
        # 게 [x, 1 오른쪽 · -1 왼쪽, 지금 짓이 끝나는 시각, 걷는 중, 화면 y] · 해파리 [x, y, 오르내리는 px/초, 다음에
        # 오므릴 시각, 오므린 시각, 위상, 가려는 높이] · 상자 [열리는 시각, 다음 거품 시각]. 시각은 첫 프레임에 정함
        self.crab = [[random.uniform(0, max(0, w - cw)), random.choice((1, -1)), None, False, None] for _ in range(CRAB_N)]
        self.jelly = [self.new_jelly() for _ in range(JELLY_N)]
        self.chest = None

    def floor_at(self, x, width):
        """x 부터 width px 밑에서 바닥(틀 윗변 + 모래)이 제일 높은 곳의 화면 y — 장식과 게가 그 위에 얹힘."""
        lo, hi = max(0, x), min(self.w, x + width)
        return self.h - max((b + s for b, s in zip(self.base[lo:hi], self.pile.h[lo:hi])), default=0)

    def rest_at(self, x, width):
        """x 에 놓으려던 폭 width 짜리가 앉을 (x, 화면 y). 가운데가 틀 단 밖이라 반 넘게 허공이면 낮은 쪽으로 넘어가
        단 바로 옆 바닥에 앉음. 넘어갈지는 바닥이 가려는 모양(goal)으로 정함 — 지금 바닥으로 정하면 무너지는 동안
        4px 묶음마다 높이가 달라 장식이 들썩임. 높은 데가 양쪽에 다 있으면(틀 둘에 걸친 다리) 그대로."""
        for _ in range(3):  # ponytail: 옮긴 자리가 또 단에 걸치면 몇 번만 다시 봄. 옆 장식·해초와 겹치는 건 안 막음
            lo, hi = max(0, x), min(self.w, x + width)
            if hi <= lo:
                break
            mid = (lo + hi) // 2
            left = [i for i in range(lo, mid) if self.goal[i] > self.goal[mid]]
            right = [i for i in range(mid + 1, hi) if self.goal[i] > self.goal[mid]]
            if bool(left) == bool(right):
                break
            x = min(max(left[-1] + 1 if left else right[0] - width, 0), max(0, self.w - width))
        return x, self.floor_at(x, width)

    def place_decor(self):
        """장식 · 상자가 앉을 자리. 틀 모양이 바뀔 때만 (render_sand 와 같이)."""
        self.decor_at = []
        for x, (dw, dh), segs in self.aq["decor"]:
            x, y = self.rest_at(x, dw)
            self.decor_at.append((x, y - dh, segs))
        cx = self.aq["chest_x"]
        self.chest_x, self.chest_floor = (None, None) if cx is None else self.rest_at(cx, self.aq["chest_size"][0][0])

    def decor(self, now):
        """바닥 장식과 보물상자. 상자는 CHEST_SHUT 동안 닫혀 있다 CHEST_OPEN 동안 열리고, 열린 동안 CHEST_PUFF 마다
        상자 입에서 거품 하나 — 숨 거품 목록에 넣어 위로 오르다 사라짐."""
        px, stride, w, h, aq = self.surface.pixels, self.stride, self.w, self.h, self.aq
        for x, y, segs in self.decor_at:
            pet.stamp(px, stride, x, y, segs, w, h)
        if self.chest_floor is None:
            return
        if self.chest is None:  # 처음엔 조금만 기다렸다 열림
            self.chest = [now + random.uniform(2, CHEST_SHUT[0]), now]
        c = self.chest
        if now >= c[0] + CHEST_OPEN:
            c[0] = now + random.uniform(*CHEST_SHUT)
        is_open = int(now >= c[0])
        (cw, ch), x = aq["chest_size"][is_open], self.chest_x
        pet.stamp(px, stride, x, self.chest_floor - ch, aq["chest"][is_open], w, h)
        if is_open and now >= c[1]:
            c[1] = now + CHEST_PUFF
            f = self.new_flake(random.randrange(len(BUBBLE_LAYERS)), False, BUBBLE_LAYERS)
            f[0], f[1] = x + cw / 2 + random.uniform(-cw * 0.3, cw * 0.3), self.chest_floor - ch + 3 * pet.SCALE
            self.breaths.append(f)

    def crabs(self, dt, now):
        """게: 모래 위를 옆걸음으로 CRAB_WALK 동안 걷다 CRAB_REST 동안 서서 집게를 들썩임. 걸음을 뗄 때 반은 돌아서고
        화면 끝에선 돌아섬. 틀 단은 300px/초로 기어오르내림."""
        px, stride, w, h, aq = self.surface.pixels, self.stride, self.w, self.h, self.aq
        cw, ch = aq["crab_size"]
        for c in self.crab:
            if c[2] is None or now >= c[2]:
                c[3] = not c[3]
                c[2] = now + random.uniform(*(CRAB_WALK if c[3] else CRAB_REST))
                if c[3] and random.random() < 0.5:
                    c[1] = -c[1]
            if c[3]:
                c[0] += c[1] * CRAB_SPEED * dt
                if c[0] <= 0 or c[0] >= w - cw:
                    c[0] = min(max(c[0], 0), max(0, w - cw))
                    c[1] = 1 if c[0] <= 0 else -1
            y = self.floor_at(int(c[0]), cw) - ch
            c[4] = y if c[4] is None else c[4] + max(-300 * dt, min(300 * dt, y - c[4]))
            frame = int(now / 0.15) % 2 if c[3] else 2 * (int(now / 0.4) % 2)
            pet.stamp(px, stride, int(c[0]), int(c[4]), aq["crab"][frame], w, h)

    def jelly_band(self):
        """해파리가 오가는 높이 (위, 아래) — 위 10% 아래부터 모래 40px 위까지."""
        lo = self.h * 0.1
        return lo, max(lo, self.h - self.rise - SAND_H[1] - self.aq["jelly_size"][1] - 40)

    def new_jelly(self):
        lo, hi = self.jelly_band()
        return [random.uniform(0, max(0, self.w - self.aq["jelly_size"][0])), random.uniform(lo, hi), JELLY_SINK, None,
                -1e9, random.uniform(0, math.tau), random.uniform(lo, hi)]

    def jellies(self, dt, now):
        """해파리: 가려는 높이보다 낮으면 JELLY_PULSE 마다 오므려 JELLY_PUSH 로 밀려 오르고, 빠르기는 천천히 가라앉는
        쪽(JELLY_SINK)으로 풀림. 높이에 닿으면 안 오므리고 가라앉다 가끔 새 높이를 고름. 옆으로는 느리게 흘러감.
        반투명이라 물고기·동물·거품보다 먼저(뒤에) 그림 — 위에 그리면 물빛을 섞어 둔 픽셀이 그것들을 지움."""
        px, stride, w, h = self.surface.pixels, self.stride, self.w, self.h
        jw, jh = self.aq["jelly_size"]
        lo, hi = self.jelly_band()
        for j in self.jelly:
            if j[3] is None:
                j[3] = now + random.uniform(*JELLY_PULSE)
            if now >= j[3]:
                j[3] = now + random.uniform(*JELLY_PULSE)
                if j[1] > j[6]:
                    j[2], j[4] = -JELLY_PUSH, now
                elif random.random() < 0.3:
                    j[6] = random.uniform(lo, hi)
            j[2] += (JELLY_SINK - j[2]) * min(1.0, 1.2 * dt)
            j[1] = min(max(j[1] + j[2] * dt, lo), hi)
            j[0] = min(max(j[0] + 8 * math.sin(now * 0.15 + j[5]) * dt, 0), max(0, w - jw))
            band = min(AQ_BANDS - 1, max(0, int((j[1] + jh / 2) * AQ_BANDS / h)))
            pet.stamp(px, stride, int(j[0]), int(j[1]), self.jelly_sprites[band][int(now - j[4] < JELLY_SQUEEZE)], w, h)

    def rays(self, now):
        """빛줄기: 위 끝을 축으로 아래가 천천히 좌우로 흔들리고, 줄기마다 제 범위(lo–hi) 안에서 밝기가 오감.
        행마다 그 행 물빛이 섞인 조각을 물빛 버퍼(self.water)에 구워 둠 — 프레임은 그 버퍼로 화면을 덮음. 흔들림은 아래
        끝이 1px 움직일 때만 갱신하므로(초당 많아야 15번) 대개의 프레임엔 할 게 없음. 바뀐 줄기는 자리·밝기가 바뀐 행만
        고침: 그 행에서 옛·새 자리를 감싼 범위를 물빛으로 되돌리고, 범위에 걸친 줄기를 놓인 차례대로 잘라 다시 씀(겹친
        줄기는 뒤의 것이 위). 프레임마다 통째로 다시 쓰던 때는 10줄기 × 648행이 2560×1440 에서 3ms — 한 프레임의 절반."""
        water, stride, rows = self.water, self.stride, self.aq_tint[1]["rows"]
        if self.rays_drawn is None:  # 처음이거나 줄기 수가 바뀜 — 남은 줄기를 지우고 다 그림
            reach = max((len(lv[0]) for lv in self.ray_rows), default=0)
            water[:reach * stride] = b"".join(p * self.w for p in rows[:reach])
            self.rays_drawn = [None] * len(self.rays_at)
        drawn, dirty = self.rays_drawn, {}  # 줄기마다 (아래 끝 흔들림 px, 밝기, 행마다 x) · 행 → (왼, 오른) 바이트
        for i, (x0, shape, ph, sp, slant, lo, hi) in enumerate(self.rays_at):
            sh = self.ray_rows[shape]
            n = len(sh[0])
            sway = round(RAY_SWAY * (n - 1) * math.sin(now * sp * 3 + ph))
            lv = ray_level(lo, hi, math.sin(now * sp * 2 + 2 * ph))
            old = drawn[i]
            if old is not None and old[0] == sway and old[1] == lv:
                continue
            slant += sway / max(1, n - 1)
            xs, new = [int(x0 + j * slant) for j in range(n)], sh[lv]
            drawn[i] = (sway, lv, xs)
            was = None if old is None else sh[old[1]]
            for j, (x, (lead, data)) in enumerate(zip(xs, new)):
                a = (x + lead) * 4
                b = a + len(data)
                if was is not None:
                    if old[1] == lv and old[2][j] == x:
                        continue
                    pl, pd = was[j]
                    pa = (old[2][j] + pl) * 4
                    a, b = min(a, pa), max(b, pa + len(pd))
                d = dirty.get(j)
                dirty[j] = (a, b) if d is None else (min(a, d[0]), max(b, d[1]))
        if not dirty:
            return
        spans = [(r[1], d) for r, d in zip(self.rays_at, drawn)]
        for j, (a, b) in dirty.items():
            o = j * stride
            water[o + a:o + b] = rows[j] * ((b - a) // 4)
            for shape, (_, lv, xs) in spans:
                lead, data = self.ray_rows[shape][lv][j]
                s = (xs[j] + lead) * 4
                lo, hi = max(a, s), min(b, s + len(data))
                if lo < hi:
                    water[o + lo:o + hi] = data[lo - s:hi - s]

    def render_sand(self):
        """모래 띠: 띠 높이의 물빛 위에, 열마다 그 열 바닥(틀 윗변) 바로 위로 모래. 틀 모양이 바뀔 때만, 바뀐 열만
        다시 그림 — 바닥이 내려앉는 동안 프레임마다 불림(통째로면 2560 폭에 2.6ms)."""
        strip32 = self.strip.cast("I")
        w, sh, tint, cols, pick = self.w, self.strip_h, self.aq_tint[1]["strip"], self.aq["sand"], self.aq["sand_pick"]
        old = self.sand_base or [-1] * w
        for x, (v, b) in enumerate(zip(self.sand, self.base)):
            if b == old[x]:
                continue
            strip32[x::w] = memoryview(tint[:(sh - b - v) * 4] + cols[pick[x]][:v * 4] + tint[(sh - b) * 4:]).cast("I")
        self.sand_base = self.base

    def weeds(self, now):
        """해초: 뿌리는 그 열의 바닥(틀 윗변) + 모래 위. 위로 갈수록 크게, 물결처럼 조금씩 늦게 흔들림."""
        px, stride, h, base, ph = self.surface.pixels, self.stride, self.h, self.base, self.pile.h
        for x, rows, phase, speed, sway in self.aq["weeds"]:
            y, t = h - base[x] - int(ph[x]), now * speed + phase
            st, ct = math.sin(t), math.cos(t)
            for data, (p, q, half) in zip(rows, sway):
                xx = x + int(st * p - ct * q) - half
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
            n = int(math.ceil(2 * BUBBLE_LAYERS[li][1][f[4]])) + 5  # bubble() 그림 크기 — shade 가 2px 늘림
            f[1] = self.h - self.base[col] - self.pile.h[col] - n - random.uniform(0, 4)
        return f

    def bubbles(self, dt, now, flakes, refill):
        """거품: 눈송이(snow)를 거꾸로 — 같은 꼴로 흔들리며 오르다 수면(화면 위)을 넘으면 refill 이면 바닥에서 다시
        나오고 아니면(동물이 내쉰 숨) 사라짐. 남은 거품을 돌려줌."""
        px, stride, w, h, live = self.surface.pixels, self.stride, self.w, self.h, []
        for f in flakes:
            layer = BUBBLE_LAYERS[f[3]]
            f[1] -= f[2] * dt
            sprites = self.bubble_sprites[min(AQ_BANDS - 1, max(0, int(f[1] * AQ_BANDS / h)))][f[3]][f[4]]
            n = sprites[0][0]
            if f[1] + n < 0:
                if refill:
                    f[:] = self.new_bubble(f[3], True)
                    live.append(f)
                continue
            live.append(f)
            x = f[0] + math.sin(f[5] + now * f[6] * 2) * layer[5]
            xi, yi = int(x), int(f[1])
            if yi < 0 or xi < 0 or xi + n > w or yi + n > h:
                continue
            stamp(px, stride, xi, yi, sprites[int((f[1] - yi) * 4) * 4 + int((x - xi) * 4)][1])
        return live

    def exhale(self, x, y):
        """호흡기(x, y)에서 작은 거품 몇 개 — 처음엔 몰려 있다 오르며 흩어짐. 같은 프레임에 한 번 오르므로 검사는 2px 더 봄."""
        for _ in range(random.randint(*BREATH_BUBBLES)):
            f = self.new_flake(0, False, BUBBLE_LAYERS)
            f[0], f[1] = x + random.uniform(-2, 2), y - random.uniform(0, 8)
            self.breaths.append(f)

    def fish_band(self, fh):
        """키 fh 인 물고기가 오가는 높이 (위, 아래) — 위 12% 아래부터 모래·작업 표시줄 위까지."""
        lo = self.h * 0.12
        return lo, max(lo, self.h - self.rise - SAND_H[1] - fh - 20)

    def new_fish(self, size=None):
        """물고기 하나. size(폭, 키)를 주면 그 크기의 떼 우두머리 — 종류는 안 씀."""
        sp = random.randrange(len(FISH_ART))
        fw, fh = size or self.aq["fish_size"][sp]
        lo, hi = self.fish_band(fh)
        # [x, y, 오른쪽이면 1 왼쪽이면 -1, 빠르기, 종류, 위상, 가려는 높이, 돌아서기 남은 초]
        return [random.uniform(0, max(0, self.w - fw)), random.uniform(lo, hi), random.choice((1, -1)),
                random.uniform(*FISH_SPEED), sp, random.uniform(0, math.tau), random.uniform(lo, hi), 0.0]

    def new_school(self):
        """떼 [우두머리, 따르는 것들]. 따르는 것 [x, y, 뒤로 px, 위아래 px, 따라가는 빠르기, 위상, 오른쪽을 봄]."""
        lead = self.new_fish(self.aq["school_size"])
        lead[3] = random.uniform(30, 44)  # 떼는 고르게 — 빠른 우두머리면 뒤가 늘어져 흩어짐
        members = []
        for _ in range(random.randint(*SCHOOL_N)):
            back, side = random.uniform(*SCHOOL_BACK), random.uniform(-SCHOOL_SIDE, SCHOOL_SIDE)
            members.append([lead[0] - lead[2] * back, lead[1] + side, back, side, random.uniform(*SCHOOL_PULL),
                            random.uniform(0, math.tau), lead[2] > 0])
        return [lead, members]

    def swim(self, f, fw, fh, dt, now):
        """f 를 dt 만큼 헤엄치게 하고 (그릴 y, 꼬리 그림, 돌아서는 몫) 을 돌려줌. 몫은 돌아서기 시작에 1 → 끝에 0 이고
        그동안 빠르기가 옛 방향에서 0 을 지나 새 방향으로 넘어감 — 제자리에서 한 프레임에 뒤집히지 않음."""
        beat = now * (2 + f[3] / 15) + f[5]  # 빠른 물고기가 꼬리를 자주 침 — 한 번 칠 때(2 만큼) 앞으로 한 번 밀림
        k = f[7] / FISH_FLIP
        f[7] = max(0.0, f[7] - dt)
        f[0] += f[2] * f[3] * (1 - 2 * k) * (1 + FISH_PULSE * math.cos(math.pi * beat)) * dt
        w = self.w
        if not f[7] and (f[0] <= 0 < -f[2] or f[0] >= w - fw and f[2] > 0 or random.random() < FISH_TURN * dt):
            f[2], f[7] = -f[2], FISH_FLIP
            f[6] = random.uniform(*self.fish_band(fh))
        f[0] = min(max(f[0], 0), max(0, w - fw))
        f[1] += max(-12 * dt, min(12 * dt, f[6] - f[1]))
        return min(max(int(f[1] + 4 * math.sin(now * 1.7 + f[5])), 0), self.h - fh), int(beat) % 2, k

    def fishes(self, dt, now):
        """물고기: 좌우로 헤엄치다 화면 끝이나 가끔 천천히 돌아서고(swim), 돌아설 때 고른 새 높이로 옮겨 감. 돌아서는
        가운데 반 동안은 반쪽 폭 그림 — 옛 방향 → 새 방향. 떼는 우두머리 뒤 제 자리를 늦게 쫓아 돌 때 둥글게 휨."""
        px, stride, w, h, aq = self.surface.pixels, self.stride, self.w, self.h, self.aq
        for f in self.fish:
            fw, fh = aq["fish_size"][f[4]]
            y, frame, k = self.swim(f, fw, fh, dt, now)
            right = (f[2] > 0) == (k <= 0.5)
            if 0.25 < k < 0.75:
                tw = aq["fish_thin_w"][f[4]]
                pet.stamp(px, stride, int(f[0]) + (fw - tw) // 2, y, aq["fish_thin"][f[4]][frame][right], w, h)
            else:
                pet.stamp(px, stride, int(f[0]), y, aq["fish"][f[4]][frame][right], w, h)
        if self.school:
            (sw, sh), tw = aq["school_size"], aq["school_thin_w"]
            lead, members = self.school
            lo, hi = self.fish_band(sh)  # 따르는 것도 물고기와 같은 높이 띠 안에만 그림
            self.swim(lead, sw, sh, dt, now)
            for m in members:
                pull = min(1.0, m[4] * dt)
                dx = (min(max(lead[0] - lead[2] * m[2], 0), w - sw) - m[0]) * pull
                m[0] += dx
                m[1] += (lead[1] + m[3] + 3 * math.sin(now * 1.3 + m[5]) - m[1]) * pull
                if abs(dx) > 8 * dt:  # 거의 멈췄을 땐 보던 쪽 그대로 — 안 그러면 제자리에서 떨림
                    m[6] = dx > 0
                thin = abs(dx) < 14 * dt
                y = int(min(max(m[1], lo), hi))
                pet.stamp(px, stride, int(m[0]) + thin * (sw - tw) // 2, y,
                          aq["school"][thin][int(now * 3 + m[5]) % 2][m[6]], w, h)

    # ── 돌리기 ──
    def reset(self):
        kind = self.kind
        self.full_clear = True
        self.flakes, self.drops, self.splashes, self.flies, self.breaths = [], [], [], [], []  # 수는 끝에 retune 이 채움
        self.crowns, self.gust_phase = [], random.uniform(0, math.tau)
        self.landed, self.glints, self.glint_due = [], [], 0.0  # 쌓인 눈 위의 내려앉은 송이 · 반짝이
        self.bolt, self.next_bolt = None, time.perf_counter() + random.uniform(2, 5)
        self.pile = Pile(self.w, self.base)
        self.strip = memoryview(bytearray(self.stride * self.strip_h))
        self.pile_last = [-1] * self.w  # 처음엔 모든 열을 그림 — 빈 열이어도 틀 높이가 들어감
        self.pile_edges, self.pile_body = self.snow_pile
        if kind in RAINY:
            self.rain_sprites = self.rain_set()
        elif kind == "snow":
            if "settled" not in self.sprite_cache:
                self.sprite_cache["settled"] = settled_set()
            self.settled_sprites = self.sprite_cache["settled"]
        elif kind == "fog":
            if "fog" not in self.sprite_cache:
                self.sprite_cache["fog"] = fog_field(self.w, int(self.h * FOG_REACH), random)
        elif kind == "aurora":
            if "aurora" not in self.sprite_cache:
                self.sprite_cache["aurora"] = aurora_field(self.w, int(self.h * AURORA_REACH), random)
            self.shooting, self.meteor_due = [], []
        elif kind == "window":
            if "window" not in self.sprite_cache:
                self.sprite_cache["window"] = [place(pane_drop(1 + k / 2), self.stride)
                                               for k in range(int((PANE_RMAX - 1) * 2) + 1)]
            self.pane_sprites, self.panes, self.runs = self.sprite_cache["window"], [], []
            if "window_rain" not in self.sprite_cache:
                self.sprite_cache["window_rain"] = shower_set(self.stride)
            self.rain_sprites = self.sprite_cache["window_rain"]
            self.splats, self.streaks, self.streak_due, self.pane_dry, self.shower_left = [], [], 0.0, 0.0, 0.0
            self.shower_in, self.shower_len = random.uniform(*PANE_SHOWER_EVERY) / 3, 1.0  # 첫 소나기는 일찍
            self.pane_due = count(self.amount) * PANE_SHARE / 2  # 첫 프레임에 반쯤 맺힌 채로 시작
        elif kind == "bugs":
            self.bugs = []
        elif kind == "soap":
            if "soap" not in self.sprite_cache:
                self.sprite_cache["soap"] = [[place(sp, self.stride) for sp in soap_balls(r, SOAP_HUES)] for r in SOAP_R]
            self.soap_sprites, self.soaps = self.sprite_cache["soap"], []
        elif kind == "fireflies":
            self.flies_sprites = self.fly_sprites()
        elif kind == "hail":
            if "hail" not in self.sprite_cache:
                self.sprite_cache["hail"] = [place(disc(r, soft, a, HAIL_COLOR, HAIL_RIM), self.stride)
                                             for r, soft, a in HAIL_SIZES]
            self.hail_sprites, self.stones = self.sprite_cache["hail"], []
        elif kind == "fireworks":
            self.fw = self.fw_sprites()
        elif kind == "aquarium":
            self.aquarium()
        if kind != "aquarium":  # 화면 크기 물빛·빛줄기 조각(2560×1440 에서 20MB)을 돌려줌. 다시 고르면 water_tint 가 40ms 에 만듦
            self.aq_tint = self.water = self.ray_rows = self.bubble_sprites = self.jelly_sprites = None
        self.fog_px = self.aurora_px = None  # 안개·오로라 행들(6·18MB)도. 무늬(오로라는 9MB)는 sprite_cache 에 남아 다시 고르면 양만 입힘
        self.rockets, self.sparks, self.next_launch = [], [], math.inf
        self.retune()

    def retune(self):
        """양·어항 막대에 수를 맞춤 — 다시 깔지 않아 쌓인 눈·모래와 떠 있던 것은 제자리, 모자라면 새로 띄우고 남으면
        버림. 설정 창이 막대를 끄는 동안 0.1초마다 부름. 불꽃놀이·뇌우 번개는 그릴 때 양을 바로 읽어 할 게 없음."""
        n, kind, layer = count(self.amount), self.kind, lambda layers, k: [round(n * k * l[0]) for l in layers]
        if kind == "snow":
            self.flakes = refit(self.flakes, layer(SNOW_LAYERS, 1), lambda li: self.new_flake(li, False))
        elif kind in RAINY:
            mult = RAIN_MULT * (STORM_MULT if kind == "storm" else 1)
            self.drops = refit(self.drops, layer(RAIN_LAYERS, mult), lambda li: self.new_drop(li, False))
        elif kind == "fog":
            self.fog_px = self.tint("fog", self.fog_px, lambda u: FOG_COLOR, FOG_ALPHA, lambda u: u ** 1.6)  # 아래가 짙음
        elif kind == "aurora" and (self.aurora_px is None or self.aurora_px[0] != self.amount):  # 색은 무늬에 들어 있음
            q = min(255, int(255 * AURORA_ALPHA * self.amount / 50))
            tab = bytes(v * q // 255 for v in range(256))
            self.aurora_px = self.amount, subpixel([r.translate(tab) for r in self.sprite_cache["aurora"]], AURORA_PHASES)
        elif kind == "window":
            self.pane_cap = round(n * PANE_SHARE)
            del self.panes[:max(0, len(self.panes) - self.pane_cap)]  # 남으면 오래된 것부터 마름
        elif kind == "bugs":
            self.bugs = refit(self.bugs, [round(n * BUG_SHARE)], lambda _: self.new_bug(), False)
        elif kind == "soap":
            self.soaps = refit(self.soaps, [round(n * SOAP_SHARE)], lambda _: self.new_soap(False), False)
        elif kind == "fireflies":
            self.flies = refit(self.flies, [round(n * FLY_SHARE)], lambda _: self.new_fly(), False)
        elif kind == "hail":
            self.stones = refit(self.stones, [round(n * HAIL_SHARE)], lambda _: self.new_stone(False), False)
        elif kind == "aquarium":
            self.water_tint()
            n = count(self.tank["bubbles"])  # 막대 50% 가 예전 양 50% 의 거품 수
            self.flakes = refit(self.flakes, layer(BUBBLE_LAYERS, BUBBLE_SHARE), lambda li: self.new_bubble(li, False))
            self.fish = refit(self.fish, [self.tank["fish"]], lambda _: self.new_fish(), False)
            if bool(self.school) != (self.tank["fish"] > 0):  # 떼는 물고기를 하나라도 고르면 하나
                self.school = self.new_school() if self.tank["fish"] else None
            rays = round(RAY_COUNT * self.tank["rays"] / 50)
            if len(self.rays_at) != rays:  # 고르게 벌려 놓으므로 수가 바뀌면 다시 놓음
                h, w = self.h, self.w
                reach = int(h * RAY_REACH)
                edge = w * RAY_WIDTHS[-1] * (1 + RAY_SPREAD) / 2  # 제일 넓은 모양의 퍼진 아래 끝 반폭
                lo, hi = edge, w - edge - (RAY_SLANT[1] + RAY_SWAY) * reach  # 퍼진 아래 끝까지 화면 안
                # [위 끝 가운데 x, 모양, 위상, 빠르기, 기울기, 밑 밝기 범위 lo · hi] — 기울기는 x 를 따라 부채꼴로 벌어짐
                xs = [] if hi <= lo else [lo + (i + random.uniform(0.15, 0.85)) * (hi - lo) / rays for i in range(rays)]
                self.rays_at = [[x, random.randrange(len(RAY_WIDTHS)), random.uniform(0, math.tau),
                                 random.uniform(0.08, 0.16), RAY_SLANT[0] + (RAY_SLANT[1] - RAY_SLANT[0]) * (x - lo) / (hi - lo),
                                 random.uniform(0.2, 0.45), random.uniform(0.7, 1.0)] for x in xs]
                self.rays_drawn = None  # 물빛에 구워 둔 옛 줄기를 지우고 다시 그림

    def water_tint(self):
        """어항 물빛과 그 위에 섞어 둔 거품·빛줄기·해파리 그림을 양에 맞춤. 2560×1440 에서 30–40ms 라 양이 바뀔 때만."""
        if self.aq_tint is None or self.aq_tint[0] != self.amount:  # 화면 크기 버퍼 하나라 지난 양 것은 안 남김
            h, aq = self.h, self.aq
            rows = water_rows(h, self.amount)
            bands = [rows[int((b + 0.5) * h / AQ_BANDS)] for b in range(AQ_BANDS)]
            water = bytearray(b"".join(p * self.w for p in rows))  # rays 가 빛줄기를 구워 넣음
            self.aq_tint = (self.amount, {
                "water": water, "water_c": (ctypes.c_char * len(water)).from_buffer(water), "rows": rows,
                "strip": b"".join(rows[h - self.strip_h:]),
                "bubbles": [[[[place(over(sp, under), self.stride) for sp in subs] for subs in radii]
                             for radii in aq["bubbles"]] for under in bands],
                "rays": tint_rays(aq["rays"], rows),
                "jelly": [[tinted(art, JELLY_COLORS, under) for art in JELLY_ART] for under in bands]})
            self.sand_base = None  # 모래 띠 바탕도 물빛이라 다음 프레임에 다시 그림
            self.rays_drawn = None  # 새 물빛엔 빛줄기가 없음
        t = self.aq_tint[1]
        self.water, self.bubble_sprites, self.ray_rows, self.jelly_sprites = t["water"], t["bubbles"], t["rays"], t["jelly"]

    # ── 동물 ──
    def react(self, now):
        """날씨에서 일어난 일을 동물들에게 알림 — 번개, 가까이 터진 불꽃, 낮게 나는 반딧불이·비눗방울·나비·잠자리."""
        bolt = self.bolt and self.bolt[0] != self.bolt_seen
        if bolt:
            self.bolt_seen = self.bolt[0]
        base, w = self.base, self.w  # 높이는 그 자리 바닥에서 셈. 거르는 건 동물이
        pts = [(f[0], f[1]) for f in self.flies] if self.kind == "fireflies" else \
            [(b[0] + SOAP_R[b[3]], b[1] + SOAP_R[b[3]]) for b in self.soaps] if self.kind == "soap" else \
            [(b[0], b[1]) for b in self.bugs] if self.kind == "bugs" else []
        low = [(x, self.h - y - base[min(max(int(x), 0), w - 1)]) for x, y in pts]
        for p in self.pets.values():
            p.kind, p.snowy = self.kind, self.kind in ("snow", "hail")
            if p.held or p.air or p.under:  # 들렸거나 떨어지는 중, 틀 뒤에 묻혀 빼꼼하는 동안은 날씨에 반응 안 함
                continue
            if bolt:
                p.startle(now)
            for x in self.bangs:
                if abs(x - p.x) < BANG_NEAR:
                    p.watch(now, x)
            if low:
                p.chase(now, low)
        self.bangs = []

    def hover(self):
        """커서 밑의 동물 — 나중에 그린 것(위에 보이는 것)부터. 없으면 None."""
        cx, cy = self.surface.cursor()
        for p in reversed(list(self.pets.values())):
            b = p.box()
            if b and b[0] <= cx < b[0] + b[2] and b[1] <= cy < b[1] + b[3]:
                return p
        return None

    def soap_at(self):
        """커서 밑의 비눗방울 — 위에 그린 것부터, 테두리 3px 밖까지 봐줌. 없거나 비눗방울 날이 아니면 None."""
        if self.kind != "soap":
            return None
        cx, cy = self.surface.cursor()
        for b in reversed(self.soaps):
            n, r = self.soap_sprites[b[3]][0][0], SOAP_R[b[3]] + 3
            if (cx - b[8] - n / 2) ** 2 + (cy - b[1] - n / 2) ** 2 <= r * r:
                return b
        return None

    def aim(self):
        """커서가 동물·비눗방울 위에 있거나 동물을 들고 있는 동안만 창이 클릭을 받게 함 — 그 밖은 늘 아래 창으로 통과.
        비눗방울은 동물 집기를 꺼도 터트릴 수 있음. 창 스타일은 바뀔 때만 고침."""
        on = self.visible and (self.drag and (any(p.held for p in self.pets.values()) or self.hover() is not None)
                               or self.soap_at() is not None)
        if on != self.catching:
            self.catching = on
            self.surface.catch(on)

    def press(self, down):
        """창이 받은 왼쪽 단추 — Surface 가 pump 중에 부름. 누르면 커서 밑 비눗방울을 터트리거나(동물보다 위에 그려짐)
        동물을 집고, 떼면 놓음(놓인 동물은 떨어짐)."""
        if not down:
            for p in self.pets.values():
                p.held = None
            return
        b = self.soap_at() if self.visible else None
        if b:
            n = self.soap_sprites[b[3]][0][0]
            self.pop(b[8] + n / 2, b[1] + n / 2, SOAP_R[b[3]])
            b[:] = self.new_soap(True)
            return
        hit = self.hover() if self.drag and self.visible else None
        if hit:
            cx, cy = self.surface.cursor()
            hit.grab(time.perf_counter(), cx - hit.at[0], cy - hit.at[1])

    def walk_pet(self, dt, now):
        rainy, wet = self.kind in RAINY, self.kind == "aquarium"
        self.react(now)
        cx, cy = self.surface.cursor() if any(p.held for p in self.pets.values()) else (0, 0)
        for p in self.pets.values():
            wide, tall = pet.DIVE_SIZE[p.DIVER] if wet else (p.W, p.H)
            if p.held:  # 커서를 따라감. 높이는 발밑을 구한 뒤에
                if wet and p.dive is None:
                    p.swim(0.0, now)  # 들고 있는 사이에 어항이 되면 잠수 장비부터 갖춤
                elif not wet:
                    p.dive = None
                p.x = min(max(cx - p.held[0], 0), max(0, self.w - wide))
            elif wet:  # 잠수 장비를 차고 헤엄 — 하던 짓은 멈춰 둠
                p.air = 0.0  # 떨어지던 중에 어항이 되면 그 자리에서 헤엄
                p.swim(dt, now)
            else:
                p.dive = None  # 어항을 벗어나면 바닥에서 하던 짓을 이어 감
                if p.air:
                    p.fall(dt, now)
                elif not p.under:  # 틀 뒤에 묻혀 빼꼼하는 동안은 제자리
                    p.update(dt, now, rainy)
            a, b = p.feet()
            want = max(v + f for v, f in zip(self.pile.h[a:b], self.base[a:b]))
            if p.held or p.air:  # 들리거나 떨어지는 동안은 틀 단을 안 뜀 — 발밑을 바로 바닥으로
                g = p.ground = want
                p.leap = None
            else:
                g = p.follow(want, dt, now)  # 틀 단은 뛰어 오르내림
            if p.held:  # 그림 윗줄이 커서에서 집은 자리만큼 위. 바닥 밑으로도 화면 위로도 안 나감
                up = min(max(self.h - g - tall - (cy - p.held[1]), 0), max(0, self.h - g - tall))
                if wet:
                    p.lift = p.depth = up  # 놓으면 이 높이에서 헤엄을 이어 감
                else:
                    p.air = up
            if wet:
                p.draw_swim(self.surface.pixels, self.stride, self.h, self.pet_sprites, g, now)
                if p.breathe:
                    self.exhale(*p.mouth)
            else:
                p.draw(self.surface.pixels, self.stride, self.h, self.pet_sprites, g + p.air, now, rainy,
                       self.base if p.under else None)

    def frame(self, dt, now):
        kind = self.kind
        # 날씨 없이 고양이만이면 고양이가 닿는 맨 아래 띠만 지우고 그만큼만 내보냄(180fps 에서 한 코어 43% → 아래 참고).
        # 종류를 바꾼 첫 프레임은 위에 남은 것까지 통째로. 맥 Surface 는 버퍼 둘을 번갈아 써서 늘 통째로
        nb = self.next_base
        if nb is not None:
            self.next_base = None
            if nb != self.goal:  # 내려앉는 중이었으면 지금 높이에서 다시 떨어지기 시작
                self.goal, self.fall = nb, (self.base, now)
                self.full_clear = True  # 동물이 있던 띠 위쪽까지 한 번 지움
        moved = self.fall is not None and self.sink(now)
        # 들거나 떨어지는 동물은 띠 위로 올라가서 그동안도 통째로
        lifted = any(p.held or p.air for p in self.pets.values())
        top = 0 if MAC or self.full_clear or kind != "none" or lifted else self.h - pet.BAND - self.rise
        self.full_clear = False
        if kind == "aquarium":  # 지우는 대신 미리 칠한 물빛으로 덮음 (2560×1440 memset 0.89 · memmove 1.15ms)
            self.rays(now)  # 빛줄기는 물빛 버퍼에 구움
            self.surface.fill(self.aq_tint[1]["water_c"])
        elif top:
            self.surface.clear(top)
        else:
            self.surface.clear()
        piled = kind in ("snow", "hail")
        if piled:
            if now - self.last_settle >= SETTLE_SEC:
                melt = MELT_PER_SEC * (HAIL_MELT if kind == "hail" else 1)
                el = now - self.last_settle
                self.pile.settle(melt * el)
                if kind == "snow":  # 우박 알은 무거워 안 날림
                    self.pile.blow(DRIFT * self.wind(now) * el)
                self.last_settle = now
                self.render_pile()
            elif moved:  # 바뀐 열만 그림
                self.render_pile()
            self.surface.pixels[(self.h - self.strip_h) * self.stride:] = self.strip
        elif kind == "aquarium":
            if self.sand_base is not self.base:  # 처음이거나 틀이 바뀜
                self.pile.h = list(self.sand)  # set_base 가 솟은 틀만큼 묻은 모래를 되살림
                self.render_sand()
                self.place_decor()
            self.surface.pixels[(self.h - self.strip_h) * self.stride:] = self.strip
            self.decor(now)
            self.weeds(now)
            self.crabs(dt, now)
            self.jellies(dt, now)
        elif kind == "fog":  # 동물은 안개 앞을 지나감
            self.fog(now)
        elif kind == "aurora":
            self.slide(self.aurora_px[1], 0, now, AURORA_DRIFT, AURORA_SWAY)
            self.meteors(dt, now)  # 하늘 멀리라 동물 뒤
        elif kind == "window":  # 소나기 빗줄기는 유리 바깥이라 동물 뒤
            self.shower(dt)
        if self.pets:  # 더미 위, 내리는 것 아래
            self.walk_pet(dt, now)
        if kind == "snow":
            self.snow(dt, now)
        elif kind == "soap":
            self.soap(dt, now)
        elif kind == "bugs":
            self.flutter(dt, now)
        elif kind == "window":  # 유리에 맺힌 것이라 동물 앞
            self.pane(dt)
        elif kind == "hail":
            self.hail(dt, now)
        elif kind == "fireworks":
            self.fireworks(dt, now)
        elif kind == "fireflies":
            self.fireflies(dt, now)
        elif kind == "aquarium":
            self.bubbles(dt, now, self.flakes, True)
            self.breaths = self.bubbles(dt, now, self.breaths, False)
            self.fishes(dt, now)
        elif kind in RAINY:
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
        if not MAC:
            self.aim()  # 집기를 껐고 비눗방울 날이 아니면 커서도 안 읽음
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
        self.rain_player.close()
        self.surface.close()


def check():
    if not getattr(sys, "frozen", False):  # 굳힌 exe 엔 소스 파일이 없음 — 같은 소스를 weather.yml 이 파이썬으로 봄
        hidden = {n for line in Path(__file__).read_text(encoding="utf-8").splitlines()
                  if re.match(r"\s*self\.\w+(\s*,\s*self\.\w+)*\s*=[^=]", line)
                  for n in re.findall(r"self\.(\w+)", line.split("=")[0]) if callable(Weather.__dict__.get(n))}
        assert not hidden, ("속성이 메서드를 가림 — 부르면 TypeError", hidden)
    fake =types.SimpleNamespace(surface=types.SimpleNamespace(pixels=bytearray(40 * 40 * 4)), stride=40 * 4, w=40, h=40,
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
             snow_sprites=snow_set(800), landed=[], glints=[], glint_due=0.0, settled_sprites=settled_set())
    li = next(i for i, layer in enumerate(SNOW_LAYERS) if layer[7])  # 쌓이는 층
    sf.new_flake = lambda li, top: [0.0, -1000.0, 0.0, li, 0, 0.0, 1.0]
    sf.settled = Weather.settled.__get__(sf)
    n = sf.snow_sprites[li][0][0][0]
    sf.flakes = [[x, 200 - 48 - n - 2, 300.0, li, 0, 0.0, 1.0] for x in (150.0, 50.0)]
    Weather.snow(sf, 1 / 60, 0.0)
    assert sf.flakes[0][1] == -1000 and sf.flakes[1][1] > 0 and sum(sf.pile.h[100:]) > 0 and not any(sf.pile.h[:100]), \
        "눈송이도 틀 위에서는 틀 윗변에, 틈에서는 계속 떨어짐"
    assert len(sf.landed) == 1 and sf.landed[0][1] >= 100, "쌓인 눈에 닿은 송이는 표면에 얹힘"
    # 눈앞 층은 쌓인 눈 앞을 지나 화면 밑변까지 가고 쌓이지 않음
    nn, before = sf.snow_sprites[SNOW_NEAR][0][0][0], sum(sf.pile.h)
    sf.flakes = [[150.0, 200 - 48 - nn - 2, 300.0, SNOW_NEAR, 0, 0.0, 1.0]]
    Weather.snow(sf, 1 / 60, 0.0)
    assert sf.flakes[0][1] > 0 and sum(sf.pile.h) == before, "눈앞 송이는 틀 윗변을 지나감"
    sf.flakes[0][1] = 200 - nn - 1
    Weather.snow(sf, 1 / 60, 0.0)
    assert sf.flakes[0][1] == -1000 and sum(sf.pile.h) == before, "밑변에서 다시 위로, 안 쌓임"
    sf.flakes = [[50.0, 10.0, 100.0, 1, 0, 1.0, 1.0]]
    Weather.snow(sf, 0.1, 0.3)
    assert abs(sf.flakes[0][1] - 20.0) > 1, "송이마다 낙하 빠르기가 오르내림"
    # 내려앉은 송이: 밝은 쪽을 남겨 찍어 흰 더미에 구멍을 안 내고, 작아지다 수명이 다하면 사라짐
    sf.flakes, sf.landed = [], [[100.0, 100, 2, 2, 0.0, 1.0]]
    sf.surface.pixels[:] = bytes((250, 250, 250, 255)) * (200 * 200)
    Weather.settled(sf, 0.01)
    assert min(bytes(sf.surface.pixels)[3::4]) == 255, "더미에 구멍을 안 냄"
    lit = []
    for age in (0.0, 0.8):
        sf.surface.pixels[:] = bytes(200 * 200 * 4)
        sf.landed[0][4] = age
        Weather.settled(sf, 0.01)
        lit.append(sum(map(bool, bytes(sf.surface.pixels)[3::4])))
    assert lit[0] > lit[1] > 0, ("작아지며 스밈", lit)
    Weather.settled(sf, 1.0)
    assert not sf.landed, "수명이 다하면 사라짐"
    # 반짝이는 1.5px 넘게 쌓인 열에만, 윗테두리에 걸쳐
    sf.pile.h, sf.glints, sf.glint_due = [1.0] * 200, [], 30.0
    Weather.settled(sf, 0.01)
    assert not sf.glints, "얇은 눈엔 안 반짝임"
    sf.pile.h, sf.glint_due = [3.0] * 200, 30.0
    sf.surface.pixels[:] = bytes(200 * 200 * 4)
    Weather.settled(sf, 0.01)
    assert len(sf.glints) == 30 and all(-0.5 <= g[1] <= 1 for g in sf.glints) and any(bytes(sf.surface.pixels)[3::4]), \
        "쌓인 눈엔 윗테두리에 반짝임"
    Weather.settled(sf, 1.0)
    assert not sf.glints, "깜빡이고 꺼짐"
    # 쌓인 눈 윗면: 오른쪽으로 오르는 비탈은 빛을 받아 밝고 내려가는 비탈은 푸르스름함. 맨 위 1px 은 이어진 테두리
    edges, bodies = pile_column_parts(PILE_STRIP)
    lf = types.SimpleNamespace(w=6, strip_h=PILE_STRIP, base=[0] * 6, pile=types.SimpleNamespace(h=[2.0, 4.0, 6.0, 6.0, 4.0, 2.0]),
                               pile_last=[-1] * 6, pile_edges=edges, pile_body=bodies, pile_zero=bytes(PILE_STRIP * 4),
                               strip=memoryview(bytearray(6 * 4 * PILE_STRIP)))
    Weather.render_pile(lf)
    col = lambda x: [bytes(lf.strip[(r * 6 + x) * 4:(r * 6 + x) * 4 + 4]) for r in range(PILE_STRIP)]
    assert sum(p[2] + p[0] for p in col(1)) > sum(p[2] + p[0] for p in col(4)) + 40, "빛 받는 비탈이 밝음"
    assert col(1)[PILE_STRIP - 4] == pixel(PILE_RIM, 255), "높이 4 면 밑에서 넷째 칸이 테두리"
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
             base=[0] * 100 + [48] * 100, pets={}, retune=lambda: None)
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
    ff = big(rockets=[], sparks=[], next_launch=math.inf, pets={}, bangs=[], fw=fw_set(800))
    ff.launch = lambda now: Weather.launch(ff, now)
    ff.burst = lambda x, y, kind=None: Weather.burst(ff, x, y, kind)
    peak = 0
    for i in range(180 * 20):
        Weather.fireworks(ff, 1 / 180, i / 180)
        peak = max(peak, len(ff.sparks))
    assert peak >= FW_SPARKS[0], "터짐"
    ff.amount = 0
    for i in range(180 * 5):  # 떠 있던 로켓이 오르는 1초 남짓 + 버들 수명
        Weather.fireworks(ff, 1 / 180, 20 + i / 180)
    assert not ff.sparks and not ff.rockets, "불꽃은 수명이 다하면 사라지고 0% 면 더 안 쏨"
    assert not ff.bangs, "동물이 없으면 터진 자리를 쌓아 두지 않음"
    seen, shifted = set(), 0
    for _ in range(400):
        ff.sparks = []
        ff.burst(100, 100)
        seen.add(ff.sparks[0][7])
        shifted += ff.sparks[0][8] != ff.sparks[0][6]
    assert seen == set(FW_KINDS) and shifted, ("모양마다 다 나오고 가끔 색이 바뀜", seen, shifted)
    for kind in ("ring", "heart"):
        ff.sparks = []
        ff.burst(100, 100, kind)
        assert abs(sum(s[2] for s in ff.sparks)) < 1e-6 > abs(sum(s[3] for s in ff.sparks)), kind + "는 고르게 놓임"
    tip = ff.sparks[28]  # t = π — 하트 아래 끝
    assert tip[3] > 0.9 * math.hypot(tip[2], tip[3]), "하트는 뾰족한 끝이 아래"
    ff.sparks = []
    ff.burst(100, 100, "crossette")
    stars = len(ff.sparks)
    for i in range(66):
        Weather.fireworks(ff, 1 / 120, 30 + i / 120)
    assert len(ff.sparks) == 4 * stars and all(not s[11] for s in ff.sparks), "갈라지기 별은 넷으로 쪼개지고 한 번만"

    def lit(kind, secs, c=0, c2=0, extra=0):  # 불꽃 하나를 secs 동안 띄움 — 프레임마다 (켜진 바이트 수, 버퍼)
        ff.sparks = [[60.0, 60.0, 150.0, 0.0, 0.0, 3.0, c, kind, c2, [], 0.0, extra, FW_KINDS[kind][3][1]]]
        for i in range(int(secs * 120)):
            ff.surface.pixels[:] = bytes(len(ff.surface.pixels))
            Weather.fireworks(ff, 1 / 120, 40 + i / 120)
            yield sum(1 for v in ff.surface.pixels[3::4] if v), ff.surface.pixels
    *_, (plain, _) = lit("peony", 0.3)
    *_, (tailed, _) = lit("chrysanthemum", 0.3)
    assert tailed > plain + 30 and len(ff.sparks[0][9]) == FW_KINDS["chrysanthemum"][3][1], ("꼬리를 끎", plain, tailed)
    ff.sparks = []
    ff.burst(100, 100, "willow")
    for i in range(120):  # 1초 — 가장 긴 꼬리(20점 × 0.035초)도 다 참
        Weather.fireworks(ff, 1 / 120, 50 + i / 120)
    lens = {len(s[9]) for s in ff.sparks}
    assert len(lens) > 5 and max(lens) <= FW_KINDS["willow"][3][1], ("버들 꼬리는 가닥마다 길이가 다름", lens)
    on = sum(1 for n, _ in lit("strobe", 0.6, FW_WHITE, FW_WHITE, 0.3) if n)
    assert 0.3 * 72 < on < 0.7 * 72, ("반짝이는 깜빡임", on)
    *_, (_, buf) = lit("peony", 1.8, 0, 3)  # 빨강 → 파랑, 수명 3초의 60%
    o = max(range(0, len(buf), 4), key=lambda o: buf[o + 3])
    assert buf[o] > buf[o + 2], "반 넘으면 둘째 색으로 바뀜"
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
    r = SOAP_R[0]
    rf.kind, rf.soaps = "soap", [[cat.x + 140 - r, 200 - 40 - r, 0, 0], [cat.x + 140 - r, 200 - 150 - r, 0, 0]]
    cat.go("walk", 0.0)
    Weather.react(rf, cat.calm)
    assert cat.state == "hop" and cat.pounce, "낮은 비눗방울로도 폴짝"
    rf.kind, rf.bugs = "bugs", [[cat.x + 140, 200 - 40], [cat.x + 140, 200 - 150]]
    cat.go("walk", 0.0)
    Weather.react(rf, cat.calm)
    assert cat.state == "hop" and cat.pounce, "낮은 나비로도 폴짝"
    assert "window" in SOUNDY and "window" not in RAINY and hearing("window", True, True, 0.5) == 0.5, \
        "창문 빗방울은 빗소리만 — 동물은 안 젖음"
    # 안개: 작업 표시줄 위 FOG_REACH 만 칠하고, 아래로 짙고, 시간 따라 흐르고, 무늬 끝이 처음과 이어짐
    row = fog_field(2000, 1, random.Random(1))[0]
    assert abs(row[0] - row[-1]) <= max(abs(a - b) for a, b in zip(row, row[1:])) + 1, "무늬가 화면 끝에서 이어짐"
    fg = big(rise=20, kind="fog", fog_px=None, sprite_cache={"fog": fog_field(200, int(200 * FOG_REACH), random.Random(1))})
    fg.slide, fg.tint = Weather.slide.__get__(fg), Weather.tint.__get__(fg)
    Weather.retune(fg)
    shots = []
    for now in (0.0, 5.0):
        fg.surface.pixels[:] = bytes(len(fg.surface.pixels))
        Weather.fog(fg, now)
        shots.append(bytes(fg.surface.pixels))
    p, top = shots[0], 200 - 20 - int(200 * FOG_REACH)
    alpha = [sum(p[(y * 200 + x) * 4 + 3] for x in range(200)) for y in range(200)]
    assert not any(alpha[:top]) and not any(alpha[180:]) and alpha[top + 2] < alpha[170], "칠하는 자리와 진하기"
    assert all(p[i + c] <= p[i + 3] for i in range(0, len(p), 4) for c in range(3)), "색은 알파를 곱한 값"
    i = max(range(0, len(p), 4), key=lambda i: p[i + 3])
    assert max(p[i:i + 3]) < p[i + 3], "안개 색을 입힘"
    assert shots[0] != shots[1], "흐름"
    # 오로라: 위 AURORA_REACH 만 칠하고, 위는 보라 아래는 초록, 아랫단 밑은 분홍 술, 흐르고, 무늬 끝이 처음과 이어짐
    rows = aurora_field(2000, 60, random.Random(2))
    row = max(rows, key=lambda r: sum(r[3::4]))[3::4]  # 가장 밝은 행의 알파
    assert abs(row[0] - row[-1]) <= max(abs(a - b) for a, b in zip(row, row[1:])) + 1 and max(row) > 60, "끝이 이어짐"
    assert len(rows) == 60 and len(rows[0]) == 2000 * 4, "크기"
    af = big(kind="aurora", aurora_px=None, sprite_cache={"aurora": aurora_field(200, int(200 * AURORA_REACH), random.Random(1))})
    af.slide = Weather.slide.__get__(af)
    Weather.retune(af)
    shots = []
    for now in (0.0, 5.0):
        af.surface.pixels[:] = bytes(len(af.surface.pixels))
        Weather.slide(af, af.aurora_px[1], 0, now, AURORA_DRIFT, AURORA_SWAY)
        shots.append(bytes(af.surface.pixels))
    p, reach = shots[0], int(200 * AURORA_REACH)
    assert any(p[3:reach * 800:4]) and not any(p[reach * 800 + 3::4]), "위 AURORA_REACH 만 칠함"
    assert all(p[i + c] <= p[i + 3] for i in range(0, len(p), 4) for c in range(3)), "색은 알파를 곱한 값"
    hue = lambda y: max((p[i + 1] - p[i + 2], i) for i in range(y * 800, y * 800 + 800, 4))[0]  # 초록 − 빨강 최대
    assert hue(int(reach * 0.75)) > 0 > min(p[i + 1] - p[i + 2] for i in range(4 * 800, 5 * 800, 4) if p[i + 3] > 8), \
        "아래는 초록, 위는 보라"
    lit = lambda y: sum(p[y * 800 + 3:y * 800 + 800:4])
    assert lit(4) < lit(int(reach * 0.62)) / 2, "아랫단 위로 갈수록 옅어짐"
    assert any(p[i + 2] > p[i + 1] + 8 for i in range(int(reach * 0.8) * 800, reach * 800, 4)), "아랫단 밑은 분홍"
    assert shots[0] != shots[1], "흐름"
    full = max(max(r[0][3::4]) for r in af.aurora_px[1])
    af.amount = 50
    Weather.retune(af)
    assert abs(max(max(r[0][3::4]) for r in af.aurora_px[1]) - full // 2) <= 2, "양에 비례"
    # 옮겨 본 벌: p 벌째는 오른쪽 이웃과 p/n 만큼 섞임. slide 는 정수 px 아래 몫으로 벌을 고름
    assert subpixel([bytes([0] * 4 + [200] * 4 + [0] * 4)], 2)[0][1] == bytes([100] * 8 + [0] * 4), "반 픽셀"
    sp = big()
    one = subpixel([bytes(40) + bytes([200] * 4) + bytes(756)], 4)
    for f, want in ((0.5, {9: 100, 10: 100}), (1.25, {8: 50, 9: 150}), (195.0, {15: 200})):  # 195 는 끝에서 감김
        sp.surface.pixels[:] = bytes(len(sp.surface.pixels))
        Weather.slide(sp, one, 0, 1.0, f, ())
        got = {x: sp.surface.pixels[x * 4 + 3] for x in range(200) if sp.surface.pixels[x * 4 + 3]}
        assert got == want, ("정수 px 아래 몫만큼 밀림", f, got)
    sp.surface.pixels[:] = bytes(len(sp.surface.pixels))
    Weather.slide(sp, one * 2, 0, 0.0, 0.0, ((4, 0.0, 1.0),))  # 행 j 는 4·sin(j) px 밀림
    lit = [min(x for x in range(200) if sp.surface.pixels[j * 800 + x * 4 + 3]) for j in range(2)]
    assert lit[0] == 10 and lit[1] == 6, ("행마다 출렁임", lit)
    # 유성: 덮어쓰지 않고 바이트마다 밝은 쪽을 남김 · 화면 밖은 잘라 냄
    gp = bytearray([90]) * 16
    glint(memoryview(gp), 8, 2, 1, [(0, -1, bytes([10, 200] * 4)), (1, 0, bytes([255] * 8))])  # 첫 픽셀은 왼쪽 밖, 둘째 행은 아래 밖
    assert gp == bytearray([90, 200] * 2 + [90] * 12), ("밝은 쪽만 남김", list(gp))

    def alphas(rows):  # (x, y) → 알파
        return {(x + i, y): d[i * 4 + 3] for y, x, d in rows for i in range(len(d) // 4) if d[i * 4 + 3]}
    a0, a1 = alphas(meteor_streak(50.0, 50.0, 0.6, 0.8, 100, 1.0)), alphas(meteor_streak(50.5, 50.0, 0.6, 0.8, 100, 1.0))
    cx = [sum(x * a for (x, _), a in m.items()) / sum(m.values()) for m in (a0, a1)]
    assert 0.4 < cx[1] - cx[0] < 0.6, ("반 px 옮기면 반 px 만큼 — 정수로 반올림하지 않음", cx)
    assert a0[50, 50] == 255 > a0[26, 18] > a0[2, -14] > 0, "머리가 가장 밝고 꼬리 끝으로 옅어짐"
    assert all((x - 50) * 0.6 + (y - 50) * 0.8 <= METEOR_R for x, y in a0), "머리 앞으로는 안 뻗음"
    mf = big(kind="aurora", amount=0, shooting=[], meteor_due=[(0.0, (100.0, -400.0))])
    Weather.meteors(mf, 0.01, 0.0)
    m = mf.shooting[0]
    assert len(mf.shooting) == 1 and not mf.meteor_due, "때가 된 유성이 나타남"
    assert m[3] > 0 and (m[0] - 100) * m[2] >= 0, "복사점에서 멀어지는 아래쪽으로"
    mf.shooting = [[100.0, 50.0, 0.6, 0.8, 100.0, 0.5, 1.0, 1.0, False]]  # 수명 60% 쯤 — 거의 가장 밝음
    Weather.meteors(mf, 0.1, 0.0)
    assert mf.surface.pixels[(58 * 200 + 106) * 4 + 3] > 200, "머리 자리가 밝음"
    Weather.meteors(mf, 0.5, 0.0)
    assert not mf.shooting, "수명이 다하면 사라짐"
    mf.surface.pixels[:] = bytes(len(mf.surface.pixels))
    mf.shooting = [[100.0, 50.0, 0.6, 0.8, 100.0, 0.0, 0.03, 1.0, False]]  # 막 떨어지기 시작함 — 2px 왔음
    Weather.meteors(mf, 0.02, 0.0)
    assert mf.surface.pixels[(52 * 200 + 101) * 4 + 3] and not mf.surface.pixels[(44 * 200 + 95) * 4 + 3], "시작점 뒤로 꼬리 없음"
    random.seed(4)
    mf.amount, showers = 100, []
    for i in range(300):
        mf.meteor_due = []
        Weather.meteors(mf, 50.0, i)  # 50초면 늘 하나는 옴 — 유성우면 나머지가 줄 서서 기다림
        showers += [mf.meteor_due] if mf.meteor_due else []
    assert 10 < len(showers) < 100, ("유성우는 가끔", len(showers))
    assert all(len(s) >= METEOR_BURST[0] - 1 and len({r for _, r in s}) == 1 for s in showers), "유성우는 한 복사점에서"
    # 비눗방울: 오르고, 수명이 다하거나 동물에 닿으면 터져 물방울이 튀고, 닿은 동물은 ♪
    mark = []
    toy = types.SimpleNamespace(box=lambda: (90, 150, 30, 30), emote=lambda m, now: mark.append(m))
    bf = big(pets={"toy": toy}, splashes=[], crowns=[], droplet=place(disc(0.8, 0.8, 190, RAIN_COLOR, RAIN_COLOR), 800),
             soap_sprites=[[place(sp, 800) for sp in soap_balls(r, SOAP_HUES)] for r in SOAP_R])
    for m in ("new_soap", "pop", "splatter", "soap_at"):
        setattr(bf, m, getattr(Weather, m).__get__(bf))
    bf.soaps = [[20.0, 60.0, 30.0, 0, 0.0, 1.0, 9.0, 0.0, 20.0]]
    Weather.soap(bf, 0.1, 0.0)
    assert bf.soaps[0][1] == 57 and not bf.splashes and not mark, "오름"
    bf.soaps[0][6] = 0.05
    Weather.soap(bf, 0.1, 0.0)
    assert bf.splashes and bf.soaps[0][6] > 1 and not mark, "수명이 다하면 터지고 새 방울"
    bf.splashes, bf.soaps = [], [[100.0 - SOAP_R[0], 165.0 - SOAP_R[0], 0.0, 0, 0.0, 0.0, 9.0, 0.0, 0.0]]
    Weather.soap(bf, 0.0, 0.0)
    assert bf.splashes and mark == ["♪"], "동물에 닿으면 터지고 ♪"
    # 비눗방울을 누르면 집기를 꺼 둬도 그 자리에서 톡. 빗나간 클릭은 아래 창으로
    caught = []
    n0 = bf.soap_sprites[0][0][0]
    bf.splashes, bf.soaps = [], [[0.0, 30.0, 0.0, 0, 0.0, 0.0, 9.0, 0.0, 40.0]]
    bf.kind, bf.visible, bf.drag, bf.catching = "soap", True, False, False
    bf.surface.catch = caught.append
    bf.surface.cursor = lambda: (40 + n0 // 2 + SOAP_R[0], 30 + n0 // 2)  # 그린 자리(b[8]) 의 오른쪽 끝
    Weather.aim(bf)
    assert caught == [True], "방울 위에선 클릭을 받음"
    Weather.press(bf, True)
    assert bf.splashes and bf.soaps[0][1] > 100, "누르면 터지고 새 방울"
    bf.surface.cursor = lambda: (5, 5)
    Weather.aim(bf)
    assert caught == [True, False], "방울 밖에선 통과"
    bf.splashes = []
    Weather.press(bf, True)
    assert not bf.splashes, "빗나간 클릭은 안 터트림"
    # 나비: 동물이 다가오면 날아오르고, 내려오다 바닥에 앉음. 잠자리: 떠 있다 휙 날아가 다시 멈춤 — 화면 안에서
    toy.held = None
    gf = big(pets={"toy": toy}, sprite_cache={}, bugs=[])
    gf.bug_sprites = Weather.bug_sprites.__get__(gf)
    bw, bh = gf.bug_sprites()[1][0]
    gf.bugs = [[100.0, 200 - bh / 2, 0, "rest", 99.0, 0.0, 0.0, 0.0, 40.0, 0, 0],
               [10.0, 200 - bh / 2, 1, "rest", 99.0, 0.0, 0.0, 0.0, 40.0, 0, 0],
               [180.0, 100.0, 2, "down", 0.0, math.pi / 2, 0.0, 0.0, 40.0, 0, 0],
               [100.0, 100.0, 4, "hover", 0.0, 0.0, 0.0, 0.0, 0.0, 0, 0]]
    Weather.flutter(gf, 0.02, 0.0)
    assert [b[3] for b in gf.bugs] == ["fly", "rest", "down", "dart"], "가까운 동물에 날아오름 · 먼 건 그대로"
    seen = set()
    for i in range(150):  # 3초 — 2.2초에 앉고 BUG_REST 동안은 그대로
        Weather.flutter(gf, 0.02, i * 0.02)
        seen.add(gf.bugs[3][3])
    assert gf.bugs[2][3] == "rest" and gf.bugs[2][1] == 200 - bh / 2, "내려와 바닥에 앉음"
    assert seen == {"hover", "dart"}, "잠자리가 날아갔다 다시 멈춤"
    assert all(0 <= b[0] <= 200 and 0 <= b[1] <= 200 for b in gf.bugs), "화면 안"
    # 창문 빗방울: 닿는 방울은 합쳐지고, 흐르는 방울은 아래 방울을 삼키고 위에 자국을 남기다 바닥에서 사라짐
    wf = big(rise=20, panes=[], runs=[], pane_cap=99, pane_due=0.0, amount=0, splats=[], pane_dry=0.0,
             pane_sprites=[place(pane_drop(1 + k / 2), 800) for k in range(int((PANE_RMAX - 1) * 2) + 1)])
    wf.wet = Weather.wet.__get__(wf)
    wf.wet(50, 50, 3)
    wf.wet(54, 50, 3)
    wf.wet(150, 50, 3)
    assert len(wf.panes) == 2 and abs(wf.panes[0][2] - math.hypot(3, 3)) < 1e-9, "닿으면 하나로, 물 양은 더함"
    wf.panes = [[100.0, 120.0, 5.0]]
    wf.runs = [[100.0, 60.0, 6.0, 9.0, True, 100.0, 0.0, 5.0]]
    Weather.pane(wf, 0.1)
    assert len(wf.panes) == 2 and wf.panes[1][1] < 70 and wf.panes[0][1] == 120, "자국은 지나온 위에"
    for _ in range(6):
        Weather.pane(wf, 0.1)
    assert all(p[2] < 2.5 for p in wf.panes) and wf.runs and wf.runs[0][2] > 6, "아래 방울을 삼켜 커짐 — 자국만 남음"
    for _ in range(30):
        Weather.pane(wf, 0.1)
    assert not wf.runs, "바닥에서 사라짐"
    wf.pane_cap, n = 1, len(wf.panes)
    Weather.pane(wf, 0.01)
    assert n > 1 and len(wf.panes) == n, "넘쳐도 한꺼번에 안 마름"
    Weather.pane(wf, 1.0)
    assert len(wf.panes) == 1, "너무 많으면 오래된 것부터 마름"
    wf.panes, wf.pane_dry, amount, wf.amount = [[10.0 + 4 * i, 50.0, 1.0] for i in range(40)], 0.0, wf.amount, 0
    Weather.pane(wf, 0.2)  # 넘친 39개 → (8 + 39/8) × 0.2 = 2.6 이라 오래된 둘만
    assert len(wf.panes) == 38 and wf.panes[0][0] == 18.0, ("소나기 뒤에도 조금씩 마름", len(wf.panes))
    wf.amount = amount
    # 새 방울은 유리에 탁 부딪혀 퍼졌다 오므라든 뒤 맺히고, 큰 방울은 잔방울을 튀김. 처음 채울 때는 그냥 맺힘
    random.seed(3)

    def spread():  # 칠한 칸이 가장 넓은 행의 폭
        p = wf.surface.pixels
        lit = [[x for x in range(200) if p[(y * 200 + x) * 4 + 3]] for y in range(200)]
        return max((r[-1] - r[0] for r in lit if r), default=0)
    wf.panes, wf.pane_cap, wf.splats = [], 99, [[100.0, 100.0, 5.0, 0.0]]
    for dt in (0.01, 0.2):
        wf.surface.pixels[:] = bytes(len(wf.surface.pixels))
        Weather.pane(wf, dt)
        if dt < 0.1:
            hit = spread()
            assert not wf.panes and len(wf.splats) == 1, "부딪히는 동안은 아직 안 맺힘"
    assert hit > spread() + 3 and wf.panes and wf.panes[0][2] >= 5 and not wf.splats, ("퍼졌다 오므라들어 맺힘", hit, spread())
    for r, want in ((2.0, 10), (5.0, 11)):  # 16px 씩 띄워 서로 안 닿음
        wf.panes, wf.splats = [], [[20.0 + 16 * i, 100.0, r, 0.0] for i in range(10)]
        Weather.pane(wf, 0.2)
        assert len(wf.panes) >= want if r > PANE_SPRAY_R else len(wf.panes) == want, ("큰 방울만 잔방울을 튀김", r, len(wf.panes))
    wf.panes, wf.amount, wf.pane_due = [], 50, 0.99
    Weather.pane(wf, 0.01)
    assert len(wf.splats) == 1 and not wf.panes, "새 방울은 부딪히며 생김"
    wf.splats, wf.pane_due = [], 10.0
    Weather.pane(wf, 0.01)
    assert not wf.splats and wf.panes, "처음 채울 때 · 돌아왔을 때는 한꺼번에 부딪히지 않고 그냥 맺힘"
    # 소나기: 때가 되면 몇 초 동안 빗줄기가 쏟아지고 몇은 유리에 부딪혀 맺힘, 지나가면 그침
    random.seed(7)
    sf = big(rise=20, amount=50, splats=[], streaks=[], streak_due=0.0, shower_in=0.05, shower_left=0.0, shower_len=1.0,
             rain_sprites=shower_set(800))
    seen = []
    for _ in range(400):  # 8초
        Weather.shower(sf, 0.02)
        seen.append(len(sf.streaks))
    assert not any(seen[:2]) and max(seen) > 3 and sf.splats, ("때가 되면 쏟아지고 몇은 유리에 부딪힘", max(seen), len(sf.splats))
    assert any(bytes(sf.surface.pixels)[3::4]), "빗줄기가 그려짐"
    assert all(s[1] <= 160 for s in sf.splats), "작업 표시줄 위에서만 맺힘"
    assert not sf.streaks and sf.shower_left <= 0 and sf.shower_in > 30, "지나가면 그침"
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
    # 틀이 다시 솟으면(전체 화면을 풂) 그 뒤에 묻혔다 머리만 빼꼼 내밀고 뛰어나옴 — 틀 아래로는 안 그림
    for i in range(60):
        Weather.walk_pet(gf, 1 / 60, (3 + i) / 60)
    walker.x = 120
    Weather.set_base(gf, [0] * 200)
    assert walker.ground == 0 and not walker.under, "발밑 바닥이 그대로면 안 묻힘"
    Weather.set_base(gf, [0] * 100 + [48] * 100)
    assert walker.under, "발밑에 틀이 솟으면 묻힘"
    tops = set()
    for i in range(60 * 3):
        gf.surface.pixels[:] = bytes(len(gf.surface.pixels))
        Weather.walk_pet(gf, 1 / 60, 2 + i / 60)
        ink = gf.surface.pixels
        if any(ink):
            tops.add((len(ink) - len(ink.lstrip(b"\0"))) // 800)
            assert walker.x == 120 and not any(ink[(200 - 48) * 800:]), "묻힌 동안 제자리, 틀 아래는 안 그림"
        if not walker.under:
            break
    assert 200 - 48 - walker.PEEK * pet.SCALE in tops and walker.ground == 48, ("빼꼼 내밀고 틀 위로 나옴", sorted(tops))
    rab = pet.Rabbit(200, random.Random(1))
    rab.x = 10
    rab.follow(0.0, 1 / 60, 0.0)
    gf.pets, gf.base = {"rabbit": rab}, [0] * 200
    Weather.set_base(gf, [0] * 100 + [48] * 100)
    assert not rab.under, "틈에 선 동물은 안 묻힘"
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
        assert len(pile_column(v, edges, body[PILE_SLOPES], bytes(PILE_STRIP * 4))) == PILE_STRIP * 4, "열 길이가 띠 높이"
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
    white, s = pixel((255, 255, 255), 255), pixel(SHADE, 255 * SHADE_K)
    assert shade((1, [(0, white)])) == (3, [(0, s + white + s), (0, s * 3)]), "그림자는 양옆·아래 1px, 그림은 위에"
    assert all(abs(s[c] + 30 * (255 - s[3]) // 255 - 30) <= 16 for c in range(3)), "그림자는 어두운 창(#1e1e1e) 위에선 묻힘"
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
    a.goal, a.fall, a.crumble, a.tank = a.base, None, crumble(aw), {k: TANK[k][1] for k in TANK}
    a.surface = types.SimpleNamespace(pixels=bytearray(aw * ah * 4), clear=lambda top=0: None, present=lambda top=0: None)
    a.surface.fill = lambda src: a.surface.pixels.__setitem__(slice(None), src)
    a.reset()
    assert (len(a.fish), len(a.flakes), len(a.rays_at)) == (FISH_N, 30, RAY_COUNT), "어항 막대 50% 면 예전 수 그대로"
    a.flakes, a.crab = [], []  # 해초 뿌리 밑을 거품·게가 가리지 않게
    a.frame(1 / 60, 0.0)
    px, st = a.surface.pixels, a.stride
    at = lambda x, y: bytes(px[y * st + x * 4:y * st + x * 4 + 4])
    assert at(0, 0) == tint[0] and at(0, 150) == tint[150], "지우는 대신 물빛으로 덮음"
    assert any(at(x, 40) != tint[40] for x in range(aw)), "위쪽에 빛줄기"
    assert all(all(d[i + c] <= d[i + 3] for i in range(0, len(d), 4) for c in range(3))
               for rows in a.ray_rows for lv in rows for _, d in lv), "빛줄기는 premultiplied"

    def baked():  # 지금 자리·밝기의 빛줄기를 새 물빛에 처음부터 통째로 그린 것
        want = bytearray(b"".join(p * aw for p in a.aq_tint[1]["rows"]))
        for (x0, shape, _, _, slant, *_), (sway, lv, xs) in zip(a.rays_at, a.rays_drawn):
            n = len(xs)
            assert xs == [int(x0 + j * (slant + sway / (n - 1))) for j in range(n)]
            for j, (lead, d) in enumerate(a.ray_rows[shape][lv]):
                want[j * st + (xs[j] + lead) * 4:j * st + (xs[j] + lead) * 4 + len(d)] = d
        return want
    moved, t, keep = set(), 0.0, (random.getstate(), a.flakes, a.crab)  # 아래 검사들이 보는 난수·거품·게는 그대로
    for i in range(1500):  # 바뀐 행만 고쳐 온 물빛이 통째로 다시 그린 것과 같음 — 줄기 수·양이 바뀌어도
        t += random.choice((1 / 180, 1 / 60, 0.4, 7.0))
        if i in (500, 750, 1000):
            a.tank["rays"], a.amount = {500: (100, 70), 750: (100, 30), 1000: (30, 50)}[i]
            a.retune()
        a.frame(1 / 60, t)
        moved.add(tuple(map(tuple, (d[:2] for d in a.rays_drawn))))
        assert all((sway, lv) == (round(RAY_SWAY * (len(xs) - 1) * math.sin(t * sp * 3 + ph)),
                                  ray_level(lo, hi, math.sin(t * sp * 2 + 2 * ph)))
                   for (_, _, ph, sp, _, lo, hi), (sway, lv, xs) in zip(a.rays_at, a.rays_drawn)), "지금 시각의 자리·밝기"
        if i % 50 == 0 or i in (501, 751, 1001):
            assert a.water == baked(), ("구워 둔 빛줄기가 통째로 그린 것과 다름", i)
    assert len(moved) > 100, "빛줄기는 흔들리고 밝기가 오감"
    a.tank, a.amount = {k: TANK[k][1] for k in TANK}, 50
    a.retune()
    state, a.flakes, a.crab = keep
    random.setstate(state)
    sand_top = pixel(SAND_COLORS[0], 255)
    for nb in (None, [rise] * aw):  # 틀이 왼쪽까지 넓어져도
        if nb:
            a.next_base = nb
            a.frame(1 / 60, 0.0)
        for x, rows, *_ in a.aq["weeds"]:  # 뿌리 높이는 x 열로 정함 — 옆 열은 모래가 1px 다를 수 있어 x 열만 봄
            y = ah - a.base[x] - a.sand[x]
            assert at(x, y - 1) == rows[0][:4] and at(x, y) == sand_top, ("해초 뿌리는 틀 윗변의 모래 위", x, nb)
        assert at(5, ah - a.base[5] - a.sand[5]) == sand_top and at(5, ah - a.base[5]) != sand_top, "모래는 틀 위"
    xs = [x for x, *_ in a.aq["weeds"]]
    assert all(any(0 < abs(x - y) <= 7 for y in xs) for x in xs), "해초는 2–3 포기씩 덤불로"
    assert len({rows[0][:4] for _, rows, *_ in a.aq["weeds"]}) == 2, "뒤 포기는 어두움"
    _, rows, _, _, sway = a.aq["weeds"][0]
    for t in (0.3, 2.0, 4.5):
        for j, (p, q, _) in enumerate(sway):
            u = j / len(rows)
            assert abs(math.sin(t) * p - math.cos(t) * q - WEED_SWAY * u * u * math.sin(t - u * 2.4)) < 1e-9, "흔들림 펼친 식"
    keep, (x, rows, phase, speed, _) = a.aq["weeds"], a.aq["weeds"][-1]
    a.aq["weeds"], now = keep[-1:], (math.tau - phase) / speed  # cos t = 1 — 펼친 식의 둘째 항이 제일 큰 때
    px[:] = bytes(len(px))
    a.weeds(now)
    j = len(rows) - 1
    u, y = j / len(rows), ah - a.base[x] - int(a.pile.h[x]) - 1 - j
    xx = x + int(WEED_SWAY * u * u * math.sin(math.tau - u * 2.4)) - len(rows[j]) // 8
    assert at(xx, y) == rows[j][:4], ("해초 꼭대기는 흔들린 자리에", xx, y)
    a.aq["weeds"] = keep
    a.flakes = [a.new_bubble(li, False) for li in (0, 1) for _ in range(10)]
    for f in a.flakes:
        f[1] = ah / 2
    a.bubbles(0.05, 1.0, a.flakes, True)
    assert all(f[1] < ah / 2 for f in a.flakes), "거품은 위로"
    a.flakes[0][1] = -50
    assert len(a.bubbles(0.05, 1.1, a.flakes, True)) == 20 and a.flakes[0][1] > ah * 0.8, "수면을 넘은 거품은 바닥에서 다시 나옴"
    a.flakes[1][1] = -50
    assert a.flakes[1] not in a.bubbles(0.05, 1.2, a.flakes, False), "내쉰 숨 거품은 수면을 넘으면 사라짐"
    # 동물은 잠수 장비를 차고 떠올라 헤엄치며 호흡기에서 거품을 내쉼. 어항을 벗어나면 바닥에서 하던 짓으로
    assert pet.SWIM_RISE < min(layer[2][0] for layer in BUBBLE_LAYERS), "떠오르는 동물이 제 숨 거품을 앞지르지 않음"
    dog = pet.Dog(aw, random.Random(5))
    a.pets, a.pet_sprites, a.bolt_seen, a.bangs, a.flakes = {"dog": dog}, pet.sprites(), None, [], []
    state, puffs, first = dog.state, 0, None
    for i in range(60 * 8):
        a.frame(1 / 60, i / 60)
        if dog.breathe:
            puffs += 1
            first = first or (a.breaths[-1], a.breaths[-1][1])
            new = a.breaths[-BREATH_BUBBLES[0]:]
            assert all(abs(f[0] - dog.mouth[0]) <= 2 and dog.mouth[1] - 10 <= f[1] <= dog.mouth[1] for f in new),                 ("거품은 호흡기에서", dog.mouth, new)
    assert dog.dive == 0 and dog.lift > 60 and dog.state == state and puffs >= 3, ("떠서 헤엄", dog.lift, puffs)
    assert first[0] not in a.breaths or first[0][1] < first[1] - 100, "숨 거품은 위로"
    # 어항에서 집어 올렸다 놓으면 안 떨어지고 그 높이에서 헤엄을 이어 감
    a.visible, a.drag, lift0 = True, True, dog.lift
    bx, by, *_ = dog.box()
    a.surface.cursor = lambda: (bx + 5, by + 5)
    a.press(True)
    a.surface.cursor = lambda: (bx + 5, by + 5 - 40)
    a.frame(1 / 60, 8.0)
    up = dog.lift
    assert dog.held and abs(up - int(lift0) - 40) <= 1, ("어항에선 헤엄 높이를 끌어 올림", lift0, up)
    a.press(False)
    a.frame(1 / 60, 8.0 + 1 / 60)
    assert not dog.held and not dog.air and abs(dog.lift - up) <= pet.SWIM_RISE / 60 + pet.SWIM_BOB, \
        ("놓으면 안 떨어지고 그 높이에서 헤엄", up, dog.lift)
    a.kind = "none"
    a.reset()
    a.frame(1 / 60, 8.0)
    assert dog.dive is None and not a.breaths, "어항을 벗어나면 바닥으로"
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
    # 돌아서기: 빠르기가 옛 방향에서 0 을 지나 새 방향으로 넘어가고, 가운데 반 동안은 반쪽 폭 그림
    random.seed(3)
    f = a.new_fish()
    f[0], f[2], f[7] = 0.0, -1, 0.0
    a.swim(f, 30, 30, 1 / 60, 0.0)
    assert f[2] == 1 and f[7] == FISH_FLIP, ("벽에 닿으면 천천히 돌기 시작", f)
    f[0], f[2], f[4], f[7] = 150.0, 1, 0, FISH_FLIP
    xs = [f[0]]
    for _ in range(int(FISH_FLIP * 60) + 6):
        a.swim(f, 30, 30, 1 / 60, 0.0)
        xs.append(f[0])
    dx = [b - c for c, b in zip(xs, xs[1:])]
    assert dx[0] < 0 < dx[-1] and min(map(abs, dx)) < max(map(abs, dx)) * 0.2, ("돌아설 때 빠르기가 0 을 지나감", dx)
    a.fish, a.school = [f], None
    for left, want in ((FISH_FLIP / 2, a.aq["fish_thin_w"][0]), (0.0, a.aq["fish_size"][0][0])):
        f[7] = left
        px[:] = bytes(len(px))
        a.fishes(0, 0.0)
        cols = {i // 4 % aw for i in range(3, len(px), 4) if px[i]}
        assert max(cols) - min(cols) + 1 == want, ("돌아서는 가운데만 반쪽 폭", left, max(cols) - min(cols) + 1, want)
    shots = []
    for d, left in ((1, FISH_FLIP * 0.9), (-1, 0.0)):
        f[2], f[7] = d, left
        px[:] = bytes(len(px))
        a.fishes(0, 0.0)
        shots.append(bytes(px))
    assert shots[0] == shots[1], "돌아서기 앞 반은 아직 옛 방향을 봄"
    xs = [f[0]]
    for i in range(60):
        a.swim(f, 30, 30, 1 / 60, i / 60)
        xs.append(f[0])
    dx = [abs(b - c) for c, b in zip(xs, xs[1:])]
    assert max(dx) > 1.5 * min(dx), ("꼬리를 칠 때마다 빨라졌다 느려짐", min(dx), max(dx))
    # 떼: 따르는 것들이 우두머리 곁에 위아래로 퍼져 대개 우두머리와 같은 쪽을 봄
    random.seed(5)
    a.fish, a.school = [], a.new_school()
    lead, members = a.school
    facing, behind, far = [0] * len(members), [0] * len(members), 0
    for i in range(60 * 60):
        a.fishes(1 / 60, i / 60)
        if i >= 600:
            for j, m in enumerate(members):
                facing[j] += m[6] == (lead[2] > 0)
                behind[j] += (m[0] - lead[0]) * lead[2] < 0
                far = max(far, abs(m[1] - lead[1] - m[3]))
    assert min(facing) > 50 * 60 * 0.7 and min(behind) > 50 * 60 * 0.6 and far < 20, \
        ("떼는 우두머리 뒤를 따름", facing, behind, far)
    assert max(m[3] for m in members) - min(m[3] for m in members) > 10, "떼는 위아래로 퍼짐"
    # 바닥 장식 · 보물상자 · 게 · 해파리 · 새 물고기
    arts = [*((r, DECOR_COLORS) for r in (*DECOR_ART, *CHEST_ART, *CRAB_ART)), *((r, JELLY_COLORS) for r in JELLY_ART),
            *((r, FISH_COLORS) for r, _ in (*FISH_ART, SCHOOL_ART))]
    for rows, colors in arts:
        assert len({len(r) for r in rows}) == 1 and set("".join(rows)) <= {".", *colors}, ("그림 칸이 맞음", rows[0])
    assert all(len(alt) == len(rows) for rows, alt in (*FISH_ART, SCHOOL_ART)), "꼬리 그림 행 수"
    a.kind, a.pets = "aquarium", {}
    del a.sprite_cache["aquarium"]  # 폭 400 이라 틈이 몇 없음 — 장식 · 상자가 다 놓이는 자리로 다시 고름
    random.seed(1)  # 장식 둘 · 상자 (scratchpad 에서 찾은 값)
    a.reset()
    a.flakes, a.crab, aq = [], [], a.aq

    def sits(x, y, sh, segs):  # 그림 맨 아래 행이 (x, y) 에 찍혀 있음
        return all(px[(y + dy) * st + x * 4 + k:(y + dy) * st + x * 4 + k + len(d)] == d for dy, k, d in segs if dy == sh - 1)
    def seated():  # 장식마다 앉은 자리(x 는 단에서 넘어가 옮겨졌을 수 있음)의 바닥 위에 찍혀 있음
        return all(y + dh == a.floor_at(x, dw) and sits(x, y, dh, segs)
                   for (x, y, segs), (_, (dw, dh), _) in zip(a.decor_at, aq["decor"]))
    assert aq["decor"] and aq["chest_x"] is not None, ("장식과 상자가 놓임", len(aq["decor"]))
    for t, nb in ((20.0, None), (20.1, [0] * 100 + [rise] * 300)):  # 틀이 바뀌면 새 바닥 위로
        if nb:
            a.next_base = nb
        a.frame(1 / 60, t)
        assert seated(), ("장식은 바닥 위", nb is not None)
    cx, (cw, ch) = a.chest_x, aq["chest_size"][1]
    a.chest, a.breaths = [30.0, 30.0], []
    for i in range(int(60 * CHEST_OPEN)):
        a.frame(1 / 60, 30 + i / 60)
        assert sits(cx, a.chest_floor - ch, ch, aq["chest"][1]), "열린 상자는 바닥 위"
    opened = len(a.breaths)
    assert CHEST_OPEN / CHEST_PUFF * 0.8 <= opened <= CHEST_OPEN / CHEST_PUFF + 2, ("열린 동안 거품", opened)
    mouth = a.chest_floor - ch + 3 * pet.SCALE
    assert all(abs(f[0] - cx - cw / 2) <= cw * 0.3 + 1 and f[1] <= mouth for f in a.breaths), "거품은 상자 입에서 위로"
    assert max(f[1] for f in a.breaths) > mouth - 10, "막 나온 거품은 상자 입 가까이"
    for i in range(60):
        a.frame(1 / 60, 30 + CHEST_OPEN + i / 60)
        sh = aq["chest_size"][0][1]
        assert sits(cx, a.chest_floor - sh, sh, aq["chest"][0]), "닫힌 상자"
    assert len(a.breaths) <= opened, "닫히면 안 뿜음"
    # 틀 단에 반 넘게 허공으로 걸치면 낮은 쪽으로 넘어가 단 옆 바닥에 앉음. 반 넘게 틀 위면 걸친 채 틀 위
    keep, ox, ow = a.base, aq["chest_x"], aq["chest_size"][0][0]
    for shape, side in (([0] * (ox + ow * 3 // 4) + [rise] * aw, -1),  # 오른쪽 1/4 만 틀 위 → 왼쪽으로
                        ([0] * (ox + ow // 4) + [rise] * aw, 0),        # 3/4 가 틀 위 → 그대로
                        ([rise] * (ox + ow // 4) + [0] * aw, 1),        # 왼쪽 1/4 만 틀 위 → 오른쪽으로
                        ([rise] * (ox + ow // 4) + [0] * (ow // 2) + [rise] * aw, 0)):  # 양쪽 틀에 걸친 다리 → 그대로
        a.base = a.goal = a.pile.base = shape[:aw]
        a.sand_base = None
        a.frame(1 / 60, 50.0)
        x, is_open = a.chest_x, int(50.0 >= a.chest[0])
        under, sh = set(a.base[x:x + ow]), aq["chest_size"][is_open][1]
        assert (x > ox) - (x < ox) == side and (under == {0} if side else under == {0, rise}), ("단에서 넘어감", side, x, ox)
        assert a.chest_floor == a.floor_at(x, ow) and sits(x, a.chest_floor - sh, sh, aq["chest"][is_open]), \
            ("넘어간 상자는 그 자리 바닥 위", side)
        assert seated(), ("장식도 단에서 넘어가 바닥 위", side)
    a.base = a.goal = a.pile.base = keep
    a.sand_base = None
    a.reset()
    cw, ch = aq["crab_size"]
    walked, settled, sides = 0, 0, set()
    for i in range(60 * 120):
        old = [c[:] for c in a.crab]
        a.crabs(1 / 60, 40 + i / 60)
        for c, b in zip(a.crab, old):
            assert 0 <= c[0] <= aw - cw, ("게는 화면 안", c)
            assert b[3] or c[3] or c[0] == b[0], "서 있을 땐 안 걸음"
            assert b[4] is None or abs(c[4] - b[4]) <= 300 / 60 + 1e-9, "틀 단은 기어오름"
            settled += c[4] == a.floor_at(int(c[0]), cw) - ch
            walked += c[3]
            sides.add(c[1])
    n = 60 * 120 * CRAB_N
    assert sides == {1, -1} and 0.3 < walked / n < 0.9 and settled / n > 0.9, ("게는 모래 위를 걷다 섬", walked / n, settled / n)
    lo, hi = a.jelly_band()
    jw = aq["jelly_size"][0]
    ys, pulses, rising = [], 0, 0
    for i in range(60 * 180):
        old = [j[:] for j in a.jelly]
        a.jellies(1 / 60, 200 + i / 60)
        for j, b in zip(a.jelly, old):
            assert lo <= j[1] <= hi and 0 <= j[0] <= aw - jw, ("해파리는 제 높이 안", j)
            pulses += j[4] != b[4]
            rising += j[1] < b[1]
            ys.append(j[1])
    n = 60 * 180 * JELLY_N
    assert pulses >= 20 and 0.05 < rising / n < 0.6 and max(ys) - min(ys) > 60, ("해파리는 오므려 오르고 가라앉음", pulses, rising / n)
    datas = [d for band in a.jelly_sprites for fr in band for _, _, d in fr]
    assert all(d[i + c] <= d[i + 3] for d in datas for i in range(0, len(d), 4) for c in range(3)), "해파리는 premultiplied"
    assert any(d[i + 3] < 255 for d in datas for i in range(0, len(d), 4)), "해파리는 비침"
    # 어항 막대: 물고기는 마릿수, 거품·빛줄기는 0% 면 없고 100% 면 두 배. 양은 물빛만 — 거품 수와 무관
    a.amount, a.tank = 100, {"fish": 0, "bubbles": 100, "rays": 100}
    a.reset()
    reach = int(ah * RAY_REACH)
    assert (len(a.fish), len(a.flakes), len(a.rays_at)) == (0, 60, 2 * RAY_COUNT), \
        ("막대 0·100% 면 없음·두 배, 양과 무관", len(a.fish), len(a.flakes), len(a.rays_at))
    assert a.school is None, "물고기 0 이면 떼도 없음"
    assert all(0 <= int(x0 + j * (slant + sw)) + lead and int(x0 + j * (slant + sw)) + lead + len(d) // 4 <= aw
               for x0, shape, _, _, slant, *_ in a.rays_at for sw in (-RAY_SWAY, RAY_SWAY)
               for lv in a.ray_rows[shape] for j, (lead, d) in enumerate(lv)), "빛줄기가 두 배여도 퍼진 아래 끝까지 화면 안"
    slants = [r[4] for r in a.rays_at]
    assert slants == sorted(slants) and RAY_SLANT[0] <= slants[0] < slants[-1] <= RAY_SLANT[1], "빛줄기는 부채꼴로 벌어짐"
    assert [ray_level(0.2, 1.0, s) for s in (-1, 0, 1)] == [1, 4, 7] and ray_level(0, 0, -1) == 0, "밝기 단계는 lo–hi 를 오감"
    under = tint[40]
    (_, d), = tint_rays([[(0, bytes(range(256)))]], [under])[0][-1]
    exact = [(a * col + under[c] * (255 - a)) / 255 for a in range(256) for c, col in enumerate((*RAY_COLOR[::-1], 255))]
    assert all(abs(v - e) <= 0.5 for v, e in zip(d, exact)), "빛줄기 섞기는 반올림 — 내림 두 번이면 가장자리가 물빛보다 어두움"
    a.tank = {"fish": FISH_MAX, "bubbles": 0, "rays": 0}
    a.reset()
    assert (len(a.fish), len(a.flakes), a.rays_at) == (FISH_MAX, 0, []), "물고기는 고른 마릿수, 거품·빛줄기 없음"
    a.fish, a.jelly = [], []  # 물고기·해파리는 화면 위 10% 아래로만 — 20 행은 그래도 비지만 다른 배치에서도 확실히
    a.frame(1 / 60, 300.0)
    assert all(at(x, 20) == water_rows(ah, 100)[20] for x in range(aw)), "빛줄기 0% 면 위쪽이 물빛만"
    # 막대를 끄는 동안(retune): 다시 깔지 않고 수만 맞춤 — 있던 물고기·거품·게는 제자리, 양이 바뀌면 물빛만 다시
    a.amount, a.tank = 50, {k: TANK[k][1] for k in TANK}
    a.reset()
    fish, flakes, crab, rays, school = a.fish[:3], list(a.flakes), a.crab, a.rays_at, a.school
    a.tank["fish"] = 3
    a.retune()
    assert len(a.fish) == 3 and all(f is g for f, g in zip(a.fish, fish)), "물고기를 줄이면 있던 것 중에서 남음"
    assert school and a.school is school, "마릿수를 바꿔도 떼는 그대로"
    a.tank["fish"], a.tank["bubbles"], a.amount = FISH_MAX, 100, 80
    a.frame(1 / 60, 400.0)  # 모래 띠를 그려 둠 — 물빛이 바뀌면 띠 바탕도 다시 그려야 함
    assert a.sand_base is not None
    a.retune()
    assert a.sand_base is None, "양을 끌면 모래 띠도 새 물빛으로 다시 그림"
    same = lambda now, was: all(f is g for f, g in zip(now, was))
    assert len(a.fish) == FISH_MAX and same(a.fish, fish) and len(a.flakes) == 60 and same(a.flakes, flakes), \
        "늘리면 있던 것은 그대로 두고 모자란 것만 새로"
    assert a.crab is crab and a.rays_at is rays, "다시 깔지 않음 — 게·빛줄기 자리 그대로"
    assert a.aq_tint[0] == 80 and a.water == b"".join(p * aw for p in water_rows(ah, 80)), "양을 끌면 물빛이 바로 바뀜"
    a.amount, a.tank = 50, {k: TANK[k][1] for k in TANK}

    # 전체 화면 앱이 작업 표시줄을 가리면 틀이 사라짐 — 바닥이 무너지듯 떨어지고, 다시 나타나면 바로 솟음
    up = [0] * 100 + [rise] * 300
    for kind in ("aquarium", "snow"):  # 어항은 물속이라 덜 빨라지다 종단 속도로 — rise 가 그 전에 닿는 거리보다 큼
        g, vt = (SINK_WATER_G, SINK_WATER_V) if kind == "aquarium" else (SINK_G, math.inf)
        land = vt / g / 2 + rise / vt if rise > vt * vt / g / 2 else math.sqrt(2 * rise / g)
        if kind == "snow":
            a.kind, a.pile_zero = "snow", bytes(a.strip_h * 4)
            a.reset()
            a.pile.h, a.last_settle = [3.0] * aw, 500.0
            a.render_pile()
        a.flakes, a.crab, a.jelly, a.fish, a.breaths = [], [], [], [], []
        a.next_base = up
        a.frame(1 / 60, 500.0)
        a.next_base, seen = [0] * aw, []
        for i in range(int(60 * (land + SINK_CRUMBLE + 0.1))):
            a.frame(1 / 60, 500 + (i + 1) / 60)
            assert all(p - q <= vt / 60 + 1 for p, q in zip(seen[-1] if seen else up, a.base)), ("종단 속도를 안 넘음", kind, i)
            seen.append(a.base)
            got = bytes(a.strip)  # 바뀐 열만 다시 그린 띠가 통째로 그린 것과 같음
            if kind == "snow":
                a.pile_last = [-1] * aw
                a.render_pile()
            else:
                a.sand_base = None
                a.render_sand()
                # 가려는 바닥이 평평하니 묶음마다 높이가 달라도 장식은 제자리에서 바닥을 따라 내려옴(옆으로 안 들썩임)
                assert seated() and [d[0] for d in a.decor_at] == [x for x, *_ in aq["decor"]] \
                    and a.chest_x == aq["chest_x"], ("떨어지는 동안에도 장식은 제자리 바닥 위", i)
            assert bytes(a.strip) == got, ("떨어지는 동안 띠가 바닥을 따라감", kind, i)
        first = next(i for i, b in enumerate(seen) if b == [0] * aw)
        assert abs((first + 1) / 60 - max(a.crumble[100:]) - land) <= 2 / 60 and a.fall is None, \
            ("중력으로 떨어져 제때 닿음 — 제일 늦은 묶음이 닿을 때 끝", kind, first)
        assert all(p >= q for s, t in zip([up] + seen, seen) for p, q in zip(s, t)), "떨어지기만 함"
        assert any(len(set(b[100:])) > 2 for b in seen), "묶음마다 늦게 떨어져 무너지듯"
        a.next_base = up
        a.frame(1 / 60, 510.0)
        assert a.base == up and a.fall is None, ("틀이 다시 나타나면 바로 솟음", kind)
    a.reset()  # 눈(위 고리가 눈으로 끝남): 양을 끄는 동안 쌓인 눈은 그대로 두고 층마다 수만 맞춤
    a.pile.h, flakes = [3.0] * aw, list(a.flakes)
    for amt in (100, 10):
        a.amount = amt
        a.retune()
        per = [sum(f[3] == li for f in a.flakes) for li in range(len(SNOW_LAYERS))]
        now_ids, old = {id(f) for f in a.flakes}, {id(f) for f in flakes}
        assert per == [round(count(amt) * l[0]) for l in SNOW_LAYERS] and a.pile.h == [3.0] * aw, ("눈 수만 맞춤", amt, per)
        assert old <= now_ids if amt == 100 else now_ids <= old, ("있던 눈송이는 제자리", amt)
    a.amount, a.kind, junk = 50, "hail", [[0.0] * 7]
    a.stones = junk * 500  # 지난번 우박 — 종류를 다시 고르면 새로 깔아야 함
    a.reset()
    assert len(a.stones) == round(count(50) * HAIL_SHARE) and not any(s is junk[0] for s in a.stones), "우박을 고르면 돌을 새로"
    a.kind = "snow"
    a.reset()
    if not MAC:  # 전체 화면이면 틀을 안 읽고 바닥 0, 바뀌면 FRAMES_EVERY 를 안 기다리고 바로 다시 냄
        states, got, a.left, a.top = iter([False, False, True, True, False]), [], 0, 0

        def nap(_):
            got.append(a.next_base)
            a.next_base = None
            if len(got) == 5:
                raise StopIteration
        real = taskbar.fullscreen_app, taskbar.frames, time.sleep
        taskbar.fullscreen_app, taskbar.frames, time.sleep = lambda: next(states), lambda: [(100, ah - rise, 400)], nap
        try:
            Weather.watch_frames(a)
        except StopIteration:
            pass
        finally:
            taskbar.fullscreen_app, taskbar.frames, time.sleep = real
        assert got == [up, None, [0] * aw, None, up], ("전체 화면을 오가면 바로 바닥을 다시 냄", got)
    assert parse_amount("many") == 100 and parse_amount(0) == 0 and parse_amount(35) == 35
    assert all(parse_amount(a) is None for a in (101, -1, True, "x", [1], None, 2.5))
    assert amount_arg("normal") == 50 and amount_arg("7") == 7
    assert {20, 50, 100} <= set(AMOUNTS.values()), "예전 세 단계가 메뉴 칸에 있음"
    ids = [*AMOUNTS, *FPS_IDS, SHOW, *PETS, DRAG, PANEL, AUTOSTART, EXIT, *KINDS, SOUND, *VOLUMES]
    assert len(ids) == len(set(ids)), "메뉴 id 가 겹치지 않음"
    assert FPS in FPS_IDS.values()
    assert max(FPS_IDS.values()) == 120, "180 은 뺐음"
    assert list(PETS.values()) == list(PET_CLASS) == list(PET_NAMES)
    check_settings()
    from types import SimpleNamespace
    z = SimpleNamespace(pets={}, w=300, save=lambda: None)
    Weather.handle(z, 24)
    dog = z.pets["dog"]
    Weather.handle(z, 22)
    assert list(z.pets) == ["cat", "dog"] and z.pets["dog"] is dog, "여럿 켜지고, 켜 둔 동물은 그대로"
    Weather.handle(z, 24)
    assert list(z.pets) == ["cat"], "다시 누르면 꺼짐"
    q = SimpleNamespace(commands=queue.Queue())
    Weather.read_panel(q, SimpleNamespace(stdout=["amount 30\n", "amount x\n", "amount 150\n", "fish 0\n", "rays 101\n",
                                                        "fish %d\n" % (FISH_MAX + 1), "bubbles x\n", "fishy 3\n", "2\n",
                                                        "42\n", "43\n", "23\n", "77\n", "27\n", "hi\n"]))
    assert list(q.commands.queue) == [("amount", 30), ("fish", 0), 2, 42, 23, 27], "설정 창이 보낸 줄 중 아는 것만(43 은 뺀 180)"
    if not MAC:  # 트레이 아이콘 왼쪽·오른쪽 클릭 — 메뉴 없이 만들면(weather) 둘 다 설정 창, 메뉴가 있으면(다른 도구) 오른쪽은 메뉴
        import tray
        for menu, want in ((None, ["창", "창"]), (lambda: [], ["창", "메뉴"])):
            got = []
            t = SimpleNamespace(on_left=lambda: got.append("창"), menu=menu, _popup=lambda: got.append("메뉴"))
            for b in (tray.WM_LBUTTONUP, tray.WM_RBUTTONUP):
                Tray._wndproc(t, 0, tray.WM_TRAY, 0, b)
            assert got == want, (want, got)
        assert tray.icon_rect("PlayroomNoSuchTray") is None, "트레이 창이 없으면 설정 창은 누른 자리 위로"
    hz = SimpleNamespace(kind="snow", amount=50, tank={k: TANK[k][1] for k in TANK}, done=[])
    hz.reset, hz.retune, hz.save = [lambda w=w: hz.done.append(w) for w in ("reset", "retune", "save")]
    Weather.handle(hz, ("fish", 0))
    assert hz.tank["fish"] == 0 and hz.amount == 50 and hz.done == ["save"], "어항이 아니면 어항 막대는 남기기만"
    Weather.handle(hz, ("amount", 40))
    assert hz.amount == 40 and hz.done == ["save", "retune", "save"], "양은 다시 깔지 않고 수만 — 쌓인 눈이 안 날아감"
    hz.kind, hz.done = "aquarium", []
    Weather.handle(hz, ("rays", 80))
    Weather.handle(hz, ("amount", 30))
    assert hz.tank == {"fish": 0, "bubbles": 50, "rays": 80} and hz.amount == 30 and hz.done == ["retune", "save"] * 2, \
        "어항이면 수만 맞추고, 양은 양에"

    # 동물 집어 옮기기 (커서·단추는 흉내): 커서가 동물 위일 때만 클릭을 받고, 누르면 집어 커서를 따라가고, 떼면 떨어짐
    dw, dh, rise = 600, 500, 40
    d = Weather.__new__(Weather)
    d.w, d.h, d.stride, d.rise, d.amount, d.kind, d.strip_h = dw, dh, dw * 4, rise, 50, "none", PILE_STRIP + rise
    # 오른쪽 절반은 틀이 없음 — 들고 넘어가도 틀 단을 뛰지 않아야 함
    d.base, d.snow_pile, d.sprite_cache, d.next_base, d.full_clear = [rise] * 300 + [0] * 300, pile_column_parts(PILE_STRIP + rise), {}, None, False
    d.goal, d.fall, d.crumble, d.on_top, d.last_settle = d.base, None, crumble(dw), False, 0
    d.visible, d.drag, d.catching, d.save = True, True, False, lambda: None
    d.pet_sprites, d.bolt_seen, d.bangs = pet.sprites(), None, []
    ms = {"at": (0, 0), "catch": [], "tops": []}
    d.surface = SimpleNamespace(pixels=bytearray(dw * dh * 4), cursor=lambda: ms["at"], catch=ms["catch"].append,
                                clear=lambda top=0: ms["tops"].append(top), present=lambda top=0: None)
    cat, bird = pet.Cat(dw, random.Random(2)), pet.Bird(dw, random.Random(2))
    d.pets = {"cat": cat, "bird": bird}
    d.reset()
    t0 = time.perf_counter()  # grab 이 perf_counter 로 시각을 찍음
    cat.x, bird.x = 100.0, 400.0
    cat.go("sleep", t0)
    d.frame(1 / 60, t0 - 1 / 60)  # reset 뒤 첫 프레임은 통째로
    d.frame(1 / 60, t0)
    band_top = 0 if MAC else dh - pet.BAND - rise  # 맥은 버퍼 둘을 번갈아 써서 늘 통째로
    assert ms["tops"][-1] == band_top, "평소엔 바닥 띠만 지움"
    d.aim()
    assert ms["catch"] == [], "커서가 동물 밖이면 클릭은 아래 창으로"
    cx, cy, cw, ch = cat.box()
    ms["at"] = (cx + cw // 2, cy + ch - 5)
    d.aim()
    d.aim()
    assert ms["catch"] == [True], "동물 위에 오면 한 번만 클릭을 받게 바꿈"
    d.press(True)
    assert cat.held == (cw // 2, ch - 5) and not bird.held and cat.state == "stand", "커서 밑 동물만 집음"
    ms["at"] = (cx + cw // 2 + 50, cy + ch - 5 - 300)
    d.bolt = (1,)  # 들려 있는 동안 번개가 쳐도
    d.surface.pixels[:] = bytes(dw * dh * 4)  # 흉내 clear 는 안 지움
    d.frame(1 / 60, t0 + 1 / 60)
    assert ms["tops"][-1] == 0, "띠 위로 든 동물은 자국이 안 남게 통째로 지움"
    assert int(cat.x) == cx + 50 and cat.air == 300 and cat.box()[:2] == (cx + 50, cy - 300), ("커서를 따라감", cat.box())
    assert cat.state == "stand" and not cat.leap, "들린 동안은 놀라지도 뛰지도 않음"
    ink = [y for y in range(dh) if any(d.surface.pixels[y * dw * 4 + (cx + 50) * 4:y * dw * 4 + (cx + 50 + cw) * 4])]
    assert cy - 300 - 30 <= ink[0] and ink[-1] < cy + ch - 300, ("든 높이에 그려짐", ink[0], ink[-1])
    ms["at"] = (dw + 500, -1000)  # 화면 밖으로 끌어도
    d.frame(1 / 60, t0 + 2 / 60)
    x, y, w, h = cat.box()
    assert x + w <= dw and y >= 0 and not cat.leap, ("화면 안, 틀이 없는 쪽으로 넘어가도 안 뜀", cat.box())
    d.press(False)
    d.press(False)  # 떼면 CAPTURECHANGED 가 또 옴
    frames, now = 0, t0 + 2 / 60
    while cat.air:
        frames, now = frames + 1, now + 1 / 60
        d.frame(1 / 60, now)
        assert ms["tops"][-1] == 0 or not cat.air, "떨어지는 동안도 통째로"
    assert frames <= (2 * dh / pet.GRAVITY) ** 0.5 * 60 + 2 and cat.ground == 0 and not cat.leap, ("떨어져 바닥에 섬", frames)
    d.frame(1 / 60, now + 1 / 60)
    assert ms["tops"][-1] == band_top, "내려앉으면 다시 띠만"
    bx, by, bw, bh = bird.box()
    ms["at"] = (bx + 3, by + 3)
    d.handle(DRAG)
    assert not d.drag, "메뉴로 끔"
    d.aim()
    d.press(True)
    assert ms["catch"][-1] is False and not bird.held, "끄면 동물 위여도 클릭은 아래 창으로, 안 집힘"
    d.handle(DRAG)
    d.press(True)
    assert bool(bird.held) == d.drag == (not MAC), "다시 켜면 집힘 (맥은 집기가 없어 안 켜짐)"
    d.handle(DRAG)
    assert not bird.held, "끄면 들던 동물을 놓음"
    if not MAC:  # 창을 안 만들고 Surface 의 마우스 갈래만: user32 를 흉내로 바꿔 끼움
        import surface
        real, calls = surface.user32, []
        surface.user32 = SimpleNamespace(GetWindowLongPtrW=lambda h, i: surface.EX_STYLE,
                                         SetWindowLongPtrW=lambda h, i, v: calls.append(("ex", v)),
                                         SetCapture=lambda h: calls.append("capture"),
                                         ReleaseCapture=lambda: calls.append("release"),
                                         DefWindowProcW=lambda *a: calls.append("default") or 0)
        try:
            s = SimpleNamespace(hwnd=1, on_mouse=lambda down: calls.append(down))
            surface.Surface.catch(s, True)
            surface.Surface.catch(s, False)
            for m in (0x200, surface.WM_LBUTTONDOWN, surface.WM_LBUTTONUP, surface.WM_CAPTURECHANGED):
                surface.Surface._wndproc(s, 1, m, 0, 0)
        finally:
            surface.user32 = real
        assert calls == [("ex", surface.EX_STYLE & ~0x20), ("ex", surface.EX_STYLE), "default", "capture", True,
                         "release", False, False], ("받을 땐 클릭 통과 비트만 빼고, 누르면 붙잡고, 떼면 놓음", calls)
    check_sound()
    print("자체 점검 통과")


def check_settings():
    """설정 파일: 이상한 값은 버리고, 남긴 것은 그대로 다시 읽힘."""
    global SETTINGS
    real, SETTINGS = SETTINGS, Path(tempfile.mkdtemp()) / "weather.json"
    try:
        for saved, want in ((True, ["cat"]), (False, []), ("bird", ["bird"]), ("", []), ("fox", []), (1, None),
                            (["penguin", "cat", "fox", "cat", [1]], ["cat", "penguin"])):
            SETTINGS.write_text(json.dumps({"pet": saved}), encoding="utf-8")
            assert load_settings().get("pet") == want, (saved, "예전 true 는 고양이, 모르는 이름은 버림")
        SETTINGS.write_text(json.dumps({"fish": FISH_MAX, "bubbles": 150, "rays": "x"}), encoding="utf-8")
        assert load_settings() == {"fish": FISH_MAX}, "거품·빛줄기는 0–100 만"
        SETTINGS.write_text(json.dumps({"fish": FISH_MAX + 1, "bubbles": 0, "rays": True}), encoding="utf-8")
        assert load_settings() == {"bubbles": 0}, "물고기는 0–FISH_MAX 마리만"
        for saved, want in ((180, 120), (120, 120), (90, None)):
            SETTINGS.write_text(json.dumps({"fps": saved}), encoding="utf-8")
            assert load_settings().get("fps") == want, (saved, "0.2.6 까지의 180 은 120 으로, 모르는 값은 버림")
        Weather.save(types.SimpleNamespace(kind="aquarium", amount=40, pets={"cat": None}, fps=60,
                                           tank={"fish": 10, "bubbles": 0, "rays": 90}, drag=True, sound=True, volume=30))
        assert load_settings() == {"kind": "aquarium", "amount": 40, "pet": ["cat"], "fps": 60, "fish": 10, "bubbles": 0,
                                   "rays": 90, "drag": True, "sound": True, "volume": 30}, "남긴 그대로 다시 읽힘"
        for saved, want in ((True, True), (False, False), (1, None), ("yes", None)):
            SETTINGS.write_text(json.dumps({"drag": saved, "sound": saved}), encoding="utf-8")
            assert load_settings().get("drag") == load_settings().get("sound") == want, (saved, "집기·빗소리는 참·거짓만")
        for saved, want in ((0, 0), (100, 100), (101, None), (-1, None), (True, None), ("many", None), (2.5, None)):
            SETTINGS.write_text(json.dumps({"volume": saved}), encoding="utf-8")
            assert load_settings().get("volume") == want, (saved, "빗소리 크기는 0–100 정수만")
    finally:
        shutil.rmtree(SETTINGS.parent, ignore_errors=True)
        SETTINGS = real


def check_sound():
    """빗소리: 언제 울리나 · 트레이·설정 창 명령 · 합성·이음매·크기. 실제 장치로 트는 것은 안 함."""
    import io
    import wave
    from array import array
    assert hearing("rain", True, True, 40) == hearing("storm", True, True, 40) == 40
    for off in (("snow", True, True, 40), ("aquarium", True, True, 40), ("none", True, True, 40),
                ("rain", False, True, 40), ("rain", True, False, 40), ("rain", True, True, 0)):
        assert hearing(*off) is None, (off, "비·뇌우가 보이고 켰고 크기가 있을 때만")
    played = []
    pl = rain_sound.Player(play=lambda v, base: played.append(v), stop=lambda: played.append(None), spawn=lambda fn: fn())
    pl.base = [0.0]  # 합성은 아래에서 따로
    for v in (50, 50, 30, None, None, 70):
        pl.set(v)
    pl.close()
    assert played == [50, 30, None, 70, None], ("같은 값은 다시 안 틀고, 끄면 멈춤", played)
    sw = types.SimpleNamespace(kind="rain", visible=True, sound=False, volume=VOLUME, commands=queue.Queue(),
                               save=lambda: None, rain_player=pl)
    sw.handle, sw.hear = lambda cid: Weather.handle(sw, cid), lambda: Weather.hear(sw)
    played.clear()
    for cid in (SOUND, ("volume", 20), min(VOLUMES), SOUND):
        sw.commands.put(cid)
    assert not Weather.poll(sw) and played == [VOLUME, 20, 10, None], ("켜기·막대·메뉴 칸·끄기가 바로 들림", played)
    out = [float(i) for i in range(30)]
    loop = rain_sound.seam(out, 20, 10)
    assert len(loop) == 20 and loop[0] == out[20] and abs(loop[5] - (5 + 25) * 0.5 ** 0.5) < 1e-9 \
        and loop[10:] == out[10:20], ("되풀이하면 [19] 다음이 원래 이웃 [20], 섞을 때 √ 무게", loop)
    a = rain_sound.synth(1, seed=3)
    assert a == rain_sound.synth(1, seed=3) and [len(ch) for ch in a] == [rain_sound.RATE] * 2
    corr = sum(x * y for x, y in zip(*a)) / math.sqrt(sum(x * x for x in a[0]) * sum(y * y for y in a[1]))
    assert max(max(map(abs, ch)) for ch in a) == 1.0 and corr < 0.9, ("최고점 1, 좌우 바닥이 따로(0.82, 같으면 0.98)", corr)
    assert a != rain_sound.synth(1, seed=4)

    def peak(volume):
        with wave.open(io.BytesIO(rain_sound.wav(a, volume))) as wf:
            assert (wf.getnchannels(), wf.getsampwidth(), wf.getframerate(), wf.getnframes()) == \
                (2, 2, rain_sound.RATE, len(a[0]))
            pcm = array("h", wf.readframes(len(a[0])))
            assert pcm[1] == int(a[1][0] * rain_sound.PEAK * 32767 * (volume / 100) ** 2), "왼·오 번갈아"
            return max(map(abs, pcm))
    loud = peak(100)
    assert peak(0) == 0 and loud == int(rain_sound.PEAK * 32767) and abs(peak(50) - loud / 4) <= 1, \
        "100% 는 끝 바로 아래, 50% 는 4분의 1(−12dB)"


def panel():
    """트레이를 누르면 보이는 설정 창. weather 가 켤 때 숨긴 채 띄워 두고, 누를 때마다 stdin 으로 지금 상태 JSON 이
    한 줄 오면 그 값을 넣고 트레이 아이콘 위에 보임. 누른 것을 한 줄씩 찍고(read_panel 이 받음), 바깥을 누르거나
    Esc 면 숨음. stdin 이 닫히면(weather 가 꺼짐) 끝남."""
    import tkinter as tk
    from tkinter import ttk
    from tray import icon_rect
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except (AttributeError, OSError):
        pass
    root = tk.Tk()
    root.withdraw()  # 상태가 오기 전엔 숨김. 보일 때는 자리를 잡은 뒤에 — 안 그러면 왼쪽 위에 잠깐 떴다가 옮겨 갔음
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

    loads = []  # 상태 → 위젯 값. 보일 때마다 다 부름
    ttk.Label(f, text="날씨", style="Title.TLabel").grid(row=0, column=0, columnspan=4, sticky="w")
    kind = tk.StringVar()
    loads.append(lambda s: kind.set(s["kind"]))
    for i, (cid, (key, label)) in enumerate(KINDS.items()):
        ttk.Radiobutton(f, text=label, value=key, variable=kind, style="Toolbutton",
                        command=lambda cid=cid: (send(cid), fit())).grid(row=1 + i // 4, column=i % 4, sticky="ew",
                                                                         padx=px(2), pady=px(2))

    bars = ttk.Frame(f)  # 막대 줄들. 한 격자라 이름 폭이 달라도 막대가 나란함
    below = 1 + (len(KINDS) + 3) // 4  # 종류 단추 줄 아래
    bars.grid(row=below, column=0, columnspan=4, sticky="ew", pady=(px(12), px(6)))
    bars.columnconfigure(1, weight=1)

    def bar(r, label, get, word, top=100, unit="%"):
        """0–top 막대 한 줄 → (이름, 막대, 숫자). get(상태) 가 막대 값. 끄는 동안 바뀐 값을 0.1초에 한 번 `word 값` 으로
        보내 바로 보이게 — 어항 물빛은 다시 만드는 데 30–40ms 라 칸마다 보내면 화면이 멈칫거림. 손을 떼면 마지막 값을 바로 보냄."""
        val, sent, later = tk.DoubleVar(), [0], []
        pct = ttk.Label(bars, width=6, anchor="e")

        def load(s):
            sent[0] = get(s)  # 받은 값은 다시 보내지 않게 먼저
            val.set(sent[0])
            pct.configure(text="%d%s" % (sent[0], unit))
        loads.append(load)

        def push():  # 바뀐 값만
            later.clear()
            if round(val.get()) != sent[0]:
                sent[0] = round(val.get())
                send(word, sent[0])

        def show(*_):
            pct.configure(text="%d%s" % (round(val.get()), unit))
            if not later:
                later.append(root.after(100, push))

        scale = ttk.Scale(bars, from_=0, to=top, variable=val, command=show)

        def jump(e):  # 볼륨 막대처럼 누른 자리로 바로 감 (ttk 기본은 한 칸씩)
            val.set(max(0.0, min(top, e.x / max(1, scale.winfo_width()) * top)))
            show()

        scale.bind("<Button-1>", jump, add="+")
        scale.bind("<ButtonRelease-1>", lambda _: push())
        scale.bind("<KeyRelease>", lambda _: push())
        name = ttk.Label(bars, text=label)
        name.grid(row=r, column=0, sticky="w", pady=px(1))
        scale.grid(row=r, column=1, sticky="ew", padx=(px(10), px(4)), pady=px(1))
        pct.grid(row=r, column=2, sticky="e", pady=px(1))
        return name, scale, pct

    bar(0, "양", lambda s: s["amount"], "amount")
    tank_bars = [wd for r, (key, (label, default, top, unit)) in enumerate(TANK.items(), start=1)
                 for wd in bar(r, label, lambda s, key=key, default=default: s.get("tank", {}).get(key, default), key,
                               top, unit)]
    volume_bar = bar(len(TANK) + 1, "소리 크기", lambda s: s.get("volume", VOLUME), "volume")

    smooth = ttk.Frame(f)
    smooth.grid(row=below + 1, column=0, columnspan=4, sticky="ew", pady=(0, px(8)))
    ttk.Label(smooth, text="부드러움").pack(side="left", padx=(0, px(8)))
    fps = tk.IntVar()
    loads.append(lambda s: fps.set(s["fps"]))
    for cid, n in FPS_IDS.items():
        ttk.Radiobutton(smooth, text=str(n), value=n, variable=fps, style="Toolbutton",
                        command=lambda cid=cid: send(cid)).pack(side="left", padx=px(2))
    ttk.Label(smooth, text="fps").pack(side="left", padx=(px(4), 0))

    animals = ttk.Frame(f)
    animals.grid(row=below + 2, column=0, columnspan=4, sticky="ew", pady=(0, px(8)))
    ttk.Label(animals, text="동물").pack(side="left", padx=(0, px(8)))
    keep = []  # tk 변수는 파이썬 쪽 참조가 없어지면 체크 표시가 풀림
    for cid, a in PETS.items():  # 여럿 켤 수 있음
        keep.append(tk.BooleanVar())
        loads.append(lambda s, v=keep[-1], a=a: v.set(a in s["pet"]))
        ttk.Checkbutton(animals, text=PET_NAMES[a], variable=keep[-1], style="Toolbutton",
                        command=lambda cid=cid: send(cid)).pack(side="left", padx=px(2))

    boxes = {}
    for r, (key, cid, label) in enumerate((("sound", SOUND, "빗소리"),
                                          ("drag", DRAG, "동물을 왼쪽 단추로 집어서 옮기기"),
                                          ("show", SHOW, "보이기"),
                                          ("auto", AUTOSTART, "Windows 시작 시 실행")), start=below + 3):
        keep.append(tk.BooleanVar())
        loads.append(lambda s, v=keep[-1], key=key: v.set(s.get(key, False)))
        boxes[key] = ttk.Checkbutton(f, text=label, variable=keep[-1], command=lambda cid=cid: send(cid))
        boxes[key].grid(row=r, column=0, columnspan=4, sticky="w", pady=px(1))
    ttk.Button(f, text="끝내기", command=lambda: (send(EXIT), root.destroy())).grid(
        row=below + 7, column=3, sticky="e", pady=(px(10), 0))

    f.columnconfigure((0, 1, 2, 3), uniform="kind")
    u = ctypes.windll.user32
    # 보이는지, 언제 숨었는지, 놓을 자리(작업 영역 l·r·b 와 아이콘 가운데 at)
    shown = {"on": False, "hid": 0.0, "l": 0, "r": 0, "b": 0, "at": 0}

    def hide(*_):
        shown["on"], shown["hid"] = False, time.perf_counter()
        root.withdraw()

    root.bind("<Escape>", hide)

    # 바깥을 누르면 숨음. 앞에 왔던 창이면 앞자리를 잃는 것으로 알고, 못 왔으면(FocusOut 도 안 옴) 창 밖에서
    # 단추가 새로 눌리는 순간을 봄. GetAsyncKeyState 의 '눌린 적 있음' 비트는 다른 프로그램이 지워 버려 안 씀.
    # 트레이를 누른 단추가 아직 눌려 있을 수 있어 눌림에서 시작. 막대를 끌다 밖으로 나가는 건 새로 누른 게 아님
    was = {}

    def outside():
        if not shown["on"]:
            return
        pid = ctypes.c_ulong()  # tk 의 바깥 창 핸들을 집기가 까다로워 앞 창이 이 프로세스 것인지로 봄
        u.GetWindowThreadProcessId(u.GetForegroundWindow(), ctypes.byref(pid))
        front = pid.value == os.getpid()
        down = bool(u.GetAsyncKeyState(1) & 0x8000 or u.GetAsyncKeyState(2) & 0x8000)
        x, y = root.winfo_pointerxy()
        x0, y0 = root.winfo_rootx(), root.winfo_rooty()
        out = not (x0 <= x < x0 + root.winfo_width() and y0 <= y < y0 + root.winfo_height())
        if was["front"] and not front or down and not was["down"] and out:
            hide()
            return
        was["front"] |= front
        was["down"] = down
        root.after(50, outside)

    def fit():
        """어항일 때만 어항 막대를, 비·뇌우·창문 빗방울일 때만 빗소리 상자·크기 막대를 보이고, 창 밑변을 작업 표시줄 위에 다시
        맞춤 — 줄이 늘면 창은 아래로 자람."""
        for wd in tank_bars:
            wd.grid() if kind.get() == "aquarium" else wd.grid_remove()
        for wd in (*volume_bar, boxes["sound"]):
            wd.grid() if kind.get() in SOUNDY else wd.grid_remove()
        root.update_idletasks()
        w, h = root.winfo_reqwidth(), root.winfo_reqheight()
        l, r, b, at = shown["l"], shown["r"], shown["b"], shown["at"]
        root.geometry("+%d+%d" % (max(l, min(at - w // 2, r - w - px(12))), b - h - px(12)))

    def show(state):
        if time.perf_counter() - shown["hid"] < 0.3:
            return  # 열린 창의 아이콘을 또 누름 — 그 누름에 숨었으니 닫힌 채로 둠
        for load in loads:
            load(state)
        shown["l"], _, shown["r"], shown["b"] = overlay.work_area()  # 작업 표시줄을 옮겼을 수 있어 열 때마다
        icon = icon_rect(TRAY_CLASS)  # 아이콘 가운데 위. 숨긴 아이콘 칸에 들어가 있으면 누른 자리 위
        shown["at"] = (icon[0] + icon[2]) // 2 if icon else root.winfo_pointerx()
        fit()
        root.deiconify()
        root.focus_force()  # Esc 가 먹게. weather 가 AllowSetForegroundWindow 로 허락해 둠
        if not shown["on"]:
            shown["on"] = True
            was.update(front=False, down=True)
            root.after(50, outside)

    inbox = queue.Queue()  # stdin 스레드 → tk 스레드. tk 는 제 스레드에서만 만짐

    def listen():
        for line in sys.stdin:
            inbox.put(json.loads(line))
        inbox.put(None)

    def take():
        while not inbox.empty():
            state = inbox.get()
            if state is None:
                root.destroy()
                return
            show(state)
        root.after(20, take)  # ponytail: 숨어 있는 동안에도 0.02초마다 큐를 봄. 거슬리면 event_generate 로

    threading.Thread(target=listen, daemon=True).start()
    take()
    root.mainloop()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--stop", action="store_true", help="떠 있는 날씨를 치움")
    ap.add_argument("--toggle", action="store_true", help="떠 있으면 치우고, 없으면 띄움")
    ap.add_argument("--check", action="store_true", help="자체 점검")
    saved = load_settings()  # 안 주면 트레이 메뉴에서 마지막으로 고른 값
    ap.add_argument("--kind", default=saved.get("kind", "snow"), choices=KIND_NAMES)
    ap.add_argument("--amount", default=saved.get("amount", 50), type=amount_arg, help="0–100 (기본 50)")
    ap.add_argument("--panel", action="store_true", help=argparse.SUPPRESS)  # 숨긴 채 띄워 두는 설정 창
    args = ap.parse_args()

    if args.check:
        check()
        return
    if args.panel:
        panel()
        return
    if args.stop:
        print("날씨를 치움" if overlay.stop(PID_FILE, TRAY_CLASS) else "떠 있는 날씨가 없음")
        return
    if MAC and overlay.running_pid(PID_FILE) is not None:  # 맥은 소스로만 돌아 갈아 끼울 exe 가 없음
        if args.toggle:
            overlay.stop(PID_FILE, TRAY_CLASS)
        return
    if not MAC and overlay.already_running(PID_FILE, TRAY_CLASS, __file__, args.toggle):
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
        startup.follow(RUN_NAME, __file__)
    PID_FILE.write_text(str(os.getpid()))
    try:
        Weather(args.kind, args.amount, saved.get("pet", []), saved.get("fps", FPS), saved,
                saved.get("drag", False), saved.get("sound", False), saved.get("volume", VOLUME)).run()
    finally:
        if not MAC:
            ctypes.windll.winmm.timeEndPeriod(1)
        if overlay.running_pid(PID_FILE) == os.getpid():
            PID_FILE.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
