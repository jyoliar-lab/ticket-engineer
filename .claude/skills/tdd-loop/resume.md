# 재개 — 새 세션에서 흔적으로 단계를 읽고, 확인받는다

승인의 흔적은 **없다.** 표가 승인됐는지 · red 가 승인됐는지는 어디에도 기록되지 않는다 — 다음 산출물이 있으면 그 앞은 승인된 것이라고 *추정*할 수 있을 뿐이다. 그러니 재개는 언제나 **파악 → 사람에게 보이고 → 확인 → 진행**이다. 추측으로 이어가지 않는다.

## 흔적을 읽는다

`ticket-run.py <N>` 이 재개 시 보여 주는 것 — 코멘트 전문 · 진행 커밋 · PR — 에서 단계를 판별한다. 부족하면 직접 본다:

```bash
gh issue view <N> -R jyoliar-lab/ops-workflow --json comments -q '.comments[] | "\(.createdAt) \(.url)\n\(.body[:200])\n"'
git -C <worktree> log --oneline origin/<branch>
git -C <worktree> status --porcelain
gh pr view <PR번호> -R <owner/repo> --json isDraft,state,body,statusCheckRollup
```

## 판별표

| 보이는 것 | 지금 어디 | 다음에 물을 것 |
|---|---|---|
| `TDD 시나리오` 코멘트 없음 | 1 이전 | "시나리오부터 시작할까요" |
| 시나리오 코멘트 있음 · 커밋 없음 | 1 게시 후 — **승인 여부 모름** | "이 표가 승인됐습니까, 수정이 필요합니까" |
| `test(#N): red` 커밋 있음 · Draft PR 없음 | 2 도중 | "red 커밋이 있는데 PR 이 없습니다 — 열까요" |
| red 커밋 + Draft PR · green 없음 | 2 게시 후 — **승인 여부 모름** | "red 가 승인됐습니까 — green 을 부를까요" |
| red 커밋 둘 이상 · green 없음 | 2 수정 중 | 위와 같음 + "마지막 red 커밋이 최종입니까" |
| green 없음 · **worktree 에 미커밋 소스 변경** | 3 도중 끊김 또는 blocked 잔여물 | 테스트를 돌려 본다 — 통과한 것이 곧 진행 상태다. "green 도중 끊긴 것으로 보입니다 — 이어서 부를까요, 버릴까요" |
| `green — 중단` 코멘트 있음 | 3 **blocked — 사람 답 대기** | "중단 사유에 대한 판단을 주십시오(시나리오 수정 / AC 수정 / 다시 호출)" |
| green 커밋 있음 · refactor 없음 · 검수 코멘트 없음 | 3 도중 또는 refactor 건너뜀 | 체크리스트에 "건너뜀" 이 적혀 있으면 verify 전. 아니면 "refactor 가 중단된 것입니까" |
| green (+refactor) · 검수 코멘트 없음 | 3 끝 — verify 전 | "verify 를 돌릴까요" |
| 검수 코멘트 있음 · PR 이 Draft | 4 게시 후 — **지시 대기** | "검수 코멘트를 보셨습니까 — ready / 되돌림 / 보완 중 무엇입니까" |
| 검수 코멘트 · PR 이 ready | 4 뒤 — `ticket-report` 4단계 | "검수 중입니까 — 수정 지시가 있습니까" |
| 검수 뒤 **미커밋 테스트 파일** | verifier 의 반증 테스트 잔여물 | 내용을 보이고 지운다 — 커밋하지 않는다 |

**착수 요약의 TDD 판정**이 없는 티켓(이 흐름 도입 전에 시작된 것)은 지금 판정을 적고 사람에게 — 흐름 중간에 들어가지 않는다.

## 확인을 요청하는 문장 — 틀

```
#<N> 재개 — 흔적으로 본 현황:
- 시나리오 코멘트: <URL> (승인 여부는 흔적에 없음)
- 커밋: red <sha> · green <sha> · refactor <없음>
- PR: <URL> (Draft · 마지막 체크 초록)
- 검수 코멘트: 없음 · 중단 코멘트: 없음
- worktree: 깨끗함
판단: 3단계까지 끝나 verify 전으로 보입니다. verify 를 돌릴까요, 아니면 다른 지시가 있습니까?
```

## 이어간다

확인이 오면 그 단계의 파일로 — [scenarios.md](scenarios.md) · [red.md](red.md) · [green-refactor.md](green-refactor.md) · [verify.md](verify.md). 코멘트 ID 는 다시 기록한다(`ticket-run.py` 출력 또는 위 `gh issue view`).

## 하지 않는 것

- "커밋이 있으니 승인됐겠지" 로 다음 단계를 시작하는 것.
- 미커밋 변경을 정리하는 것(`checkout` · `stash`) — 사람이 무엇인지 본 뒤.
- 흐름 중간에 판정 없이 들어가는 것.
