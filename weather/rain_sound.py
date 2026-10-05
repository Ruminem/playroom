# SPDX-License-Identifier: Apache-2.0
"""창밖에서 은은하게 들리는 빗소리. 녹음 파일을 싣지 않고 표준 라이브러리로 합성해 끊김 없이 되풀이한다.

좌우를 따로 만들어 섞는다 — 넓게 깔린 '쏴아', 그 속에 뭉개지는 잔방울 수백 개/초, 드물게 잎에 닿는 둥근 '툭', 낮은
우르릉. 이걸 창 너머로 듣듯 저역 통과로 먹먹하게 한 뒤, 마당 돌·콘크리트에 떨어지는 방울(둔한 툭 + 짧은 물보라)을
조금 얹는다. 루프 끝을 처음에 등전력 크로스페이드로 이어 붙여 이음매가 원래 이웃한 두 샘플이 되게 한다.
  윈도우: winmm PlaySoundW 를 메모리에서 비동기·되풀이로 — winsound.PlaySound 는 메모리와 비동기를 같이 못 씀
  맥: 임시 WAV 를 afplay 로. afplay 는 되풀이가 없어 끝나면 다시 띄움
"""
import ctypes
import io
import math
import os
import random
import subprocess
import sys
import tempfile
import threading
import wave
from array import array
from pathlib import Path

MAC = sys.platform == "darwin"
RATE = 32000       # 22050 이면 11kHz 위가 없어 물보라가 죽음
LOOP_SEC = 12      # 이 컨테이너에서 합성 2.2–3.1초 — 소리가 그만큼 늦게 남
# ponytail: 합성은 다른 스레드지만 GIL 을 나눠 써서, 그동안 60fps 흉내 루프가 45fps 로 떨어짐(가장 긴 프레임 31ms,
# 이 컨테이너). 켤 때 한 번뿐이라 둠. 거슬리면 synth 결과를 %LOCALAPPDATA%\playroom 에 캐시
FADE_SEC = 1.0     # 이음매 크로스페이드
PEAK = 0.95        # 볼륨 100% 의 최고점 (16비트 끝 대비)
# 들어 보고 고른 값(2026-10-05, 시안 2번 + 돌 방울 20%). 고치면 다시 들어 볼 것
HISS_LP, HISS_HP, HISS = 5000, 250, 0.6            # 쏴아: 흰 소리를 250Hz–5kHz 로
FINE, FINE_HZ, FINE_AMP = 800, 2500, 0.4           # 잔방울: 초당 수 · 대역 중심 · 크기
LEAF, LEAF_HZ, LEAF_AMP = 8, 700, 1.2              # 잎에 닿는 툭
RUMBLE, GUST, GLASS = 1.1, 0.25, 1300              # 우르릉 · 출렁임 폭 · 창 너머 저역 통과
STONE, STONE_SOFT = 55, 3000                       # 돌 방울: 초당 수 · 창 너머로 깎는 자리
STONE_MIX = 0.12881773386363152                    # 돌 방울 RMS ÷ 바닥 RMS — 0.2.4 타닥 비율(0.644)의 20%
# ponytail: afplay 는 SIGTERM 으로 weather 가 죽어도 안 따라 죽어 남은 길이만큼 더 울림. 길수록 다시 띄우는 틈이
# 드물고 고아는 길게 삶 — 두 바퀴(24초). 문제되면 weather 가 SIGTERM 을 받아 close 를 부르게
MAC_REPEAT = 2
MAC_FILE = Path(tempfile.gettempdir()) / "playroom-weather-rain.wav"  # 한 번만 뜨므로 이름 하나 — 안 쌓임
SND_ASYNC, SND_NODEFAULT, SND_MEMORY, SND_LOOP = 0x1, 0x2, 0x4, 0x8


def seam(out, n, f):
    """길이 n+f 의 소리 → 길이 n 의 루프. 앞 f 개를 끝 다음 f 개와 섞어, 되풀이할 때 [n-1] 다음이 원래 이웃 [n] 이 됨.
    √ 무게(등전력) — 선형으로 섞으면 서로 무관한 잡음 둘이 가운데서 3dB 꺼져 12초마다 숨을 쉼."""
    loop = out[:n]
    for i in range(f):
        a = i / f
        loop[i] = out[i] * math.sqrt(a) + out[n + i] * math.sqrt(1 - a)
    return loop


def lowpass(xs, hz, times=1):
    a = 1 - math.exp(-2 * math.pi * hz / RATE)
    for _ in range(times):
        m = 0.0
        for i, v in enumerate(xs):
            m += a * (v - m)
            xs[i] = m
    return xs


def bandpass(hz, q):
    """RBJ 대역 통과(최고점 0dB) 계수 b0, b2, a1, a2. q 는 1 아래로 — 높으면 울려서 쇳소리가 남."""
    w = 2 * math.pi * hz / RATE
    al = math.sin(w) / (2 * q)
    a0 = 1 + al
    return al / a0, -al / a0, -2 * math.cos(w) / a0, (1 - al) / a0


def rms(xs):
    return math.sqrt(sum(v * v for v in xs) / len(xs))


def bed(rng, total, swell):
    """한 채널의 쏴아 + 잔방울 + 잎의 툭. 방울은 무작위 임펄스 열을 대역 통과에 흘려 하나씩 찍지 않음 — O(N)."""
    g = rng.random
    a_lp = 1 - math.exp(-2 * math.pi * HISS_LP / RATE)
    a_hp = math.exp(-2 * math.pi * HISS_HP / RATE)
    fb0, fb2, fa1, fa2 = bandpass(FINE_HZ, 0.7)
    lb0, lb2, la1, la2 = bandpass(LEAF_HZ, 0.9)
    pf, pl = FINE / RATE, LEAF / RATE
    lp = hp = last = soft = 0.0
    x1 = x2 = y1 = y2 = u1 = u2 = v1 = v2 = 0.0
    out = [0.0] * total
    for i in range(total):
        w = g() * 2 - 1
        lp += a_lp * (w - lp)
        hp = a_hp * (hp + lp - last)
        last = lp
        r = g()  # 잔방울: 크기는 대부분 아주 작게(세제곱)
        x = (g() ** 3) * (1 if r < pf * 0.5 else -1) if r < pf else 0.0
        y = fb0 * x + fb2 * x2 - fa1 * y1 - fa2 * y2
        x2, x1, y2, y1 = x1, x, y1, y
        r = g()  # 잎에 닿는 툭: 드물고 모서리를 깎아 둥글게
        u = (g() ** 2) * (1 if r < pl * 0.5 else -1) if r < pl else 0.0
        v = lb0 * u + lb2 * u2 - la1 * v1 - la2 * v2
        u2, u1, v2, v1 = u1, u, v1, v
        soft += 0.35 * (v - soft)
        s = swell[i]
        out[i] = hp * HISS * s + y * FINE_AMP * (0.6 + 0.4 * s) + soft * LEAF_AMP
    return out


def stone_shape(rng):
    """돌·콘크리트에 떨어진 방울 하나: 둔한 툭(잡음을 600–1400Hz 저역 통과 두 겹, 0.5ms 에 올라 3–8ms 로 꺼짐)
    + 흩어지는 물보라(1.5–4kHz 대역, 1–2ms 늦게 시작해 12–30ms 로 꺼짐, 툭의 1/3). 차분·공진이 없어 쇳소리가 안 남."""
    g = rng.random
    t_thud, t_spray = rng.uniform(0.003, 0.008) * RATE, rng.uniform(0.012, 0.030) * RATE
    delay = int(rng.uniform(0.001, 0.002) * RATE)
    rise = 0.0005 * RATE
    a1 = 1 - math.exp(-2 * math.pi * rng.uniform(600, 1400) / RATE)
    s_lo = 1 - math.exp(-2 * math.pi * rng.uniform(1500, 2500) / RATE)
    s_hi = 1 - math.exp(-2 * math.pi * rng.uniform(3000, 4000) / RATE)
    length = int(max(t_thud * 5, delay + t_spray * 4))
    out = [0.0] * length
    l1 = l2 = h1 = lo = 0.0
    for j in range(length):
        w = g() * 2 - 1
        l1 += a1 * (w - l1)
        l2 += a1 * (l1 - l2)
        thud = l2 * min(1.0, j / rise) * math.exp(-j / t_thud) * 2.5
        h1 += s_hi * (w - h1)
        lo += s_lo * (w - lo)
        spray = (h1 - lo) * math.exp(-(j - delay) / t_spray) * 0.33 if j >= delay else 0.0
        out[j] = thud + spray
    return out


def stones(rng, total):
    """돌 방울 24 벌을 만들어 두고 크기만 바꿔 흩뿌림 — 방울마다 새로 만들면 몇 배 느림. 마당 소리라 창 너머로 살짝 깎음."""
    bank = [stone_shape(rng) for _ in range(24)]
    peak = max(max(abs(v) for v in s) for s in bank)
    bank = [[v / peak for v in s] for s in bank]
    out = [0.0] * total
    for _ in range(int(STONE * total / RATE)):
        s, at, amp = rng.choice(bank), rng.randrange(total), rng.random() ** 2.2 * 0.9
        for j, v in enumerate(s[:total - at]):
            out[at + j] += v * amp
    return lowpass(out, STONE_SOFT)


def synth(sec=LOOP_SEC, seed=7):
    """최고점이 1 인 빗소리 루프 [왼쪽, 오른쪽] (float 목록 둘)."""
    rng = random.Random(seed)
    n, f = int(sec * RATE), int(FADE_SEC * RATE)
    total = n + f
    # 출렁임: 1–7 바퀴 사인을 무작위 위상·1/k 무게로 — 박자가 안 느껴지고, 루프에 정수 바퀴라 이음매에서 안 튐
    parts = [(k, rng.uniform(0, math.tau), 1 / k) for k in range(1, 8)]
    norm = sum(wt for _, _, wt in parts)
    swell = [1 + GUST * sum(wt * math.sin(math.tau * k * i / n + ph) for k, ph, wt in parts) / norm
             for i in range(total)]
    br, rum = 0.0, [0.0] * total  # 우르릉: 새는 적분 갈색 소리, 좌우 같이 — 멀리서 오는 낮은 소리는 가운데
    for i in range(total):
        br = br * 0.997 + (rng.random() * 2 - 1) * 0.02
        rum[i] = br * RUMBLE * swell[i]
    chans = []
    for c in range(2):
        mixed = lowpass([a + b for a, b in zip(bed(random.Random(seed * 10 + c), total, swell), rum)], GLASS, 2)
        st = stones(random.Random(seed * 100 + c), total)
        k = STONE_MIX * rms(mixed) / (rms(st) or 1.0)
        chans.append(seam([a + b * k for a, b in zip(mixed, st)], n, f))
    peak = max(max(map(abs, ch)) for ch in chans) or 1.0
    return [[v / peak for v in ch] for ch in chans]


def wav(base, volume, repeat=1):
    """볼륨 0–100 의 16비트 스테레오 WAV 바이트. 귀는 로그로 들어 (볼륨/100)² 로 줄임 — 50% 가 최대보다 12dB 작음."""
    k = PEAK * 32767 * (volume / 100) ** 2
    left, right = base
    pcm = array("h", bytes(4 * len(left)))
    pcm[0::2] = array("h", (int(v * k) for v in left))
    pcm[1::2] = array("h", (int(v * k) for v in right))
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(pcm.tobytes() * repeat)
    return buf.getvalue()


class Player:
    """set(볼륨) 으로 틀고 set(None) 으로 멈춤. 합성(2초 남짓)과 WAV 만들기는 다른 스레드에서 — 그리는 루프가 안 멈춤.
    설정 창 막대가 0.1초마다 볼륨을 보내도 마지막 값만 틂. play·stop 은 검사가 흉내로 바꿔 끼움."""

    def __init__(self, play=None, stop=None, spawn=None):
        self.play, self.stop = play or (mac_play if MAC else win_play), stop or (mac_stop if MAC else win_stop)
        self.spawn = spawn or (lambda fn: threading.Thread(target=fn, daemon=True).start())
        self.want = self.now = None  # 바라는 볼륨 · 지금 울리는 볼륨 (None 은 조용)
        self.base, self.lock = None, threading.Lock()

    def set(self, volume):
        if volume == self.want:
            return
        self.want = volume
        self.spawn(self.apply)

    def apply(self):
        with self.lock:
            want = self.want
            if want == self.now:
                return
            if want is None:
                self.stop()
            else:
                if self.base is None:
                    self.base = synth()
                self.play(want, self.base)
            self.now = want

    def close(self):
        self.want = None
        self.apply()


_win_buf = None  # 비동기로 울리는 동안 버퍼가 살아 있어야 함


def win_play(volume, base):
    global _win_buf
    buf = ctypes.create_string_buffer(wav(base, volume))
    win_stop()  # 옛 버퍼를 놓기 전에 멈춤
    ctypes.windll.winmm.PlaySoundW(ctypes.c_void_p(ctypes.addressof(buf)), None,
                                   SND_MEMORY | SND_ASYNC | SND_LOOP | SND_NODEFAULT)
    _win_buf = buf


def win_stop():
    global _win_buf
    ctypes.windll.winmm.PlaySoundW(None, None, 0)
    _win_buf = None


_mac = {"proc": None, "on": False}


def mac_play(volume, base):
    tmp = MAC_FILE.with_suffix(".tmp")
    tmp.write_bytes(wav(base, volume, MAC_REPEAT))
    os.replace(tmp, MAC_FILE)  # 울리던 afplay 는 옛 파일을 쥐고 있음
    if _mac["on"]:
        _mac["swap"] = True
        _kill()  # 되풀이 스레드가 새 파일로 바로 다시 띄움
        return
    _mac["on"] = True
    threading.Thread(target=_mac_loop, daemon=True).start()


def _mac_loop():
    while _mac["on"]:
        try:
            _mac["proc"] = subprocess.Popen(["afplay", str(MAC_FILE)], stdin=subprocess.DEVNULL,
                                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except OSError:
            _mac["on"] = False
            return
        code = _mac["proc"].wait()
        if _mac.pop("swap", False):
            continue
        if code != 0 and _mac["on"]:  # 못 트는 것(장치 없음 등)을 쉼 없이 되풀이하지 않게
            threading.Event().wait(1.0)


def _kill():
    p = _mac["proc"]
    if p and p.poll() is None:
        p.terminate()


def mac_stop():
    _mac["on"] = False
    _kill()
    MAC_FILE.unlink(missing_ok=True)
