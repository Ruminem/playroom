# Changelog

## 0.1.0 — 2026-10-05

- First release: the Windows tools as standalone `.exe` files, so they run without Python installed — `launcher.exe`, `hud.exe` (usage-hud), `weather.exe`, `sysmon.exe` and `layers.exe`
- Keep all five in one folder. The launcher runs, stops and installs the `.exe` next to it, and "start with Windows" and Start menu shortcuts point at those files, so moving the folder turns start-with-Windows off until you switch it on again
- The files are not code-signed, so Windows SmartScreen may warn the first time you run one ("More info" → "Run anyway")
- macOS versions are not included; run them from source as described in each folder's README

**한국어**

- 첫 릴리스: 윈도우 도구를 파이썬 없이 도는 `.exe` 로 냄 — `launcher.exe`, `hud.exe`(usage-hud), `weather.exe`, `sysmon.exe`, `layers.exe`
- 다섯 개를 한 폴더에 둘 것. 런처는 옆에 있는 `.exe` 를 실행·중단·설치하고, Windows 시작 시 실행과 시작 메뉴 바로가기도 그 파일을 가리키므로 폴더를 옮기면 다시 켤 때까지 시작 시 실행이 꺼짐
- 코드 서명이 없어서 처음 실행할 때 Windows SmartScreen 이 경고할 수 있음("추가 정보" → "실행")
- macOS 판은 없음. 각 폴더 README 대로 소스에서 띄우면 됨
