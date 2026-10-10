## 측정 (클라우드 세션만)
이 저장소를 연 클라우드 세션은 규칙이 안 실린 대조군이라 `ruminem/rules` 의 측정 로그에 행을 남긴다.
작업 브랜치에 푸시할 때마다 그 뒤에 한 번 한다.
1. `add_repo`(`ruminem` / `rules`, access `push`) 를 부르고, 알려 주는 명령으로 `/tmp/rules` 에 클론한다
2. `python3 /tmp/rules/session-breakdown.py --push`
- `register_repo_root` 는 부르지 않는다. 부르면 rules 의 CLAUDE.md 가 실려 대조군이 깨진다
- 실패하면 이유를 한 줄 알리고 넘어간다. 이것 때문에 하던 일을 멈추지 않는다
- 개인 PC 에서 열었으면 할 일 없다 — 자정 작업이 PC 기록을 훑는다
