---
name: tdd-loop
description: TDD 집행 순서 — 착수 요약의 판정이 "TDD: 대상"인 티켓에서 코드를 만지기 전에 밟는다. 시나리오 표(코멘트·승인) → red(실패하는 테스트·커밋·Draft PR·승인) → green+refactor(subagent tdd-green) → verify(subagent ac-verifier) → 사람 확인. 판정이 비대상이면 부르지 않는다. 새 세션에서 진행 흔적(시나리오 코멘트·red 커밋·Draft PR)을 발견했을 때도 이 스킬의 재개 절차다.
---

# tdd-loop — 시나리오 → red → green · refactor → verify

**전제**: `ticket-start` 를 마쳤고 착수 요약에 `TDD: 대상 — <근거>` 를 적었다. 이 스킬은 그 뒤, 코드 전이다.

순서가 값이다 — 테스트가 **먼저 실패해야** 그 테스트가 무엇인가를 검사한다는 것을 안다. 단계 제약(red 는 소스를 안 쓴다 · green 은 테스트를 안 고친다)은 **규약**이다: 막는 것은 없고, 지켰는지는 커밋 diff 와 코멘트로 읽힌다. 그러니 커밋을 단계마다 닫는다 — 그것이 읽기 단위다.

## 흐름 — 한눈에

| 단계 | 누가 | 남기는 것 | 끝나면 |
|---|---|---|---|
| **1. 시나리오** | 주 대화(너) | 시그니처 + 시나리오 표(GWT) + AC 커버리지 표 — 티켓 코멘트 | **멈춤 — 사람 승인** |
| **2. red** | 주 대화(너) | red 커밋 · Draft PR · 실행 결과 코멘트 | **멈춤 — 사람 승인** |
| **3. green + refactor** | subagent `tdd-green`(opus) | green 커밋 · refactor 커밋 | 흐름 — 체크리스트 갱신 |
| **4. verify** | subagent `ac-verifier`(Fable) | 대조표 + 발견 — 티켓 코멘트 | **멈춤 — 사람이 다음을 지시** |

승인은 채팅으로 온다. 흔적은 남기지 않는다 — 다음 산출물(red 커밋 · green 커밋)이 곧 흔적이다.

## 단계별 절차 — 그 단계에 들어갈 때 읽는다

- **1. 시나리오** — AC 재조회 · 시그니처(타입 · 함수 · 오류 케이스 · 인터페이스) · GWT 표 · AC 커버리지 · 게시 · 승인: [scenarios.md](scenarios.md)
- **2. red** — stub 일괄 · 한 시나리오씩 · 실패의 종류 · 커밋 · Draft PR · 승인: [red.md](red.md)
- **3. green + refactor** — `tdd-green` 호출 프롬프트 · 결과 블록 · blocked 처리: [green-refactor.md](green-refactor.md)
- **4. verify** — preflight · `ac-verifier` 호출 프롬프트 · 사람 지시 · `ticket-report` 로: [verify.md](verify.md)
- **재개** — 새 세션에서 흔적으로 단계를 판별하고 확인받기: [resume.md](resume.md)

## 상시 규약 — 어느 단계에서든

- **승인 없이 다음 단계로 넘어가지 않는다.** 표 뒤 · red 뒤 · verify 뒤.
- **red 뒤에 소스 본문을 쓰지 않는다. green 뒤에 테스트를 고치지 않는다.** 테스트가 틀렸으면 사람에게 — 승인 뒤 red 로 되돌아간다. 조용히 고쳐 통과시키는 것이 TDD 를 무너뜨리는 정확한 경로다.
- **시나리오는 Given / When / Then 이고, 테스트 코드는 그 세 부분이 구분돼 읽힌다** — 주석 한 줄씩(`# given` · `# when` · `# then`, 저장소가 AAA 를 쓰면 그 이름으로). 이름이 아니라 구분이 규칙이다.
- **시나리오가 틀렸음을 알게 되면** 표를 새 코멘트로 다시 내고 재승인 — 어느 단계에서든.
- **target 이 여럿이면** 판정 · 표 · 흐름은 target 마다다.
- **티켓 코멘트 · PR 본문은 주 대화가 쓴다** — verifier 의 검수 코멘트만 예외(직접 게시). 코멘트 수정은 기록한 ID 로만.
- **verifier 를 건너뛰고 스스로 대조표를 쓰지 않는다.**
- **러너 · 커버리지 도구를 설치하지 않는다** — 저장소의 결정이다. 러너가 없으면 애초에 판정이 비대상이었어야 한다.
