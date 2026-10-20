# 3. green + refactor — subagent 를 부르고, 돌아온 것을 처리한다

주 대화는 여기서 **구현하지 않는다.** subagent `tdd-green`(`.claude/agents/tdd-green.md` · opus)이 한다 — 무엇을 어떻게 하는지는 그 정의가 전부 갖고 있다. 여기는 **부르는 법**과 **복귀 처리**뿐이다.

## 호출

**실패한 신규가 없으면 부르지 않는다** — 진행 표에 green 행 `건너뜀(실패 신규 없음)` 을 덧붙이고 [verify.md](verify.md) 로.

Agent 도구 · `subagent_type: tdd-green`. 입력과 반환 요청만 — 규칙은 agent 정의에 있으므로 프롬프트에 되풀이하지 않는다.

```
티켓 #<N> (<Task|Bug>) · target <owner/repo> · 단위 <단위>
worktree: <절대 경로 — workspace/target/<repo>/ticket-<N>/>
red 커밋: <sha>[, <sha>] (검토 완료 — 보강 커밋 포함 · 이 단위의 것만)
테스트 명령: <예: python -m pytest / go test ./... / npm test>

red 커밋의 테스트를 통과시키고 정리한 뒤 push 하라. 정의된 결과 블록 하나로 돌려달라.
```

단위 이름은 커밋 메시지에만 쓰인다. 앞 단위의 green 이 이미 머지 전 브랜치에 있어도 상관없다 — 이 단위의 red 커밋이 가리키는 테스트만이 이번 요구다.

**넣지 않는 것**: 티켓 본문 · AC · 시나리오 표 · 시나리오 코멘트 URL · 네가 red 를 쓰며 가졌던 구현 생각 · "이 테스트는 X 를 검사한다" 류의 설명.

**target 이 여럿이면** target 마다 따로 부른다 — worktree 가 다르다.

## 복귀

돌아오는 것은 고정 결과 블록 하나다. 블록 밖의 산문으로 판단하지 않는다. `result` 로 갈린다.

### `result: ok`

새 코멘트는 **없다** — 단위 코멘트의 진행 행과 커밋이 흔적이다.

1. 커밋이 원격에 있는지: `git -C <worktree> log --oneline origin/<branch> -3`.
2. 테스트 명령을 **네가 한 번 더 돌린다** — subagent 의 보고를 그대로 믿지 않는다. 전부 통과가 아니면 아래 blocked 와 같이 다룬다.
3. 단위 코멘트의 진행 표에 green 행 하나 — green 과 refactor 를 함께(한 subagent 가 한 번에 한 일이다), 수만:
   ```bash
   scenario-post.py <N> --repo <owner/repo> --progress "<단위>" green "`<green sha>` · refactor `<sha>`(항목 k) 또는 건너뜀(<이유>) · `<테스트 명령>` → pass <n> / fail 0"
   ```
4. [verify.md](verify.md) 로.

### `result: blocked`

멈춘다. 네가 닫을 결정이 아니다.

1. 블록의 `blocked_on` · `blocked_reason` · `last_error` · `suggest` 와, subagent 가 남긴 미커밋 변경(`git -C <worktree> status --porcelain`)을 본다.
2. **티켓에 코멘트를 남긴다** — 세션이 끊겨도 흔적이 남게. 사람 결정으로 미통과를 남긴 채 커밋했을 때도 같은 꼴. **실패한 것만** 이름 — 통과 목록은 쓰지 않는다. 그리고 채팅으로 사람에게:
   ```markdown
   ### green — 중단 | 부분 — <단위> · <target repo>

   커밋 `<sha 또는 없음>` · PR <URL>
   실행: `<테스트 명령>` → pass <n> / fail <m>
   미통과: `<이름>` — <한 줄 이유> (행 <k>)
   제안: <시나리오 재검토 · 시그니처 수정 · 사람 디버깅>
   worktree 미커밋 변경: <k>파일 (그대로 둠) | 없음
   ```
3. **테스트를 고치지 않는다.** 사람의 답에 따라:
   - **시나리오 · 테스트가 틀렸다** → 미커밋 변경을 버리고(`git -C <worktree> checkout -- .` — 사람 승인 뒤) 그 단위의 파일을 고쳐 `scenario-post.py` 로 PATCH, [scenarios.md](scenarios.md) §5 의 재승인으로. 그 뒤 [red.md](red.md) 의 흐름대로 — 새 red 커밋 → 검토자 → red 행.
   - **AC 가 틀렸다** → 티켓 갱신은 사람과(CLAUDE.md §3). 갱신 뒤 시나리오부터.
   - **구현이 부족했을 뿐이다** → 사람의 힌트를 **프롬프트에 넣지 않고** 다시 부른다. 힌트가 필요할 정도면 테스트가 명세로 부족한 것이니, 그 힌트는 테스트에 들어가야 한다 — 다시 시나리오로.
   - **새 의존성이 필요하다** → 설치는 저장소의 결정(CLAUDE.md §2④ 조사 후 설치). 사람이 승인하면 red 로 돌아가 의존성을 반영한 뒤 다시.

## 하지 않는 것

- 주 대화가 소스를 쓰는 것 — "조금만 고치면 되는데" 도 안 된다. 다시 부른다.
- subagent 의 결과를 실행 없이 믿는 것.
- blocked 를 힌트로 풀려는 것 — 힌트는 테스트에 들어가야 한다.
- blocked 를 채팅으로만 보고하고 코멘트를 안 남기는 것 — 중단 코멘트는 사람에게 가는 알림이라 진행 행이 아니라 별도 코멘트다.
