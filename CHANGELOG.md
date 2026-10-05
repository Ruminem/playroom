# Changelog

## 0.2.0 — 2026-10-05

- Opening a newer download of a tool while an older copy is running now closes the old one and takes over instead of quietly doing nothing, and start with Windows moves to the new file if it pointed at the old one
- weather: the aquarium settings panel gets fish, bubbles and light-ray sliders (0–100%, 50% is how it looked until now); in the aquarium the amount slider now sets only the tint
- weather: a new box in the settings panel (off by default) lets you grab an animal with the left button and carry it; let go and it falls to the floor, the bird fluttering down slowly
- weather: when the taskbar rises under an animal (leaving full screen), the animal is buried behind it, peeks out, looks both ways and jumps out
- weather: in the aquarium the floor sinks slowly as through water when it caves in, and decorations and the chest no longer hang off the edge of a ledge

**한국어**

- 옛 exe 가 떠 있는 채로 새로 받은 같은 도구를 띄우면 그냥 끝나지 않고 옛 것을 끄고 이어 뜸. 윈도우 시작 시 실행이 옛 파일을 가리켰으면 새 파일로 옮김
- weather: 어항 설정 창에 물고기·거품·빛줄기 막대가 생김(0–100%, 50% 가 지금까지 모습). 어항에서 양 막대는 물빛만 정함
- weather: 설정 창의 **동물을 왼쪽 단추로 집어서 옮기기**(기본 꺼짐)를 켜면 동물을 집어 옮길 수 있고, 놓으면 바닥으로 떨어짐 — 새는 천천히 팔랑이며 내려옴
- weather: 동물 밑에서 작업 표시줄이 솟으면(전체 화면이 끝날 때) 동물이 그 뒤에 묻혔다가 빼꼼 내밀어 두리번거린 뒤 뛰어나옴
- weather: 어항에서 바닥이 무너질 때 물속처럼 천천히 가라앉고, 장식과 보물상자가 턱 끝에 걸쳐 떠 있지 않음

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
