## 성능 기준값 (perf-check 가 견주는 값, 2026-10-11 점검)
- CI 성공 10번, 재실행(attempt 2) 뺌, 초: release 172–239 · mac 93–129 · weather 50–86 · sysmon 24–42 · windows 26–36 · launcher 23–33 · layers 23–27. release 의 큰 스텝은 exe 굽기 47 · 드라이브 올리기 39 · 콘솔판 `--check` 36
- weather 그리기만, 창 없이 2560×1440 · 양 100% · 동물 셋 · 600프레임 중앙: 눈 1.93 · 비 3.04 · 오로라 4.13 · 어항 5.35ms. 자는 `Surface` 를 ctypes 버퍼에 memset·memmove 하는 가짜로 바꾸고 `Weather.frame` 만 잰 것(README 의 '창 없이' 값과 같은 자)
- 떠 있는 프로세스 30초 CPU, 한 코어 대비: weather 어항·120fps·동물 다섯 79% · usage-hud 2.7% · layers 0.4% · sysmon 0.1%

## 측정 (클라우드 세션만)
이 저장소를 연 클라우드 세션은 규칙이 안 실린 대조군이라 `ruminem/rules` 의 측정 로그에 행을 남긴다.
작업 브랜치에 푸시할 때마다 그 뒤에 한 번 한다.
1. `add_repo`(`ruminem` / `rules`, access `push`) 를 부르고, 알려 주는 명령으로 `/tmp/rules` 에 클론한다
2. `python3 /tmp/rules/session-breakdown.py --push`
- `register_repo_root` 는 부르지 않는다. 부르면 rules 의 CLAUDE.md 가 실려 대조군이 깨진다
- 실패하면 이유를 한 줄 알리고 넘어간다. 이것 때문에 하던 일을 멈추지 않는다
- 개인 PC 에서 열었으면 할 일 없다 — 자정 작업이 PC 기록을 훑는다
