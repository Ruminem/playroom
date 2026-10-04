# launcher

**English** · [한국어](#korean)

One window to manage the playroom tools — [usage-hud](../usage-hud/), [weather](../weather/), [sysmon](../sysmon/) and [layers](../layers/). Windows only.

## Use

Double-click [launcher.bat](launcher.bat). Each tool gets one row:

- a green dot while it is running, and a **Run** / **Stop** button
- **Always on top** — off lets other windows cover it. The tool is restarted to apply it, and layers stops raising it. Not offered for layers, which has no window of its own to keep on top
- **Start with Windows** — the same switch as in each tool's own menu
- **Install** puts a shortcut in the Start menu under `Playroom`, so the tool can be found from Windows search; clicking it starts or stops the tool like its `.bat`. **Uninstall** asks first, then stops the tool, turns off start with Windows, and deletes the shortcut and the tool's settings file in `%LOCALAPPDATA%\playroom`. Files in the repository are left alone

The window refreshes once a second, so a tool started or stopped from its own tray icon shows up here too.

## How it works

[launcher.py](launcher.py) keeps a small table of each tool's script, PID file, tray window class and start-with-Windows name, and calls the helpers the tools already share ([shared/overlay.py](../shared/overlay.py), [shared/startup.py](../shared/startup.py)). The always-on-top choice is a `below` list in `%LOCALAPPDATA%\playroom\launcher.json`; each tool reads it once when it starts. `python launcher.py --check` imports every tool and fails if the table no longer matches it, then creates and removes a shortcut in a temporary folder.

---

## Korean

[English](#launcher) · **한국어**

놀이방 도구 — [usage-hud](../usage-hud/), [weather](../weather/), [sysmon](../sysmon/), [layers](../layers/) — 를 한 창에서 관리함. 윈도우 전용.

### 쓰는 법

[launcher.bat](launcher.bat) 을 더블클릭함. 도구마다 한 줄씩 있음:

- 떠 있으면 초록 점, **실행** / **중단** 단추
- **항상 위** — 끄면 다른 창이 그 위를 덮을 수 있음. 바꾸면 그 도구를 다시 띄워 적용하고, layers 도 그 도구를 올리지 않음. layers 는 맨 위에 둘 자기 창이 없어서 이 칸이 없음
- **Windows 시작 시 실행** — 도구 자기 메뉴의 것과 같은 스위치
- **설치** 는 시작 메뉴 `Playroom` 폴더에 바로가기를 만들어 윈도우 검색으로 찾을 수 있게 함. 누르면 `.bat` 처럼 켜고 끔. **제거** 는 먼저 묻고, 도구를 끄고, 시작 시 실행을 풀고, 바로가기와 `%LOCALAPPDATA%\playroom` 의 그 도구 설정 파일을 지움. 저장소의 파일은 안 건드림

창은 1초마다 새로 읽어서, 도구 트레이 아이콘에서 켜고 끈 것도 여기 보임.

### 어떻게 하나

[launcher.py](launcher.py) 는 도구마다 스크립트·PID 파일·트레이 창 클래스·시작 시 실행 이름을 적은 작은 표를 두고, 도구들이 이미 같이 쓰는 도우미([shared/overlay.py](../shared/overlay.py), [shared/startup.py](../shared/startup.py))를 부름. 항상 위 선택은 `%LOCALAPPDATA%\playroom\launcher.json` 의 `below` 목록이고, 도구는 뜰 때 한 번 읽음. `python launcher.py --check` 는 도구를 모두 import 해서 표가 어긋나면 실패하고, 임시 폴더에 바로가기를 만들었다 지워 봄.
