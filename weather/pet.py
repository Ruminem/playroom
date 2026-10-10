# SPDX-License-Identifier: Apache-2.0
"""weather 위를 돌아다니는 픽셀 고양이. 그림(글자 판)·하는 짓(상태 기계)·찍기가 있고, 언제 찍을지는 weather 가 정한다.

걷다가 서고, 앉고, 앉았다 잠들고(Zz), 번개가 치면 깜짝 뛰어 달아난다. 비가 오면 빨리 걷고 안 잔다.
발은 바닥(작업 표시줄 위) — 쌓인 눈·잎이 있으면 그 위 — 에 딛는다.

  python pet.py    자체 점검
"""
import math
import random

SCALE = 3  # 그림 한 칸 = 화면 px

COLORS = {"k": (38, 43, 68), "o": (247, 118, 34), "l": (254, 174, 52), "w": (255, 255, 255),
          "p": (232, 183, 150), "e": (24, 20, 37), "z": (192, 203, 220),
          "b": (150, 98, 58), "c": (236, 218, 186), "y": (250, 186, 60),  # b·c·y 는 새
          "d": (196, 128, 72), "a": (122, 76, 44),  # 강아지 털·귀
          "h": (255, 212, 222), "g": (62, 68, 94),  # 토끼 분홍 · 펭귄 등
          "r": (228, 59, 68),  # 머리 위 ♥
          "q": (255, 146, 160),  # 새·강아지 볼 홍조
          "i": (240, 130, 160), "j": (240, 110, 140),  # 토끼 귀 속·코 · 토끼 볼 홍조 (몸이 분홍이라 진하게)
          "m": (176, 228, 248), "s": (206, 212, 224), "f": (40, 120, 230)}  # 어항 잠수 장비: 마스크 유리·호흡기·오리발

# 머리 위에 잠깐 뜨는 표시. 반응마다 하나
EMOTES = {"!": ("ll", "ll", "ll", "..", "ll"),
          "♪": ("..www", "..w.w", "..w..", "www..", "www.."),
          "♥": ("rr.rr", "rrrrr", ".rrr.", "..r.."),
          "…": ("zz.zz.zz", "zz.zz.zz")}

# 오른쪽을 봄. 왼쪽은 좌우로 뒤집어 씀. 모든 그림은 같은 크기, 발바닥이 맨 아랫줄
HEAD = (".............k.....k..",
        "............kpk...kpk.",
        "............koooooook.",
        "..kk........koooooook.",
        ".kok........kooeooeok.",
        ".kok........koowwpwwk.",
        "..kok.kkkkkkkooowwwok.",
        "...kkooooooooookkkkkk.",
        "....koloolooloook.....",
        "....koloolooloook.....",
        "....koowwwwwwwook.....")
LEGS = {"stand": ("....kokkok.kokkok.....",
                  "....kwkkwk.kwkkwk.....",
                  "....kkkkkk.kkkkkk....."),
        "walk1": ("....kokkok.kokkok.....",
                  "...kwk.kwk.kwk.kwk....",
                  "...kkk.kkk.kkk.kkk...."),
        "walk2": ("....kokkok.kokkok.....",
                  ".....kwwk...kwwk......",
                  ".....kkkk...kkkk......")}
FACE = [r[12:] for r in HEAD[:7]]  # 머리만 (x 12 부터, 7줄)
SLEEPY = FACE[:4] + ["kokkokkok."] + FACE[5:]  # 감은 눈
SIT = ("......................",) * 7 + (
    "..........koooowwk....",
    ".........kolooowwk....",
    "......kk.kolooookwk...",
    ".....kok.kooooookwk...",
    ".....kok.kooooookwk...",
    "......kookooooookwk...",
    ".......kkkkkkkkkkkk...")
SLEEP = ("......................",) * 8 + (
    "....kkkkkkkk..........",
    "...kolooloook.........",
    "..kooloolooook........",
    "..koooooooooook.......",
    "..kooooooooooooooook..",
    "...kkkkkkkkkkkkkkkk...")
ZZZ = ("zzzz", "..z.", ".z..", "zzzz")


def put(rows, part, x, y):
    """part 의 '.' 아닌 칸을 rows 의 (x, y) 자리에 덮어씀."""
    rows = [list(r) for r in rows]
    for dy, line in enumerate(part):
        for dx, c in enumerate(line):
            if c != ".":
                rows[y + dy][x + dx] = c
    return tuple("".join(r) for r in rows)


ART: dict[str, tuple[str, ...]] = {name: HEAD + legs for name, legs in LEGS.items()}
ART["sit"] = put(SIT, FACE, 12, 0)
ART["sleep"] = put(SLEEP, SLEEPY, 12, 6)


ART_W, ART_H = len(ART["stand"][0]), len(ART["stand"])
W, H = ART_W * SCALE, ART_H * SCALE  # 화면 px
FOOT = (4 * SCALE, 18 * SCALE)       # 발이 닿는 가로 구간 (오른쪽을 볼 때, 그림 왼쪽 끝 기준 px)

# 새 (참새). 오른쪽을 봄, 발이 맨 아랫줄
BIRD = ("....kkkk....",
        "..kkbbbbkk..",
        ".kbbbbbbbbk.",
        ".kbbbbbbebky",
        "kkbbbbbbeqk.",
        "kbbaaabcccck",
        ".kbaaabcccck",
        "..kbbbcccck.",
        "...kkkkkkk..",
        ".....y.y....")
NO_LEGS = BIRD[:-1] + ("............",)
BIRD_ART = {"bird_stand": BIRD, "bird_air": NO_LEGS,
            "bird_peck": ("............",
                          "............",
                          "............",
                          "....kkkk....",
                          "..kkbbbbkk..",
                          "kkbbbbbbbbk.",
                          "kbaaabbbbbbk",
                          ".kbaaabbqebk",
                          "..kkkkkkkkky",
                          ".....y.y...."),
            "bird_fly1": put(NO_LEGS, ("kk..", "kak.", "kaak", ".kak"), 1, 1),  # 날개 위
            "bird_fly2": put(NO_LEGS, ("kaak", ".kak", "..kk"), 2, 6)}          # 날개 아래
BIRD_W, BIRD_H = len(BIRD[0]) * SCALE, len(BIRD) * SCALE
BIRD_FOOT = (5 * SCALE, 8 * SCALE)

# 강아지. 꼬리 자리(왼쪽 위)를 비워 두고 꼬리를 덮어 흔듦
DOG_HEAD = ("...........kkkkk....",
            "..........kdddddkk..",
            ".........kadddddddk.",
            ".........kaadddeddk.",
            ".........kaadddewwek",
            ".........kaaddqdwwk.",
            ".....kkkkkkddddddk..")
DOG_BODY = ("....kddddddddddddk..",
            "....kddddddddddddk..",
            "....kddwwwwwwwwddk..")
DOG_LEGS = {"stand": ("....kdkkdk..kdkkdk..",
                      "....kwkkwk..kwkkwk..",
                      "....kkkkkk..kkkkkk.."),
            "walk1": ("....kdkkdk..kdkkdk..",
                      "...kwk.kwk.kwk.kwk..",
                      "...kkk.kkk.kkk.kkk.."),
            "walk2": ("....kdkkdk..kdkkdk..",
                      ".....kwwk....kwwk...",
                      ".....kkkk....kkkk...")}
TAIL_UP, TAIL_WAG = (".k..", "kdk.", "kdk.", ".kdk"), ("....", "kk..", "kddk", ".kdk")
DOG_ART = {"dog_" + name: put(DOG_HEAD + DOG_BODY + legs, TAIL_UP, 1, 4) for name, legs in DOG_LEGS.items()}
DOG_ART["dog_wag"] = put(DOG_HEAD + DOG_BODY + DOG_LEGS["stand"], TAIL_WAG, 1, 4)
DOG_ART["dog_sit"] = DOG_HEAD[:6] + ("........kkdddddddk..",
                                     "........kdddddwwk...",
                                     ".......kddddddwwk...",
                                     "..kk...kddddddwwk...",
                                     "..kdk..kddddddwwk...",
                                     "...kdkkkddddkwkwk...",
                                     "....kkkkkkkkkkkkk...")
DOG_ART["dog_sleep"] = ("....................",) * 7 + ("............kkkkk...",
                                                          "....kkkkkkkkaddddk..",
                                                          "...kddddddkaadkkdk..",
                                                          "..kdddddddkaadqdwwk.",
                                                          ".kkddwwwwwwdddddwek.",
                                                          "..kkkkkkkkkkkkkkkk..")

# 토끼
RABBIT = ("........kk.kk.",
          ".......kik.kik",
          ".......kik.kik",
          "......khhhhhhk",
          ".....khhhhhhhk",
          ".....khhhhhehk",
          ".....khhhhhehi",
          "...kkkkhhhjhk.",
          "..khhhhhhhhhk.",
          ".kwhhhhhhhhhk.",
          "kwwhhhhhhhhhk.",
          ".kwhhhhhhhhk..",
          "..khhhhhhwhk..",
          "..kkkkkkkkkk..")
RABBIT_ART = {"rab_stand": RABBIT,
              "rab_sniff": put(RABBIT, ("w",), 13, 6),  # 코 씰룩
              "rab_jump": RABBIT[:11] + ("kkhhhhhhhhk...",
                                         "khhkk.kwk.....",
                                         "kkk...kkk.....")}

# 펭귄. 서 있는 그림은 양옆 한 칸씩 띄워 배 깔고 미끄러지는 그림과 폭을 맞춤
PENGUIN = ("....kkkk....",
           "...kggggk...",
           "..kgggwegk..",
           "..kgggggkoo.",
           "..kggwwwk...",
           ".kggwwwwwk..",
           ".kgwwwwwwk..",
           "kggwwwwwwwk.",
           "kggwwwwwwwk.",
           "kgkwwwwwwwk.",
           ".kkwwwwwwwk.",
           "..kwwwwwwk..",
           "..kgwwwwgk..",
           "...kggggk...")
PENGUIN_FEET = {"stand": ("...kokkok...", "..kookkook.."),
                "walk1": ("...kokkk....", "..kookk....."),
                "walk2": ("....kkkok...", ".....kkook..")}
PENG_ART = {"peng_" + name: tuple("." + r + "." for r in PENGUIN + feet) for name, feet in PENGUIN_FEET.items()}
PENG_ART["peng_slide"] = ("..............",) * 11 + ("...kkkkkkkk...",
                                                      ".kkggggggwegk.",
                                                      "kgwwwwwwwwggko",
                                                      ".kwwwwwwwwwkk.",
                                                      "kokkkkkkkkkk..")


def canvas(w, h, *parts):
    """빈 w×h 판 위에 (그림, x, y) 를 차례로 덮어 그림."""
    rows = ("." * w,) * h
    for part, x, y in parts:
        rows = put(rows, part, x, y)
    return rows


# 어항: 마스크·공기통·호흡기·오리발을 차고 엎드려 헤엄치는 그림. 오른쪽을 봄, 발차기 두 장
TANK = (".kkkkkkk.",
        "kywyyyyyk",
        ".kkkkkkk.")
KICK_UP = ("fff.....",  # 뒷다리를 뒤로 뻗고 오리발을 위아래로 참. X 는 털빛
           "ffff....",
           ".fffkkk.",
           "....kXk.")
KICK_DOWN = ("....kkk.",
             ".fffkXk.",
             "ffff....",
             "fff.....")


def dive(w, h, parts, legs_a, legs_b, top=False):
    """발차기 두 장. 다리는 몸 밑에 깔고 그 위에 parts 를 그림. top 이면 다리(새는 날개)를 맨 위에."""
    return tuple(canvas(w, h, *parts, *legs) if top else canvas(w, h, *legs, *parts) for legs in (legs_a, legs_b))


def kick(fur, x, y):
    return [(tuple(r.replace("X", fur) for r in rows), x, y) for rows in (KICK_UP, KICK_DOWN)]


CAT_DIVE_HEAD = (".k.....k...",
                 "kpk...kpk..",
                 "koooooook..",
                 "kkkkkkkkk..",
                 "kmmemmemk..",
                 "kkkkkkkkk..",
                 "kooowwwkss.",
                 ".kkkkkkk...")
CAT_DIVE_BODY = ("." + "k" * 16,
                 "k" + "ool" * 4 + "ooo" + "k",
                 "k" + "ool" * 4 + "ooo" + "k",
                 "kw" + "w" * 14 + "k",
                 "." + "k" * 16)
DOG_DIVE_HEAD = ("..kkkkk.....",
                 ".kdkkkkk....",
                 "kaakmemk....",
                 "kaakkkkkkk..",
                 "kaadddwwwek.",
                 "kaadddwwkss.",
                 "kaaddddkk...")
DOG_DIVE_BODY = ("." + "k" * 15,
                 "k" + "d" * 15,
                 "k" + "d" * 15,
                 "kd" + "w" * 13 + "d",
                 "." + "k" * 15)
RAB_DIVE_HEAD = ("..kk.kk...",
                 ".kik.kik..",
                 ".kikkkik..",
                 "khhhhhhk..",
                 "kkkkkkkk..",
                 "khkmmemk..",
                 "khkkkkkkss",
                 ".khhhhhk..")
RAB_DIVE_BODY = ("." + "k" * 11,
                 "k" + "h" * 11,
                 "k" + "h" * 11,
                 "kh" + "w" * 9 + "h",
                 "." + "k" * 11)
PENG_DIVE_BODY = ("...kkkkkkkkk...",
                  ".kkggggggkmek..",
                  "kgwwwwwwwkkkkoo",
                  ".kwwwwwwwwwkk..",
                  "..kkkkkkkkkk...")
BIRD_DIVE_BODY = ("......kkkk...",
                  "..kkkkkkkkk..",
                  ".kbbbbkmmemky",
                  "kbbbbbkkkkkk.",
                  ".kbbbbbbccck.",
                  "..kkkkkkkkk..")
BIRD_TANK = ("kkkk", "kyyk", "kkkk")
# 동물마다 (폭, 키, 몸 조각들, 발차기 두 장, 다리를 위에 그리나). 공기통은 조각 안에 — 스노클은 그걸 빼고 관을 닮
GEAR = {"cat": (33, 10, [(("kk.", "kok", ".kok"), 4, 0), (CAT_DIVE_BODY, 6, 3), (TANK, 9, 1), (CAT_DIVE_HEAD, 21, 0)],
                [kick("o", 0, 4)[0], (("kok", "kk."), 18, 8)], [kick("o", 0, 4)[1], ((".kok", ".kkk"), 17, 8)], False),
        "dog": (32, 10, [((".k..", "kdk.", "kdk.", ".kdk"), 3, 0), (DOG_DIVE_BODY, 6, 3), (TANK, 8, 1), (DOG_DIVE_HEAD, 20, 1)],
                [kick("d", 0, 4)[0], (("kdk", "kk."), 17, 8)], [kick("d", 0, 4)[1], ((".kdk", ".kkk"), 16, 8)], False),
        "rabbit": (28, 11, [(("kk.", "kwk", ".kk"), 4, 4), (RAB_DIVE_BODY, 6, 4), (TANK, 7, 2), (RAB_DIVE_HEAD, 17, 1)],
                   [kick("h", 0, 5)[0], (("khk", "kk."), 15, 9)], [kick("h", 0, 5)[1], ((".khk", ".kkk"), 14, 9)], False),
        "penguin": (21, 9, [(TANK, 7, 1), (PENG_DIVE_BODY, 6, 3)],
                    [(("fff...", "ffff..", ".fffko"), 0, 3)], [((".fffko", "ffff..", "fff..."), 0, 5)], False),
        "bird": (14, 8, [(BIRD_DIVE_BODY, 1, 1), (BIRD_TANK, 2, 0)],
                 [(("kbbk", ".kk."), 4, 3)], [((".kbk", "..kbk", "...k"), 3, 5)], True)}
DIVE_ART = {k: dive(*g) for k, g in GEAR.items()}
DIVE_MOUTH = {"cat": (30, 6), "dog": (30, 6), "rabbit": (26, 7), "penguin": (20, 5), "bird": (13, 3)}  # 호흡기·부리 끝 칸
DIVE_SIZE = {k: (len(v[0][0]) * SCALE, len(v[0]) * SCALE) for k, v in DIVE_ART.items()}  # 화면 px
SNORK_UP = 3  # 스노클 관이 그림 맨 위보다 더 솟는 칸


def snorkel(name):
    """수도꼭지에 반 넘게 찬 물: 공기통을 벗고 입에서 머리 위로 솟는 J 자 스노클을 문 그림 두 장. 관은 입 앞 한 칸
    (강아지 코끝 바로 앞)에서 곧게 서고 끝이 빨감. 판은 관만큼 위로 늘고 모자라면 옆으로도."""
    w, h, parts, legs_a, legs_b, top = GEAR[name]
    mx, my = DIVE_MOUTH[name]
    down = lambda ps: [(r, x, y + SNORK_UP) for r, x, y in ps]
    tube = ("r", "r") + ("y",) * (my + SNORK_UP - 1)
    body = down([p for p in parts if p[0] not in (TANK, BIRD_TANK)]) + [(tube, mx + 1, 0)]
    return dive(max(w, mx + 2), h + SNORK_UP, body, down(legs_a), down(legs_b), top)


SNORK_ART = {k: snorkel(k) for k in GEAR}
SNORK_MOUTH = {k: (mx + 1, 0) for k, (mx, my) in DIVE_MOUTH.items()}  # 숨이 나오는 관 끝 칸
SNORK_SIZE = {k: (len(v[0][0]) * SCALE, len(v[0]) * SCALE) for k, v in SNORK_ART.items()}
SOAK = ((96, 178, 226), 0.45)  # 물에 잠긴 몸 색: weather 수도꼭지 물빛(AQ_TOP) 쪽으로 섞는 몫

WALK, RUN = 38, 150      # px/초. 비 올 때 걷기는 RUN 의 절반
STEP, RUN_STEP = 0.2, 0.08  # 걸음 그림 바꾸는 간격 초
HOP_V, GRAVITY = 420, 1500  # 깜짝 뛰기: 처음 위로 px/초, 중력 px/초²
ZZ_EVERY, ZZ_RISE = 1.4, 3.0  # Z 하나가 나오는 간격 초, 떠오르는 데 걸리는 초
POUNCE_V, CALM = 320, (4, 10)  # 반딧불이로 폴짝: 처음 위로 px/초 · 한 번 반응한 뒤 쉬는 초
WET = ("rain", "storm")
HOP_EVERY, HOP_DX, HOP_UP = 0.32, 14, 7  # 새 콩콩 뛰기: 간격 초, 한 번에 px, 높이 px
FLY, FLY_ALT, FLAP = 170, 60, 0.09  # 새가 날 때 px/초, 높이 px(weather 가 다시 그리는 바닥 띠 안), 날갯짓 간격 초
# 어항 헤엄: 바닥 위로 뜨는 높이 px · 오르내림 px · 높이를 옮기는 px/초(weather 거품보다 느리게 — 제 숨을 앞지르지 않게) · 돌아서거나 높이를 바꾸는 간격 초 ·
# 발차기 그림 바꾸는 간격 초 · 숨 내쉬는 간격 초
SWIM_DEPTH, SWIM_BOB, SWIM_RISE, SWIM_TURN, KICK, BREATH = (40, 320), 6, 20, (4, 10), 0.3, (1.2, 2.6)
# 스노클은 높이를 고를 때 이 몫으로 수면(관 끝이 물 밖)을 고르고 나머지는 수면 아래 이 px 안으로 잠깐 잠수
# — 오르내림이 SWIM_RISE 라 깊이 들어가면 수면에 못 머묾 · 수면에서 위아래로 까딱이는 px(SWIM_BOB 대신 — 그만큼이면 관
# 끝이 수면을 넘나들어 숨이 끊김. weather 의 TAP_SNORKEL 이 2배보다 커야 늘 물 밖)
SNORK_SURFACE, SNORK_DIP, SNORK_BOB = 0.7, 60, 2
# 수도꼭지 수면 헤엄: SWIM_V 에 곱하는 몫 · 다리 그림 바꾸는 간격 초 · 물을 한 번 차는 간격 초(weather 가 물방울·물결) · 오르내림 px
PADDLE_V, PADDLE_STEP, STROKE, PADDLE_BOB = 0.5, 0.18, 0.36, 1.5
LEDGE, CLIMB = 8, 400  # 발밑이 한 번에 이 px 넘게 바뀌면(작업 표시줄 틀 단) 뜀 · 작은 굴곡(눈 더미)을 따라가는 px/초
HIDE, PEEK_UP, PEEK_HOLD = (0.3, 0.8), 0.35, 0.9  # 솟은 틀 뒤에 묻힘: 숨어 있는 초 · 머리를 내미는 초 · 두리번하는 초


def leap_height(g0, g1, apex, p):
    """g0 에서 g1 로 뛰는 포물선의 p(0..1) 자리 높이. 꼭대기가 두 끝 중 높은 쪽보다 apex 만큼 위.
    apex 0 이면 위로 안 뜨고 내려가며 점점 빨라짐(미끄럼)."""
    d = g1 - g0
    u = abs(d) + 2 * apex + 2 * math.sqrt(apex * (abs(d) + apex))  # 꼭대기 조건을 푼 4h
    return g0 + d * p + u * p * (1 - p)


def segments(rows, flip, colors=COLORS):
    """글자 판 → [(dy, 앞에서 건너뛸 바이트, 바이트), …]. 행 안의 투명한 틈은 끊어서 밑의 눈을 안 지움.
    colors 는 글자 → 색 — weather 어항의 물고기가 제 색표로 씀."""
    out = []
    for y, line in enumerate(rows):
        line = line[::-1] if flip else line
        for sy in range(SCALE):
            x = 0
            while x < len(line):
                if line[x] == ".":
                    x += 1
                    continue
                start = x
                while x < len(line) and line[x] != ".":
                    x += 1
                data = b"".join(bytes((colors[c][2], colors[c][1], colors[c][0], 255)) * SCALE for c in line[start:x])
                out.append((y * SCALE + sy, start * SCALE * 4, data))
    return out


def sprites():
    """{(그림 이름, 오른쪽을 보나): 조각들}. Z 는 ('zzz', True)."""
    sp = {(name, right): segments(rows, not right) for art in (ART, BIRD_ART, DOG_ART, RABBIT_ART, PENG_ART)
          for name, rows in art.items() for right in (True, False)}
    sp.update({("%s_dive%d" % (k, i + 1), right): segments(rows, not right)
               for k, pair in DIVE_ART.items() for i, rows in enumerate(pair) for right in (True, False)})
    # 물에 잠긴 몫을 그릴 물빛 섞은 벌 — 같은 그림이라 조각 차례가 같아 행마다 바꿔 낄 수 있음(Pet.paint)
    tint, k = SOAK
    soaked = {c: tuple(int(v + (t - v) * k) for v, t in zip(rgb, tint)) for c, rgb in COLORS.items()}
    arts = [(name, rows) for art in (ART, BIRD_ART, DOG_ART, RABBIT_ART, PENG_ART) for name, rows in art.items()]
    arts += [("%s_snork%d" % (k, i + 1), rows) for k, pair in SNORK_ART.items() for i, rows in enumerate(pair)]
    for name, rows in arts:
        for right in (True, False):
            sp.setdefault((name, right), segments(rows, not right))
            sp[(name, right, "wet")] = segments(rows, not right, soaked)
    sp[("zzz", True)] = segments(ZZZ, False)
    for mark, rows in EMOTES.items():
        sp[("emo" + mark, True)] = segments(rows, False)
    return sp


def stamp(px, stride, x, y, segs, width, height, floor=None):
    """조각을 (x, y) 에 찍음. 화면 밖으로 나가는 행과 가로로 삐져나간 부분은 잘라 냄 (새가 옆으로 날아 나감).
    floor(열마다 밑변에서 위로 px)를 주면 그 아래는 안 찍음 — 틀은 이 창이 아니라 밑의 작업 표시줄이 그려서,
    안 찍은 자리엔 틀이 보여 그 뒤에 가린 것처럼 보임."""
    for dy, skip, data in segs:
        yy = y + dy
        if 0 <= yy < height:
            a = x * 4 + skip
            lo, hi = max(a, 0), min(a + len(data), width * 4)
            o = yy * stride
            if floor is None:
                if lo < hi:
                    px[o + lo:o + hi] = data if hi - lo == len(data) else data[lo - a:hi - a]
                continue
            c, end, top = lo // 4, hi // 4, height - yy  # 바닥이 top 보다 낮은 열만 보임
            while c < end:
                if floor[c] >= top:
                    c += 1
                    continue
                s = c
                while c < end and floor[c] < top:
                    c += 1
                px[o + s * 4:o + c * 4] = data[s * 4 - a:c * 4 - a]


class Pet:
    """동물 공통: 날씨 종류, 머리 위 표시, 날씨에 맞춘 반응. 반응은 한 번 하면 CALM 초 쉼."""
    kind = "none"  # 지금 날씨 종류. weather 가 매 프레임 넣음
    snowy = False  # 눈·우박 더미가 있는 날 (펭귄이 봄)
    mood = None    # (표시, 나온 시각, 끝 시각)
    calm = 0.0     # 이 시각까지는 불꽃·반딧불이에 반응 안 함
    # 틀 단을 뛰어 오르내림: 걸리는 초, 두 끝 중 높은 쪽보다 더 뜨는 px. 이 상태 동안엔 새로 안 뜀(이미 떠 있음)
    LEAP = {"up": (0.35, 12), "down": (0.35, 8)}
    NO_LEAP = ()
    ground = None  # 지금 딛고 선 높이 px
    leap = None    # 단을 뛰는 중이면 (시작 시각, 출발 높이, 오르나)
    DIVER, SWIM_V = "cat", 50  # 어항에서 쓰는 잠수 그림(DIVE_ART), 헤엄 px/초
    dive = None      # 어항에서 헤엄치기 시작한 시각. 어항이 아니면 None — weather 가 지움
    snork = False    # 잠수 그림 대신 스노클 그림(SNORK_ART) — 수도꼭지 물이 반 넘게 찼을 때 weather 가 켬
    swam = None      # 수도꼭지 수면에서 개헤엄을 시작한 시각. 물에서 나오면 weather 가 지움
    stroke = False   # 이번 프레임에 물을 참 — weather 가 물방울·물결을 냄
    awake = False    # 발이 물에 잠겨 잠들지 않음 — weather 가 넣음
    PRE, FLOAT = "", 0.5  # 그림 이름 앞머리 · 수면에 뜰 때 잠기는 키 몫
    PADDLE = ("walk1", "walk2")  # 개헤엄 다리 두 장 (PRE 뒤)
    lift = 0.0       # 헤엄치며 바닥 위로 뜬 높이 px
    breathe = False  # 이번 프레임에 숨을 내쉼 — weather 가 mouth 에서 거품을 띄움
    mouth = (0, 0)   # 마지막으로 그린 호흡기 자리 (화면 px)
    # 마우스로 집어 옮기기 (weather 의 설정). 들린 동안은 update·swim 을 안 부르고 weather 가 x·air(어항이면 lift)를 넣음
    held = None      # 집혀 있으면 집은 자리 (그림 왼쪽 위에서 px)
    air = 0.0        # 놓인 뒤 바닥 위로 떠 있는 높이 px. 0 이 될 때까지 떨어짐
    fall_v = 0.0
    FALL = (GRAVITY, math.inf)  # 놓였을 때 떨어지는 가속 px/초², 가장 빠른 px/초
    at = None        # 마지막으로 그린 그림 왼쪽 위 (화면 px). 아직 안 그렸으면 None

    def box(self):
        """마지막으로 그린 그림 상자 (x, y, 폭, 높이) — 집을 수 있는 자리. 아직 안 그렸으면 None."""
        if self.at is None:
            return None
        return (*self.at, *(self.dive_size() if self.dive is not None else (self.W, self.H)))

    def dive_size(self):
        return (SNORK_SIZE if self.snork else DIVE_SIZE)[self.DIVER]

    def grab(self, now, dx, dy):
        """마우스로 집힘: 하던 짓·뛰기·떨어지기를 멈추고 선 채로 들림."""
        self.held, self.leap, self.air, self.fall_v = (dx, dy), None, 0.0, 0.0
        self.under, self.peek = False, None  # 틀 뒤에 숨어 있다가 집혀도 바로 나옴
        self.hop = self.vy = self.alt = 0.0  # Cat 은 hop·vy, Bird·Rabbit 은 alt
        self.zz, self.pounce, self.breathe = [], False, False
        self.go("stand", now)
        self.emote("!", now)

    def fall(self, dt, now):
        """놓인 뒤 바닥까지 떨어짐. 닿으면 서서 하던 짓으로 돌아감."""
        g, vmax = self.FALL
        self.fall_v = min(self.fall_v + g * dt, vmax)
        self.air = max(0.0, self.air - self.fall_v * dt)
        if not self.air:
            self.fall_v = 0.0
            self.go("stand", now)

    under = False    # 발밑에 솟은 틀 뒤에 묻혀 빼꼼하는 중 — 뛰어나와 착지하면 풀림. 그동안 weather 가 틀 아래를 안 찍음
    peek = None      # 묻힌 뒤 첫 follow 에서 (머리를 내밀기 시작하는 시각, 묻힐 때 보던 쪽)
    PEEK = 5         # 빼꼼할 때 틀 위로 내미는 그림 줄 수 — 눈까지

    def swim(self, dt, now, ceil=None, start=0.0):
        """어항: 사람처럼 물속에서 숨을 못 쉬니 잠수 장비를 차고 바닥에서 천천히 떠올라 헤엄침. 가끔 돌아서며
        그때마다 새 높이로 옮겨 감. 하던 짓(state)은 그대로 둬서 어항을 벗어나면 바닥에서 이어 감.
        ceil(수도꼭지)을 주면 높이를 그 아래 물 전체에서 고르고 그보다 높이 안 뜸 — 물이 빠지면 같이 눌려 내려감.
        start 는 처음 높이 — 수면에서 바로 잠수."""
        rng, room = self.rng, max(0, self.width - max(self.W, self.dive_size()[0]))
        lo, hi = SWIM_DEPTH if ceil is None else (SWIM_DEPTH[0], max(SWIM_DEPTH[0], ceil))
        bob = SNORK_BOB if self.snork else SWIM_BOB  # 위로 까딱인 만큼 ceil 에 잘리지 않게 수면은 그만큼 아래로 고름
        pick = (lambda: hi - bob if rng.random() < SNORK_SURFACE else rng.uniform(max(lo, hi - SNORK_DIP), hi - bob)) \
            if self.snork else lambda: rng.uniform(lo, hi)
        if self.dive is None:
            self.dive, self.depth, self.bob = now, start, rng.uniform(0, math.tau)
            self.under = False  # 틀 뒤에 묻혀 있었으면 헤엄쳐 나옴
            self.aim, self.turn_at = pick(), now + rng.uniform(*SWIM_TURN)
            self.breath_at = now + rng.uniform(*BREATH)
        edge = self.x <= 0 or self.x >= room  # 돌고 나서 움직임 — 늘 가는 쪽을 봄
        if edge or now >= self.turn_at:
            self.right = self.x <= 0 if edge else self.right != (rng.random() < 0.5)
            self.aim, self.turn_at = pick(), now + rng.uniform(*SWIM_TURN)
        self.x = min(max(self.x + self.SWIM_V * dt * (1 if self.right else -1), 0), room)
        self.depth += max(-SWIM_RISE * dt, min(SWIM_RISE * dt, self.aim - self.depth))
        self.lift = self.depth + bob * math.sin(now * 2.1 + self.bob) * min(1.0, self.depth / SWIM_DEPTH[0])
        if ceil is not None:
            self.aim, self.depth, self.lift = min(self.aim, ceil), min(self.depth, ceil), max(0.0, min(self.lift, ceil))
        self.breathe = now >= self.breath_at
        if self.breathe:
            self.breath_at = now + rng.uniform(*BREATH)

    def draw_swim(self, px, stride, height, sprites, ground, now, wet=None):
        """잠수(스노클) 그림을 발차기 두 장 번갈아 찍고 호흡기(관 끝) 자리(mouth)를 남김. wet 은 paint 처럼."""
        sw, sh = self.dive_size()
        x, y = int(self.x), height - int(ground) - sh - int(self.lift)
        n = int((now - self.dive) / KICK) % 2 + 1
        self.paint(px, stride, height, sprites, "%s_%s%d" % (self.DIVER, "snork" if self.snork else "dive", n), x, y,
                   now, wet=wet)
        mx, my = (SNORK_MOUTH if self.snork else DIVE_MOUTH)[self.DIVER]
        mx = mx if self.right else sw // SCALE - 1 - mx
        self.mouth = (x + mx * SCALE + SCALE // 2, y + my * SCALE + SCALE // 2)
        self.draw_mood(px, stride, height, sprites, x, y, now)

    def paint(self, px, stride, height, sprites, name, x, y, now, floor=None, wet=None):
        """그림 name 을 (x, y) 에 찍음. 수면에 떠 있으면 name 대신 개헤엄 그림. wet(화면 y)을 주면 그 행부터
        아래는 물빛 섞은 벌로 — 수면 밑에 잠긴 몸."""
        if self.swam is not None:
            a, b = self.PADDLE
            name = self.PRE + (a if int((now - self.swam) / PADDLE_STEP) % 2 == 0 else b)
        segs = sprites[(name, self.right)]
        if wet is not None and wet < y + len(segs) and segs:
            under = sprites[(name, self.right, "wet")]
            segs = [b if y + a[0] >= wet else a for a, b in zip(segs, under)]
        stamp(px, stride, x, y, segs, self.width, height, floor)

    def paddle(self, dt, now):
        """수도꼭지 수면에 떠서 개헤엄: 다리를 저으며 천천히 오가고 끝에 닿거나 가끔 돌아섬. 물이 닿는 순간 놀라
        '!' 하고 깸 — 이러는 동안 update 를 안 불러 잠들지 않음. 하던 짓은 서기로 둬서 물이 빠지면 거기서 이어 감."""
        rng, room = self.rng, max(0, self.width - self.W)
        if self.swam is None:
            self.swam, self.turn_at, self.stroke_at, self.bob = now, now + rng.uniform(*SWIM_TURN), now, rng.uniform(0, 7)
            self.go("stand", now)
            self.zz, self.leap, self.under, self.peek, self.pounce = [], None, False, None, False
            self.emote("!", now)
        edge = self.x <= 0 or self.x >= room
        if edge or now >= self.turn_at:
            self.right = self.x <= 0 if edge else self.right != (rng.random() < 0.5)
            self.turn_at = now + rng.uniform(*SWIM_TURN)
        self.x = min(max(self.x + self.SWIM_V * PADDLE_V * dt * (1 if self.right else -1), 0), room)
        self.hop = self.alt = PADDLE_BOB * math.sin(now * 3.1 + self.bob)  # Cat 무리는 hop, 새·토끼는 alt 로 그림
        self.stroke = now >= self.stroke_at
        if self.stroke:
            self.stroke_at = now + STROKE

    def follow(self, want, dt, now):
        """발밑 높이 want(발 밑 열들의 바닥+눈 중 가장 높은 것)를 따라가 그릴 높이를 돌려줌. 틀 단처럼 크게 바뀌면
        LEAP 포물선으로 뛰고 그동안 pose 가 뛰는 그림을 고름. 뛰는 중에 want 가 바뀌면 착지점도 따라 바뀜.
        묻혔으면(bury) 틀 뒤에 숨었다가 머리만 PEEK 줄 내밀고 두리번한 뒤 그 자리에서 LEAP 로 뛰어나옴."""
        if self.under and self.leap is None:
            if self.peek is None:
                self.peek = (now + self.rng.uniform(*HIDE), self.right)
                self.go("stand", now)
            t0, facing = self.peek
            t = now - t0
            self.right = facing != (t >= PEEK_UP + PEEK_HOLD / 2)  # 두리번 — 한가운데서 한 번 돌아봄
            self.ground = want - self.H + self.PEEK * SCALE * min(1.0, max(0.0, t / PEEK_UP))
            if t < PEEK_UP + PEEK_HOLD:
                return self.ground
            self.leap = (now, self.ground, True)
        g = want if self.ground is None else self.ground
        if self.leap is None and abs(want - g) > LEDGE and self.state not in self.NO_LEAP and self.dive is None:
            self.leap = (now, g, want > g)
        if self.leap:
            t0, g0, up = self.leap
            secs, apex = self.LEAP["up" if up else "down"]
            p = (now - t0) / secs
            if p < 1:
                self.ground = leap_height(g0, want, apex, p)
                return self.ground
            self.leap, g, self.under = None, want, False
        self.ground = min(want, g + CLIMB * dt) if want > g else max(want, g - CLIMB * dt)
        return self.ground

    def bury(self):
        """발밑에 틀이 솟아 그 뒤에 묻힘 — weather.set_base 가 부름. 날거나 이미 뛰는 중·헤엄치는 중이면 그대로
        틀을 따라감. 뛰던 높이·Z·머리 위 표시는 지움 — 숨은 자리 위에 떠 있지 않게."""
        if self.under or self.state in self.NO_LEAP or self.dive is not None or self.held or self.air:
            return  # 마우스로 들렸거나 떨어지는 중이면 틀 위로 그냥 내려앉음
        self.under, self.peek, self.leap, self.mood = True, None, None, None
        self.alt = self.hop = 0.0  # 토끼·새는 alt, 고양이 무리는 hop
        self.zz = []

    def emote(self, mark, now, dur=1.6):
        self.mood = (mark, now, now + dur)

    def draw_mood(self, px, stride, height, sprites, x, y, now):
        """y: 동물 그림 맨 윗줄. 머리 위에서 천천히 떠오름. 그리는 함수가 다 부르므로 그린 자리(at)도 여기서 남김."""
        self.at = (x, y)
        if self.mood is None:
            return
        mark, t0, t1 = self.mood
        if now >= t1:
            self.mood = None
            return
        rows = EMOTES[mark]
        ex = x + (self.W - len(rows[0]) * SCALE) // 2
        ey = y - len(rows) * SCALE - 4 - int(min(now - t0, 2) * 8)
        stamp(px, stride, ex, ey, sprites[("emo" + mark, True)], self.width, height)

    def watch(self, now, x):
        """불꽃이 터짐: 하던 걸 멈추고 서서 그쪽을 봄. 뛰거나 나는 중이면 그냥 둠."""
        if now < self.calm or self.state in ("hop", "run", "fly"):
            return
        self.calm = now + self.rng.uniform(*CALM)
        self.right = x >= self.x + self.W / 2
        self.go("stand", now)
        self.emote("!", now)

    def chase(self, now, flies):
        """flies: 낮게 나는 반딧불이 [(x, 바닥에서 높이 px)]. 기본은 관심 없음."""


class Cat(Pet):
    """상태: walk · stand · sit · sleep · hop(깜짝 뛰기·폴짝) · run(뛰어 달아남). 시각은 밖에서 받음.
    강아지·펭귄은 그림(PRE 로 시작하는 이름)·크기·빠르기만 바꿔 이어받음."""
    PRE, W, H, FOOT, WALK_V = "", W, H, FOOT, WALK
    DUR = {"walk": (3, 9), "stand": (1.5, 4), "sit": (3, 8), "sleep": (12, 30), "hop": (9, 9), "run": (1.2, 1.8)}
    LEAP, NO_LEAP = {"up": (0.3, 12), "down": (0.3, 8)}, ("hop",)  # 고양이는 짧고 날렵하게
    LEAP_POSE = ("walk1", "walk1")  # 뛰는 동안 그림 (내려갈 때, 오를 때) — 다리를 앞뒤로 뻗음
    pounce = False  # 지금 뛰는 게 반딧불이를 잡으려는 폴짝인가 (놀라 뛴 게 아니라)

    def __init__(self, width, rng=random):
        self.rng, self.width = rng, width
        self.x = rng.uniform(0, max(0, width - self.W))
        self.right = rng.random() < 0.5
        self.hop, self.vy = 0.0, 0.0  # 바닥 위로 뜬 높이 px, 위로 속도
        self.zz = []  # 떠오르는 Z 들의 나온 시각
        self.go("walk", 0.0)

    def go(self, state, now):
        self.state, self.since = state, now
        self.until = now + self.rng.uniform(*self.DUR[state])

    def startle(self, now):
        """번개·우박. 자고 있었어도 깸."""
        if self.state != "hop" or self.pounce:
            self.go("hop", now)
            self.vy, self.zz, self.pounce, self.mood = HOP_V, [], False, None

    def chase(self, now, flies):
        """앞뒤 160px 안 손 닿는 높이에 반딧불이가 있으면 그쪽으로 폴짝."""
        if now < self.calm or self.state not in ("walk", "stand", "sit"):
            return
        cx = self.x + self.W / 2
        near = [fx for fx, up in flies if abs(fx - cx) < 160 and up < 100]
        if not near:
            return
        self.calm = now + self.rng.uniform(*CALM)
        self.right = min(near, key=lambda fx: abs(fx - cx)) >= cx
        self.go("hop", now)
        self.vy, self.zz, self.pounce, self.mood = POUNCE_V, [], True, None

    def next_state(self, now, rainy):
        r = self.rng.random()
        if self.state == "walk":
            if r < 0.2:
                self.right = not self.right
                self.go("walk", now)
            else:
                self.go("sit" if r < 0.65 else "stand", now)
                if self.state == "sit" and self.kind == "snow" and r < 0.45:  # 앉아서 눈 구경
                    self.emote("♥", now, 2.5)
        elif self.state == "sit" and r < 0.4 and not rainy and not self.awake:
            self.go("sleep", now)
        else:
            if self.state != "run" and r < 0.5:
                self.right = not self.right
            self.go("walk", now)

    def update(self, dt, now, rainy):
        if self.state == "hop":
            self.hop += self.vy * dt
            self.vy -= GRAVITY * dt
            if self.pounce:  # 반딧불이 쪽으로 날아감
                self.x = min(max(self.x + RUN * dt * (1 if self.right else -1), 0), max(0, self.width - self.W))
            if self.hop <= 0:
                self.hop, self.vy = 0.0, 0.0
                if self.pounce:
                    self.pounce = False
                    self.go("stand", now)
                    self.emote("♪", now)
                else:
                    self.right = not self.right  # 놀란 쪽에서 반대로 달아남
                    self.go("run", now)
            return
        if now >= self.until:
            self.next_state(now, rainy)
        if self.state in ("walk", "run", "slide"):
            speed = RUN if self.state != "walk" else RUN / 2 if rainy else self.WALK_V
            self.x += speed * dt * (1 if self.right else -1)
            if self.x <= 0 or self.x >= self.width - self.W:  # 끝에 닿으면 돌아섬
                self.x = min(max(self.x, 0), max(0, self.width - self.W))
                self.right = self.x <= 0
        if self.state == "sleep":
            if not self.zz or now - self.zz[-1] >= ZZ_EVERY:
                self.zz.append(now)
            self.zz = [t for t in self.zz if now - t < ZZ_RISE]
        elif self.zz:
            self.zz = []

    def pose(self, now, rainy):
        if self.held or self.air:  # 들리거나 떨어지며 버둥거림
            return self.PRE + ("walk1" if int(now / RUN_STEP) % 2 == 0 else "walk2")
        if self.leap:
            return self.PRE + self.LEAP_POSE[self.leap[2]]
        if self.state in ("walk", "run"):
            step = RUN_STEP if self.state == "run" or rainy else STEP
            return self.PRE + ("walk1" if int((now - self.since) / step) % 2 == 0 else "walk2")
        return self.PRE + {"hop": "stand"}.get(self.state, self.state)

    def feet(self):
        """발이 닿는 열 범위 [a, b)."""
        a, b = self.FOOT if self.right else (self.W - self.FOOT[1], self.W - self.FOOT[0])
        return int(self.x) + a, int(self.x) + b

    def draw(self, px, stride, height, sprites, ground, now, rainy, floor=None, wet=None):
        """ground: 발 밑 열들 중 가장 높이 쌓인 높이 px. 그 위에 섬. floor: 틀 뒤에 묻혔을 때 그 아래를 가림.
        wet: 수면 화면 y — 그 아래 몸은 물빛 섞은 벌로."""
        x = int(self.x)
        y = height - int(ground) - self.H - int(self.hop)
        self.paint(px, stride, height, sprites, self.pose(now, rainy), x, y, now, floor, wet)
        for t in self.zz:  # 머리 위에서 비스듬히 떠오름
            k = (now - t) / ZZ_RISE
            hx = x + (self.W - 5 * SCALE if self.right else 2 * SCALE)
            zx = hx + int(k * 14 * (1 if self.right else -1))
            zy = y + 4 * SCALE - int(k * 40)
            if 0 <= zx <= self.width - 4 * SCALE:
                stamp(px, stride, zx, zy, sprites[("zzz", True)], self.width, height)
        self.draw_mood(px, stride, height, sprites, x, y, now)


class Bird(Pet):
    """Cat 과 같은 겉모습. 상태: hop(콩콩) · peck(쪼기) · stand(두리번) · fly(화면 안 다른 자리로 날아가 앉음).
    비 오면 덜 날아다니고, 반딧불이가 머리 위로 내려오면 쪼려 함."""
    W, H = BIRD_W, BIRD_H
    LEAP, NO_LEAP = {"up": (0.3, 8), "down": (0.4, 4)}, ("fly",)  # 날갯짓하며 사뿐히. 나는 중엔 glide 높이를 따라감
    DIVER, SWIM_V, PEEK = "bird", 45, 4
    PADDLE, FLOAT = ("bird_stand", "bird_air"), 0.3  # 오리처럼 얕게 떠서 물속 발만 저음
    FALL = (600, 180)  # 놓이면 날갯짓하며 천천히 내려앉음

    def __init__(self, width, rng=random):
        self.rng, self.width = rng, width
        self.x = rng.uniform(0, max(0, width - BIRD_W))
        self.right = rng.random() < 0.5
        self.alt = 0.0  # 바닥 위로 뜬 높이 px
        self.go("stand", 0.0)

    def go(self, state, now):
        self.state, self.since = state, now
        lo, hi = {"hop": (1, 3), "peck": (0.8, 2), "stand": (1, 3), "fly": (99, 99)}[state]
        self.until = now + self.rng.uniform(lo, hi)

    def fly(self, now, far):
        """화면 안 다른 자리로 날아감. far 면 지금 자리에서 화면 1/3 넘게 떨어진 아무 데로(양쪽 다)."""
        room = max(0, self.width - BIRD_W)
        if far:  # 먼 쪽 끝 1/3 로만 가면 자주 놀라는 우박·뇌우 때 양 끝 두 군데만 오감
            lo, hi = max(0.0, self.x - room / 3), min(room, self.x + room / 3)
            u = self.rng.uniform(0, room - (hi - lo))
            self.land = u + (hi - lo) if u > lo else u
        else:
            self.land = self.rng.uniform(0, room)
            if abs(self.land - self.x) < 120:  # 너무 가까우면 넓은 쪽으로 120px 밀어 냄
                self.land = self.x + (120 if self.x < room / 2 else -120)
                self.land = min(max(self.land, 0), room)
        self.start, self.right, self.g0 = self.x, self.land >= self.x, self.ground or 0.0
        self.go("fly", now)

    def glide(self, path, land):
        """나는 동안의 발밑 높이(weather 가 follow 에 넘김). path: 날아가는 길에서 가장 높은 바닥, land: 앉을 자리 바닥.
        뜬 자리에서 앉을 자리 바닥으로 고르게 옮겨 가다가 높이 뜬 만큼(alt/FLY_ALT) path 쪽으로 — 다 뜨면 길 위를
        평평하게 지나 틀 단마다 들썩이지 않음. 뜨고 내리는 80·160px 안에 단이 있으면 그 단을 지날 때만 조금 들썩임."""
        total = abs(self.land - self.start) or 1.0
        g = self.g0 + (land - self.g0) * (1 - abs(self.land - self.x) / total)
        return g + (max(path, g) - g) * self.alt / FLY_ALT

    def startle(self, now):
        """번개·우박. 땅에 있으면 멀리 날아감."""
        if self.state != "fly":
            self.fly(now, True)

    def chase(self, now, flies):
        if now < self.calm or self.state == "fly":
            return
        cx = self.x + BIRD_W / 2
        near = [fx for fx, up in flies if abs(fx - cx) < 50 and up < 80]
        if near:
            self.calm = now + self.rng.uniform(*CALM)
            self.right = near[0] >= cx
            self.go("peck", now)
            self.emote("!", now)

    def update(self, dt, now, rainy):
        s, sign = self.state, 1 if self.right else -1
        if s == "fly":  # 날아오르며 가고, 앉을 자리 가까이서 내려옴
            self.x += FLY * dt * sign
            left = (self.land - self.x) * sign  # 앉을 자리까지 남은 px
            if left <= 0:
                self.x, self.alt = self.land, 0.0
                self.go("stand", now)
            else:
                self.alt = FLY_ALT * min(1.0, (abs(self.land - self.start) - left) / 80, left / 160)
            return
        if now >= self.until:
            r = self.rng.random()
            if r < (0.03 if self.kind in WET else 0.1):
                self.fly(now, False)
                return
            if s == "hop" and r < 0.4:
                self.right = not self.right
            self.go("peck" if r < 0.45 else "stand" if r < 0.7 else "hop", now)
            s = self.state
        if s == "hop":
            p = (now - self.since) % HOP_EVERY / HOP_EVERY
            self.alt = 4 * HOP_UP * p * (1 - p)
            self.x += HOP_DX / HOP_EVERY * dt * sign
            if self.x <= 0 or self.x >= self.width - BIRD_W:
                self.x = min(max(self.x, 0), max(0, self.width - BIRD_W))
                self.right = self.x <= 0
        else:
            self.alt = 0.0
            if s == "stand" and self.rng.random() < dt * 1.2:  # 두리번
                self.right = not self.right

    def pose(self, now):
        if self.state == "fly" or self.leap or self.held or self.air:
            return "bird_fly1" if int((now - self.since) / FLAP) % 2 == 0 else "bird_fly2"
        if self.state == "peck":
            return "bird_peck" if int((now - self.since) / 0.25) % 2 == 0 else "bird_stand"
        return "bird_stand"

    def feet(self):
        """발이 닿는 열 범위 [a, b)."""
        a, b = BIRD_FOOT if self.right else (BIRD_W - BIRD_FOOT[1], BIRD_W - BIRD_FOOT[0])
        return int(self.x) + a, int(self.x) + b

    def draw(self, px, stride, height, sprites, ground, now, rainy, floor=None, wet=None):
        y = height - int(ground) - BIRD_H - int(self.alt)
        self.paint(px, stride, height, sprites, self.pose(now), int(self.x), y, now, floor, wet)
        self.draw_mood(px, stride, height, sprites, int(self.x), y, now)


class Dog(Cat):
    """고양이처럼 걷고 앉고 자며, 서 있을 땐 꼬리를 흔듦. 비나 눈이 오면 신나서 뛰어다님."""
    PRE, W, H, FOOT = "dog_", 20 * SCALE, 13 * SCALE, (4 * SCALE, 19 * SCALE)
    LEAP = {"up": (0.42, 22), "down": (0.42, 16)}  # 신나서 높이 붕
    DIVER, SWIM_V, PEEK = "dog", 60, 4  # 빼꼼하면 흔드는 꼬리 끝도 같이 보임

    def next_state(self, now, rainy):
        if self.kind in ("rain", "snow") and self.state != "run" and self.rng.random() < 0.3:
            self.right = self.rng.random() < 0.5
            self.go("run", now)
            self.emote("♪", now, self.until - now)
            return
        super().next_state(now, rainy)

    def pose(self, now, rainy):
        p = super().pose(now, rainy)
        still = self.state == "stand" and not (self.leap or self.held or self.air)
        return "dog_wag" if still and int((now - self.since) / 0.18) % 2 else p


class Penguin(Cat):
    """뒤뚱뒤뚱 걷다 서고, 눈·우박이 쌓인 날엔 가끔 배를 깔고 미끄러짐. 앉거나 자지 않음. 어항에선 제일 빨리 헤엄침."""
    PRE, W, H, FOOT, WALK_V = "peng_", 14 * SCALE, 16 * SCALE, (4 * SCALE, 10 * SCALE), 22
    DUR = {**Cat.DUR, "slide": (0.8, 1.6)}
    # 오를 땐 낮게 뒤뚱 뛰고, 내려올 땐 배를 깔고 미끄러져 내려옴(위로 안 뜸)
    LEAP, LEAP_POSE = {"up": (0.5, 4), "down": (0.6, 0)}, ("slide", "stand")
    DIVER, SWIM_V, PEEK = "penguin", 95, 4  # 부리까지
    FLOAT = 0.4

    def next_state(self, now, rainy):
        r = self.rng.random()
        if self.state == "walk":
            self.go("slide" if self.snowy and r < 0.3 else "stand", now)
            if self.state == "slide":
                self.emote("♪", now, self.until - now)
        else:
            if self.state == "stand" and r < 0.5:
                self.right = not self.right
            self.go("walk", now)


class Rabbit(Pet):
    """깡충 뛰어 다니다 서서 코를 씰룩임. 놀라면 돌아서 빠르게 뛰어 달아남. Cat 과 같은 겉모습.
    비 오면 자주 웅크려 가만히 있고, 눈 오는 날엔 더 높이 뜀."""
    W, H, FOOT = 14 * SCALE, 14 * SCALE, (2 * SCALE, 12 * SCALE)
    JUMP = {"hop": (0.42, 34, 20, (2, 6)), "run": (0.3, 60, 28, (4, 6))}  # 한 번에 초, 앞으로 px, 높이 px, 몇 번
    LEAP = {"up": (0.34, 26), "down": (0.34, 18)}  # 제일 높이 깡충. 늘 뛰는 깡충 위에 얹힘
    DIVER, SWIM_V, PEEK = "rabbit", 55, 6  # 긴 귀가 먼저 솟음
    PADDLE = ("rab_stand", "rab_jump")

    def __init__(self, width, rng=random):
        self.rng, self.width = rng, width
        self.x = rng.uniform(0, max(0, width - self.W))
        self.right = rng.random() < 0.5
        self.alt = 0.0
        self.go("stand", 0.0)

    def go(self, state, now):
        self.state, self.since = state, now
        if state in self.JUMP:  # 뛰는 동안은 착지할 때 끝나게 횟수로 셈
            self.until = now + self.JUMP[state][0] * self.rng.randint(*self.JUMP[state][3])
        else:
            self.until = now + self.rng.uniform(*{"stand": (1, 3), "sniff": (1, 2.5)}[state])

    def startle(self, now):
        if self.state != "run":
            self.right = not self.right
            self.go("run", now)

    def update(self, dt, now, rainy):
        if now >= self.until:
            r = self.rng.random()
            if self.kind in WET and r < 0.6:  # 비를 맞으며 웅크림
                self.go("stand", now)
                self.until += 2
                self.emote("…", now, self.until - now)
            elif self.state in self.JUMP:
                self.go("sniff" if r < 0.5 else "stand", now)
            else:
                if r < 0.4:
                    self.right = not self.right
                self.go("hop" if r < 0.7 else "sniff" if self.state == "stand" else "stand", now)
        jump = self.JUMP.get(self.state)
        if not jump:
            self.alt = 0.0
            return
        period, dx, up, _ = jump
        up *= 1.5 if self.kind == "snow" else 1
        p = (now - self.since) % period / period
        self.alt = 4 * up * p * (1 - p)
        self.x += dx / period * dt * (1 if self.right else -1)
        if self.x <= 0 or self.x >= self.width - self.W:
            self.x = min(max(self.x, 0), max(0, self.width - self.W))
            self.right = self.x <= 0

    def pose(self, now):
        if self.leap or self.held or self.air:
            return "rab_jump"
        if self.state in self.JUMP:
            return "rab_jump" if self.alt > 2 else "rab_stand"
        if self.state == "sniff":
            return "rab_sniff" if int((now - self.since) / 0.15) % 2 else "rab_stand"
        return "rab_stand"

    def feet(self):
        a, b = self.FOOT if self.right else (self.W - self.FOOT[1], self.W - self.FOOT[0])
        return int(self.x) + a, int(self.x) + b

    def draw(self, px, stride, height, sprites, ground, now, rainy, floor=None, wet=None):
        y = height - int(ground) - self.H - int(self.alt)
        self.paint(px, stride, height, sprites, self.pose(now), int(self.x), y, now, floor, wet)
        self.draw_mood(px, stride, height, sprites, int(self.x), y, now)


# weather 가 동물만 있을 때 다시 그리는 맨 아래 띠 높이 px. 깜짝 뛰기는 프레임마다 더해 가서 30fps 에서
# v·dt 만큼 더 오름. Zz 는 이보다 낮게 뜸
BAND = max(max(c.H for c in (Cat, Dog, Penguin)) + int(HOP_V ** 2 / (2 * GRAVITY) + HOP_V / 30),
           BIRD_H + FLY_ALT, Rabbit.H + int(Rabbit.JUMP["run"][2] * 1.5)) + 4


def check():
    for name, rows in ART.items():
        assert len(rows) == ART_H and all(len(r) == ART_W for r in rows), name
        assert set("".join(rows)) <= set(COLORS) | {"."}, name
        assert rows[-1].strip(".") or name == "sleep", "발바닥이 맨 아랫줄"
    sp = sprites()
    seg = sp[("stand", True)]
    assert all(0 <= dy < H and skip % 4 == 0 and skip + len(d) <= W * 4 for dy, skip, d in seg)
    gaps = [s for s in seg if s[0] == H - 1]
    assert len(gaps) >= 2, "다리 사이 틈은 끊겨야 함 — 밑의 눈을 안 지움"
    # 좌우 뒤집기: 오른쪽 그림의 첫 칸이 왼쪽 그림의 끝 칸
    r, l = sp[("walk1", True)], sp[("walk1", False)]
    row = lambda segs, dy: {skip // 4 + i // 4 for d0, skip, d in segs if d0 == dy for i in range(0, len(d), 4)}
    assert row(l, 10) == {W - 1 - c for c in row(r, 10)}

    # 틀 단 뛰기: 꼭대기는 높은 끝보다 apex 위, 끝은 정확히 착지
    for g0, g1, a in ((0, 48, 12), (48, 0, 8), (48, 0, 0), (0, 5, 3)):
        ys = [leap_height(g0, g1, a, i / 1000) for i in range(1001)]
        assert abs(max(ys) - (max(g0, g1) + a)) < 0.05 and ys[0] == g0 and abs(ys[-1] - g1) < 1e-9, (g0, g1, a)
    leap_poses = {Cat: ({"walk1"}, {"walk1"}), Dog: ({"dog_walk1"}, {"dog_walk1"}),
                  Penguin: ({"peng_slide"}, {"peng_stand"}), Rabbit: ({"rab_jump"}, {"rab_jump"}),
                  Bird: ({"bird_fly1", "bird_fly2"}, {"bird_fly1", "bird_fly2"})}
    for cls, (down_pose, up_pose) in leap_poses.items():
        a = cls(300, random.Random(1))
        a.state = "stand"
        pose = (lambda t: a.pose(t, False)) if isinstance(a, Cat) else a.pose
        assert a.follow(48.0, 1 / 60, 0.0) == 48 and a.follow(45.0, 1 / 60, 0.0) == 45 and not a.leap, \
            ("눈 더미 굴곡 정도는 뛰지 않고 따라감", cls)
        for target, want_pose, apex in ((0.0, down_pose, cls.LEAP["down"][1]), (45.0, up_pose, cls.LEAP["up"][1])):
            t, start, top, poses = 0.0, a.ground, 0.0, set()
            while True:
                t += 1 / 60
                g = a.follow(target, 1 / 60, t)
                if not a.leap:
                    break
                top, poses = max(top, g), poses | {pose(t)}
            secs = cls.LEAP["up" if target > start else "down"][0]
            assert g == target and t <= secs + 2 / 60 + 1e-9, ("제때 정확히 착지", cls, target, t)  # 첫 프레임에 뛰기 시작
            assert max(start, target) + apex - 1 <= top <= max(start, target) + apex + 1e-9, ("동물마다 뜨는 높이", cls, top)
            assert poses == want_pose, ("뛰는 동안 그 동물의 뛰는 그림", cls, poses)
        assert cls.H + cls.LEAP["up"][1] <= BAND and cls.H + cls.LEAP["down"][1] <= BAND, "다시 그리는 띠 안"
    assert Rabbit.H + Rabbit.JUMP["run"][2] * 1.5 + Rabbit.LEAP["up"][1] <= BAND, "토끼는 늘 뛰는 깡충 위에 얹혀도 띠 안"
    for a, state in ((Bird(300), "fly"), (Cat(300), "hop")):
        a.state = state
        a.follow(48.0, 1 / 60, 0.0)
        a.follow(0.0, 1 / 60, 1 / 60)
        assert not a.leap and a.ground == 48 - CLIMB / 60, ("날거나 이미 뛰는 중엔 새로 안 뛰고 높이만 따라감", state)
        a.bury()
        assert not a.under, ("날거나 이미 뛰는 중엔 안 묻힘", state)

    # 발밑에 틀이 솟으면 그 뒤에 묻혔다가 머리만 빼꼼(눈까지) 내밀고 두리번한 뒤 뛰어나옴
    stands = {Cat: ART["stand"], Dog: DOG_ART["dog_stand"], Penguin: PENG_ART["peng_stand"],
              Rabbit: RABBIT_ART["rab_stand"], Bird: BIRD_ART["bird_stand"]}
    for cls, rows in stands.items():
        assert "e" in "".join(rows[:cls.PEEK]) and cls.PEEK * SCALE < cls.H / 2, ("머리만, 눈까지 내밂", cls)
        a = cls(300, random.Random(1))
        a.follow(0.0, 1 / 60, 0.0)
        a.mood = ("♪", 0.0, 9.0)
        a.bury()
        assert a.under and a.mood is None, cls
        t, out, sides = 0.0, [], set()
        while a.under:
            t += 1 / 60
            out.append(round(a.follow(45.0, 1 / 60, t) + cls.H - 45, 6))  # 틀 윗변 위로 나온 px
            sides.add(a.right)
            assert t < HIDE[1] + PEEK_UP + PEEK_HOLD + cls.LEAP["up"][0] + 0.1, ("제때 나옴", cls)
        hid, held = out.index(next(v for v in out if v > 0)), out.count(cls.PEEK * SCALE)
        assert HIDE[0] * 60 - 1 <= hid <= HIDE[1] * 60 + 1 and max(out[:hid]) <= 0, ("처음엔 다 숨음", cls, hid)
        j = next(i for i, v in enumerate(out) if v > cls.PEEK * SCALE)  # 뛰어나오기 시작
        assert PEEK_HOLD * 60 - 2 <= held and out[j - held:j] == [cls.PEEK * SCALE] * held, ("머리만 내밀고 버팀", cls, held)
        assert sides == {True, False} and a.state == "stand", ("두리번", cls)
        assert a.ground == 45 and not a.leap and max(out) > cls.H, ("뛰어나와 틀 위에 섬", cls, max(out))
    a = Cat(300)
    a.dive = 1.0
    a.bury()
    assert not a.under, "헤엄치는 중엔 안 묻힘"
    a = Cat(300)
    a.air = 30.0
    a.bury()
    assert not a.under, "놓여 떨어지는 중엔 안 묻힘"
    a.air = 0.0
    a.bury()
    a.grab(1.0, 5, 6)
    assert not a.under and a.peek is None, "묻혀 있다 집히면 바로 나옴"
    # 틀 뒤에 가림: 틀 열(바닥 20)에선 그 아래를 안 찍고, 틈 열(바닥 0)은 그대로
    sp0 = sprites()[("stand", True)]
    full, px, floor = bytearray(100 * 4 * 50), bytearray(100 * 4 * 50), [0] * 30 + [20] * 70
    stamp(full, 400, 10, 50 - H + 9, sp0, 100, 50)  # 몸이 화면 끝을 넘고 틀 가장자리(30)에 걸침
    stamp(px, 400, 10, 50 - H + 9, sp0, 100, 50, floor)
    for y in range(50):
        for c in range(100):
            o = y * 400 + c * 4
            assert px[o:o + 4] == (full[o:o + 4] if y < 50 - floor[c] else bytes(4)), ("틀 아래만 가림", y, c)
    assert any(full[35 * 400 + 120:35 * 400 + 160]) and any(px[35 * 400:35 * 400 + 120]), "시험이 양쪽에 걸침"

    rng = random.Random(7)
    cat = Cat(500, rng)
    now, seen, rights = 0.0, set(), set()
    for _ in range(30 * 600):  # 10분
        now += 1 / 30
        before = cat.x
        cat.update(1 / 30, now, False)
        assert 0 <= cat.x <= 500 - W, "화면 안"
        if cat.x != before and 0 < cat.x < 500 - W:
            assert (cat.x > before) == cat.right, "가는 쪽을 봄"
        seen.add(cat.state)
        rights.add(cat.right)
    assert {"walk", "stand", "sit", "sleep"} <= seen and rights == {True, False}, seen
    facing = cat.right
    cat.startle(now)
    assert cat.state == "hop" and cat.zz == []
    top = 0
    while cat.state == "hop":
        now += 1 / 30
        cat.update(1 / 30, now, False)
        top = max(top, cat.hop)
    assert cat.state == "run" and cat.hop == 0 and 40 < top < 80, top
    assert cat.right != facing, "놀라면 반대로 달아남"
    for edge, right in ((500 - W, True), (0, False)):  # 끝에 닿으면 돌아서 다시 안쪽으로
        cat.x, cat.right = edge, right
        cat.go("walk", now)
        for _ in range(30):
            cat.update(1 / 30, now, False)
        assert 0 < cat.x < 500 - W, ("끝에 붙어 있음", edge)
    # 비 오는 날은 안 잠
    cat = Cat(500, random.Random(3))
    for _ in range(30 * 600):
        now += 1 / 30
        cat.update(1 / 30, now, True)
        assert cat.state != "sleep", "비 오면 안 잠"
    # 쌓인 눈 위에 섬: 바닥 높이만큼 위에 찍힘
    px = bytearray(500 * 4 * 200)
    cat = Cat(500, random.Random(1))
    cat.x, cat.state = 100, "stand"
    cat.draw(px, 500 * 4, 200, sp, 20, 0.0, False)
    rows = [y for y in range(200) if any(px[y * 2000 + 400:(y + 1) * 2000])]
    assert rows[-1] == 200 - 20 - 1 and rows[0] == 200 - 20 - H, (rows[0], rows[-1])

    for art, cls in ((BIRD_ART, Bird), (DOG_ART, Dog), (RABBIT_ART, Rabbit), (PENG_ART, Penguin)):
        for name, rows in art.items():
            assert all(len(r) * SCALE == getattr(cls, "W", BIRD_W) for r in rows), name
            assert len(rows) * SCALE == getattr(cls, "H", BIRD_H), name
            assert set("".join(rows)) <= set(COLORS) | {"."}, name
            assert rows[-1].strip(".") or name in ("bird_air", "bird_fly1", "bird_fly2"), (name, "발바닥이 맨 아랫줄")
    # 다른 동물: 10분 돌리며 몇 프레임마다 실제로 그려, 화면 안·weather 가 다시 그리는 바닥 띠 안인지 봄
    band = BAND
    px = bytearray(500 * 4 * 200)
    # 날씨를 1분마다 바꾸며 반딧불이·불꽃도 계속 알려 줌 — 머리 위 표시까지 띠 안이어야 함
    kinds = ("none", "snow", "rain", "fireflies", "fireworks")
    for cls, want, moods in ((Cat, {"walk", "stand", "sit", "sleep"}, {"♥", "♪", "!"}),
                             (Dog, {"walk", "stand", "sit", "sleep", "run"}, {"♪", "!"}),
                             (Rabbit, {"hop", "stand", "sniff"}, {"…", "!"}),
                             (Penguin, {"walk", "stand", "slide"}, {"♪", "!"})):
        a = cls(500, random.Random(4))
        a.snowy, now, seen, top, felt = True, 0.0, set(), 200, set()
        for i in range(30 * 600):
            now += 1 / 30
            a.kind = kinds[int(now // 60) % len(kinds)]
            if a.kind == "fireflies":
                a.chase(now, [(a.x + a.W / 2 + 90, 60)])
            if a.kind == "fireworks" and i % 60 == 0:
                a.watch(now, 400)
            a.update(1 / 30, now, False)
            assert 0 <= a.x <= 500 - cls.W, (cls.__name__, a.x)
            assert a.state != "slide" or a.mood[0] == "♪", "미끄러지며 ♪"
            seen.add(a.state)
            felt |= {a.mood[0]} if a.mood else set()
            if i % 7 == 0 or a.state in ("hop", "run") or a.mood:
                px[:] = bytes(len(px))
                a.draw(px, 2000, 200, sp, 0, now, False)
                top = min(top, (len(px) - len(px.lstrip(b"\0"))) // 2000)
        assert want <= seen and moods <= felt, (cls.__name__, seen, felt)
        a.startle(now)
        assert a.state == ("run" if cls is Rabbit else "hop"), (cls.__name__, "놀람")
        for _ in range(60):
            now += 1 / 30
            a.update(1 / 30, now, False)
            px[:] = bytes(len(px))
            a.draw(px, 2000, 200, sp, 0, now, False)
            top = min(top, (len(px) - len(px.lstrip(b"\0"))) // 2000)
        assert 200 - top <= band, (cls.__name__, 200 - top, "바닥 띠 밖으로 나감")
    dog = Dog(500, random.Random(1))
    dog.go("stand", 0.0)
    assert {dog.pose(t / 30, False) for t in range(30)} == {"dog_stand", "dog_wag"}, "서 있으면 꼬리를 흔듦"
    peng = Penguin(500, random.Random(4))
    for _ in range(30 * 600):
        now += 1 / 30
        peng.update(1 / 30, now, False)
        assert peng.state != "slide", "눈 없는 날엔 안 미끄러짐"

    # 어항: 다섯 다 잠수 장비를 차고 떠올라 헤엄침. 하던 짓은 그대로 두고, 숨을 내쉬는 자리는 호흡기
    for name, pair in DIVE_ART.items():
        mx, my = DIVE_MOUTH[name]
        assert len({len(r) for rows in pair for r in rows}) == 1 and len(pair[0]) == len(pair[1]), name
        assert set("".join(pair[0] + pair[1])) <= set(COLORS) | {"."}, name
        assert all(rows[my][mx] in "soy" and rows[my][mx + 1:].strip(".") == "" for rows in pair), ("입이 앞 끝", name)
        assert pair[0] != pair[1] and (name == "bird" or "f" in "".join(pair[0])), ("발차기 두 장·오리발(새는 날개)", name)
        assert "m" in "".join(pair[0]), ("마스크", name)
    for cls in (Cat, Dog, Rabbit, Penguin, Bird):
        a = cls(1000, random.Random(6))
        sw, sh = DIVE_SIZE[a.DIVER]
        state, now, lifts, sides, breaths, kicks = a.state, 0.0, [], set(), 0, set()
        a.follow(48.0, 1 / 60, now)
        for i in range(60 * 120):
            now += 1 / 60
            before = a.x
            a.swim(1 / 60, now)
            assert 0 <= a.x <= 1000 - max(a.W, sw), (cls.__name__, a.x)
            if 0 < a.x < 1000 - max(a.W, sw) and a.x != before:
                assert (a.x > before) == a.right, ("가는 쪽을 봄", cls.__name__)
            lifts.append(a.lift)
            sides.add(a.right)
            breaths += a.breathe
            g = a.follow(48.0 if i % 600 < 300 else 0.0, 1 / 60, now)
            assert not a.leap, ("헤엄치는 동안은 틀 단을 안 뜀", cls.__name__)
            if i % 60 == 0:
                px = bytearray(1000 * 4 * 450)
                a.draw_swim(px, 4000, 450, sp, g, now)
                y = 450 - int(g) - sh - int(a.lift)
                ink = ((len(px) - len(px.lstrip(b"\0"))) // 4000, (len(px.rstrip(b"\0")) - 1) // 4000)
                assert y <= ink[0] <= ink[1] < y + sh, (cls.__name__, "떠 있는 높이에 그림")
                mx, my = a.mouth
                o = my * 4000 + mx * 4
                assert px[o + 3] == 255, ("호흡기 자리에 그림이 있음", cls.__name__)
                kicks.add(bytes(px))
                px = bytearray(len(px))
                a.draw_swim(px, 4000, 450, sp, g, now + KICK)  # 같은 자리, 다음 발차기
                kicks.add(bytes(px))
                assert len(kicks) == 2, ("오리발을 참", cls.__name__)
                kicks.clear()
        assert lifts[0] < 5 and lifts[60] < SWIM_RISE + SWIM_BOB + 1, ("바닥에서 천천히 떠오름", cls.__name__, lifts[:61:20])
        assert SWIM_DEPTH[0] < max(lifts) <= SWIM_DEPTH[1] + SWIM_BOB, (cls.__name__, max(lifts))
        assert max(lifts) - min(lifts[600:]) > 60, ("높이를 바꿔 가며 헤엄", cls.__name__)
        assert sides == {True, False} and 120 / BREATH[1] - 2 <= breaths <= 120 / BREATH[0] + 1, (cls.__name__, breaths)
        assert a.state == state, ("하던 짓은 그대로", cls.__name__)
    # 스노클: 대개 수면(관 끝이 물 밖 — 까딱여도 ceil 을 안 넘음)에 떠 있고 가끔 SNORK_DIP 안으로 잠깐 잠수
    a = Cat(1920, random.Random(3))
    a.snork, out, lifts = True, 0, []
    for i in range(60 * 600):
        a.swim(1 / 60, i / 60, 300.0, 300.0)
        lifts.append(a.lift)
        out += a.lift >= 300 - 2 * SNORK_BOB - 0.5
    assert 0.55 < out / len(lifts) < 0.85, ("대개 수면", out / len(lifts))
    assert max(lifts) <= 300 and 300 - SNORK_DIP - SNORK_BOB <= min(lifts), ("수면 밑 얕게만", min(lifts))

    def tally(a, kind, minutes=10):
        """kind 날씨에서 상태별 머문 프레임 수와 가장 높이 뜬 px."""
        a.kind, t, count, high = kind, 0.0, {}, 0.0
        for _ in range(30 * 60 * minutes):
            t += 1 / 30
            a.update(1 / 30, t, kind in WET)
            count[a.state] = count.get(a.state, 0) + 1
            high = max(high, getattr(a, "alt", 0))
        return count, high
    dry, _ = tally(Dog(500, random.Random(2)), "none")
    wet, _ = tally(Dog(500, random.Random(2)), "rain")
    assert "run" not in dry and wet.get("run", 0) > 30 * 20, ("강아지는 비에 신나서 뜀", wet)
    dry, high = tally(Rabbit(500, random.Random(2)), "none")
    wet, _ = tally(Rabbit(500, random.Random(2)), "rain")
    _, snow_high = tally(Rabbit(500, random.Random(2)), "snow")
    assert wet.get("hop", 0) < dry["hop"] / 2, ("토끼는 비 오면 웅크림", dry, wet)
    assert snow_high > high * 1.3, ("눈 오면 더 높이 뜀", high, snow_high)
    # 반딧불이로 폴짝: 그쪽으로 날아가 앉고, 달아나지 않고 ♪. 한 번 하면 한동안 안 함
    cat, t = Cat(500, random.Random(1)), 0.0
    cat.x, cat.right = 100, False
    cat.go("stand", t)
    cat.chase(t, [(cat.x + W / 2 + 100, 50)])
    assert cat.state == "hop" and cat.right, "반딧불이 쪽을 보고 뜀"
    while cat.state == "hop":
        t += 1 / 30
        cat.update(1 / 30, t, False)
    assert cat.state == "stand" and cat.right and cat.x > 140 and cat.mood[0] == "♪", (cat.state, cat.x)
    cat.go("walk", t)
    cat.chase(t, [(cat.x + 50, 50)])
    assert cat.state == "walk", "쉬는 동안은 안 쫓음"
    cat.chase(t + CALM[1], [(cat.x + W / 2 + 300, 50), (cat.x, 150)])
    assert cat.state == "walk", "멀거나 높은 건 안 쫓음"
    # 불꽃: 멈춰 서서 그쪽을 보고 놀람. 쉬는 동안은 하던 걸 계속함
    cat = Cat(500, random.Random(1))
    cat.x, cat.right = 100, False
    cat.go("sleep", 0.0)
    cat.watch(0.0, 400)
    assert cat.state == "stand" and cat.right and cat.mood[0] == "!", "깨서 불꽃 쪽을 봄"
    cat.go("walk", 1.0)
    cat.watch(1.0, 0)
    assert cat.state == "walk", "쉬는 동안은 계속 걸음"
    def above(now):
        px[:] = bytes(len(px))
        cat.draw(px, 2000, 200, sp, 0, now, False)
        return any(px[:2000 * (200 - H - 4)])
    cat.go("stand", 0.0)
    cat.emote("!", 0.0)
    assert above(0.5), "표시는 머리 위에 그려짐"
    assert not above(2.0) and cat.mood is None, "때가 지나면 사라짐"

    # 새
    bird, now, seen, trips = Bird(500, random.Random(5)), 0.0, set(), 0
    for _ in range(30 * 600):
        now += 1 / 30
        before = bird.state
        bird.update(1 / 30, now, False)
        assert 0 <= bird.x <= 500 - BIRD_W, ("화면 밖으로 안 나감", bird.x)
        assert 0 <= bird.alt and bird.alt + BIRD_H <= band, bird.alt
        if before == "fly" and bird.state == "stand":
            trips += 1
            assert abs(bird.x - bird.start) >= 100, "옆으로 조금 옮기는 게 아니라 날아서 감"
            assert bird.x == bird.land, "고른 자리에 정확히 앉음 (지나치면 끝에서 화면 밖)"
        seen.add(bird.state)
    assert seen == {"hop", "peck", "stand", "fly"} and trips >= 3, (seen, trips)
    flights = []
    for kind in ("none", "rain"):
        b, t = Bird(500, random.Random(5)), 0.0
        b.kind, n = kind, 0
        for _ in range(30 * 600):
            t += 1 / 30
            was = b.state
            b.update(1 / 30, t, kind in WET)
            n += was != "fly" and b.state == "fly"
        flights.append(n)
    assert flights[1] < flights[0] / 2, ("비 오면 덜 날아다님", flights)
    bird.go("stand", now)
    bird.chase(now, [(bird.x + BIRD_W / 2 + 30, 40)])
    assert bird.state == "peck" and bird.right and bird.mood[0] == "!", "머리 위 반딧불이를 쪼려 함"
    bird.state, bird.alt = "fly", FLY_ALT  # 표시가 사라지기 직전 가장 높이 떠오른 채 가장 높이 날아도
    px[:] = bytes(len(px))
    bird.draw(px, 2000, 200, sp, 0, bird.mood[2] - 0.01, False)
    assert 200 - (len(px) - len(px.lstrip(b"\0"))) // 2000 <= BAND, "날 때도 띠 안"
    for x in (20, 400):
        bird.x = x
        bird.go("peck", now)
        bird.startle(now)
        assert bird.state == "fly" and abs(bird.land - x) >= (500 - BIRD_W) / 3, "놀라면 멀리 날아감"
    spots = set()
    for _ in range(300):  # 왼쪽 끝에서 놀라도 반대쪽 끝 1/3 만이 아니라 화면 1/3 너머 아무 데나 — 열 칸 중 일곱 칸
        bird.x, bird.state = 20.0, "peck"
        bird.startle(now)
        spots.add(int(bird.land / (500 - BIRD_W) * 10))
    assert len(spots) >= 6, ("놀라 앉는 자리가 고루 퍼짐", sorted(spots))
    # 가로 잘라내기: 왼쪽 끝 밖으로 반쯤 나간 새는 화면 안쪽 절반만, 버퍼 밖으로 안 넘침
    px = bytearray(100 * 4 * 50)
    full = bytearray(len(px))
    seg = sp[("bird_stand", True)]
    stamp(full, 400, 40, 10, seg, 100, 50)
    stamp(px, 400, -18, 10, seg, 100, 50)
    stamp(px, 400, 100 - 18, 10, seg, 100, 50)
    assert len(px) == 100 * 4 * 50
    for y in range(10, 10 + BIRD_H):
        row, ref = px[y * 400:(y + 1) * 400], full[y * 400:(y + 1) * 400]
        assert row[:18 * 4] == ref[(40 + 18) * 4:(40 + 36) * 4], y   # 왼쪽 끝: 그림의 오른쪽 부분
        assert row[82 * 4:] == ref[40 * 4:(40 + 18) * 4], y           # 오른쪽 끝: 그림의 왼쪽 부분

    # 마우스로 집기: 그린 자리가 집는 상자, 집히면 하던 짓을 멈추고 버둥, 놓이면 떨어져 섬. 새는 천천히 내려앉음
    px, landed = bytearray(500 * 4 * 400), {}
    for cls in (Cat, Dog, Rabbit, Penguin, Bird):
        a = cls(500, random.Random(8))
        assert a.box() is None, "안 그렸으면 못 집음"
        a.startle(1.0)  # 뛰거나 날아오르는 중에 집어도
        a.update(0.1, 1.1, False)
        a.draw(px, 2000, 400, sp, 0, 1.1, False)
        x, y, w, h = a.box()
        assert (x, w, h) == (int(a.x), a.W, a.H) and y == 400 - a.H - int(getattr(a, "hop", 0) + getattr(a, "alt", 0)), cls.__name__
        a.grab(1.1, 5, 6)
        assert a.held == (5, 6) and a.state == "stand" and a.mood[0] == "!" and not (a.hop or a.alt), cls.__name__
        pose = (lambda t: a.pose(t, False)) if isinstance(a, Cat) else a.pose
        poses = {pose(1.1 + i / 30) for i in range(30)}
        assert all((p, a.right) in sp for p in poses) and not poses & {"dog_wag", "dog_stand", "stand", "peng_stand"}, \
            ("들린 동안 버둥", cls.__name__, poses)
        a.held, a.air = None, 300.0
        t, last = 0.0, a.air
        while a.air:
            t += 1 / 60
            a.fall(1 / 60, 100 + t)
            assert a.air <= last, ("떨어지기만 함", cls.__name__)
            last = a.air
        assert a.state == "stand" and a.until > 100 and not a.fall_v, ("내려앉은 때부터 잠깐 섬", cls.__name__)
        landed[cls] = t
        a.dive = 0.0
        assert a.box()[2:] == DIVE_SIZE[a.DIVER], "어항에선 잠수 그림 상자"
    assert all(t <= math.sqrt(2 * 300 / GRAVITY) + 2 / 60 for c, t in landed.items() if c is not Bird), landed
    assert landed[Bird] > 1.0, ("새는 날갯짓하며 천천히", landed[Bird])
    print("자체 점검 통과")


if __name__ == "__main__":
    check()
