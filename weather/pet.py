# SPDX-License-Identifier: Apache-2.0
"""weather 위를 돌아다니는 픽셀 고양이. 그림(글자 판)·하는 짓(상태 기계)·찍기가 있고, 언제 찍을지는 weather 가 정한다.

걷다가 서고, 앉고, 앉았다 잠들고(Zz), 번개가 치면 깜짝 뛰어 달아난다. 비가 오면 빨리 걷고 안 잔다.
발은 바닥(작업 표시줄 위) — 쌓인 눈·잎이 있으면 그 위 — 에 딛는다.

  python pet.py    자체 점검
"""
import random

SCALE = 3  # 그림 한 칸 = 화면 px

COLORS = {"k": (38, 43, 68), "o": (247, 118, 34), "l": (254, 174, 52), "w": (255, 255, 255),
          "p": (232, 183, 150), "e": (24, 20, 37), "z": (192, 203, 220),
          "b": (150, 98, 58), "c": (236, 218, 186), "y": (250, 186, 60),  # b·c·y 는 새
          "d": (196, 128, 72), "a": (122, 76, 44),  # 강아지 털·귀
          "h": (214, 214, 226), "g": (62, 68, 94)}  # 토끼 회색 · 펭귄 등

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
BIRD = ("............",
        "......kkk...",
        ".....kbbbk..",
        ".....kbebky.",
        "kk..kbbbbk..",
        "kbkkbbbccck.",
        ".kbbbbbccck.",
        "..kbbbbcck..",
        "...kkkkkk...",
        ".....y.y....")
NO_LEGS = BIRD[:-1] + ("............",)
BIRD_ART = {"bird_stand": BIRD, "bird_air": NO_LEGS,
            "bird_peck": ("............",
                          "............",
                          "............",
                          "kk..........",
                          "kbk..kkkk...",
                          ".kbkkbbbbk..",
                          "..kbbbbbbbk.",
                          "..kbbbccbebk",
                          "...kkkkkkkky",
                          ".....y.y...."),
            "bird_fly1": put(NO_LEGS, ("kk...", "kbk..", ".kbk.", "..kbk"), 1, 0),  # 날개 위
            "bird_fly2": put(NO_LEGS, ("kbbk", ".kbk", "..kk"), 3, 7)}             # 날개 아래
BIRD_W, BIRD_H = len(BIRD[0]) * SCALE, len(BIRD) * SCALE
BIRD_FOOT = (5 * SCALE, 8 * SCALE)

# 강아지. 꼬리 자리(왼쪽 위)를 비워 두고 꼬리를 덮어 흔듦
DOG_HEAD = ("...........kkkkk....",
            "..........kdddddk...",
            ".........kaaddedk...",
            ".........kaaddddkkk.",
            ".........kaadddwwwek",
            ".........kaadddwwwk.",
            ".....kkkkkaaddddkk..")
DOG_BODY = ("....kddddddddddddk..",
            "....kdddddddddddddk.",
            "....kddwwwwwwwwddk..")
DOG_LEGS = {"stand": ("....kdk.kdk.kdk.kdk.",
                      "....kdk.kdk.kdk.kdk.",
                      "....kkk.kkk.kkk.kkk."),
            "walk1": ("....kdk.kdk.kdk.kdk.",
                      "...kdk..kdk..kdk.kdk",
                      "...kkk..kkk..kkk.kkk"),
            "walk2": ("....kdk.kdk.kdk.kdk.",
                      ".....kdkdk...kdkdk..",
                      ".....kkkkk...kkkkk..")}
TAIL_UP, TAIL_WAG = (".k..", "kdk.", "kdk.", ".kdk"), ("....", "kk..", "kddk", ".kdk")
DOG_ART = {"dog_" + name: put(DOG_HEAD + DOG_BODY + legs, TAIL_UP, 1, 2) for name, legs in DOG_LEGS.items()}
DOG_ART["dog_wag"] = put(DOG_HEAD + DOG_BODY + DOG_LEGS["stand"], TAIL_WAG, 1, 2)
DOG_ART["dog_sit"] = DOG_HEAD[:6] + (".........kaaddddkk..",
                                     "........kddddddk....",
                                     ".......kdddddwwk....",
                                     ".......kddddwwwk....",
                                     "..kk...kddddwwwk....",
                                     "..kdkkkkddddkdk.....",
                                     "...kkkkkkkkkkkk.....")
DOG_ART["dog_sleep"] = ("....................",) * 7 + (".............kddddk.",
                                                          "....kkkkkkkkkaddkdkk",
                                                          "...kdddddddddaaddwwk",
                                                          "..kddddddddddaadwwwk",
                                                          ".kkdddwwwwwwdddddkk.",
                                                          "..kkkkkkkkkkkkkkkk..")

# 토끼
RABBIT = ("........kk.kk.",
          ".......kpk.kpk",
          ".......kpk.kpk",
          ".......kpkkkpk",
          "......khhhhhhk",
          "......khhhhehk",
          "...kkkkhhhhhhp",
          "..khhhhhhhhhk.",
          ".kwhhhhhhhhhk.",
          "kwwhhhhhhhhk..",
          ".khhhhhhhhhk..",
          "..khhhwhhhkk..",
          "..khhk.khhhk..",
          "..kkkk.kkkkkk.")
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

WALK, RUN = 38, 150      # px/초. 비 올 때 걷기는 RUN 의 절반
STEP, RUN_STEP = 0.2, 0.08  # 걸음 그림 바꾸는 간격 초
HOP_V, GRAVITY = 420, 1500  # 깜짝 뛰기: 처음 위로 px/초, 중력 px/초²
ZZ_EVERY, ZZ_RISE = 1.4, 3.0  # Z 하나가 나오는 간격 초, 떠오르는 데 걸리는 초
HOP_EVERY, HOP_DX, HOP_UP = 0.32, 14, 7  # 새 콩콩 뛰기: 간격 초, 한 번에 px, 높이 px
FLY, FLY_ALT, FLAP = 170, 60, 0.09  # 새가 날 때 px/초, 높이 px(weather 가 다시 그리는 바닥 띠 안), 날갯짓 간격 초


def segments(rows, flip):
    """글자 판 → [(dy, 앞에서 건너뛸 바이트, 바이트), …]. 행 안의 투명한 틈은 끊어서 밑의 눈을 안 지움."""
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
                data = b"".join(bytes((COLORS[c][2], COLORS[c][1], COLORS[c][0], 255)) * SCALE for c in line[start:x])
                out.append((y * SCALE + sy, start * SCALE * 4, data))
    return out


def sprites():
    """{(그림 이름, 오른쪽을 보나): 조각들}. Z 는 ('zzz', True)."""
    sp = {(name, right): segments(rows, not right) for art in (ART, BIRD_ART, DOG_ART, RABBIT_ART, PENG_ART)
          for name, rows in art.items() for right in (True, False)}
    sp[("zzz", True)] = segments(ZZZ, False)
    return sp


def stamp(px, stride, x, y, segs, width, height):
    """조각을 (x, y) 에 찍음. 화면 밖으로 나가는 행과 가로로 삐져나간 부분은 잘라 냄 (새가 옆으로 날아 나감)."""
    for dy, skip, data in segs:
        yy = y + dy
        if 0 <= yy < height:
            a = x * 4 + skip
            lo, hi = max(a, 0), min(a + len(data), width * 4)
            if lo < hi:
                o = yy * stride
                px[o + lo:o + hi] = data if hi - lo == len(data) else data[lo - a:hi - a]


class Cat:
    """상태: walk · stand · sit · sleep · hop(깜짝 뛰기) · run(뛰어 달아남). 시각은 밖에서 받음.
    강아지·펭귄은 그림(PRE 로 시작하는 이름)·크기·빠르기만 바꿔 이어받음."""
    PRE, W, H, FOOT, WALK_V = "", W, H, FOOT, WALK
    DUR = {"walk": (3, 9), "stand": (1.5, 4), "sit": (3, 8), "sleep": (12, 30), "hop": (9, 9), "run": (1.2, 1.8)}
    snowy = False  # 눈·우박 더미가 있는 날. weather 가 매 프레임 넣음 (펭귄만 봄)

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
        if self.state != "hop":
            self.go("hop", now)
            self.vy, self.zz = HOP_V, []

    def next_state(self, now, rainy):
        r = self.rng.random()
        if self.state == "walk":
            if r < 0.2:
                self.right = not self.right
                self.go("walk", now)
            else:
                self.go("sit" if r < 0.65 else "stand", now)
        elif self.state == "sit" and r < 0.4 and not rainy:
            self.go("sleep", now)
        else:
            if self.state != "run" and r < 0.5:
                self.right = not self.right
            self.go("walk", now)

    def update(self, dt, now, rainy):
        if self.state == "hop":
            self.hop += self.vy * dt
            self.vy -= GRAVITY * dt
            if self.hop <= 0:
                self.hop, self.vy = 0.0, 0.0
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
        if self.state in ("walk", "run"):
            step = RUN_STEP if self.state == "run" or rainy else STEP
            return self.PRE + ("walk1" if int((now - self.since) / step) % 2 == 0 else "walk2")
        return self.PRE + {"hop": "stand"}.get(self.state, self.state)

    def feet(self):
        """발이 닿는 열 범위 [a, b)."""
        a, b = self.FOOT if self.right else (self.W - self.FOOT[1], self.W - self.FOOT[0])
        return int(self.x) + a, int(self.x) + b

    def draw(self, px, stride, height, sprites, ground, now, rainy):
        """ground: 발 밑 열들 중 가장 높이 쌓인 높이 px. 그 위에 섬."""
        x = int(self.x)
        y = height - int(ground) - self.H - int(self.hop)
        stamp(px, stride, x, y, sprites[(self.pose(now, rainy), self.right)], self.width, height)
        for t in self.zz:  # 머리 위에서 비스듬히 떠오름
            k = (now - t) / ZZ_RISE
            hx = x + (self.W - 5 * SCALE if self.right else 2 * SCALE)
            zx = hx + int(k * 14 * (1 if self.right else -1))
            zy = y + 4 * SCALE - int(k * 40)
            if 0 <= zx <= self.width - 4 * SCALE:
                stamp(px, stride, zx, zy, sprites[("zzz", True)], self.width, height)


class Bird:
    """Cat 과 같은 겉모습. 상태: hop(콩콩) · peck(쪼기) · stand(두리번) · fly(화면 안 다른 자리로 날아가 앉음)."""

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
        """화면 안 다른 자리로 날아감. far 면 지금 자리에서 먼 쪽 1/3 로."""
        room = max(0, self.width - BIRD_W)
        if far:
            self.land = self.rng.uniform(0, room / 3) if self.x > room / 2 else self.rng.uniform(room * 2 / 3, room)
        else:
            self.land = self.rng.uniform(0, room)
            if abs(self.land - self.x) < 120:  # 너무 가까우면 넓은 쪽으로 120px 밀어 냄
                self.land = self.x + (120 if self.x < room / 2 else -120)
                self.land = min(max(self.land, 0), room)
        self.start, self.right = self.x, self.land >= self.x
        self.go("fly", now)

    def startle(self, now):
        """번개·우박. 땅에 있으면 멀리 날아감."""
        if self.state != "fly":
            self.fly(now, True)

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
            if r < 0.1:
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
        if self.state == "fly":
            return "bird_fly1" if int((now - self.since) / FLAP) % 2 == 0 else "bird_fly2"
        if self.state == "peck":
            return "bird_peck" if int((now - self.since) / 0.25) % 2 == 0 else "bird_stand"
        return "bird_stand"

    def feet(self):
        """발이 닿는 열 범위 [a, b)."""
        a, b = BIRD_FOOT if self.right else (BIRD_W - BIRD_FOOT[1], BIRD_W - BIRD_FOOT[0])
        return int(self.x) + a, int(self.x) + b

    def draw(self, px, stride, height, sprites, ground, now, rainy):
        y = height - int(ground) - BIRD_H - int(self.alt)
        stamp(px, stride, int(self.x), y, sprites[(self.pose(now), self.right)], self.width, height)


class Dog(Cat):
    """고양이처럼 걷고 앉고 자며, 서 있을 땐 꼬리를 흔듦."""
    PRE, W, H, FOOT = "dog_", 20 * SCALE, 13 * SCALE, (4 * SCALE, 19 * SCALE)

    def pose(self, now, rainy):
        p = super().pose(now, rainy)
        return "dog_wag" if self.state == "stand" and int((now - self.since) / 0.18) % 2 else p


class Penguin(Cat):
    """뒤뚱뒤뚱 걷다 서고, 눈·우박이 쌓인 날엔 가끔 배를 깔고 미끄러짐. 앉거나 자지 않음."""
    PRE, W, H, FOOT, WALK_V = "peng_", 14 * SCALE, 16 * SCALE, (4 * SCALE, 10 * SCALE), 22
    DUR = {**Cat.DUR, "slide": (0.8, 1.6)}

    def next_state(self, now, rainy):
        r = self.rng.random()
        if self.state == "walk":
            self.go("slide" if self.snowy and r < 0.3 else "stand", now)
        else:
            if self.state == "stand" and r < 0.5:
                self.right = not self.right
            self.go("walk", now)


class Rabbit:
    """깡충 뛰어 다니다 서서 코를 씰룩임. 놀라면 돌아서 빠르게 뛰어 달아남. Cat 과 같은 겉모습."""
    W, H, FOOT = 14 * SCALE, 14 * SCALE, (2 * SCALE, 12 * SCALE)
    JUMP = {"hop": (0.42, 34, 20, (2, 6)), "run": (0.3, 60, 28, (4, 6))}  # 한 번에 초, 앞으로 px, 높이 px, 몇 번

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
            if self.state in self.JUMP:
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
        p = (now - self.since) % period / period
        self.alt = 4 * up * p * (1 - p)
        self.x += dx / period * dt * (1 if self.right else -1)
        if self.x <= 0 or self.x >= self.width - self.W:
            self.x = min(max(self.x, 0), max(0, self.width - self.W))
            self.right = self.x <= 0

    def pose(self, now):
        if self.state in self.JUMP:
            return "rab_jump" if self.alt > 2 else "rab_stand"
        if self.state == "sniff":
            return "rab_sniff" if int((now - self.since) / 0.15) % 2 else "rab_stand"
        return "rab_stand"

    def feet(self):
        a, b = self.FOOT if self.right else (self.W - self.FOOT[1], self.W - self.FOOT[0])
        return int(self.x) + a, int(self.x) + b

    def draw(self, px, stride, height, sprites, ground, now, rainy):
        y = height - int(ground) - self.H - int(self.alt)
        stamp(px, stride, int(self.x), y, sprites[(self.pose(now), self.right)], self.width, height)


# weather 가 동물만 있을 때 다시 그리는 맨 아래 띠 높이 px. 깜짝 뛰기는 프레임마다 더해 가서 30fps 에서
# v·dt 만큼 더 오름. Zz 는 이보다 낮게 뜸
BAND = max(max(c.H for c in (Cat, Dog, Penguin)) + int(HOP_V ** 2 / (2 * GRAVITY) + HOP_V / 30),
           BIRD_H + FLY_ALT, Rabbit.H + Rabbit.JUMP["run"][2]) + 4


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
    for cls, want in ((Cat, {"walk", "stand", "sit", "sleep"}), (Dog, {"walk", "stand", "sit", "sleep"}),
                      (Rabbit, {"hop", "stand", "sniff"}),
                      (Penguin, {"walk", "stand", "slide"})):
        a = cls(500, random.Random(4))
        a.snowy, now, seen, top = True, 0.0, set(), 200
        for i in range(30 * 600):
            now += 1 / 30
            a.update(1 / 30, now, False)
            assert 0 <= a.x <= 500 - cls.W, (cls.__name__, a.x)
            seen.add(a.state)
            if i % 7 == 0 or a.state in ("hop", "run"):
                px[:] = bytes(len(px))
                a.draw(px, 2000, 200, sp, 0, now, False)
                top = min(top, (len(px) - len(px.lstrip(b"\0"))) // 2000)
        assert want <= seen, (cls.__name__, seen)
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
    for x in (20, 400):
        bird.x = x
        bird.go("peck", now)
        bird.startle(now)
        assert bird.state == "fly" and abs(bird.land - x) > 200, "놀라면 먼 쪽으로 날아감"
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
    print("자체 점검 통과")


if __name__ == "__main__":
    check()
