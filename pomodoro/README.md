# pomodoro

**English** · [한국어](#korean)

A pomodoro timer that lives on the taskbar, just left of [sysmon](../sysmon/). When a focus session ends, a sound plays and pixel confetti bursts up from the taskbar, and the break starts on its own. Windows only, Python standard library only.

## Use

Double-click [pomodoro.bat](pomodoro.bat) to start or stop it. A tomato icon sits in the notification area; its menu starts a focus session, then offers pause / resume, skip and stop. Under **Length** pick 25 + 5 or 50 + 10 minutes, and **Sound** turns the chime off. It can also start with Windows, the same way as [usage-hud](../usage-hud/#hud). Your choices are kept in `%LOCALAPPDATA%\playroom\pomodoro.json`.

- While a session runs, the taskbar shows `FOCUS` (red) or `BREAK` (green) above the time left; paused, both turn grey. Hover the icon for the same as text
- Focus ends → confetti, chime, the break starts. Break ends → confetti and chime once more, then it stops and the text goes away. The next focus session is started from the menu
- A length change applies from the next session; the one counting now keeps its time
- No long break every fourth session in this version

`python pomodoro.py --stop` closes it, `python pomodoro.py --check` runs the self-check.

## Cost

While counting it wakes ten times a second and redraws four times a second. Measured on one PC: 0.03 s of CPU over 20 s of focus, 0.05 s for one 3-second confetti burst, nothing measurable while stopped.

## How it works

- The text uses the same click-through, per-pixel-alpha taskbar drawing as sysmon ([taskbar.py](../shared/taskbar.py)). It sits left of the sysmon window if that is visible, otherwise left of the notification area. sysmon's window is as wide as its longest memory format, so with the percent format there is a little extra space between the two
- The confetti is a separate transparent window above the taskbar: 140 squares thrown up and left with gravity and some air drag, fading out over the last second, at 30 fps for 3 seconds
- Time is counted from `time.monotonic()` deadlines, so a busy PC cannot make it drift. If the PC sleeps through the end of a focus session, the break starts when it wakes
- Hidden while a full-screen app runs, like sysmon. [layers](../layers/) ranks both its windows by default

---

## Korean

[English](#pomodoro) · **한국어**

작업 표시줄에서 [sysmon](../sysmon/) 바로 왼쪽에 사는 뽀모도로 타이머. 집중이 끝나면 소리와 함께 작업 표시줄 위로 픽셀 색종이가 터지고 휴식이 저절로 이어짐. 윈도우 전용이고 파이썬 표준 라이브러리만 씀.

### 쓰는 법

[pomodoro.bat](pomodoro.bat) 을 더블클릭하면 켜지고, 다시 누르면 꺼짐. 알림 영역에 토마토 아이콘이 뜨고, 그 메뉴에서 집중을 시작하면 일시정지·계속, 건너뛰기, 그만이 나옴. **길이** 에서 25분 + 5분 또는 50분 + 10분을 고르고, **소리** 로 알림음을 끔. 윈도우 시작 시 실행도 [usage-hud](../usage-hud/#hud-1) 와 같은 방식으로 켤 수 있음. 고른 것은 `%LOCALAPPDATA%\playroom\pomodoro.json` 에 남음.

- 세는 동안 작업 표시줄에 `FOCUS`(빨강) 또는 `BREAK`(초록)와 그 아래 남은 시간이 뜸. 일시정지하면 둘 다 회색이 됨. 아이콘에 마우스를 올리면 같은 내용을 글로 보여 줌
- 집중 끝 → 색종이·알림음, 휴식 시작. 휴식 끝 → 색종이·알림음 한 번 더, 그리고 멈추며 글자가 사라짐. 다음 집중은 메뉴로 시작함
- 길이를 바꾸면 다음 단계부터 적용되고, 지금 세는 단계는 그대로임
- 네 번째마다 긴 휴식은 이번 판에 없음

`python pomodoro.py --stop` 으로 끄고, `python pomodoro.py --check` 로 자체 점검을 돌림.

### 비용

세는 동안 1초에 열 번 깨고 네 번 다시 그림. PC 한 대에서 잰 값: 집중 20초에 CPU 0.03초, 3초짜리 색종이 한 번에 0.05초, 멈춰 있을 때는 잴 만큼 안 씀.

### 어떻게 도는지

- 글자는 sysmon 과 같은 클릭 통과·픽셀 알파 작업 표시줄 그리기([taskbar.py](../shared/taskbar.py))를 씀. sysmon 창이 보이면 그 왼쪽, 아니면 알림 영역 왼쪽에 붙음. sysmon 창은 가장 긴 메모리 모양 너비라, 퍼센트 모양이면 둘 사이가 조금 벌어짐
- 색종이는 작업 표시줄 위의 따로 된 투명 창임. 네모 140개를 왼쪽 위로 던져 중력과 약간의 공기 저항을 주고, 마지막 1초 동안 옅어짐. 30fps 로 3초
- 시간은 `time.monotonic()` 마감 시각으로 세서 PC 가 바빠도 밀리지 않음. 집중이 끝날 때 PC 가 잠자고 있었으면 깨어난 때부터 휴식을 셈
- sysmon 처럼 전체 화면 앱이 돌면 숨음. [layers](../layers/) 는 기본 순서에 이 창 둘을 넣어 둠
