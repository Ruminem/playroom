# weather

**English** · [한국어](#korean)

Snow, rain, a thunderstorm, cherry blossom petals, autumn leaves or fireflies over every window — a picture-in-picture video, the app you are typing in, all of it. It is only something to look at: clicks and keys go straight through to whatever is underneath. Windows only, Python standard library only.

- **Snow** falls in three layers of depth — small dim flakes far away, large soft ones close up — swaying and drifting with a gusting wind. Near flakes pile up on top of the taskbar into a soft bank that slowly melts; far ones disappear behind it
- **Rain** falls in slanted streaks that fade towards the tail and splashes at the bottom. It falls on a strip of bumpy ground along the floor, and water pools in its dips — rain on a slope runs down into the nearest dip, small bumps go under as a dip fills, and the water level stays flat. Puddles start empty, fill over a few minutes and stop where inflow and drying balance: light rain covers about a fifth of the floor, heavy rain about two thirds. Drops landing on water open a small ripple instead of a splash
- **Storm** is heavier rain with a lightning bolt every few seconds — a jagged channel with side branches that flashes, goes dark, flashes again and fades. The whole screen does not flash; that would get in the way of work
- **Petals** and **leaves** fall in the same three layers as snow but spin and flip as they go; a petal turned edge-on falls faster than one lying flat. They pile up on the taskbar in a patchwork of their colours
- **Fireflies** drift slowly around the lower two thirds of the screen, each glowing up, holding and fading on its own rhythm
- A **cat** can be switched on with any of these, or on its own with **No weather**. A pixel cat walks along the top of the taskbar — on top of the snow or leaf bank if there is one — stops, sits, curls up to sleep with a rising Z, and jumps and runs off when lightning strikes. In rain it trots faster and never sleeps. It walks on the ground, sinks into puddles up to its legs and kicks up water and ripples as it wades through

## Use

Double-click [weather.bat](weather.bat) to start or stop it. A snowflake icon sits in the notification area; its menu picks the kind (or **No weather**), sets the amount (light · normal · heavy), turns the **Cat** on or off, hides it, starts it with Windows and exits. Your choice is remembered in `%LOCALAPPDATA%\playroom\weather.json`, and starting with Windows uses it.

```bash
python weather.py --toggle --kind rain --amount many
```

`python weather.py --stop` closes it, `python weather.py --check` runs the self-check.

## macOS

The same script runs on a Mac with the system Python 3.9, nothing to install. It reaches AppKit through ctypes ([shared/mac](../shared/mac/)), the snowflake sits in the menu bar, and **Start at login** writes a LaunchAgent to `~/Library/LaunchAgents`. Your choice is remembered in `~/Library/Application Support/playroom/weather.json`.

Double-click [weather.command](weather.command) in Finder to start or stop it; the Terminal window it opens closes itself. From a terminal:

```bash
python3 weather.py --toggle
```

`--toggle` detaches it from the terminal, so closing the terminal keeps it running. It floats over full-screen apps too. Snow piles along the very bottom of the screen; when the Dock is showing it settles on top of the Dock. It keeps animating while the menu is open. On a MacBook (1680×924 pt): empty screen with the cat 2.7%, normal snow with the cat 6–7%, heavy rain with the cat 19%.

## Cost

30 frames a second. Measured on one PC (2560×1392 work area), share of one CPU core: snow 7–8% (heavy 10%), rain 8–14% depending on the amount, storm 13% (heavy 19%), petals 9% (heavy 10%), leaves 7–8%, fireflies 7%. An empty screen (no weather, no cat) already costs 6.2%, so most of each figure is clearing and pushing the full-screen buffer. The cat on its own is 6.3% — nearly all of that is the same full-screen cost; with heavy snow it adds about 1 point. Hide it from the menu and it stops drawing. The compositor's own share was not measured separately.

With normal snow the bank settles at about 5px after ten minutes, light at about 2px and heavy at about 10px (16px at most), so it barely covers the bottom of the screen.

## How it works

- [surface.py](../shared/surface.py) is a window with per-pixel alpha: a 32-bit DIB section drawn in premultiplied BGRA and pushed with `UpdateLayeredWindow`. A colour-keyed tkinter window, which this started as, can only be fully clear or fully opaque, so nothing could have a soft edge
- `WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE | WS_EX_TOPMOST` makes it click-through and non-activating, and topmost is re-asserted every two seconds — the same as [usage-hud](../usage-hud/), and likewise left to [layers](../layers/) when that is running
- Flakes and streaks are rendered once at start into small sprites. Flakes come in quarter-pixel offsets so slow ones glide instead of stepping a pixel at a time. Each frame clears the buffer and copies sprite rows in with slice assignment; overlapping sprites overwrite rather than blend, but transparent row ends are trimmed so round corners do not punch holes
- The snow bank is a height per pixel column. A landing flake adds a wide low mound; four times a second, anything steeper than the angle of repose slides down, the surface is smoothed, and it melts in proportion to its height. Petals and leaves use the same bank, drawn from a few mixed-colour columns picked in runs of 3–7 so it looks like a heap rather than stripes
- The rain ground is a sum of three sine waves with random phases. The highest a column can hold water is min(highest ground to its left, highest ground to its right); a run of columns where that is above the ground is one basin, holding just a water volume. The flat water level follows from the volume by sorting the basin's ground heights once. Rain on a slope is routed downhill to the basin it ends in. Letting water flow column by column like the snow bank was the first idea, but thin water on the slopes then takes minutes to reach the dips. Ground is drawn into the strip once; only basins whose level moved get redrawn
- The cat ([pet.py](pet.py)) is drawn as character grids, scaled ×3 and mirrored for walking left. Its sprites are cut into runs at every transparent gap, so the space between its legs does not erase the snow behind it. It is drawn after the bank and before the falling things, so snow falls in front of it. A small state machine picks walk · stand · sit · sleep with random durations and turns around at the screen edges; a new lightning bolt starts a jump
- Petals and leaves are drawn the first time that kind is picked (about 0.2 s): 12 angles × 6 flips (narrower edge-on, darker on the back) per size and colour, so a frame only copies rows like snow
- A lightning bolt is drawn once when it strikes (16–30 ms): brightness is stamped into one byte plane with a max, then coloured and dimmed for each flicker step with `bytes.translate` tables instead of a Python loop per pixel
- The timer resolution is raised to 1ms while it runs; at the default 15.6ms a 30fps request stalls at about 21fps
- The tray icon and the single-instance helpers live in [shared](../shared/)

The size of the work area is read once at start. After changing resolution or moving the taskbar, restart it.

---

## Korean

[English](#weather) · **한국어**

PIP 영상이든 지금 타이핑하는 앱이든 모든 창 위로 눈·비·뇌우·벚꽃잎·낙엽을 내리거나 반딧불이를 띄움. 보이기만 하고, 클릭과 키 입력은 그대로 아래 창으로 감. 윈도우 전용이고 파이썬 표준 라이브러리만 씀.

- **눈**은 원근 세 층으로 내림 — 멀리 있는 것은 작고 흐리고, 가까이 있는 것은 크고 번짐. 돌풍에 흔들리며 흘러가고, 가까운 눈송이는 작업 표시줄 위에 부드러운 눈더미로 쌓였다가 천천히 녹음. 먼 것은 그 뒤로 사라짐
- **비**는 꼬리 쪽이 옅어지는 비스듬한 빗줄기로 내리고 바닥에서 튐. 바닥에 깔린 울퉁불퉁한 땅에 떨어지고, 우묵한 곳에 물이 고임 — 비탈에 떨어진 비는 가까운 우묵한 데로 흘러가고, 차오르면 작은 둔덕은 잠기며 수면은 늘 평평함. 빈 채로 시작해 몇 분에 걸쳐 차오르고 들어오는 양과 마르는 양이 맞는 데서 멈춤. 조금 오면 바닥의 5분의 1쯤, 많이 오면 3분의 2쯤이 물임. 물 위에 떨어진 빗방울은 튀는 대신 작은 물결을 냄
- **뇌우**는 더 굵은 비에 몇 초마다 번개가 침. 곁가지가 붙은 지그재그 줄기가 번쩍–꺼짐–번쩍–사그라듦 순으로 깜빡임. 화면 전체를 번쩍이게 하지는 않음 — 일하는 데 방해가 됨
- **벚꽃**과 **낙엽**은 눈과 같은 세 층으로 내리되 빙글빙글 돌고 뒤집히며 떨어짐. 옆으로 선 잎은 누운 잎보다 빨리 떨어짐. 작업 표시줄 위에 제 색들이 섞인 무더기로 쌓임
- **반딧불이**는 화면 아래쪽 2/3 를 천천히 떠다니며, 마리마다 제 박자로 밝아졌다 머물렀다 사그라듦
- **고양이**는 위의 어느 것과도 같이 켜거나, **날씨 없음** 으로 혼자 켤 수 있음. 픽셀 고양이가 작업 표시줄 위 — 눈이나 잎 더미가 있으면 그 위 — 를 걸어 다니다 서고, 앉고, Z 를 띄우며 웅크려 자고, 번개가 치면 펄쩍 뛰어 달아남. 비가 오면 종종걸음을 치고 안 잠. 땅을 딛고 걸어서 웅덩이에선 다리까지 물에 잠기고, 물 속을 지나면 첨벙거리며 물방울과 물결을 튀김

### 쓰는 법

[weather.bat](weather.bat) 을 더블클릭하면 켜지고 다시 누르면 꺼짐. 알림 영역에 눈송이 아이콘이 뜨고, 그 메뉴에서 종류(또는 **날씨 없음**)를 고르고, 양(적게·보통·많이)을 정하고, **고양이** 를 켜고 끄고, 숨기고, 윈도우 시작 시 실행을 켜고, 끝냄. 고른 것은 `%LOCALAPPDATA%\playroom\weather.json` 에 남고, 윈도우와 같이 켜질 때도 이걸 따름.

```bash
python weather.py --toggle --kind rain --amount many
```

`python weather.py --stop` 으로 끄고, `python weather.py --check` 로 자체 점검을 돌림.

### 맥

같은 스크립트가 맥 기본 파이썬 3.9 로 돌고, 깔 것은 없음. ctypes 로 AppKit 을 부르고([shared/mac](../shared/mac/)), 눈송이 아이콘은 메뉴 막대에 뜨며, **로그인 시 실행** 은 `~/Library/LaunchAgents` 에 LaunchAgent 를 씀. 고른 것은 `~/Library/Application Support/playroom/weather.json` 에 남음.

Finder 에서 [weather.command](weather.command) 를 더블클릭하면 켜지고 다시 누르면 꺼짐. 그때 열리는 터미널 창은 저절로 닫힘. 터미널에서는 이렇게 함.

```bash
python3 weather.py --toggle
```

`--toggle` 은 터미널과 떼어 띄우므로 터미널을 닫아도 안 꺼짐. 전체 화면 앱 위에도 뜸. 눈은 화면 맨 아래에 쌓이고, 독이 보일 때는 독 위에 쌓임. 메뉴를 연 동안에도 계속 그림. 맥북(1680×924 pt)에서 빈 화면+고양이 2.7%, 눈 보통+고양이 6–7%, 비 많이+고양이 19%.

### 비용

1초에 30번 그림. PC 한 대(작업 영역 2560×1392)에서 잰 CPU 한 코어 대비 몫은 눈 7–8%(많이 10%), 비는 양에 따라 8–14%, 뇌우 13%(많이 19%), 벚꽃 9%(많이 10%), 낙엽 7–8%, 반딧불이 7%. 아무것도 안 그리는 빈 화면(날씨 없음, 고양이 끔)이 이미 6.2% 라, 몫의 대부분은 화면 전체 버퍼를 비우고 내보내는 데 듦. 고양이만 띄우면 6.3% 로 거의 다 같은 화면 전체 몫이고, 눈 많이에 얹으면 1포인트쯤 더함. 메뉴에서 숨기면 그리기를 멈춤. 화면 합성기(DWM) 쪽 몫은 따로 못 잼.

눈 보통이면 눈더미가 10분쯤 지나 5px 안팎에서 멈추고, 적게는 2px, 많이는 10px 안팎(최대 16px)이라 화면 아래를 거의 안 가림.

### 어떻게 하나

- [surface.py](../shared/surface.py) 는 픽셀마다 알파가 있는 창임. 32비트 DIB 섹션에 premultiplied BGRA 로 그리고 `UpdateLayeredWindow` 로 내보냄. 처음에 쓴 색 키 tkinter 창은 완전 투명과 완전 불투명뿐이라 가장자리를 부드럽게 할 수 없었음
- `WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE | WS_EX_TOPMOST` 로 클릭 통과·포커스 안 뺏음, 2초마다 다시 맨 위로 올림 — [usage-hud](../usage-hud/) 와 같고, [layers](../layers/) 가 떠 있으면 마찬가지로 그쪽에 맡김
- 눈송이와 빗줄기는 시작할 때 작은 그림으로 한 번 그려 둠. 눈송이는 1/4픽셀씩 어긋난 벌을 둬서 느린 것도 1px 씩 덜컥거리지 않고 미끄러짐. 매 프레임 버퍼를 비우고 그림의 행을 슬라이스 대입으로 붙임. 겹친 그림은 섞지 않고 덮어쓰지만, 행 앞뒤의 투명한 부분을 잘라 둬서 둥근 모서리가 밑의 것을 뚫지 않음
- 눈더미는 픽셀 열마다 높이를 둠. 떨어진 눈송이는 넓고 낮은 둔덕을 보태고, 1초에 네 번 안식각보다 가파른 곳은 흘러내리고, 표면을 매끈하게 펴고, 높이에 비례해 녹음. 꽃잎·낙엽도 같은 더미를 쓰되, 색을 섞은 몸통 몇 벌을 3–7열씩 골라 칠해 줄무늬가 아니라 무더기처럼 보임
- 비 올 때의 땅은 위상을 무작위로 준 사인파 셋의 합임. 열마다 물이 고일 수 있는 높이는 min(왼쪽 최고 땅, 오른쪽 최고 땅)이고, 그 높이가 땅보다 높은 이어진 열들이 그릇 하나로 물 부피 하나만 둠. 평평한 수면 높이는 그릇의 땅 높이를 한 번 정렬해 두고 부피에서 바로 구함. 비탈에 떨어진 비는 내리막을 따라 그 끝 그릇으로 감. 처음엔 눈더미처럼 열마다 물을 흘려 보내려 했는데, 그러면 비탈의 얇은 물이 몇 분씩 걸려야 우묵한 데로 모임. 땅은 띠에 한 번만 그리고, 수면이 움직인 그릇만 다시 그림
- 고양이([pet.py](pet.py))는 글자 판으로 그린 그림을 3배로 키우고, 왼쪽으로 걸을 때는 좌우로 뒤집어 씀. 그림을 투명한 틈마다 끊어 둬서 다리 사이가 뒤의 눈을 지우지 않음. 더미 다음, 내리는 것들 전에 그려서 눈이 고양이 앞으로 내림. 작은 상태 기계가 걷기·서기·앉기·자기를 무작위 길이로 고르고 화면 끝에서 돌아섬. 새 번개가 치면 뛰어오름
- 꽃잎·낙엽 그림은 그 종류를 처음 고를 때 그림(0.2초쯤). 크기·색마다 각도 12 × 뒤집힘 6(옆으로 서면 좁고 뒷면은 어두움)벌이라, 프레임마다 하는 일은 눈처럼 행 복사뿐임
- 번개는 칠 때 한 번 그림(16–30ms). 밝기를 바이트 판 하나에 최댓값으로 찍은 뒤, 깜빡임 단계마다 색 입히기와 어둡게 하기를 픽셀마다 파이썬을 돌리지 않고 `bytes.translate` 표로 함
- 도는 동안 타이머 해상도를 1ms 로 올림. 기본값 15.6ms 에서는 30fps 를 청해도 21fps 쯤에서 멈춤
- 트레이 아이콘과 한 번만 뜨게 하는 코드는 [shared](../shared/) 에 있음

작업 영역 크기는 켤 때 한 번만 읽음. 해상도를 바꾸거나 작업 표시줄을 옮겼으면 다시 켜야 함.
