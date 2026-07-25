---
name: ticket-report
description: 티켓 완료 보고 절차 — preflight(PR·참조·close 키워드·게이트) 기계 확인 통과 후, Acceptance Criteria 항목별 대조 코멘트를 초안·확인·게시한다. 작업이 끝났다고 판단되면 이 절차로 보고한다.
---

# ticket-report — 완료 보고

보고 형식의 일관성이 곧 사람의 검수 비용이다. 기계가 확인할 수 있는 것은 스크립트가, 충족 여부의 **의미 판정은 네가** 한다.

## 절차

1. **preflight** — `preflight.py <N> workspace/target/<repo>/ticket-<N>` — **target 저장소마다** 그 worktree에서 실행한다(PR이 여럿이면 각각). (스킬 스크립트는 SessionStart hook가 PATH에 올린다 — bare name으로 실행한다.)
   - ① 현재 브랜치의 열린 PR ② 본문의 `jyoliar-lab/ops-workflow#<N>` 참조 ③ close 키워드 부재 ④ 게이트(체크) 통과 ⑤ 이 저장소가 티켓 target 목록에 있음 — 하나라도 실패면 **보고하지 않는다.** 해결 후 재실행.
   - ⑤가 실패하면 코드가 아니라 **티켓이 낡은 것**일 수 있다 — 작업 중 수정 범위가 늘었는데 target 목록을 갱신하지 않았다면, 사람과 합의해 목록부터 갱신한다(CLAUDE.md §3 — 갱신 필수).
2. **대조표 초안** — 착수 때 추출한 **Acceptance Criteria 각 항목별로**: 항목 | 충족 방식 | 근거(코드 위치·확인 방법). PR 링크 포함 — **target 저장소별로 전부**.
   - 충족 못 한 항목이 있으면 보고가 아니라 **사람과 논의**가 먼저다.
   - Requirements의 범위 밖 축에 닿았던 일이 있으면 그 경위를 명시한다(원칙은 닿기 전에 멈추는 것 — CLAUDE.md §3).
3. **사용자 확인** — 초안을 보여 확인받는다. 코멘트는 컨트롤 플레인에 공표되는 원자료다 — 초안 없이 쏘지 않는다.
4. **게시** — `gh issue comment <N> -R jyoliar-lab/ops-workflow --body "..."`
5. **이후는 사람의 것** — 검수·머지·close. 재촉하지 않고 다음 지시를 기다린다.

## preflight는 완료를 판정하지 않는다

스크립트가 통과해도 Acceptance Criteria가 충족됐는지는 별개다 — 그 판정은 2단계에서 네가 코드·동작을 근거로 한다. 애매하면 사용자에게 근거를 제시하고 묻는다.
