# weather

**English** · [한국어](#korean)

Pixel snow or rain falling over every window — a picture-in-picture video, the app you are typing in, all of it. It is only something to look at: clicks and keys go straight through to whatever is underneath. Windows only, Python standard library only.

- **Snow** drifts down, sways a little, and piles up on top of the taskbar, then slowly melts
- **Rain** falls in slanted streaks and splashes at the bottom

## Use

Double-click [weather.bat](weather.bat) to start or stop it. A snowflake icon sits in the notification area; its menu switches between snow and rain, sets the amount (light · normal · heavy), hides it and exits. Your choice is remembered in `%LOCALAPPDATA%\playroom\weather.json`.

```bash
python weather.py --toggle --kind rain --amount many
```

`python weather.py --stop` closes it, `python weather.py --check` runs the self-check.

## Cost

It redraws at about 13 frames a second. Measured on one PC (2560×1392 work area): about 10–18% of one CPU core for normal snow or rain, 17–22% for heavy. The numbers swing from run to run; the amount matters less than you would think, because the canvas redraws one box covering every flake that moved. Hide it from the menu and it stops drawing.

## How it works

- A borderless tkinter window over the whole work area of the primary monitor. Its background colour is keyed out with `-transparentcolor`, so only the flakes are drawn
- `WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE` makes it click-through and non-activating, and topmost is re-asserted every two seconds — the same as [usage-hud](../usage-hud/)
- Movement is scaled by elapsed time, so a slow frame does not slow the snow down
- Each landing flake rolls to a lower neighbour column if there is one, which keeps the pile smooth
- The tray icon and the single-instance helpers live in [shared](../shared/)

The size of the work area is read once at start. After changing resolution or moving the taskbar, restart it.

---

## Korean

[English](#weather) · **한국어**

PIP 영상이든 지금 타이핑하는 앱이든 모든 창 위로 픽셀 눈이나 비를 내림. 보이기만 하고, 클릭과 키 입력은 그대로 아래 창으로 감. 윈도우 전용이고 파이썬 표준 라이브러리만 씀.

- **눈**은 살랑거리며 내려와 작업 표시줄 위에 쌓였다가 천천히 녹음
- **비**는 비스듬한 빗줄기로 내리고 바닥에서 튐

### 쓰는 법

[weather.bat](weather.bat) 을 더블클릭하면 켜지고 다시 누르면 꺼짐. 알림 영역에 눈송이 아이콘이 뜨고, 그 메뉴에서 눈과 비를 바꾸고, 양(적게·보통·많이)을 정하고, 숨기고, 끝냄. 고른 것은 `%LOCALAPPDATA%\playroom\weather.json` 에 남음.

```bash
python weather.py --toggle --kind rain --amount many
```

`python weather.py --stop` 으로 끄고, `python weather.py --check` 로 자체 점검을 돌림.

### 비용

1초에 13번쯤 다시 그림. PC 한 대(작업 영역 2560×1392)에서 잰 값은 눈이나 비 보통이 CPU 한 코어의 10–18% 쯤, 많이는 17–22%. 돌릴 때마다 꽤 흔들림. 캔버스가 움직인 눈송이를 다 덮는 상자 하나를 통째로 다시 그려서, 양은 생각보다 덜 영향을 줌. 메뉴에서 숨기면 그리기를 멈춤.

### 어떻게 하나

- 주 모니터 작업 영역 전체를 덮는 테두리 없는 tkinter 창. 배경색을 `-transparentcolor` 로 뚫어 눈송이만 보임
- `WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE` 로 클릭 통과·포커스 안 뺏음, 2초마다 다시 맨 위로 올림 — [usage-hud](../usage-hud/) 와 같음
- 움직임은 흐른 시간에 비례시켜서 프레임이 늦어도 눈이 느려지지 않음
- 바닥에 닿은 눈송이는 옆 칸이 더 낮으면 그쪽으로 굴러가서 쌓인 눈이 매끈해짐
- 트레이 아이콘과 한 번만 뜨게 하는 코드는 [shared](../shared/) 에 있음

작업 영역 크기는 켤 때 한 번만 읽음. 해상도를 바꾸거나 작업 표시줄을 옮겼으면 다시 켜야 함.
