# layers

**English** · [한국어](#korean)

Decides which always-on-top window goes in front. The overlays in this playroom ([usage-hud](../usage-hud/), [sysmon](../sysmon/), [weather](../weather/)) each push themselves to the top every second or two, so without this they take turns jumping in front of each other — and in front of the snipping tool's overlay too. Windows only, Python standard library only.

## Use

Double-click [layers.bat](layers.bat) to start or stop it. A stacked-squares icon sits in the notification area; **Arrange…** opens a window with two lists:

- **Order** — windows higher in the list stay in front. Move with Up / Down, drop with Remove. ● means the window is open right now
- **Open windows** — everything visible that is not in the order yet (★ = already always-on-top). Double-click or press Add to put it at the bottom of the order

The tray menu can also start it with Windows, the same way as [usage-hud](../usage-hud/#hud).

The default order is usage-hud › sysmon › weather. Changes apply at once and are kept in `%LOCALAPPDATA%\playroom\layers.json`. A window is recognised by its program, class and title, so a picture-in-picture video added once stays ranked the next time one opens.

`python layers.py --stop` closes it, `python layers.py --check` runs the self-check.

## Cost

Twice a second it walks the window list. Measured on one PC: 0.03 s of CPU over 30 s, 41 MB of memory.

## How it works

- While it is running, the overlays stop re-asserting topmost themselves (`overlay.layers_running()` looks for its tray window) and this is the only thing that orders them
- Every half second it fixes only the relative order of the listed windows: a window that is above the one ranked over it is moved to just below that one. Nothing is ever lifted, so windows not in the list — the snipping tool, Task Manager — are never buried
- The taskbar is treated as the last entry, because clicking it brings it to the front and would hide sysmon
- A normal window you add is made always-on-top; remove it or exit and it goes back
- Windows of a program running as administrator cannot be reordered from here and are skipped

---

## Korean

[English](#layers) · **한국어**

맨 위에 뜨는 창들 중 무엇이 앞에 올지 정함. 이 놀이방의 오버레이들([usage-hud](../usage-hud/), [sysmon](../sysmon/), [weather](../weather/))은 1–2초마다 스스로 맨 위로 올라가서, 이게 없으면 서로 번갈아 앞으로 튀어나오고 캡처 도구 화면까지 덮음. 윈도우 전용이고 파이썬 표준 라이브러리만 씀.

### 쓰는 법

[layers.bat](layers.bat) 을 더블클릭하면 켜지고, 다시 누르면 꺼짐. 알림 영역에 사각형이 겹친 아이콘이 뜨고, **순서 정하기…** 를 누르면 목록 둘이 있는 창이 열림.

- **순서** — 목록에서 위에 있을수록 앞에 뜸. 위로·아래로로 옮기고 빼기로 뺌. ● 는 지금 떠 있는 창
- **지금 열린 창** — 보이는 창 중 아직 순서에 없는 것(★ 는 원래 맨 위). 두 번 누르거나 추가를 누르면 순서 맨 아래에 들어감

트레이 메뉴에서 윈도우 시작 시 실행도 켤 수 있음. [usage-hud](../usage-hud/#hud-1) 와 같은 방식임.

기본 순서는 usage-hud › sysmon › weather 임. 바꾸면 바로 적용되고 `%LOCALAPPDATA%\playroom\layers.json` 에 남음. 창은 프로그램·클래스·제목으로 알아보므로, 한 번 넣은 PIP 영상은 다음에 뜨는 PIP 에도 그대로 적용됨.

`python layers.py --stop` 으로 끄고, `python layers.py --check` 로 자체 점검을 돌림.

### 비용

1초에 두 번 창 목록을 훑음. PC 한 대에서 잰 값: 30초에 CPU 0.03초, 메모리 41MB.

### 어떻게 도는지

- 이게 떠 있는 동안 오버레이들은 스스로 맨 위로 올리지 않음(`overlay.layers_running()` 이 트레이 창을 찾아 봄). 순서를 정하는 것은 이것 하나뿐임
- 0.5초마다 목록에 든 창끼리의 상대 순서만 맞춤. 바로 윗 순위 창보다 위에 있는 창을 그 창 바로 밑으로 내림. 끌어올리는 일은 없어서 목록 밖 창(캡처 도구·작업 관리자)은 묻히지 않음
- 작업 표시줄은 목록 맨 아래 칸으로 다룸. 누르면 앞으로 와서 sysmon 을 가리기 때문임
- 직접 넣은 일반 창은 맨 위로 고정되고, 빼거나 끝내면 풀림
- 관리자 권한으로 도는 프로그램의 창은 여기서 순서를 못 바꿔 건너뜀
