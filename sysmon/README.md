# sysmon

**English** · [한국어](#korean)

CPU and memory use in two small lines on the taskbar, right next to the notification icons. White normally, orange above 70%, red above 90%. Windows only, Python standard library only.

## Use

Double-click [sysmon.bat](sysmon.bat) to start or stop it. A small bar-chart icon sits in the notification area; hover it for memory in GB, and use its menu to exit.

`python sysmon.py --stop` closes it, `python sysmon.py --check` runs the self-check.

## Cost

It wakes ten times a second to handle messages and measures once a second. Measured on one PC: 0.03 s of CPU over 30 s (0.1% of one core), 34 MB of memory.

## How it works

- CPU is the share of non-idle time between two `GetSystemTimes` calls a second apart; memory is `dwMemoryLoad` from `GlobalMemoryStatusEx`. Both matched the performance counters and WMI when checked
- It draws onto a click-through, topmost window with per-pixel alpha ([surface.py](../shared/surface.py)) placed over the taskbar. Text is drawn by GDI in white with greyscale anti-aliasing, then the brightness becomes alpha and the line colour is applied, so the edges stay soft on any taskbar colour
- Every second it re-reads where the notification area (`TrayNotifyWnd`) starts, so it follows when tray icons come and go, and re-asserts topmost because clicking the taskbar brings it to the front
- When a full-screen app is running (`SHQueryUserNotificationState`: busy, Direct3D full screen or presentation mode) it hides, since the taskbar is gone too
- Not handled: an auto-hiding taskbar, a taskbar on the side or top, and monitors other than the primary one

---

## Korean

[English](#sysmon) · **한국어**

작업 표시줄의 알림 아이콘 바로 옆에 CPU·메모리 사용률을 작은 두 줄로 띄움. 평소엔 흰색, 70% 를 넘으면 주황, 90% 를 넘으면 빨강. 윈도우 전용이고 파이썬 표준 라이브러리만 씀.

### 쓰는 법

[sysmon.bat](sysmon.bat) 을 더블클릭하면 켜지고, 다시 누르면 꺼짐. 알림 영역에 작은 막대그래프 아이콘이 뜸. 마우스를 올리면 메모리를 GB 로 보여 주고, 메뉴에서 끌 수 있음.

`python sysmon.py --stop` 으로 끄고, `python sysmon.py --check` 로 자체 점검을 돌림.

### 비용

메시지를 처리하려고 1초에 열 번 깨고, 재는 것은 1초에 한 번임. PC 한 대에서 잰 값: 30초에 CPU 0.03초(한 코어의 0.1%), 메모리 34MB.

### 어떻게 도는지

- CPU 는 1초 간격으로 부른 `GetSystemTimes` 두 번 사이에서 쉬지 않은 시간의 비율이고, 메모리는 `GlobalMemoryStatusEx` 의 `dwMemoryLoad` 임. 성능 카운터·WMI 값과 맞는 것을 봤음
- 작업 표시줄 위에 얹은 클릭 통과·맨 위·픽셀 알파 창([surface.py](../shared/surface.py))에 그림. 글자는 GDI 로 흰색 회색조 안티에일리어싱으로 그린 뒤 밝기를 알파로 바꿔 줄 색을 입힘. 그래서 작업 표시줄 색이 무엇이든 가장자리가 부드러움
- 1초마다 알림 영역(`TrayNotifyWnd`)이 어디서 시작하는지 다시 읽어 트레이 아이콘이 늘거나 줄면 따라감. 작업 표시줄을 누르면 그쪽이 앞으로 오므로 맨 위도 1초마다 다시 잡음
- 전체 화면 앱이 돌면(`SHQueryUserNotificationState` 가 바쁨·Direct3D 전체 화면·발표 모드) 작업 표시줄도 사라지므로 같이 숨음
- 안 따지는 것: 자동 숨기기 작업 표시줄, 옆이나 위에 둔 작업 표시줄, 주 모니터가 아닌 모니터
