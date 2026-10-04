# weather

**English** · [한국어](#korean)

Snow, rain, a thunderstorm, hail, fireflies or fireworks over every window — a picture-in-picture video, the app you are typing in, all of it. It is only something to look at: clicks and keys go straight through to whatever is underneath. Windows only, Python standard library only.

- **Snow** falls in three layers of depth — small dim flakes far away, large soft ones close up — swaying and drifting with a gusting wind. Near flakes pile up on top of the taskbar into a soft bank that slowly melts; far ones disappear behind it
- **Rain** falls in three depths of even, soft-ended streaks — faint and thin far away, bold up close. Gusts slowly tilt the rain back and forth, and drops landing up front kick up a little crown and a few droplets
- **Storm** is heavier rain with a lightning bolt every few seconds — a jagged channel with side branches that flashes, goes dark, flashes again and fades. Gusts are stronger, the rain thickens and thins in waves, and the streaks light up while the bolt is brightest. The whole screen does not flash; that would get in the way of work
- **Hail** is fast white ice pellets in two sizes that bounce up to twice off the taskbar before settling into a bank like snow's, which melts four times faster. A pellet landing right next to the animal now and then startles it
- **Fireflies** drift slowly around the lower two thirds of the screen, each glowing up, holding and fading on its own rhythm
- **Fireworks**: rockets with a gold trail climb from the bottom and burst a third to half way up into a ring of 60–110 sparks in red, gold, green, blue, purple or white (sometimes two colours mixed). The sparks slow, droop and twinkle out
- **Animals** — a **cat**, **bird**, **dog**, **rabbit** and **penguin**, as many as you like at once — can be switched on with any of these, or on their own with **No weather**. The pixel cat walks along the top of the taskbar — on top of the snow bank if there is one — stops, sits, curls up to sleep with a rising Z, and jumps and runs off when lightning strikes. In rain it trots faster and never sleeps. The dog does the same and wags its tail while it stands. The sparrow hops, pecks and looks around, and now and then flies to another spot on the screen; lightning or hail sends it to the far side at once. The rabbit hops in short runs, stops to twitch its nose, and when startled turns and bounds away. The penguin waddles slowly and, when snow or hail is falling, sometimes slides on its belly. The animals also react to the weather, with a small mark over their heads: in rain or snow the dog runs around happily (♪); in snow the cat sometimes sits watching it (♥) and the rabbit jumps higher; in rain the rabbit hunkers down (…) and the bird flies less; fireflies flying low get pounced on by the cat, dog and penguin (♪ on landing) and pecked at by the bird (!); a firework bursting nearby makes them stop and turn to look (!). Sliding penguins show ♪ too

## Use

Double-click [weather.bat](weather.bat) to start or stop it. A snowflake icon sits in the notification area. Left-click it for a small settings panel above the taskbar: kind buttons (or **No weather**), an amount slider from 0 to 100% that applies when you let go, a **Smoothness** row (30 · 60 · 120 · 180 fps), an **Animal** row of on/off buttons (cat · bird · dog · rabbit · penguin), boxes for showing it and starting with Windows, and **Exit**. Clicking anywhere else closes it. The right-click menu does the same, with the amount in 10% steps (the old light · normal · heavy are 20 · 50 · 100%). Your choice is remembered in `%LOCALAPPDATA%\playroom\weather.json`, and starting with Windows uses it.

```bash
python weather.py --toggle --kind rain --amount 80
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

60 frames a second by default; **Smoothness** picks 30, 60, 120 or 180 for faster monitors, and the cost grows almost in step with it — at 100% amount snow takes 9 · 16 · 46% of one core at 30 · 60 · 180 fps and rain 13 · 27 · 77%, because every frame clears and pushes the whole screen. With **No weather** and an animal on, only the strip the animal can reach is cleared and pushed (6% instead of 43% at 180 fps; all five animals at once 9–11%), and with no animal either it stops drawing (0% instead of 27%). The figures below were measured at 30 fps on one PC (2560×1392 work area), share of one CPU core: snow 7–8% (heavy 10%), rain 8–14% depending on the amount, storm 13% (heavy 19%), fireflies 7%. Hail and fireworks were measured only at 180 fps, 100%: drawing takes 0.4 and 0.5 ms a frame (rain 1.7, snow 1.2), so the cost is almost all the full-screen clear and push. An empty screen (no weather, no cat) already costs 6.2%, so most of each figure is clearing and pushing the full-screen buffer. The cat on its own is 6.3% — nearly all of that is the same full-screen cost; with heavy snow it adds about 1 point. Hide it from the menu and it stops drawing. The compositor's own share was not measured separately.

With normal snow the bank settles at about 5px after ten minutes, light at about 2px and heavy at about 10px (16px at most), so it barely covers the bottom of the screen.

## How it works

- [surface.py](../shared/surface.py) is a window with per-pixel alpha: a 32-bit DIB section drawn in premultiplied BGRA and pushed with `UpdateLayeredWindow`. A colour-keyed tkinter window, which this started as, can only be fully clear or fully opaque, so nothing could have a soft edge
- `WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE | WS_EX_TOPMOST` makes it click-through and non-activating, and topmost is re-asserted every two seconds — the same as [usage-hud](../usage-hud/), and likewise left to [layers](../layers/) when that is running
- Flakes and streaks are rendered once at start into small sprites. Flakes come in quarter-pixel offsets so slow ones glide instead of stepping a pixel at a time. Each frame clears the buffer and copies sprite rows in with slice assignment; overlapping sprites overwrite rather than blend, but transparent row ends are trimmed so round corners do not punch holes
- The snow bank is a height per pixel column. A landing flake adds a wide low mound; four times a second, anything steeper than the angle of repose slides down, the surface is smoothed, and it melts in proportion to its height.
- The cat ([pet.py](pet.py)) is drawn as character grids, scaled ×3 and mirrored for walking left. Its sprites are cut into runs at every transparent gap, so the space between its legs does not erase the snow behind it. It is drawn after the bank and before the falling things, so snow falls in front of it. A small state machine picks walk · stand · sit · sleep with random durations and turns around at the screen edges; a new lightning bolt starts a jump. The bird, dog, rabbit and penguin have their own grids. Every animal stays within one bottom strip (`pet.BAND`, 124 px, worked out from the tallest sprite plus the highest jump or flight), so **No weather** with any of them is as cheap as with the cat. The bird picks a landing spot inside the screen before it takes off, so it never leaves the screen
- A lightning bolt is drawn once when it strikes (16–30 ms): brightness is stamped into one byte plane with a max, then coloured and dimmed for each flicker step with `bytes.translate` tables instead of a Python loop per pixel
- The timer resolution is raised to 1ms while it runs; at the default 15.6ms a 30fps request stalls at about 21fps
- The tray icon and the single-instance helpers live in [shared](../shared/)

The size of the work area is read once at start. After changing resolution or moving the taskbar, restart it.

---

## Korean

[English](#weather) · **한국어**

PIP 영상이든 지금 타이핑하는 앱이든 모든 창 위로 눈·비·뇌우·우박을 내리거나 반딧불이·불꽃놀이를 띄움. 보이기만 하고, 클릭과 키 입력은 그대로 아래 창으로 감. 윈도우 전용이고 파이썬 표준 라이브러리만 씀.

- **눈**은 원근 세 층으로 내림 — 멀리 있는 것은 작고 흐리고, 가까이 있는 것은 크고 번짐. 돌풍에 흔들리며 흘러가고, 가까운 눈송이는 작업 표시줄 위에 부드러운 눈더미로 쌓였다가 천천히 녹음. 먼 것은 그 뒤로 사라짐
- **비**는 양끝만 부드러운 고른 빗줄기가 세 겹 깊이로 내림 — 멀리는 가늘고 흐리게, 가까이는 굵게. 돌풍에 빗줄기가 천천히 기울었다 섰다 하고, 앞쪽 빗방울은 바닥에 닿을 때 작은 ㅅ자 튐과 물방울을 튀김
- **뇌우**는 더 굵은 비에 몇 초마다 번개가 침. 곁가지가 붙은 지그재그 줄기가 번쩍–꺼짐–번쩍–사그라듦 순으로 깜빡임. 화면 전체를 번쩍이게 하지는 않음 — 일하는 데 방해가 됨. 돌풍이 더 세고, 빗발이 물결처럼 굵어졌다 가늘어지며, 번개가 가장 밝을 때 빗줄기도 번쩍 드러남
- **우박**은 크고 작은 흰 얼음 알이 빠르게 떨어져 작업 표시줄에서 두 번까지 튄 뒤 눈처럼 쌓이고, 더미는 눈보다 4배 빨리 녹음. 동물 바로 옆에 떨어지면 가끔 놀람
- **반딧불이**는 화면 아래쪽 2/3 를 천천히 떠다니며, 마리마다 제 박자로 밝아졌다 머물렀다 사그라듦
- **불꽃놀이**는 금빛 꼬리를 끄는 로켓이 아래에서 올라가 화면 위에서 1/5–1/2 쯤에서 터지며, 빨강·금·초록·파랑·보라·흰색(가끔 두 색 섞임) 불꽃 60–110개가 고리로 퍼짐. 불꽃은 느려지며 처지고 반짝이다 꺼짐
- **동물**(**고양이**·**새**·**강아지**·**토끼**·**펭귄**, 여럿을 같이 켤 수 있음)은 위의 어느 것과도 같이 켜거나, **날씨 없음** 으로 혼자 켤 수 있음. 픽셀 고양이가 작업 표시줄 위 — 쌓인 더미가 있으면 그 위 — 를 걸어 다니다 서고, 앉고, Z 를 띄우며 웅크려 자고, 번개가 치면 펄쩍 뛰어 달아남. 비가 오면 종종걸음을 치고 안 잠. 강아지도 똑같이 하고, 서 있을 땐 꼬리를 흔듦. 참새는 콩콩 뛰고 쪼고 두리번거리다 가끔 화면 안 다른 자리로 날아감. 번개나 우박에는 바로 먼 쪽으로 날아감. 토끼는 몇 번씩 깡충 뛰다 서서 코를 씰룩이고, 놀라면 돌아서 뛰어 달아남. 펭귄은 느리게 뒤뚱뒤뚱 걷고, 눈이나 우박이 오면 가끔 배를 깔고 미끄러짐. 동물들은 날씨에 따라 머리 위에 작은 표시를 띄우며 반응함: 비나 눈이 오면 강아지가 신나서 뛰어다니고(♪), 눈 오는 날엔 고양이가 가끔 앉아서 구경하고(♥) 토끼가 더 높이 뜀. 비가 오면 토끼는 웅크리고(…) 새는 덜 날아다님. 반딧불이가 낮게 날면 고양이·강아지·펭귄이 폴짝 뛰어들고(내려앉으며 ♪) 새는 쪼려 함(!). 불꽃이 가까이 터지면 멈춰 서서 그쪽을 봄(!). 미끄러지는 펭귄도 ♪ 를 띄움

### 쓰는 법

[weather.bat](weather.bat) 을 더블클릭하면 켜지고 다시 누르면 꺼짐. 알림 영역에 눈송이 아이콘이 뜸. 왼쪽 클릭하면 작업 표시줄 위에 작은 설정 창이 떠서 종류 단추(또는 **날씨 없음**), 0–100% 양 막대(손을 떼면 적용됨), **부드러움** 줄(30·60·120·180fps), **동물** 줄(고양이·새·강아지·토끼·펭귄, 하나씩 켜고 끄는 단추), 보이기·윈도우 시작 시 실행 상자와 **끝내기** 가 있음. 다른 데를 누르면 닫힘. 오른쪽 클릭 메뉴로도 같은 걸 하고, 거기서 양은 10% 칸임(예전 적게·보통·많이는 20·50·100%). 고른 것은 `%LOCALAPPDATA%\playroom\weather.json` 에 남고, 윈도우와 같이 켜질 때도 이걸 따름.

```bash
python weather.py --toggle --kind rain --amount 80
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

기본은 1초에 60번 그림. **부드러움** 에서 주사율 높은 모니터용으로 30·60·120·180 을 고르고, 비용은 거의 그 비율로 늘어남 — 양 100% 에서 눈은 30·60·180fps 에 한 코어의 9·16·46%, 비는 13·27·77% 임. 프레임마다 화면 전체를 비우고 내보내기 때문임. **날씨 없음** 에 동물만 켜면 동물이 닿는 맨 아래 띠만 비우고 내보내고(180fps 에서 43% → 6%, 다섯 마리를 다 켜면 9–11%), 동물도 끄면 그리기를 멈춤(27% → 0%). 아래는 30fps 일 때 PC 한 대(작업 영역 2560×1392)에서 잰 CPU 한 코어 대비 몫으로, 눈 7–8%(많이 10%), 비는 양에 따라 8–14%, 뇌우 13%(많이 19%), 반딧불이 7%. 우박·불꽃놀이는 180fps 100% 에서만 쟀고 그리기가 프레임당 0.4·0.5ms(비 1.7, 눈 1.2)라 비용은 거의 다 화면 전체를 비우고 내보내는 몫임. 아무것도 안 그리는 빈 화면(날씨 없음, 고양이 끔)이 이미 6.2% 라, 몫의 대부분은 화면 전체 버퍼를 비우고 내보내는 데 듦. 고양이만 띄우면 6.3% 로 거의 다 같은 화면 전체 몫이고, 눈 많이에 얹으면 1포인트쯤 더함. 메뉴에서 숨기면 그리기를 멈춤. 화면 합성기(DWM) 쪽 몫은 따로 못 잼.

눈 보통이면 눈더미가 10분쯤 지나 5px 안팎에서 멈추고, 적게는 2px, 많이는 10px 안팎(최대 16px)이라 화면 아래를 거의 안 가림.

### 어떻게 하나

- [surface.py](../shared/surface.py) 는 픽셀마다 알파가 있는 창임. 32비트 DIB 섹션에 premultiplied BGRA 로 그리고 `UpdateLayeredWindow` 로 내보냄. 처음에 쓴 색 키 tkinter 창은 완전 투명과 완전 불투명뿐이라 가장자리를 부드럽게 할 수 없었음
- `WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE | WS_EX_TOPMOST` 로 클릭 통과·포커스 안 뺏음, 2초마다 다시 맨 위로 올림 — [usage-hud](../usage-hud/) 와 같고, [layers](../layers/) 가 떠 있으면 마찬가지로 그쪽에 맡김
- 눈송이와 빗줄기는 시작할 때 작은 그림으로 한 번 그려 둠. 눈송이는 1/4픽셀씩 어긋난 벌을 둬서 느린 것도 1px 씩 덜컥거리지 않고 미끄러짐. 매 프레임 버퍼를 비우고 그림의 행을 슬라이스 대입으로 붙임. 겹친 그림은 섞지 않고 덮어쓰지만, 행 앞뒤의 투명한 부분을 잘라 둬서 둥근 모서리가 밑의 것을 뚫지 않음
- 눈더미는 픽셀 열마다 높이를 둠. 떨어진 눈송이는 넓고 낮은 둔덕을 보태고, 1초에 네 번 안식각보다 가파른 곳은 흘러내리고, 표면을 매끈하게 펴고, 높이에 비례해 녹음
- 고양이([pet.py](pet.py))는 글자 판으로 그린 그림을 3배로 키우고, 왼쪽으로 걸을 때는 좌우로 뒤집어 씀. 그림을 투명한 틈마다 끊어 둬서 다리 사이가 뒤의 눈을 지우지 않음. 더미 다음, 내리는 것들 전에 그려서 눈이 고양이 앞으로 내림. 작은 상태 기계가 걷기·서기·앉기·자기를 무작위 길이로 고르고 화면 끝에서 돌아섬. 새 번개가 치면 뛰어오름. 새·강아지·토끼·펭귄은 판을 따로 씀. 동물은 모두 한 바닥 띠(`pet.BAND`, 124px — 가장 큰 그림에 가장 높은 점프나 비행을 더해 셈) 안에 머물러서, **날씨 없음** 에 어느 동물을 켜도 고양이만큼 쌈. 새는 날아오르기 전에 화면 안에서 앉을 자리를 골라서 화면 밖으로 안 나감
- 번개는 칠 때 한 번 그림(16–30ms). 밝기를 바이트 판 하나에 최댓값으로 찍은 뒤, 깜빡임 단계마다 색 입히기와 어둡게 하기를 픽셀마다 파이썬을 돌리지 않고 `bytes.translate` 표로 함
- 도는 동안 타이머 해상도를 1ms 로 올림. 기본값 15.6ms 에서는 30fps 를 청해도 21fps 쯤에서 멈춤
- 트레이 아이콘과 한 번만 뜨게 하는 코드는 [shared](../shared/) 에 있음

작업 영역 크기는 켤 때 한 번만 읽음. 해상도를 바꾸거나 작업 표시줄을 옮겼으면 다시 켜야 함.
