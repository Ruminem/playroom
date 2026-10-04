# weather

**English** · [한국어](#korean)

Snow or rain falling over every window — a picture-in-picture video, the app you are typing in, all of it. It is only something to look at: clicks and keys go straight through to whatever is underneath. Windows only, Python standard library only.

- **Snow** falls in three layers of depth — small dim flakes far away, large soft ones close up — swaying and drifting with a gusting wind. Near flakes pile up on top of the taskbar into a soft bank that slowly melts; far ones disappear behind it
- **Rain** falls in slanted streaks that fade towards the tail and splashes at the bottom

## Use

Double-click [weather.bat](weather.bat) to start or stop it. A snowflake icon sits in the notification area; its menu switches between snow and rain, sets the amount (light · normal · heavy), hides it and exits. Your choice is remembered in `%LOCALAPPDATA%\playroom\weather.json`.

```bash
python weather.py --toggle --kind rain --amount many
```

`python weather.py --stop` closes it, `python weather.py --check` runs the self-check.

## Cost

30 frames a second. Measured on one PC (2560×1392 work area), share of one CPU core: snow 7–8% (heavy 10%), rain 8–14% depending on the amount. Hide it from the menu and it stops drawing. The compositor's own share was not measured separately.

With normal snow the bank settles at about 10px after eight minutes, heavy at about 20px (28px at most).

## How it works

- [surface.py](../shared/surface.py) is a window with per-pixel alpha: a 32-bit DIB section drawn in premultiplied BGRA and pushed with `UpdateLayeredWindow`. A colour-keyed tkinter window, which this started as, can only be fully clear or fully opaque, so nothing could have a soft edge
- `WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE | WS_EX_TOPMOST` makes it click-through and non-activating, and topmost is re-asserted every two seconds — the same as [usage-hud](../usage-hud/), and likewise left to [layers](../layers/) when that is running
- Flakes and streaks are rendered once at start into small sprites. Flakes come in quarter-pixel offsets so slow ones glide instead of stepping a pixel at a time. Each frame clears the buffer and copies sprite rows in with slice assignment; overlapping sprites overwrite rather than blend, but transparent row ends are trimmed so round corners do not punch holes
- The snow bank is a height per pixel column. A landing flake adds a wide low mound; four times a second, anything steeper than the angle of repose slides down, the surface is smoothed, and it melts in proportion to its height
- The timer resolution is raised to 1ms while it runs; at the default 15.6ms a 30fps request stalls at about 21fps
- The tray icon and the single-instance helpers live in [shared](../shared/)

The size of the work area is read once at start. After changing resolution or moving the taskbar, restart it.

---

## Korean

[English](#weather) · **한국어**

PIP 영상이든 지금 타이핑하는 앱이든 모든 창 위로 눈이나 비를 내림. 보이기만 하고, 클릭과 키 입력은 그대로 아래 창으로 감. 윈도우 전용이고 파이썬 표준 라이브러리만 씀.

- **눈**은 원근 세 층으로 내림 — 멀리 있는 것은 작고 흐리고, 가까이 있는 것은 크고 번짐. 돌풍에 흔들리며 흘러가고, 가까운 눈송이는 작업 표시줄 위에 부드러운 눈더미로 쌓였다가 천천히 녹음. 먼 것은 그 뒤로 사라짐
- **비**는 꼬리 쪽이 옅어지는 비스듬한 빗줄기로 내리고 바닥에서 튐

### 쓰는 법

[weather.bat](weather.bat) 을 더블클릭하면 켜지고 다시 누르면 꺼짐. 알림 영역에 눈송이 아이콘이 뜨고, 그 메뉴에서 눈과 비를 바꾸고, 양(적게·보통·많이)을 정하고, 숨기고, 끝냄. 고른 것은 `%LOCALAPPDATA%\playroom\weather.json` 에 남음.

```bash
python weather.py --toggle --kind rain --amount many
```

`python weather.py --stop` 으로 끄고, `python weather.py --check` 로 자체 점검을 돌림.

### 비용

1초에 30번 그림. PC 한 대(작업 영역 2560×1392)에서 잰 CPU 한 코어 대비 몫은 눈 7–8%(많이 10%), 비는 양에 따라 8–14%. 메뉴에서 숨기면 그리기를 멈춤. 화면 합성기(DWM) 쪽 몫은 따로 못 잼.

눈 보통이면 눈더미가 8분쯤 지나 10px 안팎에서 멈추고, 많이는 20px 안팎(최대 28px).

### 어떻게 하나

- [surface.py](../shared/surface.py) 는 픽셀마다 알파가 있는 창임. 32비트 DIB 섹션에 premultiplied BGRA 로 그리고 `UpdateLayeredWindow` 로 내보냄. 처음에 쓴 색 키 tkinter 창은 완전 투명과 완전 불투명뿐이라 가장자리를 부드럽게 할 수 없었음
- `WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE | WS_EX_TOPMOST` 로 클릭 통과·포커스 안 뺏음, 2초마다 다시 맨 위로 올림 — [usage-hud](../usage-hud/) 와 같고, [layers](../layers/) 가 떠 있으면 마찬가지로 그쪽에 맡김
- 눈송이와 빗줄기는 시작할 때 작은 그림으로 한 번 그려 둠. 눈송이는 1/4픽셀씩 어긋난 벌을 둬서 느린 것도 1px 씩 덜컥거리지 않고 미끄러짐. 매 프레임 버퍼를 비우고 그림의 행을 슬라이스 대입으로 붙임. 겹친 그림은 섞지 않고 덮어쓰지만, 행 앞뒤의 투명한 부분을 잘라 둬서 둥근 모서리가 밑의 것을 뚫지 않음
- 눈더미는 픽셀 열마다 높이를 둠. 떨어진 눈송이는 넓고 낮은 둔덕을 보태고, 1초에 네 번 안식각보다 가파른 곳은 흘러내리고, 표면을 매끈하게 펴고, 높이에 비례해 녹음
- 도는 동안 타이머 해상도를 1ms 로 올림. 기본값 15.6ms 에서는 30fps 를 청해도 21fps 쯤에서 멈춤
- 트레이 아이콘과 한 번만 뜨게 하는 코드는 [shared](../shared/) 에 있음

작업 영역 크기는 켤 때 한 번만 읽음. 해상도를 바꾸거나 작업 표시줄을 옮겼으면 다시 켜야 함.
