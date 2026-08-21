---
name: ticket-start
description: 티켓 착수·재개 절차 — 티켓·근거 문서 읽기, Acceptance Criteria·Requirements 추출, ticket-run.py로 원격 브랜치·로컬 worktree 정렬. 사람이 티켓 번호를 지정하면 코드를 만지기 전에 이 절차부터 밟는다.
---

# ticket-start — 착수·재개

낡은 코퍼스·오염된 브랜치 위에서 일하지 않기 위한 고정 순서다. 판단(티켓 이해·설계)은 네 것이고, 이 skill은 그 전에 밟을 바닥을 깐다.

## 절차

1. **티켓 읽기** — `gh issue view <N> -R jyoliar-lab/ops-workflow --json title,body,comments` — **`--json`으로 읽는다.** 사람용 기본 출력은 간헐적으로 exit 0인 채 빈 stdout을 낸다(pager/tty 상호작용 추정) — 빈 출력을 "코멘트 없음"으로 오판하지 말고 `--json`으로 읽는다.
2. **경계 추출** — 티켓에서 두 절을 **그대로 옮겨 적는다**(요약하지 않는다):
   - **Acceptance Criteria** — 검수 기준이다. 그대로 `ticket-report`의 대조표 행이 된다.
   - **Requirements** — 지켜야 할 제약과 **의도적 미결정 축**("~은 범위 밖이다" 항목들)이다. 작업 중 그 축에 닿으면 **멈추고 사람에게**(CLAUDE.md §3). ("없음"이면 그대로 기록한다 — 빈칸과 다르다.)
   - **코멘트도 경계다** — 추가 요구·방향 수정은 본문이 아니라 코멘트로 오기도 한다. 코멘트에 요구·제약이 있으면 위 두 절과 **같은 무게로** 옮겨 적는다. (`ticket-run.py`도 실행 시 코멘트 전문을 다시 보인다 — 착수 후 쌓인 코멘트는 재개 시 그 출력으로 들어온다.)
3. **근거 읽기** — 본문 **'근거 ADR' 절**(YAML의 `path`)이 가리키는 문서를 `workspace/ref/ops-workflow/`에서 읽는다. 절이 없는 리프는 **Context가 "왜"의 전부다** — discussion은 티켓에 링크되지 않는다. (ref 경로는 SessionStart hook가 세션 시작 시 최신화했다. 읽기 전용 — 저작 규약은 알 필요 없다.)
4. **저장소 정렬** — 판단하지 말고 스크립트를 돌린다:
   ```bash
   ticket-run.py <N> [--slug <slug>]
   ```
   착수(원격 linked branch 생성·Status 전환)와 재개(진행 보고·worktree 정렬)를 스크립트가 판별한다 — 원격이 진실의 원천이고, target 저장소마다 수행된다. `--slug`는 새 착수에만 필요하다(소문자 kebab 3–6단어).

   **exit 코드가 다음 행동이다** — `0` 진행 / `1` 전제 거부 / `2` 제안 후 승인받아 진행 / `3` 보고만. **사유와 할 일은 스크립트가 그 자리에서 말한다** — 읽고 그대로 한다. 우회하지 않고, 파괴적 정리(`reset --hard`·`stash drop`·강제 checkout)는 exit가 무엇이든 하지 않는다.
   - 착수에는 게이트가 있다 — **계층 전체**(리프+부모)의 근거 ADR accepted + Status 비Draft. 거부 해소(ADR accept·Draft 해제·부모 되돌림)는 전부 사람의 일이다 — 보고하고 기다린다.
   - 구식 티켓에 '저장소' 절을 소급 기입할 때, 대상 저장소는 **넓게 탐색해 특정한다**: `gh org list`로 접근 가능한 조직을 전부 확인하고, 조직·개인 계정별로 `gh repo list <owner>`·`gh search repos`로 찾는다 — 한두 owner만 보고 "없다 → 신규 생성"으로 판단하지 않는다. 단서가 없으면 추측하지 말고 사람에게 묻는다.
5. **작업 위치** — `workspace/target/<repo>/ticket-<N>/` (티켓별 worktree). 다른 티켓의 worktree·`workspace/target/.bare/`는 건드리지 않는다. 티켓에 나열된 ref는 ticket-run이 `workspace/ref/<repo>`에 **선제 clone해 뒀다** — ref는 비완전 목록이므로, 나열 밖 저장소가 더 필요하면 같은 경로에 직접 clone한다. ref는 **읽기만** — hook가 쓰기를 거부한다. PR 본문 초안은 `tmp/pr/`에 쓴다(`ticket-pr.py --body-file`).
6. **착수 요약** — 경계 2절 + 스크립트가 보인 상태 + 이해한 작업 계획을 사용자에게 보인다. 계획이 티켓과 어긋날 소지가 보이면 진행 전에 묻는다.

## 뒷정리 — 사람이 close를 확인한 뒤에만

```bash
ticket-clean.py <N>
```
worktree·브랜치(로컬·원격)를 정리한다. **자동 실행 금지 — 사람의 지시가 트리거다.** 조기 정리는 스크립트가 거부한다.
