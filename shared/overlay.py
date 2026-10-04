# SPDX-License-Identifier: Apache-2.0
"""놀이방의 맨 위 오버레이들이 같이 쓰는 것: 한 번만 뜨게 하기, 작업 영역, tk 창 클릭 통과, layers 양보.

각 폴더의 스크립트는 sys.path 에 이 폴더를 넣고 import 한다.
"""
import ctypes
import json
import os
import tempfile
import time
from pathlib import Path

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
