# sysmon

**English** · [한국어](#korean)

CPU and memory use in two small lines on the taskbar, right next to the notification icons. White normally, orange above 70%, red above 90%. On Windows it can add two more lines to their left: disk activity and network speed. Windows and macOS (in the menu bar there), Python standard library only.

## Use

Double-click [sysmon.bat](sysmon.bat) to start or stop it. If its files changed since it started (after a `git pull`, say), the `.bat` swaps in the new code instead of stopping it. Hovering the mouse over it fades it so the taskbar buttons underneath show through. A small bar-chart icon sits in the notification area; hover it for memory in GB. Its menu picks how memory is shown — percent (`MEM 22%`), amount (`MEM 14.2/63.9G`) or both (`MEM 14.2/63.9G 22%`) — and the **theme**, both kept in `%LOCALAPPDATA%\playroom\sysmon.json`. **Show disk and network** (off by default) adds a second column to the left: `DSK 34%`, the busiest disk's active time, coloured like CPU, and `↓1.2M ↑85K`, bytes per second received and sent by the busiest network adapter. It also starts it with Windows (same as [usage-hud](../usage-hud/#hud)) and exits.

- **Default** — the two lines of text above
- **Pixel** — the [usage-hud](../usage-hud/) look: a dark box with a chip and a memory-stick icon, an 8-cell bar per line and pixel-font numbers. Bars are green, orange above 70%, red above 90%. It comes in the same six palettes as usage-hud (classic, Game Boy, neon, amber terminal, deep sea, paper), picked separately. With disk and network on, the box gets a disk and an arrows icon in a second column; the network line has no bar, since there is no full mark to measure it against. Put usage-hud on the taskbar too and the two sit side by side

`python sysmon.py --stop` closes it, `python sysmon.py --check` runs the self-check.

## macOS

The same script runs on a Mac with the system Python 3.9, nothing to install. There is no taskbar, so the reading goes into its own menu bar item instead: one line of text, `CPU 17%  MEM 62%`, in the menu bar's own text colour (orange above 70%, red above 90%), or the pixel box with CPU and memory side by side in one row, as tall as the menu bar (22 pt) so the pixel font is a little larger than the system text (stacked as on Windows, it would be only 5 pt). Click it for the same menu as on Windows; **Start at login** writes a LaunchAgent to `~/Library/LaunchAgents`, and settings live in `~/Library/Application Support/playroom/sysmon.json`.

Double-click [sysmon.command](sysmon.command) in Finder to start or stop it; the Terminal window it opens closes itself. From a terminal:

```bash
python3 sysmon.py --toggle
```

`--toggle` detaches it from the terminal. It keeps updating while its menu is open. On a MacBook: 0.2 s of CPU over 30 s (0.7% of one core), 50 MB of memory.

- CPU is the share of non-idle ticks from `host_statistics` (`HOST_CPU_LOAD_INFO`) a second apart
- Memory is Activity Monitor's *Memory Used*: app memory (anonymous pages minus purgeable) + wired + compressed, out of `hw.memsize`. File cache is left out, otherwise a Mac always looks nearly full. The self-check compares it with `vm_stat`
- Percentages are padded with figure spaces to the width of `100%`, so the icons next to it do not shift as the numbers change
- On a MacBook with a notch, menu bar items that do not fit beside the notch are hidden by macOS. If it does not show up, quit something else in the menu bar or switch to the text theme, which is narrower than the pixel box (about 205 pt against 340 pt with memory shown both ways)

## Cost

It wakes ten times a second to handle messages and measures once a second. Measured on one PC: 0.03 s of CPU over 30 s (0.1% of one core), 34 MB of memory.

## How it works

- CPU is the share of non-idle time between two `GetSystemTimes` calls a second apart; memory is `dwMemoryLoad` from `GlobalMemoryStatusEx`. Both matched the performance counters and WMI when checked
- Disk and network come from the performance counters through `pdh.dll`, added by their English names so they work on any Windows language. Disk is 100 − `\PhysicalDisk(*)\% Idle Time` for the busiest disk (Task Manager's *Active time*). Network is `\Network Interface(*)\Bytes Received/sec` and `Bytes Sent/sec` of the one busiest adapter, not the sum: with a Hyper-V virtual switch the same traffic also shows up on `vEthernet`. Speeds are in 1024-byte units, at most four characters (`8.5K`, `512K`, `1.2M`). The counters are opened only while the column is on. Not on macOS
- It draws onto a click-through, topmost window with per-pixel alpha ([surface.py](../shared/surface.py)) placed over the taskbar. Text is drawn by GDI in white with greyscale anti-aliasing, then the brightness becomes alpha and the line colour is applied, so the edges stay soft on any taskbar colour. The taskbar drawing lives in [taskbar.py](../shared/taskbar.py)
- Every second it re-reads where the notification area (`TrayNotifyWnd`) starts, so it follows when tray icons come and go, and re-asserts topmost because clicking the taskbar brings it to the front — unless [layers](../layers/) is running, which then keeps the order
- When a full-screen app is running (`SHQueryUserNotificationState`: busy, Direct3D full screen or presentation mode) it hides, since the taskbar is gone too
- The pixel theme stamps rectangles straight into the same buffer, with the font, icons and palettes from [pixelfont.py](../shared/pixelfont.py). The buffer is sized for the widest theme and format, but the window only shows the part that is drawn (`Surface.view`), so usage-hud can sit right next to it
- Not handled: an auto-hiding taskbar, a taskbar on the side or top, and monitors other than the primary one

---

## Korean

[English](#sysmon) · **한국어**

작업 표시줄의 알림 아이콘 바로 옆에 CPU·메모리 사용률을 작은 두 줄로 띄움. 평소엔 흰색, 70% 를 넘으면 주황, 90% 를 넘으면 빨강. 윈도우에서는 그 왼쪽에 디스크 활성도와 네트워크 속도 두 줄을 더 띄울 수 있음. 윈도우와 맥(맥은 메뉴 막대)에서 돌고 파이썬 표준 라이브러리만 씀.

### 쓰는 법

[sysmon.bat](sysmon.bat) 을 더블클릭하면 켜지고, 다시 누르면 꺼짐. 켠 뒤로 파일이 바뀌었으면(`git pull` 등) 끄는 대신 새 코드로 갈아 끼움. 마우스를 올리면 흐려져 밑의 작업 표시줄 단추가 비쳐 보임. 알림 영역에 작은 막대그래프 아이콘이 뜸. 마우스를 올리면 메모리를 GB 로 보여 줌. 메뉴에서 메모리를 퍼센트(`MEM 22%`)·용량(`MEM 14.2/63.9G`)·둘 다(`MEM 14.2/63.9G 22%`) 중 어떻게 보일지와 **테마** 를 고르고(둘 다 `%LOCALAPPDATA%\playroom\sysmon.json` 에 남음), 윈도우 시작 시 실행([usage-hud](../usage-hud/#hud-1) 와 같음)을 켜고 끝냄. **디스크·네트워크 보기**(기본은 꺼짐)를 켜면 왼쪽에 칸이 하나 더 섬: `DSK 34%` 는 가장 바쁜 디스크의 활성 시간이고 CPU 와 같은 색 문턱을 씀. `↓1.2M ↑85K` 는 가장 바쁜 네트워크 어댑터가 1초에 받고 보내는 바이트임.

- **기본** — 위의 글자 두 줄
- **픽셀** — [usage-hud](../usage-hud/) 모양. 어두운 상자 안에 칩·메모리 막대 아이콘, 줄마다 8칸 막대, 픽셀 글꼴 숫자가 들어감. 막대는 초록이고 70% 를 넘으면 주황, 90% 를 넘으면 빨강. usage-hud 와 같은 팔레트 여섯(클래식·게임보이·네온·앰버 단말기·심해·종이) 중 하나를 따로 고름. 디스크·네트워크를 켜면 둘째 칸에 디스크·화살표 아이콘이 들어감. 네트워크 줄은 기준 삼을 최대치가 없어 막대 없이 숫자만 씀. usage-hud 도 작업 표시줄에 두면 둘이 나란히 붙음

`python sysmon.py --stop` 으로 끄고, `python sysmon.py --check` 로 자체 점검을 돌림.

### 맥

같은 스크립트가 맥 기본 파이썬 3.9 로 돌고, 깔 것은 없음. 작업 표시줄이 없으므로 메뉴 막대에 제 칸을 하나 두고 거기에 띄움. 글자 테마는 `CPU 17%  MEM 62%` 한 줄이고 메뉴 막대 글자색을 따름(70% 를 넘으면 주황, 90% 를 넘으면 빨강). 픽셀 테마는 CPU 와 메모리를 한 줄로 나란히 둔 상자이고, 메뉴 막대 높이(22pt)를 꽉 채워 픽셀 글자가 시스템 글자보다 살짝 큼(윈도우처럼 위아래로 쌓으면 5pt 밖에 안 됨). 누르면 윈도우와 같은 메뉴가 뜨고, **로그인 시 실행** 은 `~/Library/LaunchAgents` 에 LaunchAgent 를 씀. 설정은 `~/Library/Application Support/playroom/sysmon.json` 에 남음.

Finder 에서 [sysmon.command](sysmon.command) 를 더블클릭하면 켜지고 다시 누르면 꺼짐. 그때 열리는 터미널 창은 저절로 닫힘. 터미널에서는 이렇게 함.

```bash
python3 sysmon.py --toggle
```

`--toggle` 은 터미널과 떼어 띄움. 메뉴를 연 동안에도 숫자가 바뀜. 맥북에서 잰 값: 30초에 CPU 0.2초(한 코어의 0.7%), 메모리 50MB.

- CPU 는 1초 간격으로 읽은 `host_statistics`(`HOST_CPU_LOAD_INFO`) 틱에서 쉬지 않은 틱의 비율임
- 메모리는 활동 모니터의 *사용한 메모리* 와 같은 셈임. 앱 메모리(익명 쪽 − 지울 수 있는 쪽) + 와이어드 + 압축을 `hw.memsize` 로 나눔. 파일 캐시는 뺌 — 넣으면 맥은 늘 거의 꽉 차 보임. 자체 점검이 `vm_stat` 과 견줌
- 퍼센트는 자릿수 너비 빈칸으로 `100%` 너비에 맞춰서, 숫자가 바뀌어도 옆 아이콘이 안 밀림
- 노치가 있는 맥북은 노치 옆에 다 안 들어가는 메뉴 막대 칸을 macOS 가 숨김. 안 보이면 메뉴 막대의 다른 것을 끄거나 픽셀 상자보다 좁은 글자 테마로 바꿈(메모리 '둘 다' 에서 약 205pt 대 340pt)

### 비용

메시지를 처리하려고 1초에 열 번 깨고, 재는 것은 1초에 한 번임. PC 한 대에서 잰 값: 30초에 CPU 0.03초(한 코어의 0.1%), 메모리 34MB.

### 어떻게 도는지

- CPU 는 1초 간격으로 부른 `GetSystemTimes` 두 번 사이에서 쉬지 않은 시간의 비율이고, 메모리는 `GlobalMemoryStatusEx` 의 `dwMemoryLoad` 임. 성능 카운터·WMI 값과 맞는 것을 봤음
- 디스크·네트워크는 `pdh.dll` 로 성능 카운터를 읽음. 영어 이름으로 더해서 윈도우 언어와 상관없이 됨. 디스크는 가장 바쁜 디스크의 100 − `\PhysicalDisk(*)\% Idle Time`(작업 관리자의 *활성 시간*)임. 네트워크는 `\Network Interface(*)\Bytes Received/sec`·`Bytes Sent/sec` 중 가장 바쁜 어댑터 하나의 값이고 다 더하지 않음 — Hyper-V 가상 스위치가 있으면 같은 트래픽이 `vEthernet` 에도 한 번 더 잡힘. 속도는 1024 단위로 네 글자 안(`8.5K`·`512K`·`1.2M`). 카운터는 칸을 켠 동안만 엶. 맥에는 없음
- 작업 표시줄 위에 얹은 클릭 통과·맨 위·픽셀 알파 창([surface.py](../shared/surface.py))에 그림. 글자는 GDI 로 흰색 회색조 안티에일리어싱으로 그린 뒤 밝기를 알파로 바꿔 줄 색을 입힘. 그래서 작업 표시줄 색이 무엇이든 가장자리가 부드러움. 작업 표시줄 그리기는 [taskbar.py](../shared/taskbar.py) 에 있음
- 1초마다 알림 영역(`TrayNotifyWnd`)이 어디서 시작하는지 다시 읽어 트레이 아이콘이 늘거나 줄면 따라감. 작업 표시줄을 누르면 그쪽이 앞으로 오므로 맨 위도 1초마다 다시 잡음. [layers](../layers/) 가 떠 있으면 순서는 그쪽에 맡김
- 전체 화면 앱이 돌면(`SHQueryUserNotificationState` 가 바쁨·Direct3D 전체 화면·발표 모드) 작업 표시줄도 사라지므로 같이 숨음
- 픽셀 테마는 같은 버퍼에 네모를 바로 찍고, 글꼴·아이콘·팔레트는 [pixelfont.py](../shared/pixelfont.py) 의 것을 씀. 버퍼는 가장 넓은 테마·모양에 맞춰 잡지만 창은 그린 부분만 보여서(`Surface.view`) usage-hud 가 바로 옆에 붙을 수 있음
- 안 따지는 것: 자동 숨기기 작업 표시줄, 옆이나 위에 둔 작업 표시줄, 주 모니터가 아닌 모니터
