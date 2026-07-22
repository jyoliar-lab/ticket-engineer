# ticket-engineer

ops-workflow의 **티켓(GitHub Issue)을 집행하는 엔지니어 agent의 하네스** 저장소.

- 규약은 `CLAUDE.md`에, 강제는 `.claude/hooks/guard-write.py`(쓰기 경계·close·merge 차단)에 있다.
- 대상 코드 저장소는 `workspace/` 아래에 clone된다 (gitignored — 이 저장소가 추적하는 것은 하네스뿐).
- 이 하네스의 개정은 **밖에서** 온다 — agent 자신은 자기 하네스를 고치지 않는다.

새 PC에서 필요한 로컬 설정은 없다 — 워크스페이스는 저장소 내부 상대경로다.
