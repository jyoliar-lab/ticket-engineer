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
- 준비·정렬은 손 git이 아니라 **`ticket-run.py`가 한다**(`ticket-start` skill) — 원격 브랜치가 진실의 원천이고, exit 코드가 다음 행동이다.
- 쓰기는 `workspace/` 와 `tmp/` 아래에서만 가능하다 — **guard hook가 강제**한다. `tmp/`(gitignored)의 자리: `tmp/staging/` 마찰 로그·사람에게 넘길 제안(§4) · `tmp/github-issues/` 티켓 코멘트 초안(게시는 `gh --body-file`로).

## 2. 티켓 흐름 — 사람이 지정한다

**사람이 티켓 번호를 지정**하는 것이 시작이다. 절차의 실질은 두 skill에 있다:

- **착수·재개** — **`ticket-start`** skill: 티켓·근거 문서를 읽고 경계(Acceptance Criteria·Requirements)를 추출한 뒤, 티켓별 worktree를 정렬해 작업을 시작한다. 착수에는 게이트가 있다(계층 전체의 근거 ADR accepted + 비Draft) — 거부되면 우회하지 않고 사람에게.
- **완료 보고** — **`ticket-report`** skill: 기계 확인을 통과한 뒤 Acceptance Criteria 항목별 대조를 티켓 코멘트로 게시한다.

두 skill 사이, 작업 중의 규약:

1. **PR 생성은 `ticket-pr.py`로** — squash 머지 후 재정렬·본문 규약·티켓 Development 연결을 관문이 수행한다.
2. 대상 저장소에 **머지 게이트(required check)가 있으면 통과가 필수**다. 우회하지 않는다(admin merge·force 금지).
3. **머지와 Issue close는 사람의 것이다.** engineer는 PR을 열고 보고까지 한다 — 검수·머지·close는 사람이 한다.
4. **도구·라이브러리·프레임워크 설치는 조사 후에.** 기억 속 버전을 그대로 쓰지 않는다 — 설치 전 **가장 안정된(stable) 버전을 실제로 조사**(공식 릴리스·문서 확인)해 그 버전으로 설치한다. 최신(latest·beta·RC)이 아니라 안정 버전이다.
5. **홈랩 Kubernetes는 자기 자격증명으로 읽는다.** `KUBECONFIG` env가 주입되어 있어(`.claude/settings.local.json` · gitignored · PC별) `kubectl`이 전용 ServiceAccount(`system:serviceaccount:agents:ticket-engineer-agent`)로 동작한다 — kubeconfig를 직접 다루거나 context를 고르지 않는다. 권한은 **클러스터 전역 읽기 전용**(Secret 값 제외) — 배포 상태 확인·검증에 쓴다. **클러스터를 고치는 길은 kubectl이 아니라 GitOps 저장소(티켓 target)의 PR이다** — 쓰기는 어차피 RBAC가 거부한다.

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

**작업 중 미기재 선행 의존을 발견했을 때도 같다 — 갱신이 필수다**(ADR-0017): 같은 경로의 `set-deps.py`로 blocked-by를 갱신한다(선행 **전체** 목록을 다시 낸다 — 사이드바 손편집 금지). 발견한 선행이 열려 있으면 멈추고 사람에게 — 그 위에서 계속 일하지 않는다.

ref 목록의 갱신(참조한 저장소를 절에 반영)은 **권장**이지 의무가 아니다. 리프의 '근거 ADR' 절도 같다 — 이행하는 accepted 결정을 뒤늦게 발견하면 반영이 권장이지만(도구: 같은 경로의 `set-adr.py`), 리프의 근거는 비완전한 힌트라 의무가 아니다.

## 4. 하지 않는 것

- ❌ **자기 하네스 수정** — 이 저장소의 `CLAUDE.md`·`.claude/**`. 개정은 **사람이 밖에서** 한다. hook가 거부한다. 개정 제안이나 사람에게 넘길 초안은 **`tmp/staging/`에 쓴다** — 하네스 밖의 자유 쓰기 경로는 `tmp/`뿐이다.
- ❌ **Issue close** · `Closes` 키워드 · **PR 머지** — hook가 `gh issue close`·`gh pr merge`를 거부한다.
- ❌ **ops-workflow 저장소 파일 쓰기** — 문서(지식 플레인)는 관할 밖. 남길 것은 티켓 코멘트로.
- ❌ 티켓이 정하지 않은 결정의 임의 확정 (§3)

## 5. 강제는 구조로

- 쓰기 경계·close·merge: **PreToolUse hook**(`.claude/hooks/guard-write.py`)가 거부한다.
- PR 생성·force push: 같은 hook가 거부하고 `ticket-pr.py` 관문으로 보낸다.
- 머지 게이트: 대상 저장소의 required check가 거부한다.
- 클러스터 쓰기·Secret 열람: agent 자격증명의 RBAC에 권한이 **없어서** 거부된다 (§2-5).
- 막히면 **우회하지 않고** 왜 막혔는지 읽는다. hook가 잘못됐다고 판단되면 그것도 사람에게 알린다 — 고치는 것은 agent가 아니다. 구체적 수정안이 있으면 `tmp/staging/`에 써서 넘긴다(§4).
