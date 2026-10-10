# SPDX-License-Identifier: Apache-2.0
"""놀이방의 맨 위 오버레이들이 같이 쓰는 것: 한 번만 뜨게 하기, 작업 영역, tk 창 클릭 통과, layers 양보.

각 폴더의 스크립트는 sys.path 에 이 폴더를 넣고 import 한다.
"""
import ctypes
import hashlib
import json
import os
import sys
import tempfile
import time
from pathlib import Path

import startup

LAYERS_TRAY = "PlayroomLayersTray"
# 작업 표시줄 패널(HUD · sysmon)에 커서가 올라오면 이만큼(255 중)으로 흐려져 밑의 단추가 보임. 클릭은 원래 통과됨.
# ponytail: 눈으로 고른 값이 아니라 어림. 너무 안 보이거나 너무 진하면 이 숫자만 바꾸면 됨
HOVER_ALPHA = 48
LAUNCHER_FILE = Path(os.environ.get("LOCALAPPDATA", tempfile.gettempdir())) / "playroom" / "launcher.json"


def below():
    """런처에서 '항상 위' 를 끈 도구 이름들 (weather · sysmon · usage-hud)."""
    try:
        names = json.loads(LAUNCHER_FILE.read_text(encoding="utf-8")).get("below", [])
    except (OSError, ValueError, AttributeError):
        return set()
    return {n for n in names if isinstance(n, str)} if isinstance(names, list) else set()


def on_top(name):
    """도구는 뜰 때 한 번 읽는다. 런처는 값을 바꾸면 그 도구를 다시 띄운다."""
    return name not in below()


def running_pid(pid_file):
    """PID 파일의 프로세스가 아직 살아 있으면 그 pid (cursor-playground 의 cat.py 와 같은 방식).
    재부팅 뒤 남은 파일의 pid 를 다른 프로세스가 다시 받았으면 None — 그 프로세스는 파일을 적은 뒤에 시작했으므로
    가려짐. 안 가리면 그냥 실행은 떠 있는 줄 알고 안 뜨고, 토글·끄기는 남의 프로세스를 죽임(2026-10-10 HUD·layers)."""
    try:
        pid = int(pid_file.read_text())
        written = pid_file.stat().st_mtime
    except (OSError, ValueError):
        return None
    k32 = ctypes.windll.kernel32
    handle = k32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
    if not handle:
        return None
    code, times = ctypes.c_ulong(), (ctypes.c_ulonglong * 4)()  # 시작 · 끝 · 커널 · 사용자 (FILETIME)
    alive = k32.GetExitCodeProcess(handle, ctypes.byref(code)) and code.value == 259  # STILL_ACTIVE
    got = k32.GetProcessTimes(handle, *(ctypes.byref(times, 8 * i) for i in range(4)))
    k32.CloseHandle(handle)
    started = times[0] / 1e7 - 11644473600  # 1601 년부터 100ns → 유닉스 초
    # 1초 여유는 파일 시각이 거칠게 찍히는 몫. 도구는 뜨고 나서 파일을 적으므로 제 것이면 늘 started < written
    return pid if alive and (not got or started <= written + 1) else None


def stop(pid_file, tray_class):
    """트레이 창에 닫으라고 보내고 기다린다. 그냥 죽이면 트레이에 유령 아이콘이 남는다."""
    pid = running_pid(pid_file)
    if pid is None:
        return False
    hwnd = ctypes.windll.user32.FindWindowW(tray_class, None)
    if hwnd:
        ctypes.windll.user32.PostMessageW(hwnd, 0x0010, 0, 0)  # WM_CLOSE
        for _ in range(30):
            if running_pid(pid_file) is None:
                return True
            time.sleep(0.1)
    os.kill(pid, 9)  # 3초 안에 안 끝나면 강제로
    pid_file.unlink(missing_ok=True)
    return True


def exe_of(pid):
    """그 프로세스의 실행 파일 전체 경로. 못 열면 None."""
    k32 = ctypes.windll.kernel32
    handle = k32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
    if not handle:
        return None
    buf = ctypes.create_unicode_buffer(32768)
    size = ctypes.c_ulong(len(buf))
    ok = k32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size))
    k32.CloseHandle(handle)
    return buf.value if ok else None


def replaces(running, me, script):
    """새로 띄운 릴리스 exe(me)가 떠 있는 쪽(running 경로)을 갈아 끼우는지: 같은 도구의 exe 인데 다른 파일이면.
    소스(pythonw)로 뜬 것은 안 건드리고, PID 가 남의 프로세스로 재사용됐으면 그걸 죽이지 않게 이름도 봄."""
    if not running or not startup.release_exe(running, script):
        return False
    return os.path.normcase(os.path.abspath(running)) != os.path.normcase(os.path.abspath(me))


def fingerprint(script):
    """그 도구 폴더와 shared/ 의 .py 내용을 묶은 해시. 수정 시각은 안 씀 — zip 을 풀거나 복사하면 옛 시각이 남고,
    브랜치를 오가면 내용은 같은데 시각만 바뀜. 릴리스 exe 는 소스가 없으니 'exe'."""
    if getattr(sys, "frozen", False):
        return "exe"
    h = hashlib.sha1()
    for folder in (Path(script).resolve().parent, Path(__file__).resolve().parent):
        for f in sorted(folder.glob("*.py")):
            try:
                h.update(f.name.encode() + b"\0" + f.read_bytes() + b"\0")
            except OSError:
                pass  # 못 읽은 파일은 빠진 채로 셈 — 다음에 읽히면 달라져 한 번 더 갈아 끼울 뿐
    return h.hexdigest()


def claim(pid_file, script):
    """뜰 때 부름: PID 파일과 옆의 .src 에 '지금 pid 와 코드 해시' 를 적음. PID 파일에 덧붙이지 않는 건 옛 런처가
    그 파일을 숫자로만 읽기 때문."""
    pid_file.write_text(str(os.getpid()))
    try:
        pid_file.with_suffix(".src").write_text("%d %s" % (os.getpid(), fingerprint(script)))
    except OSError:
        pass  # 못 적으면 다음 .bat 때 옛 코드로 보고 갈아 끼울 뿐


def stale(pid_file, pid, script):
    """소스로 띄울 때, 떠 있는 pid 가 지금 파일과 다른 코드로 돌고 있으면 True. 적힌 게 없거나(이 기능 전에 뜬 것)
    다른 pid 것이어도 True. 릴리스 exe 로 띄울 때는 아래 replaces 가 따로 봄."""
    if getattr(sys, "frozen", False):
        return False
    try:
        old_pid, old = pid_file.with_suffix(".src").read_text().split()
    except (OSError, ValueError):
        return True
    return old_pid != str(pid) or old != fingerprint(script)


def already_running(pid_file, tray_class, script, toggle):
    """True 면 부른 쪽은 그냥 끝남. --toggle 은 떠 있는 것을 끄기만 하고, 그냥 실행은 떠 있으면 아무것도 안 함 —
    다만 떠 있는 것이 옛 코드면(소스가 바뀌었거나 새로 받은 릴리스 exe 를 실행) 옛것을 끄고 이어서 뜸(False)."""
    pid = running_pid(pid_file)
    if pid is None:
        return False
    if stale(pid_file, pid, script):
        stop(pid_file, tray_class)
        return False
    if toggle:
        stop(pid_file, tray_class)
        return True
    if getattr(sys, "frozen", False) and replaces(exe_of(pid), sys.executable, script):
        stop(pid_file, tray_class)
        return False
    return True


def work_area():
    """작업 표시줄을 뺀 주 모니터 영역 (left, top, right, bottom)."""
    rect = (ctypes.c_long * 4)()
    ctypes.windll.user32.SystemParametersInfoW(0x30, 0, rect, 0)  # SPI_GETWORKAREA
    return tuple(rect)


def click_through(root):
    """tk 창을 클릭 통과·작업 표시줄에 안 뜸·포커스 안 뺏음으로. 다시 보일 때마다 다시 부른다."""
    user32 = ctypes.windll.user32
    hwnd = int(root.wm_frame(), 16)
    flags = 0x80000 | 0x20 | 0x80 | 0x8000000  # LAYERED | TRANSPARENT | TOOLWINDOW | NOACTIVATE
    user32.SetWindowLongW(hwnd, -20, user32.GetWindowLongW(hwnd, -20) | flags)
    # 겹친 창은 알파를 한 번 정해 줘야 그려진다. 색 키(-transparentcolor) 창에 부르면 색 키가 지워진다
    user32.SetLayeredWindowAttributes(hwnd, 0, 255, 2)  # LWA_ALPHA, 불투명


def fade(root, on):
    """tk 창판 Surface.fade: on 이면 HOVER_ALPHA 로 흐리게. click_through 가 다시 불리면 불투명으로 돌아감."""
    hwnd = int(root.wm_frame(), 16)
    ctypes.windll.user32.SetLayeredWindowAttributes(hwnd, 0, HOVER_ALPHA if on else 255, 2)  # LWA_ALPHA


def layers_running():
    """layers 가 떠 있으면 창 순서는 그쪽이 정하므로, 오버레이는 스스로 맨 위로 올리지 않는다.
    둘 다 올리면 2초마다 서로 앞을 뺏고, 캡처 도구 같은 남의 맨 위 창까지 덮는다."""
    return bool(ctypes.windll.user32.FindWindowW(LAYERS_TRAY, None))
