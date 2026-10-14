# ticket-engineer

ops-workflow의 **티켓(GitHub Issue)을 집행하는 엔지니어 agent의 하네스** 저장소. 티켓은 전부 `jyoliar-lab/ops-workflow`에 있고, 코드는 티켓이 가리키는 target 저장소에서 고친다.

- 규약은 `CLAUDE.md`에, 절차는 `.claude/skills/`에, 강제는 `.claude/hooks/`에 있다. 이 하네스의 개정은 **밖에서** 온다 — agent 자신은 자기 하네스를 고치지 않는다.
- 이 저장소가 추적하는 것은 하네스뿐이다. `workspace/`(대상·참조 저장소 클론)와 `tmp/`(agent의 자유 쓰기 경로), `.claude/settings.local.json`은 gitignored.

## 디렉터리

| 경로 | 무엇 | 쓰기 |
|---|---|---|
| `workspace/target/<repo>/ticket-<N>/` | 티켓별 worktree — 작업 디렉터리 | agent |
| `workspace/target/.bare/<repo>.git` | bare 저장소 | `ticket-run.py`만 |
| `workspace/ref/<repo>` | 참조 저장소. `ref/ops-workflow`는 정책·티켓 코퍼스 | 읽기 전용 — 세션 시작 시 ff-pull |
| `tmp/` | 초안·마찰 로그·PR 본문·테스트 venv (`staging/` · `github-issues/` · `pr/` · `venv-<repo>/`) | agent |

## 구조로 강제하는 것

`CLAUDE.md`는 규약만 적는다. 규약을 어기면 아래가 거부하고, 거부 사유가 그 자리에서 할 일을 말한다.

| 무엇 | 어디서 |
|---|---|
| 쓰기 경계(`workspace/target/**`·`tmp/**`만, `.bare`·`ref`·하네스 자신은 불가) · `gh issue close` · `gh pr merge` | PreToolUse hook `.claude/hooks/guard-write.py` |
| `gh pr create` · force push | 같은 hook가 거부하고 `ticket-pr.py` 관문으로 보낸다 (재정렬 push의 `--force-with-lease`는 그 안에만) |
| 착수 게이트(계층 전체의 근거 ADR accepted · Status Todo/In Progress · 열린 선행 없음) | `ticket-run.py` — exit 코드가 다음 행동 |
| 완료 보고 전제(PR 상태 · 티켓 참조 · close 키워드 · 체크 · target↔worktree 대조) | `preflight.py` — 실패 시 exit 1 |
| TDD 시나리오 코멘트의 게시 · 제자리 갱신 · 승인 표식 · 진행 행(red · green · verify — 단계마다 행 하나를 덧붙여 되감기가 보인다) — 머리 줄(`### TDD 시나리오 — <repo> — <단위>`)이 열쇠라 세션이 바뀌어도 같은 코멘트를 PATCH 한다 · 판 · 승인 줄 · 진행 표는 스크립트가 쓴다 · 한도 초과 · 손으로 쓴 판 줄 · 진행 표 · 풀 수 없는 `{url:}` · 승인 전 진행은 거부 | `scenario-post.py` — 변경 이력은 GitHub 코멘트 편집 이력(discussion 261014_1530) |
| 머지 게이트 | 대상 저장소의 required check |
| 클러스터 쓰기 · Secret 열람 | agent ServiceAccount(`system:serviceaccount:agents:ticket-engineer-agent`)의 RBAC에 권한이 없다 — 클러스터 전역 읽기 전용 |
| `workspace/ref/*` 최신화 · 스킬 `scripts/`의 PATH 등록(맨 이름 실행) | SessionStart hook `refresh-refs.py` · `session-path.sh` |

hook는 fail-open이다 — 입력을 못 읽으면 세션을 막지 않고 통과시킨다. `CLAUDE_PROJECT_DIR`가 없으면 쓰기는 거부한다.

## 로컬 설정 — PC별, 커밋하지 않음

`.claude/settings.local.json`의 `env`에 `KUBECONFIG`(위 ServiceAccount의 kubeconfig)와 플러그인(obs-toolkit)이 요구하는 토큰을 둔다. 워크스페이스는 저장소 내부 상대경로라 그 밖의 설정은 없다. 티켓 '저장소'·선행·'근거 ADR' 절을 갱신하는 도구(`set-repos.py` 등)는 ops-workflow 쪽에 있고 **사람이 돌린다** — agent는 필요를 알리기만 한다.
