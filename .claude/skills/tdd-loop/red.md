# 2. red — 실패하는 테스트를 먼저 본다

주 대화가 쓴다. 승인된 시그니처 · 시나리오 표가 입력이다. 끝은 **red 커밋 → `tdd-red-reviewer` 복귀 → Draft PR + 완료 코멘트**이고, 그대로 green 으로 흐른다. red 에서 사람 승인은 없다 — 시나리오 승인이 *무엇을* 검사하나를 정했고, *어떻게* 검사하나는 검토자가 본다.

순서가 있다 — **stub 일괄 → 시나리오 하나씩 → 전체 실행 → 커밋 → 검토자 → PR · 코멘트.** stub 을 먼저 다 놓아야 첫 시나리오부터 "카운트조차 안 되는 실패"(import · 컴파일)가 아니라 진짜 red 가 잡힌다.

## 1. stub 을 일괄로 놓는다

시나리오 코멘트의 **`#### 타입 · 상수` 블록과 각 시나리오 블록 머리의 선언 fence 를 그대로 옮겨 적는다** — 그것들이 stub 목록이다. 아직 없는 것 전부 — 새 함수 · 새 모듈 · 타입의 새 필드 · 바뀌는 시그니처. 컴파일이 살고 · 신규 테스트만 실패하고 · 나머지는 통과하는 **최소**가 하한이다. 본문을 쓰지 않는다(`...` 자리에 raise/panic/throw).

| 언어 | stub |
|---|---|
| Python | `def parse(text: str) -> Doc:\n    raise NotImplementedError("parse")` — import 오류는 파일 단위라 stub 없이도 red 가 서는 경우가 많다 |
| Go | `func Parse(text string) (Doc, error) { panic("TODO: Parse") }` — 컴파일이 안 되면 **패키지 전체**가 돌지 않아 기존 테스트 통과를 확인할 수 없다. 시그니처는 반드시 |
| TypeScript | `export function parse(text: string): Doc { void text; throw new Error("not implemented: parse"); }` — 타입 검사가 CI 에 있으면 타입까지. 컴포넌트는 반환 타입을 명시해야 JSX 에서 쓰인다 |

- **타입에 필드 추가**는 추가만 — 동작을 바꾸지 않는다.
- **금지**: `if` · 값을 돌려주는 `return` · 상태 갱신. stub 의 마지막 줄은 언제나 throw/panic/raise 다. "if 하나만 넣으면 돌 텐데" 가 들면 그것이 green 의 시작이다 — 멈춘다.
- 기존 시그니처를 바꾸는 시나리오면 **호출자의 컴파일이 살 만큼만** 손댄다.

## 2. 시나리오를 하나씩 — 쓰고 · 그것만 돌리고 · 실패 이유를 본다

표의 순서대로(정상 → 경계 → 예외 → 가드). 한 행을 끝내기 전에 다음 행의 코드를 쓰지 않는다 — 일괄로 쓰고 한꺼번에 빨강을 보면 어느 실패가 어느 시나리오의 것인지, 부수효과인지 분간이 안 된다.

### (a) 쓴다

- **표의 테스트 이름 그대로.** 이름이 저장소 규약과 맞지 않으면 표를 고치고 재승인이지, 이름을 슬쩍 바꾸는 것이 아니다.
- **저장소의 테스트 규약**을 따른다 — `.claude/rules/*` · `CLAUDE.md` · 기존 테스트의 자리와 모양 · 메타테스트. 하네스가 아니라 저장소가 정한 것이다.
- **Given / When / Then 을 코드에서 구분해 보이게 쓴다.** 표의 세 칸이 그대로 세 부분이다. 주석 한 줄씩(`# given` · `# when` · `# then` / `// given …`)으로 나누고, 저장소가 AAA(arrange · act · assert)를 쓰면 그 이름으로 — **이름이 아니라 구분이 규칙이다.** 짧아도 세 부분은 보여야 한다. docstring(또는 it 문장)은 Then 을 현재형으로 말한다.

  ```python
  def test_token_env_beats_file(monkeypatch, tmp_path):
      """env 의 토큰이 파일의 토큰을 이긴다."""
      # given — env 에도 파일에도 토큰이 있다
      monkeypatch.setenv("OBS_TOKEN", "from-env")
      (tmp_path / "obs.toml").write_text('token = "from-file"')
      # when
      cfg = Config.load(config_dir=tmp_path)
      # then
      assert cfg.token == "from-env"
  ```

- **단언과 Given 은 [strength.md](strength.md) 의 "쓸 때" 절대로.** 성질마다 단언 한 줄 · 결과를 골라 단언 · 긍정이 먼저 · Then 의 어휘 그대로 · 규칙이 갈리는 Given · 정적 대역 · 모킹 격리. 알려진 약함의 패턴 일곱이 거기 있다 — 보이면 그 자리에서 고쳐 쓴다. 검토자가 같은 파일의 원리로 판정한다.

### (b) 그것만 돌린다

저장소의 테스트 명령에 필터를 건다 — `pytest -k <이름>` · `go test -run <이름> ./...` · `npx vitest run <파일> -t "<이름>"`. 전체는 마지막에.

### (c) 실패의 종류를 본다

| 실패 | 뜻 | 하는 것 |
|---|---|---|
| stub 의 `NotImplementedError` / `panic` / `not implemented` 에 닿았다 | **의도된 red** — 가장 흔하다 | 다음 행 |
| 단언 실패(`expected X, got Y`) — 기존 코드가 시나리오와 다르게 동작 | **의도된 red** | 다음 행 |
| `ImportError` · `Cannot find module` · 컴파일 오류 · `is not a function` | **red 가 아니다** — 카운트조차 안 됐다. stub 이 모자라거나 시그니처가 안 맞는다 | stub 을 보강한다(§1). 이 상태로 다음 행에 가지 않는다 |
| 문법 오류 · import 경로 오타 · 모킹 설정 실수 | **테스트 표현의 문제** | 테스트를 고친다 — 시나리오를 바꾸는 것이 아니다 |
| **통과했다** | 종류가 `가드` 면 정상. 아니면 **동어반복 후보** — 모양은 [strength.md](strength.md) 패턴 표의 마지막 행 | 단언을 구체화해 다시 돌린다. 그래도 통과하면 시나리오가 틀린 것 — 표를 새 코멘트로 다시 내고 [scenarios.md](scenarios.md) 의 승인으로 |

의심스러우면 한 줄 기록해 둔다(완료 코멘트에 들어간다): `#3 — NotImplementedError(parse) 로 실패, 의도 일치`.

## 3. 전체를 한 번 돌린다

- **신규 전부 fail**(`가드` 제외 — 그것은 pass 여야 한다) · **기존 전부 pass**.
- 기존이 깨졌으면 stub 부족 · 시그니처 변경의 호출자 · **모킹 오염** 중 하나다 — 테스트 쪽에서 고친다. 구현 코드로 고치지 않는다.
- 표의 행과 테스트를 **대조**한다 — 빠진 행이 없는지. parametrize 로 접은 행은 `[id]` 마다 하나.

## 4. 커밋 하나

```bash
git add -A && git commit -m "test(#<N>): red — 시나리오 <k>개 (가드 <g>개)"
```

이 커밋의 소스 diff 가 곧 stub 목록이다 — 검토자와 verifier 가 읽는다. 테스트와 stub 을 커밋 둘로 나누지 않는다. **여기서 push · PR · 코멘트는 아직이다** — red 의 끝은 검토자 복귀 뒤다.

## 5. 검토자를 부른다 — `tdd-red-reviewer`

Agent 도구 · `subagent_type: tdd-red-reviewer`. 무엇을 어떻게 검토하는지는 agent 정의가 전부 갖고 있다 — 여기는 부르는 법과 복귀 처리뿐이다.

```
티켓 #<N> · target <owner/repo>
worktree: <절대 경로 — workspace/target/<repo>/ticket-<N>/>
시나리오 코멘트: <URL>
red 커밋: <sha>[, <sha>]
테스트 명령: <예: python -m pytest / go test ./... / npm test>

표와 대조하고 변별력을 판정해 보강한 뒤, 정의된 결과 블록 하나로 돌려달라.
```

**넣지 않는 것**: 티켓 본문 · AC · 네가 red 를 쓰며 가졌던 의도 · "이 테스트는 X 를 검사한다" 류의 설명. 표가 명세다 — 표에 없는 의도는 표의 구멍이고, 검토자가 메울 것이 아니다.

**target 이 여럿이면** target 마다 따로 부른다.

### 복귀 — `result: ok`

1. 테스트 명령을 **네가 한 번 더 돌린다** — 신규 fail(가드 pass) · 기존 pass. subagent 의 보고를 그대로 믿지 않는다.
2. 보강 커밋(`reinforced`)이 있으면 `git -C <worktree> log --oneline -3` 으로 확인한다. 되돌리지 않는다 — 보강은 표를 더 정확히 가르는 것이고, 이상해 보이면 `fixed` 의 패턴 이름으로 [strength.md](strength.md) 를 읽는다.
3. §6 으로.

### 복귀 — `result: blocked`

표의 문제다 — 네가 테스트로 메우지 않는다.

1. `blocked_on` · `blocked_reason` · `suggest` 를 읽는다. 보강 커밋이 함께 왔으면 그것은 유효하다 — 남긴다.
2. 표를 **새 코멘트**로 다시 낸다 — 머리 한 줄 `v<n> — <무엇이 바뀌었나> · 앞 코멘트 <URL> 를 대체`. [scenarios.md](scenarios.md) §5 의 승인으로 — 사람이 재승인하면 바뀐 행만 red 를 다시 쓰고(§2) **새 커밋**으로 올린 뒤 검토자를 다시 부른다(§5). amend 하지 않는다 — green 전의 커밋 전부가 red 다.
3. `blocked_reason` 이 `소스 본문 포함` 이면 네 red 커밋이 stub 범위를 넘은 것이다 — 본문을 raise/panic/throw 로 되돌린 **새 커밋** 뒤 다시 §5.

## 6. Draft PR 을 연다

```bash
ticket-pr.py <N> --draft --title "<티켓 제목 또는 그 요지>" --body-file tmp/pr/<N>.md
```

도구가 `Closes jyoliar-lab/ops-workflow#<N>` 줄을 `tmp/pr/<N>.md` 에 되쓴다 — 체크리스트를 갱신할 때 그 줄을 지우지 않는다. Draft 인 동안 이슈의 Development 연결은 비어 있다 — ready 전환 때 생긴다.

본문은 링크와 체크리스트뿐 — 표를 복사하지 않는다(사본은 낡는다). `Closes` 연결은 도구가 덧붙인다.

```markdown
TDD — 시나리오: <시나리오 코멘트 URL>

- [x] red
- [ ] green
- [ ] refactor
- [ ] verify
```

red 커밋들의 **CI 는 빨강**이다 — 의도된 것이고 "신규 테스트가 실제로 실패했다" 의 증거다. 머지 게이트는 마지막 커밋의 런을 본다.

## 7. 완료 코멘트

티켓에 **새 코멘트**. 검토 뒤의 최종 수다. 수와 예외만 — **테스트를 전부 나열하지 않는다**(원천은 러너 출력과 diff). 보강 여부는 따로 말하지 않는다 — 커밋이 흔적이다. 한 화면:

```markdown
### red — <target repo>

커밋 `<sha>`[ · `<sha>`] · PR <URL> (Draft)
실행: `<테스트 명령>` → 신규 <n>: fail <f> · pass <p>(가드) · 기존 <m> pass
stub: <모듈 — 함수 k 개 · 타입 j 개 — 한 줄>

예외: 없음
```

예외가 있을 때만 표 — **기대와 다른 행만**:

```markdown
| # | 테스트 | 결과 | 왜 |
|---|---|---|---|
| 12 | `test_y` | fail | stub 이 아니라 AssertionError — 기존 코드가 파일 우선(의도된 red) |
```

`주의:` 는 사람이 다음 결정에 필요한 것만 한 절 — 테스트 하네스(conftest · 레시피)를 바꿨다 · green 이 fixture 를 재녹화해야 한다. 한 것의 서술이 아니다.

이 코멘트가 **"검토까지 끝났다"** 의 흔적이다 — 재개 때 새 세션이 이것으로 red 의 끝을 안다.

## 8. green 으로

멈추지 않는다. [green-refactor.md](green-refactor.md) 로.

## 하지 않는 것

- 소스 본문. "잘 짜였는지 보려고" 잠깐 구현해 보는 것도 — 그것은 green 의 일이고 다른 컨텍스트가 한다.
- `skip` · `xfail` 로 초록을 만드는 것.
- 실패 이유를 안 보고 "빨강이니 됐다" 로 넘어가는 것 — collect 실패는 red 가 아니다.
- 일괄 작성 뒤 한꺼번에 실행.
- 검토자 복귀 전에 push · PR · 코멘트. 검토자를 건너뛰고 green 으로 가는 것.
- 검토자의 보강 커밋을 되돌리거나 amend 하는 것.
- blocked 를 테스트 수정으로 푸는 것 — 표의 문제는 표에서.
