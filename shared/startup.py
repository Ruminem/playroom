# SPDX-License-Identifier: Apache-2.0
"""Windows 시작 시 실행: 현재 사용자의 Run 키에 'pythonw <스크립트>' 를 넣고 뺀다.

설정 앱 '시작 앱' 에서 끄면 Run 값은 남고 StartupApproved 에 첫 바이트가 홀수인 값이 생긴다
(이 PC 실측 2026-10-04: 켬 2 · 끔 3). 체크 표시는 그쪽 스위치도 따른다.

  python startup.py    자체 점검 (시험용 이름으로 실제 레지스트리를 켰다 끄고 지움)
"""
import sys
import winreg
from pathlib import Path

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
APPROVED_KEY = r"Software\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved\Run"


def beside(script, here=None):
    """릴리스 exe 로 돌 때 스크립트 이름을 딴 옆의 exe (hud.py → hud.exe). 드라이브에서 받으면 hud-0.1.2.exe 처럼
    버전이 붙어 있으므로, hud.exe 가 없으면 hud-<버전>.exe 중 버전이 가장 높은 것."""
    here = Path(here or Path(sys.executable).parent)
    stem = Path(script).stem
    exact = here / f"{stem}.exe"
    if exact.exists():
        return exact

    def version(p):
        try:
            return tuple(int(x) for x in p.stem[len(stem) + 1:].split("."))
        except ValueError:
            return None
    found = [(v, p) for p in here.glob(f"{stem}-*.exe") if (v := version(p))]
    return max(found)[1] if found else exact


def command(script):
    """시작할 때 부를 명령. 콘솔 창이 안 뜨게 pythonw, 나머지는 각자 저장된 설정을 따름.
    릴리스 exe 로 돌면 옆의 도구 exe(beside) — 런처가 남의 것을 켜도 맞게."""
    exe = Path(sys.executable)
    if getattr(sys, "frozen", False):
        return '"%s"' % beside(script)
    w = exe.with_name("pythonw.exe")
    return '"%s" "%s"' % (w if w.exists() else exe, Path(script).resolve())


def is_on(name, script):
    """Run 값이 지금 이 스크립트를 가리키고, 설정 앱에서 꺼 두지도 않았으면 True.
    저장소 폴더를 옮겨 경로가 달라졌으면 False — 다시 켜면 새 경로로 고쳐 씀."""
    hkcu = winreg.HKEY_CURRENT_USER
    try:
        with winreg.OpenKey(hkcu, RUN_KEY) as k:
            if winreg.QueryValueEx(k, name)[0] != command(script):
                return False
    except OSError:
        return False
    try:
        with winreg.OpenKey(hkcu, APPROVED_KEY) as k:
            data = winreg.QueryValueEx(k, name)[0]
    except OSError:
        return True  # 설정 앱에서 손댄 적 없음
    return not (data and data[0] & 1)


def set(name, script, on):
    hkcu = winreg.HKEY_CURRENT_USER
    with winreg.CreateKey(hkcu, RUN_KEY) as k:
        if on:
            winreg.SetValueEx(k, name, 0, winreg.REG_SZ, command(script))
        else:
            try:
                winreg.DeleteValue(k, name)
            except FileNotFoundError:
                pass
    # 설정 앱에서 꺼 둔 표식이 남아 있으면 켜도 안 뜨므로 같이 지운다. 끌 때도 지워 흔적을 안 남김
    try:
        with winreg.OpenKey(hkcu, APPROVED_KEY, 0, winreg.KEY_SET_VALUE) as k:
            winreg.DeleteValue(k, name)
    except OSError:
        pass


def toggle(name, script):
    """트레이 메뉴용. 레지스트리를 못 쓰면 체크가 그대로 남아 실패가 보이므로 삼킴."""
    try:
        set(name, script, not is_on(name, script))
    except OSError:
        pass


def check():
    name, me = "PlayroomStartupSelfCheck", __file__
    hkcu = winreg.HKEY_CURRENT_USER
    try:
        set(name, me, False)
        assert not is_on(name, me), "처음엔 꺼짐"
        toggle(name, me)
        assert is_on(name, me), "켜짐"
        with winreg.CreateKey(hkcu, APPROVED_KEY) as k:  # 설정 앱에서 끈 흉내
            winreg.SetValueEx(k, name, 0, winreg.REG_BINARY, bytes([3]) + bytes(11))
        assert not is_on(name, me), "설정 앱에서 끄면 체크도 풀림"
        toggle(name, me)
        assert is_on(name, me), "다시 켜면 끈 표식이 지워짐"
        with winreg.CreateKey(hkcu, RUN_KEY) as k:  # 저장소를 옮긴 흉내
            winreg.SetValueEx(k, name, 0, winreg.REG_SZ, command(Path(me).with_name("moved.py")))
        assert not is_on(name, me), "옛 경로면 꺼진 것으로 봄"
        toggle(name, me)
        assert is_on(name, me), "다시 켜면 새 경로"
        toggle(name, me)
        assert not is_on(name, me), "끔"
    finally:
        set(name, me, False)
    print("자체 점검 통과")


if __name__ == "__main__":
    check()
