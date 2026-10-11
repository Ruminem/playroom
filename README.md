# playroom

**English** · [한국어](#korean)

[![mac](https://github.com/Ruminem/playroom/actions/workflows/mac.yml/badge.svg)](https://github.com/Ruminem/playroom/actions/workflows/mac.yml) [![windows](https://github.com/Ruminem/playroom/actions/workflows/windows.yml/badge.svg)](https://github.com/Ruminem/playroom/actions/workflows/windows.yml) [![weather](https://github.com/Ruminem/playroom/actions/workflows/weather.yml/badge.svg)](https://github.com/Ruminem/playroom/actions/workflows/weather.yml) [![launcher](https://github.com/Ruminem/playroom/actions/workflows/launcher.yml/badge.svg)](https://github.com/Ruminem/playroom/actions/workflows/launcher.yml) [![sysmon](https://github.com/Ruminem/playroom/actions/workflows/sysmon.yml/badge.svg)](https://github.com/Ruminem/playroom/actions/workflows/sysmon.yml) [![layers](https://github.com/Ruminem/playroom/actions/workflows/layers.yml/badge.svg)](https://github.com/Ruminem/playroom/actions/workflows/layers.yml)

A hobby playroom. One folder per experiment, each with its own short README.

## Contents

- [usage-hud](usage-hud/) — Claude Code subscription limits as a retro game HUD: hearts for the weekly limit, a bolt for the five-hour one, a coin for what today would have cost at API prices, and a cat that runs while Claude Code is working and flashes the HUD when a turn finishes. A click-through overlay that stays on top of everything, plus a browser page with the last seven days. On macOS it sits in the menu bar instead
- [weather](weather/) — snow, rain, a thunderstorm, hail, raindrops on the window, fog, an aurora, fireflies, butterflies and dragonflies, soap bubbles, fireworks, an aquarium or a faucet that floods the screen over every window, picture-in-picture video included. Clicks go straight through to whatever you are working on; snow piles up on the taskbar and slowly melts. Optional pixel animals — a cat, bird, dog, rabbit or penguin, several at once — wander along the taskbar, with or without weather. With several monitors each one gets its own weather, or they join into one wide scene the animals can walk across. Also runs on macOS, with its icon in the menu bar
- [sysmon](sysmon/) — CPU and memory use in two small lines on the taskbar, just left of the notification icons. Turns orange above 70% and red above 90%. On Windows it can also show disk activity and network speed. A pixel theme matches usage-hud, which can sit on the taskbar right next to it. Also runs on macOS, in the menu bar
- [layers](layers/) — decides which always-on-top window goes in front: the overlays here, a picture-in-picture video, any window you add. Without it the overlays take turns jumping in front of each other
- [launcher](launcher/) — one window to run or stop the tools above, keep each on top or not, start it with Windows, and install or uninstall it as a Start menu shortcut
- [shared](shared/) — the tray icon, per-pixel alpha window, taskbar text, single-instance, work-area and start-with-Windows helpers the overlays share

## Download

The Windows tools come as standalone `.exe` files on the [Releases](https://github.com/Ruminem/playroom/releases) page, no Python needed: `launcher.exe`, `hud.exe` (usage-hud), `weather.exe`, `sysmon.exe` and `layers.exe`. Keep them in one folder — the launcher runs and installs the `.exe` next to it. Names with the version on them (`hud-0.1.2.exe`) work too; with several, the highest version is used. Open a newer download while an older copy of the same tool is running and it closes the old one and takes over, and if start-with-Windows pointed at the old file it now points at the new one. They are not code-signed, so SmartScreen may warn the first time. What changed in each release is in [CHANGELOG.md](CHANGELOG.md).

## License

Apache-2.0. See [LICENSE](LICENSE). The `.exe` files also carry the Python runtime and the libraries listed in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

---

## Korean

[English](#playroom) · **한국어**

[![mac](https://github.com/Ruminem/playroom/actions/workflows/mac.yml/badge.svg)](https://github.com/Ruminem/playroom/actions/workflows/mac.yml) [![windows](https://github.com/Ruminem/playroom/actions/workflows/windows.yml/badge.svg)](https://github.com/Ruminem/playroom/actions/workflows/windows.yml) [![weather](https://github.com/Ruminem/playroom/actions/workflows/weather.yml/badge.svg)](https://github.com/Ruminem/playroom/actions/workflows/weather.yml) [![launcher](https://github.com/Ruminem/playroom/actions/workflows/launcher.yml/badge.svg)](https://github.com/Ruminem/playroom/actions/workflows/launcher.yml) [![sysmon](https://github.com/Ruminem/playroom/actions/workflows/sysmon.yml/badge.svg)](https://github.com/Ruminem/playroom/actions/workflows/sysmon.yml) [![layers](https://github.com/Ruminem/playroom/actions/workflows/layers.yml/badge.svg)](https://github.com/Ruminem/playroom/actions/workflows/layers.yml)

취미용 놀이방. 실험 하나당 폴더 하나로 두고, 폴더마다 짧은 README 를 붙임.

### 구성

- [usage-hud](usage-hud/) — Claude Code 구독 한도를 레트로 게임 HUD 로 보여 줌. 하트는 7일 한도, 번개는 5시간 한도, 동전은 오늘 쓴 양을 API 정가로 친 값이고, 고양이는 Claude Code 가 일하는 동안 달리다 한 차례가 끝나면 HUD 를 깜빡임. 모든 창 위에 떠 있되 클릭은 통과시키는 오버레이와, 7일치를 함께 보는 브라우저 페이지. 맥에서는 메뉴 막대에 뜸
- [weather](weather/) — PIP 영상까지 포함해 모든 창 위로 눈·비·뇌우·우박을 내리거나 유리창에 빗방울을 맺히게 하거나 안개·오로라·반딧불이·나비와 잠자리·비눗방울·불꽃놀이·어항을 띄우거나 수도꼭지로 화면을 물에 잠기게 함. 클릭은 하던 작업으로 그대로 통과하고, 눈은 작업 표시줄 위에 쌓였다가 천천히 녹음. 픽셀 고양이·새·강아지·토끼·펭귄을 켜면(여럿도 됨) 날씨와 같이 또는 혼자 작업 표시줄 위를 돌아다님. 모니터가 여럿이면 모니터마다 날씨를 따로 두거나, 이어서 동물이 건너다니는 넓은 화면 하나로 만듦. 맥에서도 돌고, 아이콘은 메뉴 막대에 뜸
- [sysmon](sysmon/) — 작업 표시줄의 알림 아이콘 바로 왼쪽에 CPU·메모리 사용률을 작은 두 줄로 띄움. 70% 를 넘으면 주황, 90% 를 넘으면 빨강. 윈도우에서는 디스크 활성도와 네트워크 속도도 띄울 수 있음. 픽셀 테마는 usage-hud 와 같은 모양이고, usage-hud 를 작업 표시줄에 두면 바로 옆에 붙음. 맥에서도 돌고, 메뉴 막대에 뜸
- [layers](layers/) — 맨 위에 뜨는 창들 중 무엇이 앞에 올지 정함. 여기 오버레이들, PIP 영상, 직접 넣은 아무 창이나. 없으면 오버레이들이 서로 번갈아 앞으로 튀어나옴
- [launcher](launcher/) — 위 도구들을 한 창에서 실행·중단하고, 항상 위·윈도우 시작 시 실행을 켜고 끄고, 시작 메뉴 바로가기로 설치·제거함
- [shared](shared/) — 오버레이들이 같이 쓰는 트레이 아이콘, 픽셀 알파 창, 작업 표시줄 글자, 한 번만 뜨게 하기, 작업 영역, 윈도우 시작 시 실행 코드

### 받기

윈도우 도구는 [Releases](https://github.com/Ruminem/playroom/releases) 페이지에 파이썬 없이 도는 `.exe` 로 있음: `launcher.exe`, `hud.exe`(usage-hud), `weather.exe`, `sysmon.exe`, `layers.exe`. 한 폴더에 둘 것 — 런처가 옆에 있는 `.exe` 를 실행하고 설치함. 이름에 버전이 붙어 있어도(`hud-0.1.2.exe`) 되고, 여럿이면 버전이 가장 높은 것을 씀. 같은 도구의 옛 exe 가 떠 있는 채로 새로 받은 것을 띄우면 옛 것을 끄고 이어 뜨고, 윈도우 시작 시 실행이 옛 파일을 가리켰으면 새 파일로 고침. 코드 서명이 없어서 처음엔 SmartScreen 이 경고할 수 있음. 릴리스마다 무엇이 바뀌었는지는 [CHANGELOG.md](CHANGELOG.md) 에 있음.

### 라이선스

Apache-2.0. [LICENSE](LICENSE) 참고. `.exe` 에는 Python 런타임과 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) 에 적은 라이브러리도 같이 실림.
