# 4. verify — 다른 눈이 읽고, 사람이 결론을 낸다

주 대화는 여기서 **판정하지 않는다.** `preflight.py` 로 기계 확인을 지나고, subagent `ac-verifier`(`.claude/agents/ac-verifier.md` · Fable)를 부르고, 사람의 지시를 기다린다. verifier 가 무엇을 검사하는지는 그 정의가 전부 갖고 있다. **단위마다** 한 번이다 — 그 단위의 담당 AC 만 대조한다.

## preflight 먼저

```bash
preflight.py <N>
```

기계 확인이 막히면 verifier 를 돌릴 이유가 없다. TDD 흐름에서 지금 상태는 이래야 한다:

- Draft PR 이 열려 있다(① 통과 — Draft 도 OPEN 이다).
- 마지막 커밋(refactor 또는 green)의 체크가 초록이다(④). **red 커밋의 빨강은 지나간 런**이라 보지 않는다 — 진행 중이면 기다린다.
- target 마다 worktree 가 있다(⑤ ⑥).

막히면 해결한 뒤 재실행. 막힌 것이 티켓이면 사람과(CLAUDE.md §3).

## 호출

Agent 도구 · `subagent_type: ac-verifier`. green 과 달리 **맥락을 전부 준다** — verifier 는 대조가 일이다. 검사 항목은 되풀이하지 않는다.

```
티켓 #<N> · target <owner/repo> · 단위 <단위>
worktree: <절대 경로>
시나리오 코멘트: <단위 코멘트 URL> (v<n>)
색인 코멘트: <URL — 단위 하나면 "없음">
커밋: red <sha>[, <sha>] · green <sha> · refactor <sha 또는 건너뜀>   (이 단위의 것)
PR: <URL>
테스트 명령: <…>

이 단위의 담당 AC 를 검수하고 티켓 #<N> 에 직접 게시한 뒤 코멘트 URL 만 돌려달라.
```

**target 이 여럿이면** target 마다 부른다 — 코멘트도 target 마다 · 단위마다다.

## 복귀

돌아오는 것은 **코멘트 URL 한 줄**이다. 산문이 붙어 있어도 그것으로 판단하지 않는다 — 코멘트가 정본이다.

1. 코멘트가 실제로 게시됐는지 본다(`gh issue view <N> -R jyoliar-lab/ops-workflow --json comments` 의 마지막).
2. verifier 가 반증 테스트를 worktree 에 남기지 않았는지 본다: `git -C <worktree> status --porcelain` 이 비어 있어야 한다. 남았으면 지운다 — 커밋하지 않는다.
3. 단위 코멘트의 진행 표에 verify 행 하나 — 검수 코멘트 링크:
   ```bash
   scenario-post.py <N> --repo <owner/repo> --progress "<단위>" verify "<verifier 코멘트 URL>"
   ```

## 멈춘다 — 사람의 지시

사람이 verifier 코멘트를 읽고 다음을 정한다. **너는 결론을 내지 않는다** — 대조표의 ✅/❌ 는 "테스트가 있고 통과한다" 의 기록이지 검수의 결론이 아니다.

| 지시 | 네가 하는 것 |
|---|---|
| **다음 단위** | 다음 승인된 단위로 [red.md](red.md). 승인된 단위가 없으면 [scenarios.md](scenarios.md) §5 에서 기다린다 |
| **ready** — 마지막 단위의 verify 뒤 | `gh pr ready <PR번호> -R <owner/repo>` — Draft 를 푼다. 그 뒤 [ticket-report](../ticket-report/SKILL.md) 4단계(게시 후 검수 · 지정 수정)부터. 2·3단계(대조표 작성 · 게시)는 단위마다의 verifier 코멘트가 대신했다 |
| **표가 틀렸다** (verifier 의 첫 묶음 · 시나리오 후보) | 그 단위의 파일을 고쳐(행 추가 · 결번 · 선언 수정) `scenario-post.py` 로 PATCH → [scenarios.md](scenarios.md) §5 재승인 → [red.md](red.md) 의 흐름대로(새 red 커밋 → 검토자 → red 행) → green 다시 호출. PR 은 그대로 Draft |
| **구현이 틀렸다** (둘째 묶음) | 반증을 행으로 더해 그 단위 재승인 → red(검토자 포함) → green. 테스트가 통과하는 구현을 "고쳐 달라" 고만 green 에 보내지 않는다 — 고칠 근거는 테스트에 있어야 한다 |
| **사람에게** 묶음 | AC · Technical Notes 갱신은 사람과(CLAUDE.md §3). 갱신 뒤 그 단위의 시나리오부터 |

**`gh pr ready` 는 지시 뒤다.** 지시 전에 풀지 않는다 — Draft 가 "아직 사람이 안 봤다" 의 표식이다. 단위가 남아 있는데 ready 가 오면 남은 단위를 한 줄로 말하고 확인을 받는다.

## 하지 않는 것

- verifier 를 건너뛰고 스스로 대조표를 쓰는 것.
- verifier 의 발견을 스스로 판정해 닫는 것("이 정도 하드코딩은 괜찮다") — 사람의 것.
- 지시 전 `gh pr ready` · 머지 · close.
