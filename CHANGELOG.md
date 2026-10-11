# Changelog

## 0.2.20 — 2026-10-11

- weather: the rain sound also stops while a full-screen app is up on any monitor, so it doesn't play over the video, and comes back when full screen ends

**한국어**

- weather: 어느 모니터든 전체 화면 앱이 떠 있는 동안은 영상 소리와 안 겹치게 빗소리도 멈추고, 전체 화면이 끝나면 다시 남

## 0.2.19 — 2026-10-11

- weather: no longer shows over full-screen apps. While a video (YouTube full screen and the like), game or slideshow fills a monitor, the weather and animals on that monitor are hidden, and they come back when full screen ends. It still stays on top of ordinary windows, and other monitors carry on as before
- weather: the penguin is redrawn as a chubby baby — a rounder, wider body, a bigger black head, short flippers and a round bottom, and a thicker belly slide with its feet kicked back

**한국어**

- weather: 이제 전체 화면 앱 위로 안 뜸. 영상(유튜브 전체 화면 등)·게임·발표가 모니터를 채운 동안은 그 모니터의 날씨와 동물을 숨기고, 전체 화면이 끝나면 다시 보임. 보통 창들 위에는 그대로 맨 위이고, 다른 모니터는 하던 대로 그림
- weather: 펭귄을 통통한 아기로 다시 그림. 더 둥글고 넓은 몸, 커진 검은 머리, 짧은 날개, 둥근 엉덩이, 발을 뒤로 뻗은 한 줄 두꺼운 배 미끄럼

## 0.2.18 — 2026-10-11

- weather: the dog and rabbit are redrawn so they read as a dog and a rabbit. The dog has a big round head, long floppy ears and a snout sticking out with a black nose (before, with no snout, it looked like a goat or a cat standing). The rabbit crouches low with long ears laid back, a white cotton tail and big hind feet (before, it looked like a pig), and when it stops it twitches an ear instead of its nose

**한국어**

- weather: 강아지와 토끼를 다시 그려 강아지·토끼로 보이게 함. 강아지는 큰 둥근 머리, 늘어진 긴 귀, 앞으로 내민 주둥이 끝의 까만 코(전에는 주둥이가 없어 서 있으면 염소나 고양이처럼 보였음). 토끼는 낮게 엎드린 몸에 뒤로 눕힌 긴 귀, 흰 솜꼬리, 큰 뒷발(전에는 돼지처럼 보였음). 멈춰 서면 코 대신 귀를 쫑긋함

## 0.2.17 — 2026-10-11

- weather: in **Joined** mode, the buttons that set the monitor order now show ← → instead of ↑ ↓, matching the left / right they move a monitor in the wide board

**한국어**

- weather: **이어서** 모드에서 모니터 순서를 바꾸는 버튼이 ↑ ↓ 대신 ← → 로 보임. 넓은 판에서 모니터를 왼쪽·오른쪽으로 옮기는 것과 맞춤

## 0.2.16 — 2026-10-11

- layers: weather, usage-hud and sysmon no longer flicker in and out of "always on top" every second or so when an ordered program (such as yt-pip with two windows open) has a window that won't stay on top. Windows below it in the order are no longer slotted under that window

**한국어**

- layers: 순서 목록의 프로그램(창 둘을 띄운 yt-pip 등)에 맨 위로 안 올라가는 창이 있으면 weather·usage-hud·sysmon 의 '항상 위' 가 1초 남짓마다 켜졌다 꺼졌다 했음. 이제 그 창 밑에 목록의 다음 창들을 끼우지 않음

## 0.2.15 — 2026-10-11

- weather: works on more than one monitor. With two or more, the settings panel gets a **Monitors** row to turn the weather on or off per monitor and pick a mode. **Each** (the default) runs separate weather on every monitor — kind, amount, aquarium sliders and animals are set per monitor, and **Same weather** keeps them all alike. **Joined** strings the monitors into one wide scene in the order you set (left to right by default), bottoms lined up, so snow piles along one floor and animals walk from one monitor to the next. Plugging monitors in or out, rearranging them or changing resolution is picked up within two seconds. Existing settings start as before, on the primary monitor only. Two monitors cost about twice the CPU of one
- layers: windows that keep their "always on top" flag but have sunk under ordinary windows (weather, usage-hud and sysmon stuck under browser windows) are raised again
- layers: a program with only one window of its kind is now matched by name alone, not by its title, so a yt-pip window still fits its place in the order after it plays a different video. Remove and re-add an existing yt-pip entry once to pick this up

**한국어**

- weather: 모니터 여럿에서 돎. 모니터가 둘 이상이면 설정 창에 **모니터** 칸이 생겨 모니터마다 날씨를 켜고 끄고 모드를 고름. **각자**(기본)는 모니터마다 날씨를 따로 돌림 — 종류·양·어항 막대·동물을 모니터마다 정하고, **날씨 같이** 를 켜면 다 같게 움직임. **이어서**는 모니터를 정한 순서(기본은 왼쪽부터)로 밑변을 맞춰 넓은 화면 하나로 이어서, 눈이 한 바닥에 쌓이고 동물이 이 모니터에서 다음 모니터로 걸어감. 모니터를 꽂거나 빼거나 배치·해상도를 바꾸면 2초 안에 따라감. 원래 쓰던 설정은 예전처럼 주 모니터 하나로 시작함. 모니터 둘이면 CPU 를 하나일 때의 두 배쯤 씀
- layers: '항상 위' 표시는 켠 채 보통 창 밑에 깔린 창(브라우저 밑에 남은 weather·usage-hud·sysmon)을 다시 올림
- layers: 같은 종류 창이 하나뿐인 프로그램은 제목 없이 이름으로만 맞춰서, yt-pip 이 다른 영상을 틀어도 순서 목록의 제자리에 맞음. 이미 있는 yt-pip 줄은 한 번 빼고 다시 넣어야 적용됨

## 0.2.14 — 2026-10-10

- all tools: after a reboot a tool could fail to start silently, or stopping it could kill an unrelated program, when Windows had handed yesterday's process number to something else. A tool now only counts as running if that process started before it wrote its PID file
- usage-hud: no longer overlaps sysmon for about half a second when a full-screen app ends and the HUD reappears before sysmon
- layers: when it lowers a window, it now lowers the click-through glow window that some Windhawk mods lay right under it too, so the glow no longer covers every window for a second or two
- layers: the **Arrange…** window stays on top, above even the windows it orders
- weather: the bird, dog and rabbit are redrawn to be cuter — rounder bodies, bigger eyes, rosy cheeks and shorter legs — and recoloured: a lavender bird, a white Maltese-style dog and a pink rabbit

**한국어**

- 모든 도구: 재부팅 뒤 어제 프로세스 번호를 윈도우가 다른 프로그램에 다시 주면, 도구가 조용히 안 뜨거나 끌 때 상관없는 프로그램을 죽일 수 있었음. 이제 그 프로세스가 PID 파일을 쓰기 전에 시작된 것일 때만 떠 있는 것으로 봄
- usage-hud: 전체 화면 앱이 끝나고 HUD 가 sysmon 보다 먼저 나타날 때 0.5초쯤 sysmon 과 겹치던 것을 고침
- layers: 창을 내릴 때, 몇몇 Windhawk 모드가 그 창 바로 밑에 깔아 두는 클릭 통과 글로우 창도 같이 내림. 글로우가 1–2초 동안 모든 창을 덮던 것이 없어짐
- layers: **순서 정하기…** 창이 순서를 맞추는 창들보다도 늘 위에 뜸
- weather: 새·강아지·토끼를 더 귀엽게 다시 그림 — 둥근 몸, 큰 눈, 볼 홍조, 짧은 다리. 색도 바꿈: 라벤더 새, 흰 말티즈 강아지, 분홍 토끼

## 0.2.13 — 2026-10-09

- weather: butterflies and dragonflies now play in a sunny garden. A soft glow spreads from a sun just above the top edge of the screen and a fan of warm rays bursts out of it, each ray made of finer strands that drop out one by one as it fades, with specks of dust glinting in them. The sun follows the real one by the clock — the left edge is east, so in the morning it sits low near the upper-left corner, at noon high above the middle and in the afternoon it moves to the upper right; it is faint and orange just after sunrise and before sunset and gone at night (worked out roughly for Seoul's latitude and the date). A leafy branch juts out from the left or right edge, flowers in six colours stand along the top of the taskbar, and butterflies and dragonflies land on free flowers and spots on the branch, one to a spot
- weather: a breeze comes and goes in the garden — thin white wind lines trace wavy paths across the screen, the branch sways gently, flowers bend with the wind, flying butterflies and the dust drift, a strong gust blows butterflies off the flowers and leaves come off the branch. Move the mouse over the branch and it turns see-through (Windows only)
- weather: piled-up hail is drawn as a heap of lumpy ice balls instead of a snow drift. A melting pile could flip upside down and crash after the window was hidden for a while; it now stops at zero
- weather: a bird flying over the taskbar no longer bobs up and down with every step in the ground below; it glides over the highest point of its path. A startled bird now lands anywhere more than a third of the screen away instead of going back and forth between the two ends
- weather: in the faucet, animals dog-paddle at the surface while the water is less than half full and swim underwater with a snorkel above that. Bubbles rise in the water, the stream stretches and breaks into drops as it falls and splashes white where it lands, and every 20–40 seconds something odd floats by — a rubber duck, a bottle with a letter, a boot that plops in and sinks — all sucked down the hole when the water drains

**한국어**

- weather: 나비·잠자리가 햇볕 드는 뜰에서 놂. 화면 위 가장자리 바로 너머의 해 둘레로 해무리가 은은히 번지고 따뜻한 빛줄기가 부챗살로 퍼져 내려옴. 줄기마다 가는 빛살 여러 가닥이 겹쳐 있어 옅어지며 한 가닥씩 빠지고, 그 속에 먼지가 반짝임. 해는 시계에 맞춰 실제 해를 따라감 — 왼쪽이 동쪽이라 아침엔 왼쪽 위 구석 가까이 낮게, 정오엔 가운데 위 높이, 오후엔 오른쪽 위로 옮겨 가고, 해 뜬 직후와 지기 직전엔 옅은 주황빛, 밤엔 없음(서울 위도와 날짜로 어림해 셈). 벽에서 잎 달린 가지가 뻗고, 작업 표시줄 위에 여섯 가지 색 꽃이 서며, 나비와 잠자리가 빈 꽃과 가지 자리에 하나씩 앉음
- weather: 뜰에 바람이 불었다 잦아들었다 함 — 가는 흰 바람줄이 물결진 길로 화면을 지나가고, 가지가 살살 흔들리고, 꽃이 바람 쪽으로 눕고, 나는 나비와 먼지가 밀리고, 센 바람엔 꽃에 앉은 나비가 날려 가고 가지에서 잎이 떨어짐. 가지에 마우스를 올리면 반투명해짐(윈도우만)
- weather: 쌓인 우박이 눈 더미 대신 찌그러진 얼음 알 더미로 그려짐. 창이 한동안 가려졌다 돌아오면 녹던 더미가 뒤집혀 꺼지던 것을 0 에서 멈추게 고침
- weather: 작업 표시줄 위를 나는 새가 바닥 높이를 따라 들썩이지 않고 길에서 가장 높은 곳 위를 미끄러지듯 지나감. 놀란 새가 양 끝만 오가지 않고 화면 1/3 넘게 떨어진 아무 데나 앉음
- weather: 수도꼭지에서 물이 반 아래면 동물이 수면에서 개헤엄치고 반 넘으면 스노클을 물고 물속을 헤엄침. 물속에 거품이 오르고, 물줄기는 떨어질수록 늘어나다 방울로 끊기며 닿는 자리에 흰 물보라를 냄. 20–40초마다 뜬금없는 물건이 뜸 — 고무 오리, 편지 든 병, 퐁당 떨어져 가라앉는 장화 — 물이 빠지면 다 구멍으로 빨려 들어감

## 0.2.12 — 2026-10-08

- All tools: running a tool's `.bat` again used to just stop it. Now, if the tool's files changed since it started (after a `git pull`, say), the `.bat` stops the old one and starts the new code instead; if nothing changed it still stops it. A tool already running from before this update counts as changed, so the first `.bat` after updating swaps it in. The release `.exe` files work as before
- usage-hud, sysmon: moving the mouse over them fades them so whatever is underneath, such as taskbar buttons, shows through. Clicks already went through to it
- weather: hail is drawn as shiny ice balls instead of 1–2 pixel dots. Fast stones leave a short streak, ice chips bounce off where they land, and a few big stones are mixed in. The kinds are now listed snow, hail, rain, storm, so the icy ones and the rainy ones sit together

**한국어**

- 모든 도구: 도구의 `.bat` 을 다시 누르면 지금까지는 끄기만 했음. 이제 켠 뒤로 도구 파일이 바뀌었으면(`git pull` 등) 옛것을 끄고 새 코드로 다시 띄움. 안 바뀌었으면 지금처럼 끔. 이 업데이트 전부터 떠 있던 도구는 바뀐 것으로 보므로 업데이트 뒤 첫 `.bat` 에 갈아 끼워짐. 릴리스 `.exe` 는 예전과 같음
- usage-hud·sysmon: 마우스를 올리면 흐려져 밑에 있는 것(작업 표시줄 단추 등)이 비쳐 보임. 클릭은 원래 밑으로 통과됐음
- weather: 우박이 1–2px 점이 아니라 빛 받는 얼음 공으로 그려짐. 빠른 알은 짧은 자국을 남기고, 닿은 자리에서 얼음 부스러기가 튀며, 가끔 큰 알이 섞임. 종류 순서가 눈·우박·비·뇌우로 바뀌어 얼음끼리, 비끼리 붙어 있음

## 0.2.11 — 2026-10-08

- usage-hud: when you are on pace to use up a limit before it resets, the reset time on that bar turns into a red `!` with how long until it runs out, and the tooltip says the same. The pace is what you have used since the window opened divided by the time since then; the window is assumed to open one span (5 hours or 7 days) before its reset, and the HUD waits until it has been open 15 minutes (5h) or 6 hours (7d) so the first few minutes do not make wild guesses. Being an average, it follows a sudden burst late
- sysmon: on Windows a new **Show disk and network** menu item (off by default) adds a second column left of CPU and memory — `DSK 34%`, how busy the busiest disk is, and `↓1.2M ↑85K`, what the busiest network adapter is receiving and sending per second. The numbers come from Windows performance counters, so they work in any display language. With it on, sysmon takes about twice the width on the taskbar, and usage-hud moves over to stay next to it. The macOS menu bar does not have it
- weather: a new **Faucet** kind — a faucet comes down at a random spot and fills the screen with sloshing water from the bottom up (the amount sets how fast: 120 seconds to the top at 50%). When it is full the tap shuts, cracks spread across the floor and a hole breaks open, and the water drains through it in 40 seconds, fast at first and trickling at the end. Then the hole seals and it starts again somewhere else. The animals float while there is water
- weather: in the aquarium the fish now slow down and turn round over 0.4 seconds, showing a narrow side view, instead of flipping in one frame, and pulse a little faster with each tail beat. Whenever there are fish, a school of 12–16 small silver fish follows an invisible leader, and the seaweed grows in clumps of two or three

**한국어**

- usage-hud: 재설정 전에 한도를 다 쓸 빠르기면 그 막대의 재설정 시간 자리가 빨간 `!` 와 바닥까지 남은 시간으로 바뀌고, 툴팁에도 같이 나옴. 빠르기는 창이 열린 뒤 쓴 양 ÷ 그때부터 지난 시간이고, 창은 재설정보다 한 창 길이(5시간·7일) 앞서 열렸다고 봄. 처음 몇 분으로는 추정이 크게 튀므로 창이 열리고 15분(5시간 창)·6시간(7일 창)은 기다림. 평균이라 갑자기 몰아 쓰면 늦게 따라감
- sysmon: 윈도우에서 메뉴에 **디스크·네트워크 보기**(기본 꺼짐)가 생김. 켜면 CPU·메모리 왼쪽에 둘째 칸이 붙음 — `DSK 34%` 는 가장 바쁜 디스크가 얼마나 바쁜지, `↓1.2M ↑85K` 는 가장 바쁜 네트워크 어댑터가 1초에 받고 보내는 양임. 윈도우 성능 카운터에서 읽어 표시 언어와 상관없이 돎. 켜면 작업 표시줄에서 두 배쯤 넓어지고, usage-hud 는 옆에 붙은 채로 따라 비킴. 맥 메뉴 막대에는 없음
- weather: 종류에 **수도꼭지** 가 생김 — 아무 자리에서 꼭지가 내려와 화면을 바닥부터 출렁이는 물로 채움(양이 빠르기를 정함, 50% 면 꼭대기까지 120초). 다 차면 꼭지가 잠기고 바닥에 금이 번지다 구멍이 뚫려 물이 40초에 걸쳐 빠짐 — 처음엔 콸콸, 끝엔 졸졸. 그다음 구멍이 메워지고 다른 자리에서 다시 틂. 물이 있는 동안 동물은 수면에 뜸
- weather: 어항 물고기가 한 프레임에 뒤집히지 않고 0.4초에 걸쳐 느려지며 좁은 옆모습을 보이고 돌아섬. 꼬리 칠 때마다 살짝 빨라짐. 물고기가 있으면 은빛 작은 물고기 떼 12–16마리가 안 보이는 우두머리를 따라다니고, 해초가 두세 포기씩 모여 자람

## 0.2.10 — 2026-10-08

- usage-hud: a little cat now sits in the HUD. It runs while a Claude Code session on this PC is working and curls up asleep when none is, and when a turn finishes the HUD's border flashes for three seconds — so you can look away while Claude works. It reads the end of the session records changed in the last ten minutes every two seconds. A turn you stop with Esc does not flash. While Claude waits for you to allow a tool the cat keeps running, and a tool that runs for over ten minutes without a new line looks asleep. On the taskbar the flat panel is a little wider to make room for it; in the corners the size is unchanged
- weather: fireworks now burst in eight kinds instead of one — peony (sometimes changing colour halfway), chrysanthemum with short tails, gold willow whose long trails of different lengths droop for over three seconds, palm, tilted ring, crossettes that split into four, blinking strobe glitter, and now and then a heart

**한국어**

- usage-hud: HUD 에 작은 고양이가 생김. 이 PC 의 Claude Code 세션이 일하는 동안 달리고, 일하는 세션이 없으면 웅크려 자며, 한 차례가 끝나면 HUD 테두리가 3초 깜빡임 — Claude 가 일하는 동안 딴 데를 보고 있어도 됨. 최근 10분 안에 바뀐 세션 기록의 끝부분을 2초마다 읽음. Esc 로 끊은 차례는 안 깜빡임. Claude 가 도구 허락을 기다리는 동안은 고양이가 계속 달리고, 새 줄 없이 10분 넘게 도는 도구는 잠든 것으로 보임. 작업 표시줄의 납작한 패널은 고양이 자리만큼 조금 넓어졌고, 구석 패널은 크기가 그대로임
- weather: 불꽃놀이가 한 가지 대신 여덟 가지 모양으로 터짐 — 모란(가끔 중간에 색이 바뀜), 짧은 꼬리를 끄는 국화, 가닥마다 길이가 다른 금빛 꼬리가 3초 넘게 처지는 버들, 야자, 기울어진 고리, 넷으로 쪼개지는 갈라지기, 깜빡이는 반짝이, 가끔 하트

## 0.2.9 — 2026-10-07

- usage-hud: a new **Taskbar diagnostic** item in the tray menu writes what is on the taskbar — each taskbar and the windows inside it, and other windows lying over it, with class, title, position and program name — to `%TEMP%\playroom-taskbar.txt` and opens it in Notepad. On the taskbar the HUD does not yet step around other programs that sit there too and can land on top of them; this is for seeing how they sit before teaching it to avoid them. Window titles are in it, so look it over before sharing
- weather: five new kinds — **Raindrops on the window** (drops bead up on the glass in front of everything, merge and run down, and now and then a slanted shower passes; the rain sound plays with it), **Fog** (a pale bank drifting over the bottom two fifths of the screen), **Aurora** (three curtains of light over the top of the screen, with a meteor now and then), **Butterflies and dragonflies**, and **Soap bubbles** that pop after a while, on an animal, or when clicked. The kind buttons in the settings panel now take four rows
- weather: snow flutters as it falls, a big out-of-focus flake drifts past the lens now and then, landed flakes stay on the bank for a moment before sinking in, and the bank has a bright rim, shaded slopes and glints along its edge

**한국어**

- usage-hud: 트레이 메뉴에 **작업 표시줄 진단** 이 생김. 작업 표시줄 위에 무엇이 있는지 — 작업 표시줄마다 그 안의 창, 그 위에 얹힌 다른 창을 클래스·제목·자리·프로그램 이름과 함께 — `%TEMP%\playroom-taskbar.txt` 에 적고 메모장으로 염. 작업 표시줄 자리의 HUD 는 거기 같이 뜨는 다른 프로그램을 아직 피하지 않아 그 위에 겹칠 수 있는데, 피하게 만들기 전에 그런 프로그램이 어떻게 떠 있는지 보려고 둔 것임. 창 제목이 들어 있으니 남에게 보내기 전에 한 번 훑어볼 것
- weather: 종류 다섯이 새로 생김 — **창문 빗방울**(모든 것 앞의 유리에 빗방울이 맺혀 합쳐지고 흘러내리며, 가끔 비스듬한 소나기가 지나감. 빗소리도 같이 남), **안개**(화면 아래 2/5 위로 흐르는 옅은 안개), **오로라**(화면 위쪽에 드리운 빛의 커튼 세 겹, 가끔 유성), **나비·잠자리**, 그리고 시간이 지나거나 동물에 닿거나 누르면 터지는 **비눗방울**. 설정 창의 종류 단추가 네 줄이 됨
- weather: 눈이 내려오며 팔랑이고, 가끔 초점 밖의 크고 흐린 눈송이가 렌즈 앞을 지나가며, 내려앉은 눈송이가 잠깐 더미 위에 보였다가 스며들고, 더미에 밝은 테두리와 비탈 명암, 가장자리 반짝임이 생김

## 0.2.8 — 2026-10-05

- weather: right-clicking the tray icon on Windows now opens the same settings panel as a left click, instead of a separate menu that could fall out of step with it. The macOS menu bar keeps its menu
- weather: the settings panel now opens at once (about 10–40 ms instead of 0.35–0.57 s) — it waits hidden from the start, using about 54 MB
- weather: the settings panel now sits right above the tray icon instead of wherever the mouse was, and no longer flashes in the top-left corner first. If the icon is tucked into the hidden icons, it opens above the mouse as before

**한국어**

- weather: 윈도우에서 트레이 아이콘을 오른쪽 클릭해도 왼쪽 클릭과 같은 설정 창이 뜸. 전에는 따로 있는 메뉴가 떠서 설정 창과 어긋날 수 있었음. 맥 메뉴 막대는 메뉴 그대로임
- weather: 설정 창이 바로 뜸(0.35–0.57초에서 10–40ms 쯤으로). 켤 때부터 숨은 채 떠 있고 54MB 쯤 씀
- weather: 설정 창이 마우스 자리가 아니라 트레이 아이콘 바로 위에 뜨고, 왼쪽 위에 잠깐 떴다 옮겨 가던 것이 없어짐. 아이콘이 숨긴 아이콘 칸에 들어가 있으면 예전처럼 마우스 자리 위에 뜸

## 0.2.7 — 2026-10-05

- weather: **Smoothness** now offers 30 · 60 · 120 fps; 180 is gone because it took a whole CPU core. If 180 was picked before, it is read as 120
- weather: dragging the rain sound volume slider on Windows now just turns the sound up or down, like a video player, instead of starting it over each time
- weather: the settings panel's rain sound box is now called just **Rain sound**, and it shows — with its volume slider, now named **Volume** — only while rain or storm is picked

**한국어**

- weather: **부드러움** 은 이제 30·60·120fps 만 고를 수 있음. 180 은 CPU 한 코어를 다 써서 뺐음. 전에 180 을 골라 뒀으면 120 으로 읽음
- weather: 윈도우에서 빗소리 크기 막대를 끌면 동영상 볼륨처럼 소리가 끊기지 않고 커지고 작아짐. 전에는 끌 때마다 소리를 처음부터 다시 틀었음
- weather: 설정 창의 빗소리 상자 이름을 **빗소리** 로 줄였고, 비·뇌우를 골랐을 때만 크기 막대(이름은 **소리 크기**)와 같이 보임

## 0.2.6 — 2026-10-05

- weather: rain and storm now draw at most 120 frames a second even when **Smoothness** is set to 180, as the aquarium already did in 0.2.5 — at 180 they took a whole CPU core. On one PC, a full-strength storm with all five animals went from 100% of a core to about 50–58%. Other kinds still use 180 when it is picked
- weather: also in 0.2.5 but not listed there — the aquarium light rays are redrawn only where they move, which makes an aquarium frame about 30% cheaper, and leaving the aquarium hands back about 22 MB of memory

**한국어**

- weather: **부드러움** 을 180 으로 둬도 비와 뇌우는 1초에 120번까지만 그림. 어항은 0.2.5 부터 그랬음 — 180 이면 CPU 한 코어를 다 썼음. PC 한 대에서 뇌우 100% 에 동물 다섯을 켜 두면 한 코어의 100% 에서 50–58% 쯤으로 줄었음. 다른 종류는 180 을 고르면 180 그대로임
- weather: 0.2.5 에 들어갔는데 거기 안 적은 것 — 어항 빛줄기를 움직인 자리만 다시 그려 어항 한 프레임이 30% 쯤 가벼워졌고, 어항에서 다른 종류로 바꾸면 메모리를 22MB 쯤 돌려줌

## 0.2.5 — 2026-10-05

- weather: picking rain or storm in 0.2.4 stopped the animation for good (a name clash with the new rain sound); fixed
- weather: the rain sound is redone to sound like rain heard from indoors through a window — a muffled, steady wash in stereo with now and then a soft tap of a drop on stone, instead of the metallic ticking of 0.2.4. The first time it is turned on it starts a couple of seconds late

**한국어**

- weather: 0.2.4 에서 비나 뇌우를 고르면 그림이 아예 멈추던 것을 고침(새 빗소리와 이름이 겹쳤음)
- weather: 빗소리를 창 너머 방 안에서 듣는 비처럼 다시 만들었음 — 0.2.4 의 철판에 떨어지는 듯한 타닥 대신, 먹먹하고 고른 스테레오 쏴아에 가끔 돌바닥에 떨어지는 방울이 툭 하고 섞임. 처음 켤 때는 2초쯤 늦게 남

## 0.2.4 — 2026-10-05

- weather: a new **rain sound** box in the settings panel and right-click menu (off by default) plays a soft hiss of rain against a window, like white noise, while rain or storm is showing, with a volume slider (50% by default). Storm uses the same sound, without thunder. It stops when the weather is hidden or another kind is picked, and works on macOS too

**한국어**

- weather: 설정 창과 오른쪽 클릭 메뉴에 **빗소리** 상자(기본 꺼짐)가 생김 — 비나 뇌우가 보이는 동안 창밖에서 비 내리는 듯한 잔잔한 소리를 백색소음처럼 틀고, 크기 막대(기본 50%)로 조절함. 뇌우도 같은 소리이고 천둥은 없음. 날씨를 숨기거나 다른 종류로 바꾸면 멈추고, 맥에서도 남

## 0.2.3 — 2026-10-05

- weather: the aquarium fish are redrawn to look like real tropical fish — the clownfish gets black-edged white bands, the blue tang its yellow tail and black marking, the neon tetra a cyan stripe and red belly, the pufferfish spots, the angelfish long fins and stripes — and they are about twice as big as before
- weather: the aquarium light rays are made of several thin shafts instead of one smooth bar, fan out as if the sun were up to one side, and brighten and dim smoothly instead of in jumps; the faint dark edge around each ray is gone
- weather: snow, rain, hail, bubbles and fireflies get a faint dark-blue shadow so they show on white web pages too; on dark windows they look the same as before

**한국어**

- weather: 어항 물고기를 진짜 열대어처럼 다시 그렸음 — 흰동가리는 검은 테를 두른 흰 띠, 블루탱은 노란 꼬리와 검은 무늬, 네온테트라는 청록 줄과 빨간 배, 복어는 점박이, 엔젤피시는 긴 지느러미와 줄무늬 — 크기도 예전의 두 배쯤임
- weather: 어항 빛줄기가 매끈한 막대 하나가 아니라 가는 빛살 여러 가닥으로 이루어지고, 해가 한쪽 위에 있는 듯 부채꼴로 벌어지며, 밝기가 뚝뚝 끊기지 않고 부드럽게 오감. 줄기 둘레의 옅은 어두운 테두리도 없어짐
- weather: 눈·비·우박·거품·반딧불에 옅은 남색 그림자가 생겨 흰 웹 페이지 위에서도 보임. 어두운 창 위에서는 예전과 같아 보임

## 0.2.2 — 2026-10-05

- layers: if putting the windows in order failed once (a window closing at that very moment), it stopped ordering them for good until restarted — the taskbar could then stay above weather, and with a see-through taskbar the animals standing in it could not be grabbed. It now tries again next time and keeps the last error in `%LOCALAPPDATA%\playroom\layers-error.txt`

**한국어**

- layers: 창 순서 맞추기가 한 번 실패하면(그 순간 창이 닫히는 등) 다시 켤 때까지 영영 순서를 안 맞췄음 — 그러면 작업 표시줄이 weather 위에 남아, 작업 표시줄이 투명할 때 그 안에 선 동물이 안 집혔음. 이제 다음 차례에 다시 하고 마지막 오류를 `%LOCALAPPDATA%\playroom\layers-error.txt` 에 남김

## 0.2.1 — 2026-10-05

- weather: the sliders in the settings panel now apply while you drag them instead of only when you let go, and moving one no longer starts the weather over — snow already on the ground stays and fish keep swimming where they are
- weather: the aquarium fish slider picks a number of fish (0–20, 8 by default) instead of a percentage

**한국어**

- weather: 설정 창 막대가 손을 뗄 때가 아니라 끄는 동안 바로 반영되고, 막대를 움직여도 날씨를 처음부터 다시 깔지 않음 — 쌓인 눈은 그대로, 물고기는 헤엄치던 자리에 남음
- weather: 어항 물고기 막대가 퍼센트 대신 마릿수(0–20마리, 기본 8마리)를 고름

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
