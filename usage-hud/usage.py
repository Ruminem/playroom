# SPDX-License-Identifier: Apache-2.0
"""Claude Code 사용량을 읽는다 — 구독 한도 두 창과 날마다 쓴 정가. 표준 라이브러리만 씀.

  python usage.py           지금 값을 한 번 찍음
  python usage.py --check   자체 점검

한도는 CLI 가 로그인해 둔 OAuth 토큰으로 haiku 1토큰 요청을 보내 응답 헤더
`anthropic-ratelimit-unified-{5h,7d}-{utilization,reset}` 에서 받는다. 문서에 없는 헤더라
이름이나 스케일이 바뀌면 조용히 틀린 값이 된다 — 그래서 의심스러운 창은 None 으로 뺀다.
요청 하나가 구독 한도에 1토큰씩 잡히므로 LIMIT_EVERY 초에 한 번만 받는다.

토큰은 윈도우·리눅스면 `~/.claude/.credentials.json`, 맥이면 Keychain 의
`Claude Code-credentials` 에 있다. 토큰은 8시간짜리이고, 데스크톱 앱은 인증을 따로 들고 그 자리를
안 고친다. 그래서 401 이 오면 CLI 를 한 번(훅·세션 기록 없이 haiku `-p`) 불러 고치게 하고 다시 받는다.
그래도 안 되면 `expired` 가 된다 — 터미널에서 `claude` 를 한 번 열면 풀린다.

정가는 `~/.claude/projects/**/*.jsonl` 의 assistant 줄 `usage` 에 단가를 곱한 값이다.
구독이면 실제로 나가는 돈은 아니지만, 모델과 캐시 종류를 한 단위로 합쳐 주는 자로 쓴다.
"""
import contextlib
import json
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import types
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta
from pathlib import Path

PROJECTS = Path.home() / ".claude" / "projects"
CREDENTIALS = Path.home() / ".claude" / ".credentials.json"
LIMIT_URL = "https://api.anthropic.com/v1/messages"
LIMIT_EVERY = 5 * 60
TIMEOUT = 5
# 만료된 토큰을 CLI 가 고치게 하는 가장 가벼운 호출 (2026-10-05 13초). --bare 는 OAuth 를 안 써서 못 씀
REVIVE = ["-p", ".", "--model", "haiku", "--no-session-persistence", "--strict-mcp-config",
          "--settings", '{"disableAllHooks": true}']
REVIVE_EVERY = 30 * 60  # 로그아웃된 채면 매번 실패하므로 이 초에 한 번만

# 100만 토큰당 달러. (입력, 출력, 캐시 읽기, 캐시 쓰기 5분, 캐시 쓰기 1시간)
# 규칙 저장소 turn-usage.py 의 표를 옮김 — 그쪽에서 기록의 cost-state 로 역산해 맞춘 값이다.
# 모르는 모델은 0 으로 세지 않고 unknown 에 이름을 남긴다
PRICES = {
    "claude-opus-5-5":   (4.0, 20.0, 0.2, 5.0,  8.0),
    "claude-opus-5":     (5.0, 25.0, 0.5, 6.25, 10.0),
    "claude-opus-4-8":   (5.0, 25.0, 0.5, 6.25, 10.0),
    "claude-opus-4-7":   (5.0, 25.0, 0.5, 6.25, 10.0),
    "claude-opus-4-6":   (5.0, 25.0, 0.5, 6.25, 10.0),
    "claude-fable-5-1":  (10.0, 50.0, 0.25, 20.0, 20.0),
    "claude-sonnet-5":   (2.0, 10.0, 0.2, 2.50,  4.0),
    "claude-sonnet-4-6": (3.0, 15.0, 0.3, 3.75,  6.0),
    "claude-haiku-4-5":  (1.0,  5.0, 0.1, 1.25,  2.0),
}

# (이름, 헤더 앞머리, 창 길이 초)
WINDOWS = (("5h", "5h", 5 * 3600), ("7d", "7d", 7 * 86400))


# ── 한도 ────────────────────────────────────────────────────────────────
def oauth_token():
    """CLI 가 로그인해 둔 토큰. 윈도우·리눅스는 파일, 맥은 Keychain 에 있다."""
    try:
        raw = CREDENTIALS.read_text(encoding="utf-8")
    except OSError:
        if sys.platform != "darwin":
            return None
        import subprocess
        try:
            raw = subprocess.run(
                ["security", "find-generic-password", "-s", "Claude Code-credentials", "-w"],
                capture_output=True, text=True, timeout=TIMEOUT).stdout
        except (OSError, subprocess.SubprocessError):
            return None
    try:
        return json.loads(raw)["claudeAiOauth"]["accessToken"]
    except (ValueError, KeyError, TypeError):
        return None


def windows_from(headers, now):
    """응답 헤더 → {"5h": (쓴 비율 0–1, 재설정 시각) | None, "7d": ...}.

    빼는 자리 셋 — 헤더가 없다 · 비율이 0–1 밖이다 · 재설정이 지났거나 창보다 멀다.
    뒤의 둘은 스케일이나 뜻이 바뀌었을 때 틀린 값을 그리지 않으려는 것이다.
    """
    out = {}
    for name, key, span in WINDOWS:
        try:
            pct = float(headers.get("anthropic-ratelimit-unified-%s-utilization" % key))
            reset = float(headers.get("anthropic-ratelimit-unified-%s-reset" % key))
        except (TypeError, ValueError):
            out[name] = None
            continue
        ok = 0 <= pct <= 1 and 0 < reset - now <= span + 600
        out[name] = (pct, reset) if ok else None
    return out


def fetch_limits():
    """{"5h", "7d", "expired", "at"}. 토큰이 없거나 요청이 실패하면 두 창 다 None."""
    now = time.time()
    empty = {"5h": None, "7d": None, "expired": False, "at": now}
    token = oauth_token()
    if not token:
        return empty
    req = urllib.request.Request(
        LIMIT_URL, method="POST",
        data=json.dumps({"model": "claude-haiku-4-5-20251001", "max_tokens": 1,
                         "messages": [{"role": "user", "content": "."}]}).encode(),
        headers={"Authorization": "Bearer " + token, "anthropic-version": "2023-06-01",
                 "anthropic-beta": "oauth-2025-04-20", "content-type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            return {**windows_from(r.headers, now), "expired": False, "at": now}
    except urllib.error.HTTPError as e:
        if e.code == 401:
            # 고쳤으면 한 번 더 받음. 다시 401 이어도 revive 가 쉬는 중이라 되풀이되지 않음
            return fetch_limits() if revive() else {**empty, "expired": True}
        # 429 여도 헤더는 붙어 온다 — 한도가 찼다는 것이 바로 보여 줄 값이다
        return {**windows_from(e.headers, now), "expired": False, "at": now}
    except (OSError, ValueError):
        return empty


_revived = 0.0


def revive():
    """CLI 를 한 번 불러 만료된 토큰을 새로 고치게 함. 고쳤으면 True. REVIVE_EVERY 초에 한 번만."""
    global _revived
    exe = shutil.which("claude") or shutil.which(str(Path.home() / ".local" / "bin" / "claude"))
    if not exe or time.time() - _revived < REVIVE_EVERY:
        return False
    _revived = time.time()
    try:  # 임시 폴더에서 — 프로젝트 CLAUDE.md 를 싣지 않게. pythonw 아래서 콘솔 창이 뜨지 않게
        r = subprocess.run([exe, *REVIVE], cwd=tempfile.gettempdir(), capture_output=True, timeout=120,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except (OSError, subprocess.SubprocessError):
        return False
    return r.returncode == 0


_limits = None


def limits():
    """fetch_limits 를 LIMIT_EVERY 초에 한 번만 부른다."""
    global _limits
    if _limits is None or time.time() - _limits["at"] >= LIMIT_EVERY:
        _limits = fetch_limits()
    return _limits


# ── 정가 ────────────────────────────────────────────────────────────────
def base_model(name):
    """`claude-opus-5[1m]`·날짜 붙은 이름을 단가표 이름으로. 긴 이름부터 맞춘다."""
    if not name:
        return None
    name = name.split("[")[0]
    for known in sorted(PRICES, key=len, reverse=True):
        if name.startswith(known):
            return known
    return name


def dollars(model, u):
    """호출 하나의 정가. 모르는 모델이면 None."""
    price = PRICES.get(base_model(model))
    if not price:
        return None
    fresh = u.get("input_tokens") or 0
    read_ = u.get("cache_read_input_tokens") or 0
    write = u.get("cache_creation_input_tokens") or 0
    out = u.get("output_tokens") or 0
    # 5분/1시간 캐시 쓰기는 단가가 다르다. 쪼갠 값이 없으면 전부 1시간으로 본다
    split = u.get("cache_creation") or {}
    w5, w1 = split.get("ephemeral_5m_input_tokens"), split.get("ephemeral_1h_input_tokens")
    if w5 is None and w1 is None:
        w5, w1 = 0, write
    p_in, p_out, p_read, p_w5, p_w1 = price
    return (fresh * p_in + out * p_out + read_ * p_read + (w5 or 0) * p_w5 + (w1 or 0) * p_w1) / 1e6


def local_day(ts):
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone().date()
    except (AttributeError, ValueError):
        return None


def file_days(lines):
    """jsonl 줄들 → ({날짜: 달러}, 모르는 모델 이름들).

    한 API 호출이 텍스트·생각·도구 호출마다 따로 줄이 되고 usage 는 그 줄들에 똑같이
    복사된다. requestId 로 묶어 처음 본 줄만 센다 — 줄마다 더하면 몇 배로 부푼다.
    """
    seen, days, unknown = set(), {}, set()
    for line in lines:
        if '"assistant"' not in line:  # 대부분의 줄을 json 을 안 풀고 넘긴다
            continue
        try:
            rec = json.loads(line)
        except ValueError:
            continue  # 쓰는 중에 읽으면 마지막 줄이 잘려 있을 수 있다
        if rec.get("type") != "assistant":
            continue
        msg = rec.get("message") or {}
        key = rec.get("requestId") or msg.get("id")
        if key in seen:
            continue
        seen.add(key)
        day = local_day(rec.get("timestamp"))
        cost = dollars(msg.get("model"), msg.get("usage") or {})
        if cost is None:
            unknown.add(base_model(msg.get("model")) or "?")
        elif day:
            days[day] = days.get(day, 0.0) + cost
    return days, unknown


_files = {}  # 경로 → ((mtime, size), 날짜별 달러, 모르는 모델)


def spend(days=7):
    """오늘부터 거슬러 days 일 동안 날마다 쓴 정가. ({날짜: 달러}, 모르는 모델 이름들).

    바뀐 파일만 다시 읽는다. 이 PC 실측(2026-10-04) 7일치 기록 82MB.
    """
    first = date.today() - timedelta(days=days - 1)
    since = datetime.combine(first, datetime.min.time()).timestamp()
    total = {first + timedelta(days=i): 0.0 for i in range(days)}
    unknown = set()
    for path in PROJECTS.rglob("*.jsonl"):
        try:
            st = path.stat()
        except OSError:
            continue
        if st.st_mtime < since:
            continue
        sig = (st.st_mtime, st.st_size)
        cached = _files.get(path)
        if not cached or cached[0] != sig:
            try:
                with path.open(encoding="utf-8", errors="replace") as f:
                    cached = (sig, *file_days(f))
            except OSError:
                continue
            _files[path] = cached
        for day, d in cached[1].items():
            if day in total:
                total[day] += d
        unknown |= cached[2]
    return total, unknown


# ── 찍기 ────────────────────────────────────────────────────────────────
def left(sec):
    """재설정까지 남은 시간을 짧게: 2D6H · 3H20M · 12M."""
    m = max(0, int(sec // 60))
    d, m = divmod(m, 1440)
    h, m = divmod(m, 60)
    if d:
        return "%dD%dH" % (d, h)
    if h:
        return "%dH%dM" % (h, m)
    return "%dM" % m


_lock = threading.Lock()


def snapshot(days=7):
    """HUD 와 페이지가 같이 쓰는 한 덩어리. 캐시가 프로세스 전역이라 스레드끼리 겹치지 않게 잠근다
    (HUD 가 페이지 서버를 제 프로세스 안에 띄우면 두 쪽이 같은 캐시를 만진다)."""
    with _lock:
        lim = limits()
        by_day, unknown = spend(days)
    now = time.time()
    bars = {}
    for name, _, _ in WINDOWS:
        w = lim[name]
        bars[name] = None if w is None else {"left": 1 - w[0], "reset": w[1], "in": left(w[1] - now)}
    return {"bars": bars, "expired": lim["expired"],
            "today": by_day[date.today()],
            "days": [[d.isoformat(), round(v, 2)] for d, v in sorted(by_day.items())],
            "unknown": sorted(unknown)}


def check():
    # 정가: opus-5-5 로 각 칸 100만씩 → 단가 합
    u = {"input_tokens": 1e6, "output_tokens": 1e6, "cache_read_input_tokens": 1e6,
         "cache_creation_input_tokens": 2e6,
         "cache_creation": {"ephemeral_5m_input_tokens": 1e6, "ephemeral_1h_input_tokens": 1e6}}
    assert abs(dollars("claude-opus-5-5[1m]", u) - (4 + 20 + 0.2 + 5 + 8)) < 1e-9
    # 쪼갠 값이 없으면 1시간 단가
    assert abs(dollars("claude-opus-5-5", {"cache_creation_input_tokens": 1e6}) - 8) < 1e-9
    # 긴 이름이 먼저 맞아야 함 — opus-5-5 가 opus-5 로 새면 안 됨. 표에 적힌 순서가
    # 우연히 맞춰 주지 않게 뒤집은 표로도 본다
    saved = list(PRICES.items())
    for order in (saved, saved[::-1]):
        PRICES.clear()
        PRICES.update(order)
        assert base_model("claude-opus-5-5-20260101") == "claude-opus-5-5"
    assert dollars("gpt-x", u) is None

    # 같은 requestId 는 한 번만, 모르는 모델은 이름으로, 깨진 줄은 넘김
    def row(rid, model="claude-haiku-4-5", ts="2026-10-04T03:00:00Z"):
        return json.dumps({"type": "assistant", "requestId": rid, "timestamp": ts,
                           "message": {"model": model, "usage": {"output_tokens": 1e6}}})
    days, unknown = file_days([row("a"), row("a"), row("b"), row("c", "mystery"), '{"type": "assist'])
    day = local_day("2026-10-04T03:00:00Z")
    assert days == {day: 10.0}, days
    assert unknown == {"mystery"}

    # 한도 검증: 정상 · 비율이 % 단위로 바뀜 · 재설정이 지남 · 헤더 없음
    now = 1_000_000.0
    h = {"anthropic-ratelimit-unified-5h-utilization": "0.25",
         "anthropic-ratelimit-unified-5h-reset": str(now + 3600),
         "anthropic-ratelimit-unified-7d-utilization": "72",
         "anthropic-ratelimit-unified-7d-reset": str(now + 86400)}
    w = windows_from(h, now)
    assert w["5h"] == (0.25, now + 3600) and w["7d"] is None
    h["anthropic-ratelimit-unified-5h-reset"] = str(now - 1)
    assert windows_from(h, now)["5h"] is None
    assert windows_from({}, now) == {"5h": None, "7d": None}

    assert left(2 * 86400 + 6 * 3600 + 59) == "2D6H"
    assert left(3 * 3600 + 20 * 60) == "3H20M"
    assert left(-5) == "0M"

    # 401 → CLI 로 고친 뒤 한 번 더 받음. 30분 안에 또 401 이면 CLI 를 다시 부르지 않고 만료
    global _revived
    real = urllib.request.urlopen, subprocess.run, oauth_token, _revived
    answers, runs = [], []

    def fake_open(req, timeout):
        a = answers.pop(0)
        if a == 401:
            raise urllib.error.HTTPError(LIMIT_URL, 401, "", {}, None)
        return contextlib.nullcontext(types.SimpleNamespace(headers=h))
    try:
        globals()["oauth_token"] = lambda: "t"
        urllib.request.urlopen, _revived = fake_open, 0.0
        subprocess.run = lambda *a, **k: runs.append(a) or types.SimpleNamespace(returncode=0)
        answers[:] = [401, 200]
        assert fetch_limits()["expired"] is False and len(runs) == 1 and not answers
        answers[:] = [401]
        assert fetch_limits()["expired"] is True and len(runs) == 1, "쉬는 동안은 CLI 를 안 부름"
        _revived = 0.0
        subprocess.run = lambda *a, **k: types.SimpleNamespace(returncode=1)
        answers[:] = [401]
        assert fetch_limits()["expired"] is True and not answers, "CLI 가 실패하면 다시 받지 않음"
    finally:
        urllib.request.urlopen, subprocess.run, globals()["oauth_token"], _revived = real
    print("ok")


if __name__ == "__main__":
    if "--check" in sys.argv:
        check()
    else:
        t = time.perf_counter()
        s = snapshot()
        print(json.dumps(s, indent=1, ensure_ascii=False))
        print("%.2f초" % (time.perf_counter() - t), file=sys.stderr)
