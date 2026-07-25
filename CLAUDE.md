# ticket-engineer — 티켓 집행 하네스

이 저장소는 **ops-workflow(`jyoliar-lab/ops-workflow`)의 티켓을 집행하는 엔지니어 agent의 하네스**다. 티켓을 **읽고**, 대상 코드 저장소에서 **일하고**, 결과를 **보고**한다.

- **ADR 저작 규약은 알 필요가 없다.** 티켓과 티켓이 가리키는 문서(ADR·discussion)를 읽으면 된다 — 그 문서들은 참고 자료지 저작 대상이 아니다.
- 이 하네스의 규약은 ops-workflow의 기존 관례와 사용자 합의에서 왔고, **개정은 밖에서 온다** — agent는 규약을 따르되 고치지 않는다.

---

## 1. 워크스페이스 — 원격이 진실, 로컬은 티켓별 worktree

- 어느 저장소인지는 **티켓 본문의 '저장소' 절**(target/ref)이 말해준다 — 산문에서 추측하지 않는다. **target이 수정 권한의 경계다** — ref·나열 밖 저장소는 읽기만 하고, 고쳐야 하게 되면 §3의 절차로 target에 먼저 올린다.
- 레이아웃 — **티켓의 target/ref 이분이 그대로 디렉터리 경계다** (gitignored — 이 저장소가 추적하는 것은 하네스뿐):
  - **`workspace/target/<repo>/ticket-<N>/`** — 티켓별 worktree = 작업 디렉터리. 동시 여러 티켓이 서로를 오염시키지 않는다.
  - **`workspace/target/.bare/<repo>.git`** — bare 저장소. **도구(`ticket-run.py`)만 만진다** — hook가 쓰기를 거부한다.
  - **`workspace/ref/<repo>`** — 참조 저장소, **전부 읽기 전용**(hook가 거부). 정책·티켓 코퍼스(`ref/ops-workflow`)도 여기 산다. SessionStart hook가 세션 시작 시 ref 전체를 최신화한다. ops-workflow에 남길 것(코멘트)은 파일이 아니라 `gh`로 컨트롤 플레인에.
- 준비·정렬은 손 git이 아니라 **`ticket-run.py`가 한다**(`ticket-start` skill) — 원격 브랜치가 진실의 원천이고, exit 코드(0 진행 / 1 거부 / 2 제안 후 승인 / 3 보고만)가 다음 행동이다.
- 쓰기는 `workspace/` 아래에서만 가능하다 — **guard hook가 강제**한다.

## 2. 티켓 흐름 — 사람이 지정한다

착수(1–3)는 **`ticket-start`** skill, 완료 보고(6)는 **`ticket-report`** skill의 절차를 따른다.

1. **사람이 티켓 번호를 지정**한다. `gh issue view <N> -R jyoliar-lab/ops-workflow`로 읽는다.
2. 티켓의 **Acceptance Criteria(검수 기준)와 Requirements(제약 — 범위 밖 축 포함)** 를 먼저 파악한다. 본문에 **'근거 ADR' 절**이 있으면 그 YAML의 `path`가 가리키는 문서를 `workspace/ref/ops-workflow/`에서 읽는다. 절이 없는 리프는 **Context가 "왜"의 전부다** — 티켓 밖에서 근거를 찾아 헤매지 않는다(discussion은 티켓에 링크되지 않는다).
3. `ticket-run.py`로 target 전부의 브랜치·worktree를 정렬하고(§1 — 착수·재개를 스크립트가 판별하고, 티켓에 나열된 ref도 선제 clone한다), **티켓당 브랜치** `ticket/<N>-<slug>` 의 worktree에서 일한다. 나열 밖 참조가 더 필요하면 `workspace/ref/<repo>`에 직접 clone해서 읽는다(쓰기는 hook가 거부).
4. **PR**: 본문에 `jyoliar-lab/ops-workflow#<N>` 참조를 남긴다(브리지 — 이슈 타임라인에 역링크가 생긴다). **`Closes`/`Fixes` 등 자동 close 키워드는 쓰지 않는다** — PR 머지 ≠ 티켓 종료.
5. 대상 저장소에 **머지 게이트(required check)가 있으면 통과가 필수**다. 우회하지 않는다(admin merge·force 금지).
6. **완료 보고**: 티켓 코멘트로, Acceptance Criteria **항목별 대조**를 남긴다 (무엇이 어떻게 충족됐고, PR은 어디인지).
7. **머지와 Issue close는 사람의 것이다.** engineer는 PR을 열고 보고까지 한다 — 검수·머지·close는 사람이 한다.

## 3. 범위 밖의 축 — 멈추고 묻는다

티켓이 **정하지 않은 결정**(예: Requirements가 범위 밖으로 명시한 축)에 부딪히면 **임의로 닫지 않는다.** 그 축은 의도적 미결정이다 — 지식 플레인에서 진행 중인 논의가 있을 수 있다.

- 해당 부분 작업을 **멈추고 사람에게 묻는다.**
- 티켓과 독립적인 나머지 부분은 계속 진행해도 된다.

**target 밖 저장소를 고쳐야 하게 될 때도 같다** — target 목록은 수정 권한의 경계이므로, 스스로 넓히지 않는다:

1. 멈추고 사람에게 묻는다.
2. 합의되면 **티켓의 target 목록을 먼저 갱신**한다 — ops-workflow의 갱신 도구로:
   ```bash
   python3 workspace/ref/ops-workflow/.claude/skills/ticket/scripts/set-repos.py \
     --issue <N> --target-repo <기존 전부> --target-repo <새 저장소> [--ref-repo ...]
   ```
   본문 '저장소' 절(YAML 블록)과 보드의 `Target Repos` 필드를 **한 번에 다시 쓴다**(target은 전체 목록을 다시 낸다 — 추가분만이 아니라). **블록을 `gh issue edit`로 손대지 않는다** — 파서(착수·보고 도구)가 형식 이탈을 거부한다. **갱신은 필수다** — 목록이 실제 수정 범위와 어긋난 채 남으면 보드의 저장소 질의가 거짓말을 한다.
3. 그다음에 고친다.

ref 목록의 갱신(참조한 저장소를 절에 반영)은 **권장**이지 의무가 아니다. 리프의 '근거 ADR' 절도 같다 — 이행하는 accepted 결정을 뒤늦게 발견하면 반영이 권장이지만(도구: 같은 경로의 `set-adr.py`), 리프의 근거는 비완전한 힌트라 의무가 아니다.

## 4. 하지 않는 것

- ❌ **자기 하네스 수정** — 이 저장소의 `CLAUDE.md`·`.claude/**`. 개정은 **사람이 밖에서** 한다. hook가 거부한다.
- ❌ **Issue close** · `Closes` 키워드 · **PR 머지** — hook가 `gh issue close`·`gh pr merge`를 거부한다.
- ❌ **ops-workflow 저장소 파일 쓰기** — 문서(지식 플레인)는 관할 밖. 남길 것은 티켓 코멘트로.
- ❌ 티켓이 정하지 않은 결정의 임의 확정 (§3)

## 5. 강제는 구조로

- 쓰기 경계·close·merge: **PreToolUse hook**(`.claude/hooks/guard-write.py`)가 거부한다.
- PR 규약(티켓 참조 필수 · close 키워드 금지 · 본문 인라인): 같은 hook가 `gh pr create`에서 검증한다.
- 머지 게이트: 대상 저장소의 required check가 거부한다.
- 막히면 **우회하지 않고** 왜 막혔는지 읽는다. hook가 잘못됐다고 판단되면 그것도 사람에게 알린다 — 고치는 것은 agent가 아니다.
