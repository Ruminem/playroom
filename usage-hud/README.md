# usage-hud

**English** · [한국어](#korean)

Claude Code subscription limits drawn as a retro game HUD. Python standard library only. The HUD is Windows only; on macOS there is a menu bar item, and the page and `usage.py` run there too.

- **HP** (heart) — what is left of the 7-day limit
- **ST** (bolt) — what is left of the 5-hour limit
- **Coin** — what today's sessions on this PC would have cost at API list prices. On a subscription nothing is billed; it is a ruler for which day was expensive
- **Cat** — runs while a Claude Code session on this PC is working and curls up asleep when none is. When a turn finishes, the HUD's border flashes for three seconds, so you can look away while Claude works

Each bar shows the time left until it resets, and blinks below 10%.

## HUD

Double-click [hud.bat](hud.bat) to show or hide it. It sits in the bottom-left corner above the taskbar, on top of every window, even a picture-in-picture video that is topmost too, but clicks pass straight through it and it never takes focus.

Because the HUD itself cannot be clicked, a heart icon sits in the notification area. Its menu shows or hides the HUD, moves it to another corner or onto the **taskbar**, changes its size (2–5×) or **theme**, starts it with Windows, opens the page, shows a short help, saves a taskbar diagnostic and exits. The corner, size and theme you pick are remembered in `%LOCALAPPDATA%\playroom\usage-hud.json`. Hovering the icon shows the numbers as text.

There are six themes — only the colours change: classic, Game Boy (four greens), neon, amber terminal, deep sea and paper (a light one). The tray icon picks up a new theme the next time the HUD starts, and the page always stays classic

On the taskbar it turns into a flat two-line panel — HP and ST on the left, the coin and today's cost on the right, then the cat — just left of [sysmon](../sysmon/) (or of the notification icons when sysmon is off). Its size follows the taskbar height there, so the size menu applies only in the corners. It follows when sysmon moves or changes width, hides with a full-screen app, and may cover the end of a long row of taskbar buttons. It does not yet step around other programs that also sit on the taskbar, so it can land on top of them. **Taskbar diagnostic** in the menu writes what is on the taskbar — each taskbar and the windows inside it, and other windows lying over it, with class, title, position and program name — to `%TEMP%\playroom-taskbar.txt` and opens it in Notepad. It is there to find out how such programs sit before teaching the HUD to avoid them; window titles are in it, so look it over before sharing

**Start with Windows** adds `pythonw hud.py` under `HKCU\Software\Microsoft\Windows\CurrentVersion\Run`, the same per-user place as other startup apps, so it also shows up in Settings → Apps → Startup. The tick reflects that switch too, and clears if the folder was moved (tick it again to point at the new path). The code is [shared/startup.py](../shared/startup.py), which sysmon, weather and layers use too. `hud.bat` again or `python hud.py --stop` also closes it.

```bash
python hud.py --toggle --corner tr --scale 4
```

## Page

```bash
python page.py
```

Opens `http://127.0.0.1:8765/` with the same bars and a bar chart of the last seven days. It listens on 127.0.0.1 only. Light by default; the button switches to dark.

## macOS menu bar

```bash
mac/build.sh && mac/UsageBar
```

The HUD is Windows only, so on a Mac the same numbers sit in the menu bar instead: `♥12% ⚡95%` — the 7-day limit, then the 5-hour one. A number turns red below 10%, and `LOGIN` means the token has expired. The menu shows the time left until each reset and today's cost, and can refresh now, open the page, start at login or quit.

[mac/UsageBar.swift](mac/UsageBar.swift) is AppKit only and builds with `swiftc` from Xcode or the Command Line Tools in about two seconds. It does not compute anything itself — every five minutes it runs `/usr/bin/python3 usage.py` and reads the JSON, so prices and header checks live in one place. **Start at login** writes `~/Library/LaunchAgents/com.ruminem.playroom.usage-bar.plist`; like the Windows switch, it clears if the folder was moved. `mac/UsageBar --check` runs the self-check.

## Where the numbers come from

- **Limits**: a one-token Haiku request with the OAuth token the Claude Code CLI saved in `~/.claude/.credentials.json` (on macOS, in the Keychain under `Claude Code-credentials`), reading the `anthropic-ratelimit-unified-*` response headers. Sent at most once every five minutes. These headers are undocumented, so a window whose value looks wrong is left blank rather than drawn wrong
- **LOGIN**: the token has expired and could not be refreshed. The token lasts eight hours and the desktop app keeps its own login without refreshing it, so on a 401 [usage.py](usage.py) — behind both the HUD and the Mac menu bar — runs the CLI once in the background (a one-word Haiku `claude -p` with hooks off and no session saved, about 10 seconds) and asks again. It tries this at most once every 30 minutes, kept in a stamp file in the temp folder because the menu bar starts a fresh `usage.py` each time. Besides the PATH it looks in `~/.local/bin`, `/opt/homebrew/bin` and `/usr/local/bin`, since start-at-login on a Mac runs with a bare PATH. If that fails (logged out, `claude` not found), opening `claude` in a terminal once fixes it
- **Coin**: `usage` of every assistant line in `~/.claude/projects/**/*.jsonl`, counted once per request and priced per model. Sessions run in the cloud are not on this PC and are not counted
- **Cat**: every two seconds the HUD reads the end of each session record in `~/.claude/projects/*/*.jsonl` changed in the last ten minutes. A prompt, a tool result or a tool call last means working; Claude's final reply last means the turn is done and the border flashes. A turn you stopped with Esc, or a local command like `/model`, does not flash. Subagent records are skipped. Two gaps: while Claude waits for you to allow a tool the record looks the same as a tool running, so the cat keeps running; and a tool that runs for more than ten minutes without a new line looks asleep — that one does not flash either

`python usage.py --check` runs the self-check.

## How it works

- A borderless tkinter window, kept on top by re-asserting topmost every two seconds, or left to [layers](../layers/) when that is running
- `WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE` makes it click-through, hidden from the taskbar and non-activating — the same trick as [cat-follower](https://github.com/Ruminem/cursor-playground/tree/main/cat-follower)
- [pixelfont.py](../shared/pixelfont.py) holds a 3×5 pixel font, 7×7 icons and the colour palettes that the HUD, the page and sysmon's pixel theme draw from
- [shared/tray.py](../shared/tray.py) calls `Shell_NotifyIconW` through ctypes, with a hidden window and message loop on its own thread. The tray icon is the heart drawn into a multi-size `.ico` at start. pystray was left out because it is LGPL

---

## Korean

[English](#usage-hud) · **한국어**

Claude Code 구독 한도를 레트로 게임 HUD 로 그림. 파이썬 표준 라이브러리만 씀. HUD 는 윈도우 전용이고, 맥에는 메뉴 막대 항목이 있으며 페이지와 `usage.py` 도 맥에서 돎.

- **HP**(하트) — 7일 한도의 남은 양
- **ST**(번개) — 5시간 한도의 남은 양
- **동전** — 이 PC 에서 오늘 돈 세션을 API 정가로 친 값. 구독이면 실제로 나가는 돈은 없고, 어느 날이 비쌌는지 재는 자임
- **고양이** — 이 PC 의 Claude Code 세션이 일하는 동안 달리고, 일하는 세션이 없으면 웅크려 잠. 한 차례가 끝나면 HUD 테두리가 3초 깜빡여서, Claude 가 일하는 동안 딴 데를 보고 있어도 됨

막대마다 재설정까지 남은 시간이 붙고, 10% 아래로 내려가면 깜빡임.

### HUD

[hud.bat](hud.bat) 을 더블클릭하면 켜지고 다시 누르면 꺼짐. 작업 표시줄 위 왼쪽 아래 구석에 모든 창보다 위에 뜨지만(같이 맨 위에 뜨는 PIP 영상보다도 위), 클릭은 그대로 아래로 통과하고 포커스도 안 뺏음.

HUD 자체는 클릭이 안 되므로 알림 영역에 하트 아이콘이 뜸. 그 메뉴에서 HUD 보이기·숨기기, 다른 구석이나 **작업 표시줄** 로 옮기기, 크기(2–5배)나 **테마** 바꾸기, 윈도우 시작 시 실행, 페이지 열기, 짧은 도움말, 작업 표시줄 진단, 끝내기를 함. 고른 위치·크기·테마는 `%LOCALAPPDATA%\playroom\usage-hud.json` 에 남음. 아이콘에 마우스를 올리면 숫자가 글로 보임.

테마는 여섯이고 색만 바뀜: 클래식, 게임보이(초록 네 가지), 네온, 앰버 단말기, 심해, 종이(밝은 바탕). 트레이 아이콘은 다음에 켤 때 새 테마 색이 되고, 페이지는 늘 클래식임

작업 표시줄에서는 두 줄짜리 납작한 패널이 됨 — 왼쪽에 HP·ST, 오른쪽에 동전과 오늘 정가, 그 옆에 고양이 — [sysmon](../sysmon/) 바로 왼쪽(sysmon 이 꺼져 있으면 알림 아이콘 왼쪽)에 붙음. 크기는 작업 표시줄 높이에 맞춰 정해져서 크기 메뉴는 구석에서만 먹음. sysmon 이 옮기거나 폭이 바뀌면 따라가고, 전체 화면 앱이 돌면 숨고, 작업 표시줄 단추가 길게 늘어서 있으면 그 끝을 덮을 수 있음. 작업 표시줄에 같이 뜨는 다른 프로그램은 아직 피하지 않아서 그 위에 겹칠 수 있음. 메뉴의 **작업 표시줄 진단** 은 작업 표시줄 위에 무엇이 있는지 — 작업 표시줄마다 그 안의 창, 그 위에 얹힌 다른 창을 클래스·제목·자리·프로그램 이름과 함께 — `%TEMP%\playroom-taskbar.txt` 에 적고 메모장으로 염. 그런 프로그램이 어떻게 떠 있는지 보고 피하게 만들려고 둔 것임. 창 제목이 들어 있으니 남에게 보내기 전에 한 번 훑어볼 것

**Windows 시작 시 실행** 은 `HKCU\Software\Microsoft\Windows\CurrentVersion\Run` 에 `pythonw hud.py` 를 넣음. 다른 시작 프로그램과 같은 사용자별 자리라 설정 → 앱 → 시작 프로그램에도 뜸. 체크 표시는 그쪽 스위치도 따르고, 폴더를 옮겨 경로가 달라지면 풀림(다시 체크하면 새 경로로 고쳐 씀). 코드는 [shared/startup.py](../shared/startup.py) 이고 sysmon·weather·layers 도 같이 씀. `hud.bat` 을 다시 누르거나 `python hud.py --stop` 으로도 끔.

```bash
python hud.py --toggle --corner tr --scale 4
```

### 페이지

```bash
python page.py
```

`http://127.0.0.1:8765/` 를 열어 같은 막대와 7일치 일별 막대그래프를 보여 줌. 127.0.0.1 에만 열림. 기본은 밝은 화면이고 단추로 어둡게 바꿈.

### 맥 메뉴 막대

```bash
mac/build.sh && mac/UsageBar
```

HUD 는 윈도우 전용이라 맥에서는 같은 값을 메뉴 막대에 띄움: `♥12% ⚡95%` — 앞이 7일 한도, 뒤가 5시간 한도. 10% 아래면 숫자가 빨개지고, `LOGIN` 은 토큰이 만료된 것임. 메뉴에서 재설정까지 남은 시간과 오늘 정가를 보고, 지금 새로 받기·페이지 열기·로그인 시 실행·끝내기를 함.

[mac/UsageBar.swift](mac/UsageBar.swift) 는 AppKit 만 쓰고 Xcode 나 Command Line Tools 의 `swiftc` 로 2초쯤에 묶임. 값을 스스로 계산하지 않음 — 5분마다 `/usr/bin/python3 usage.py` 를 돌려 JSON 을 읽으므로 단가와 헤더 검증은 한 곳에만 있음. **로그인 시 실행** 은 `~/Library/LaunchAgents/com.ruminem.playroom.usage-bar.plist` 를 씀. 윈도우 쪽처럼 폴더를 옮기면 체크가 풀림. `mac/UsageBar --check` 가 자체 점검임.

### 값이 오는 곳

- **한도**: Claude Code CLI 가 `~/.claude/.credentials.json`(맥은 Keychain 의 `Claude Code-credentials`)에 둔 OAuth 토큰으로 Haiku 1토큰 요청을 보내 응답 헤더 `anthropic-ratelimit-unified-*` 에서 읽음. 5분에 한 번만 보냄. 문서에 없는 헤더라 값이 이상한 창은 틀리게 그리지 않고 비워 둠
- **LOGIN**: 토큰이 만료됐고 새로 고치지도 못한 것. 토큰은 8시간짜리이고 데스크톱 앱은 로그인을 따로 들고 그 자리를 안 고침. 그래서 401 이 오면 HUD 와 맥 메뉴 막대가 같이 쓰는 [usage.py](usage.py) 가 CLI 를 백그라운드로 한 번 불러(훅을 끄고 세션 기록 없이 Haiku 로 한 낱말 `claude -p`, 10초쯤) 고치게 한 뒤 다시 받음. 30분에 한 번만 해 보고, 그 시각은 임시 폴더의 표식 파일에 남김 — 메뉴 막대는 `usage.py` 를 매번 새로 띄우기 때문임. 맥의 로그인 시 실행은 PATH 가 비어 있다시피 해서 PATH 말고도 `~/.local/bin`·`/opt/homebrew/bin`·`/usr/local/bin` 에서 찾음. 그래도 안 되면(로그아웃됐거나 `claude` 를 못 찾음) 터미널에서 `claude` 를 한 번 열면 풀림
- **동전**: `~/.claude/projects/**/*.jsonl` 의 assistant 줄 `usage` 를 요청마다 한 번씩 세어 모델별 단가를 곱함. 클라우드에서 돈 세션은 이 PC 에 없어 안 셈
- **고양이**: HUD 가 2초마다 `~/.claude/projects/*/*.jsonl` 중 최근 10분 안에 바뀐 세션 기록의 끝부분을 읽음. 마지막 줄이 프롬프트·도구 결과·도구 호출이면 일하는 중이고, Claude 의 마지막 답이면 그 차례가 끝난 것이라 테두리가 깜빡임. Esc 로 끊은 차례나 `/model` 같은 로컬 명령은 안 깜빡임. 서브에이전트 기록은 안 봄. 빈틈 둘 — Claude 가 도구 허락을 기다리는 동안은 기록이 도구가 도는 것과 같아 고양이가 계속 달림. 새 줄 없이 10분 넘게 도는 도구는 잠든 것으로 보이고, 이때도 안 깜빡임

`python usage.py --check` 가 자체 점검을 돌림.

### 어떻게 하나

- 테두리 없는 tkinter 창을 2초마다 다시 맨 위로 올림. [layers](../layers/) 가 떠 있으면 그쪽에 맡김
- `WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE` 로 클릭 통과, 작업 표시줄 숨김, 포커스 안 뺏음 — [cat-follower](https://github.com/Ruminem/cursor-playground/tree/main/cat-follower) 와 같은 방식
- [pixelfont.py](../shared/pixelfont.py) 에 3×5 픽셀 글꼴·7×7 아이콘·색 팔레트가 있고 HUD·페이지·sysmon 픽셀 테마가 같이 씀
- [shared/tray.py](../shared/tray.py) 가 ctypes 로 `Shell_NotifyIconW` 를 부르고, 제 스레드에서 숨은 창과 메시지 루프를 돌림. 트레이 아이콘은 시작할 때 하트를 크기 여러 벌짜리 `.ico` 로 그려 씀. pystray 는 LGPL 이라 안 씀
