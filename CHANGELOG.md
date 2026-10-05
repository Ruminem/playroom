# Changelog

## 0.1.3 — 2026-10-05

- weather: the aquarium gets coral, a shell, a starfish and rocks on the sand, a treasure chest that opens now and then and lets out a stream of bubbles, two crabs walking sideways along the bottom, three see-through jellyfish that squeeze their way up and slowly sink, and a pufferfish and an angelfish among the fish
- weather: when a full-screen app (a browser after F11, a video, a game) hides the taskbar, the floor that stood on it now caves in — the snow, sand, decorations and animals on it crumble down to the bottom of the screen — and rises back at once when the taskbar returns

**한국어**

- weather: 어항 모래 위에 산호·조개·불가사리·돌이 놓이고, 가끔 열려 거품을 뿜는 보물상자, 바닥을 옆걸음으로 걷는 게 두 마리, 오므렸다 펴며 오르고 천천히 가라앉는 반투명 해파리 세 마리가 생기고, 물고기에 복어와 엔젤피시가 더해짐
- weather: 전체 화면 앱(F11 을 누른 브라우저, 동영상, 게임)이 작업 표시줄을 가리면 그 위에 있던 바닥이 무너져 내림 — 그 위의 눈·모래·장식·동물이 화면 맨 아래로 무너지듯 내려오고, 작업 표시줄이 돌아오면 바로 다시 솟음

## 0.1.2 — 2026-10-05

- The files in Google Drive now carry the version in their names (`hud-0.1.2.exe`); the launcher and start-with-Windows find a tool as `hud.exe` or, failing that, the highest `hud-<version>.exe` next to them
- Start with Windows points at the exact file, so after swapping in files of a new version it shows as off until you switch it on again

**한국어**

- 구글 드라이브의 파일 이름에 버전이 붙음(`hud-0.1.2.exe`). 런처와 Windows 시작 시 실행은 옆의 `hud.exe` 를, 없으면 버전이 가장 높은 `hud-<버전>.exe` 를 찾음
- Windows 시작 시 실행은 그 파일 경로를 그대로 가리키므로, 새 버전 파일로 바꿔 넣으면 다시 켤 때까지 꺼진 것으로 보임

## 0.1.1 — 2026-10-05

- weather: a new kind, Aquarium — the screen gets a light water tint with light rays, bubbles, tropical fish, and sand and swaying seaweed along the taskbar and the bottom
- weather: in the aquarium the pets put on goggles, an air tank and (all but the bird) flippers, swim up and down, and breathe out bubbles
- The `.exe` files are now also in Google Drive (`Apps/playroom/`), replaced in place on every release

**한국어**

- weather: 새 종류 어항 — 화면을 옅은 물빛으로 덮고 빛줄기·거품·열대어, 작업 표시줄과 화면 바닥에 모래와 흔들리는 해초를 그림
- weather: 어항에서는 동물들이 물안경·공기통·오리발(새 빼고)을 차고 위아래로 헤엄치며 숨 거품을 내쉼
- `.exe` 가 이제 구글 드라이브(`Apps/playroom/`)에도 있고, 릴리스마다 같은 파일에 덮어씀

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
