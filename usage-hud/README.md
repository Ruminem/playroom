# usage-hud

**English** · [한국어](#korean)

Claude Code subscription limits drawn as a retro game HUD. Windows only, Python standard library only.

- **HP** (heart) — what is left of the 7-day limit
- **ST** (bolt) — what is left of the 5-hour limit
- **Coin** — what today's sessions on this PC would have cost at API list prices. On a subscription nothing is billed; it is a ruler for which day was expensive

Each bar shows the time left until it resets, and blinks below 10%.

## HUD

Double-click [hud.bat](hud.bat) to show or hide it. It sits in the bottom-left corner above the taskbar, on top of every window (not yet checked against a picture-in-picture video, which is topmost too), but clicks pass straight through it and it never takes focus.

Because the HUD itself cannot be clicked, a heart icon sits in the notification area. Its menu shows or hides the HUD, moves it to another corner, changes its size (2–5×), opens the page, shows a short help and exits. The corner and size you pick are remembered in `%LOCALAPPDATA%\playroom\usage-hud.json`. Hovering the icon shows the numbers as text. `hud.bat` again or `python hud.py --stop` also closes it.

```bash
python hud.py --toggle --corner tr --scale 4
```

## Page

```bash
python page.py
```

Opens `http://127.0.0.1:8765/` with the same bars and a bar chart of the last seven days. It listens on 127.0.0.1 only. Light by default; the button switches to dark.

## Where the numbers come from

- **Limits**: a one-token Haiku request with the OAuth token the Claude Code CLI saved in `~/.claude/.credentials.json`, reading the `anthropic-ratelimit-unified-*` response headers. Sent at most once every five minutes. These headers are undocumented, so a window whose value looks wrong is left blank rather than drawn wrong
- **LOGIN**: the token has expired. The desktop app keeps its own login and does not refresh that file, so on days you only use the app it goes stale. Opening `claude` in a terminal once refreshes it
- **Coin**: `usage` of every assistant line in `~/.claude/projects/**/*.jsonl`, counted once per request and priced per model. Sessions run in the cloud are not on this PC and are not counted

`python usage.py --check` runs the self-check.

## How it works

- A borderless tkinter window, kept on top by re-asserting topmost every two seconds
- `WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE` makes it click-through, hidden from the taskbar and non-activating — the same trick as [cat-follower](https://github.com/Ruminem/cursor-playground/tree/main/cat-follower)
- [font.py](font.py) holds a 3×5 pixel font and 7×7 icons that both the HUD and the page draw from
- [tray.py](tray.py) calls `Shell_NotifyIconW` through ctypes, with a hidden window and message loop on its own thread. The tray icon is the heart drawn into a multi-size `.ico` at start. pystray was left out because it is LGPL

---

## Korean

[English](#usage-hud) · **한국어**

Claude Code 구독 한도를 레트로 게임 HUD 로 그림. 윈도우 전용이고 파이썬 표준 라이브러리만 씀.

- **HP**(하트) — 7일 한도의 남은 양
- **ST**(번개) — 5시간 한도의 남은 양
- **동전** — 이 PC 에서 오늘 돈 세션을 API 정가로 친 값. 구독이면 실제로 나가는 돈은 없고, 어느 날이 비쌌는지 재는 자임

막대마다 재설정까지 남은 시간이 붙고, 10% 아래로 내려가면 깜빡임.

### HUD

[hud.bat](hud.bat) 을 더블클릭하면 켜지고 다시 누르면 꺼짐. 작업 표시줄 위 왼쪽 아래 구석에 모든 창보다 위에 뜨지만(같이 맨 위에 뜨는 PIP 영상과는 아직 안 견줘 봄), 클릭은 그대로 아래로 통과하고 포커스도 안 뺏음.

HUD 자체는 클릭이 안 되므로 알림 영역에 하트 아이콘이 뜸. 그 메뉴에서 HUD 보이기·숨기기, 다른 구석으로 옮기기, 크기(2–5배) 바꾸기, 페이지 열기, 짧은 도움말, 끝내기를 함. 고른 위치와 크기는 `%LOCALAPPDATA%\playroom\usage-hud.json` 에 남음. 아이콘에 마우스를 올리면 숫자가 글로 보임. `hud.bat` 을 다시 누르거나 `python hud.py --stop` 으로도 끔.

```bash
python hud.py --toggle --corner tr --scale 4
```

### 페이지

```bash
python page.py
```

`http://127.0.0.1:8765/` 를 열어 같은 막대와 7일치 일별 막대그래프를 보여 줌. 127.0.0.1 에만 열림. 기본은 밝은 화면이고 단추로 어둡게 바꿈.

### 값이 오는 곳

- **한도**: Claude Code CLI 가 `~/.claude/.credentials.json` 에 둔 OAuth 토큰으로 Haiku 1토큰 요청을 보내 응답 헤더 `anthropic-ratelimit-unified-*` 에서 읽음. 5분에 한 번만 보냄. 문서에 없는 헤더라 값이 이상한 창은 틀리게 그리지 않고 비워 둠
- **LOGIN**: 토큰이 만료된 것. 데스크톱 앱은 로그인을 따로 들고 그 파일을 안 고쳐서, 앱만 쓴 날은 낡음. 터미널에서 `claude` 를 한 번 열면 새로 고쳐짐
- **동전**: `~/.claude/projects/**/*.jsonl` 의 assistant 줄 `usage` 를 요청마다 한 번씩 세어 모델별 단가를 곱함. 클라우드에서 돈 세션은 이 PC 에 없어 안 셈

`python usage.py --check` 가 자체 점검을 돌림.

### 어떻게 하나

- 테두리 없는 tkinter 창을 2초마다 다시 맨 위로 올림
- `WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE` 로 클릭 통과, 작업 표시줄 숨김, 포커스 안 뺏음 — [cat-follower](https://github.com/Ruminem/cursor-playground/tree/main/cat-follower) 와 같은 방식
- [font.py](font.py) 에 3×5 픽셀 글꼴과 7×7 아이콘이 있고 HUD 와 페이지가 같이 씀
- [tray.py](tray.py) 가 ctypes 로 `Shell_NotifyIconW` 를 부르고, 제 스레드에서 숨은 창과 메시지 루프를 돌림. 트레이 아이콘은 시작할 때 하트를 크기 여러 벌짜리 `.ico` 로 그려 씀. pystray 는 LGPL 이라 안 씀
