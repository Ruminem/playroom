# SPDX-License-Identifier: Apache-2.0
"""창밖에서 비 내리는 듯한 빗소리. 녹음 파일을 싣지 않고 표준 라이브러리로 합성해 끊김 없이 되풀이한다.

세 겹을 섞는다 — 저역 통과한 흰 소리의 '쉬', 낮게 깔리는 갈색 소리, 창에 톡톡 닿는 짧은 방울. 루프 끝을 처음에
크로스페이드로 이어 붙여 이음매가 원래 이웃한 두 샘플이 되게 한다.
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
RATE = 22050
LOOP_SEC = 12      # 이 컨테이너에서 합성 0.35–0.43초
FADE_SEC = 1.0     # 이음매 크로스페이드
DROPS = 55         # 초당 창에 닿는 방울
PEAK = 0.95        # 볼륨 100% 의 최고점 (16비트 끝 대비)
# ponytail: afplay 는 SIGTERM 으로 weather 가 죽어도 안 따라 죽어 남은 길이만큼 더 울림. 길수록 다시 띄우는 틈이
# 드물고 고아는 길게 삶 — 두 바퀴(24초). 문제되면 weather 가 SIGTERM 을 받아 close 를 부르게
MAC_REPEAT = 2
MAC_FILE = Path(tempfile.gettempdir()) / "playroom-weather-rain.wav"  # 한 번만 뜨므로 이름 하나 — 안 쌓임
SND_ASYNC, SND_NODEFAULT, SND_MEMORY, SND_LOOP = 0x1, 0x2, 0x4, 0x8


def seam(out, n, f):
    """길이 n+f 의 소리 → 길이 n 의 루프. 앞 f 개를 끝 다음 f 개와 섞어, 되풀이할 때 [n-1] 다음이 원래 이웃 [n] 이 됨."""
    loop = out[:n]
    for i in range(f):
        a = i / f
        loop[i] = out[i] * a + out[n + i] * (1 - a)
    return loop


def synth(sec=LOOP_SEC, seed=7):
    """최고점이 1 인 빗소리 루프(float 목록)."""
    rng = random.Random(seed)
    g = rng.random
    n, f = int(sec * RATE), int(FADE_SEC * RATE)
    total = n + f
    out = [0.0] * total
    a_lp = 1 - math.exp(-2 * math.pi * 2500 / RATE)  # 쉬: 흰 소리를 2.5kHz 저역 통과 · 200Hz 고역 통과
    a_hp = math.exp(-2 * math.pi * 200 / RATE)
    lp = hp = last = br = 0.0
    for i in range(total):
        w = g() * 2 - 1
        lp += a_lp * (w - lp)
        hp = a_hp * (hp + lp - last)
        last = lp
        br = br * 0.995 + w * 0.02  # 갈색 소리(새는 적분) — 우르릉
        t = i / n  # 느린 출렁임은 루프 길이에 정수 바퀴라 이음매에서 안 튐
        out[i] = (hp * 0.55 + br * 0.9) * (1 + 0.18 * math.sin(math.tau * 2 * t) + 0.1 * math.sin(math.tau * 5 * t + 1.3))
    for _ in range(int(DROPS * (sec + FADE_SEC))):  # 방울: 1차 차분한 잡음이 2–10ms 로 꺼짐 — 톡
        at, amp, tau = rng.randrange(total), g() ** 2.2 * 0.9, rng.uniform(0.002, 0.010) * RATE
        prev = 0.0
        for j in range(min(int(tau * 5), total - at)):
            x = g() * 2 - 1
            out[at + j] += (x - prev) * amp * math.exp(-j / tau)
            prev = x
    loop = seam(out, n, f)
    peak = max(abs(v) for v in loop) or 1.0
    return [v / peak for v in loop]


def wav(base, volume, repeat=1):
    """볼륨 0–100 의 16비트 모노 WAV 바이트. 귀는 로그로 들어 (볼륨/100)² 로 줄임 — 50% 가 최대보다 12dB 작음."""
    k = PEAK * 32767 * (volume / 100) ** 2
    pcm = array("h", (int(v * k) for v in base)).tobytes()
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(pcm * repeat)
    return buf.getvalue()


class Player:
    """set(볼륨) 으로 틀고 set(None) 으로 멈춤. 합성(0.4초)과 WAV 만들기는 다른 스레드에서 — 그리는 루프가 안 멈춤.
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
