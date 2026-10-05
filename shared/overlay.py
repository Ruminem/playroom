# SPDX-License-Identifier: Apache-2.0
"""놀이방의 맨 위 오버레이들이 같이 쓰는 것: 한 번만 뜨게 하기, 작업 영역, tk 창 클릭 통과, layers 양보.

각 폴더의 스크립트는 sys.path 에 이 폴더를 넣고 import 한다.
"""
import ctypes
import json
import os
import sys
import tempfile
import time
from pathlib import Path

import startup

LAYERS_TRAY = "PlayroomLayersTray"
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
    """PID 파일의 프로세스가 아직 살아 있으면 그 pid (cursor-playground 의 cat.py 와 같은 방식)."""
    try:
        pid = int(pid_file.read_text())
    except (OSError, ValueError):
        return None
    k32 = ctypes.windll.kernel32
    handle = k32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
    if not handle:
        return None
    code = ctypes.c_ulong()
    alive = k32.GetExitCodeProcess(handle, ctypes.byref(code)) and code.value == 259  # STILL_ACTIVE
    k32.CloseHandle(handle)
    return pid if alive else None


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


def already_running(pid_file, tray_class, script, toggle):
    """True 면 부른 쪽은 그냥 끝남. --toggle 은 떠 있는 것을 끄기만 하고, 그냥 실행은 떠 있으면 아무것도 안 함 —
    다만 새로 받은 릴리스 exe 를 실행하면 떠 있는 옛 exe 를 끄고 이어서 뜸(False)."""
    pid = running_pid(pid_file)
    if pid is None:
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


def layers_running():
    """layers 가 떠 있으면 창 순서는 그쪽이 정하므로, 오버레이는 스스로 맨 위로 올리지 않는다.
    둘 다 올리면 2초마다 서로 앞을 뺏고, 캡처 도구 같은 남의 맨 위 창까지 덮는다."""
    return bool(ctypes.windll.user32.FindWindowW(LAYERS_TRAY, None))
