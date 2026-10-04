# SPDX-License-Identifier: Apache-2.0
"""shared/startup.py 의 맥판. 로그인 시 실행을 ~/Library/LaunchAgents 의 plist 로 넣고 뺀다.

launchd 는 로그인할 때 이 폴더를 읽으므로 지금 바로 띄우지는 않는다(launchctl 을 안 부름).

  python3 startup.py    자체 점검 (시험용 이름으로 실제 폴더에 썼다 지움)
"""
import plistlib
import sys
from pathlib import Path

AGENTS = Path.home() / "Library" / "LaunchAgents"


def label(name):
    return "com.ruminem." + name


def plist_path(name):
    return AGENTS / (label(name) + ".plist")


def command(script):
    return [sys.executable, str(Path(script).resolve())]


def is_on(name, script):
    """plist 가 지금 이 파이썬·스크립트를 가리키면 True. 저장소 폴더를 옮겼으면 False — 다시 켜면 새 경로로 씀."""
    try:
        with open(plist_path(name), "rb") as f:
            return plistlib.load(f).get("ProgramArguments") == command(script)
    except (OSError, plistlib.InvalidFileException):
        return False


def set(name, script, on):
    path = plist_path(name)
    if on:
        AGENTS.mkdir(parents=True, exist_ok=True)
        with open(path, "wb") as f:
            plistlib.dump({"Label": label(name), "ProgramArguments": command(script), "RunAtLoad": True}, f)
    else:
        path.unlink(missing_ok=True)


def toggle(name, script):
    """메뉴용. 못 쓰면 체크가 그대로 남아 실패가 보이므로 삼킴."""
    try:
        set(name, script, not is_on(name, script))
    except OSError:
        pass


def check():
    name, me = "PlayroomStartupSelfCheck", __file__
    try:
        set(name, me, False)
        assert not is_on(name, me), "처음엔 꺼짐"
        toggle(name, me)
        assert is_on(name, me), "켜짐"
        with open(plist_path(name), "rb") as f:
            d = plistlib.load(f)
        assert d["Label"] == label(name) and d["RunAtLoad"] is True, "launchd 가 읽을 키"
        set(name, Path(me).with_name("moved.py"), True)  # 저장소를 옮긴 흉내
        assert not is_on(name, me), "옛 경로면 꺼진 것으로 봄"
        toggle(name, me)
        assert is_on(name, me), "다시 켜면 새 경로"
        toggle(name, me)
        assert not is_on(name, me) and not plist_path(name).exists(), "끄면 파일도 지움"
    finally:
        set(name, me, False)
    print("자체 점검 통과")


if __name__ == "__main__":
    check()
