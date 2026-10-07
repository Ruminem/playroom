# SPDX-License-Identifier: Apache-2.0
"""shared/overlay.py 의 맥판: 한 번만 뜨게 하기와 작업 영역."""
import os
import signal
import subprocess
import time

from cocoa import main_screen


def running_pid(pid_file):
    """PID 파일의 프로세스가 아직 살아 있고 파이썬이면 그 pid. 재부팅 뒤 남은 파일의 pid 가
    다른 프로그램에 다시 쓰였을 수 있어서, 그걸 끄지 않게 이름까지 본다."""
    try:
        pid = int(pid_file.read_text())
        os.kill(pid, 0)  # 신호 0 은 보내지 않고 살아 있는지만 봄
        name = subprocess.run(["ps", "-o", "comm=", "-p", str(pid)], capture_output=True, text=True).stdout
    except (OSError, ValueError, subprocess.SubprocessError):
        return None
    return pid if "python" in name.lower() else None


def stop(pid_file, tray_class=None):
    """SIGTERM 으로 끝냄. 맥은 프로세스가 죽으면 메뉴 막대 아이콘도 같이 사라져 윈도우처럼 유령이 안 남는다."""
    pid = running_pid(pid_file)
    if pid is None:
        return False
    os.kill(pid, signal.SIGTERM)
    for _ in range(30):
        if running_pid(pid_file) is None:
            break
        time.sleep(0.1)
    else:
        os.kill(pid, signal.SIGKILL)
    pid_file.unlink(missing_ok=True)
    return True


def claim(pid_file, script):
    """윈도우판은 코드 해시도 적어 .bat 이 옛 코드를 갈아 끼움. 맥 .command 는 그 판정을 안 거쳐 PID 만."""
    pid_file.write_text(str(os.getpid()))


def work_area():
    """메뉴 막대만 뺀 주 화면 영역 (left, top, right, bottom). 윈도우판처럼 왼쪽 위가 원점, 단위는 pt.
    독은 빼지 않는다 — 전체 화면에선 독이 숨어서, 빼면 눈더미가 독 높이만큼 허공에 뜬다. 독이 보이면
    오버레이가 독보다 위 수준이라 그 위에 쌓인다."""
    frame, vis = main_screen()
    top = int(frame.s.h - vis.o.y - vis.s.h)
    return 0, top, int(frame.s.w), int(frame.s.h)
