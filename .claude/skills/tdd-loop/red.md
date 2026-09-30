# 2. red — 실패하는 테스트를 먼저 본다

주 대화가 한다. 승인된 시그니처 · 시나리오 표가 입력이다. 끝은 **red 커밋 + Draft PR + 실행 결과 코멘트**이고, 사람이 PR diff 에서 테스트 본문을 읽고 승인한다.

순서가 있다 — **stub 일괄 → 시나리오 하나씩 → 전체 실행.** stub 을 먼저 다 놓아야 첫 시나리오부터 "카운트조차 안 되는 실패"(import · 컴파일)가 아니라 진짜 red 가 잡힌다.

## 1. stub 을 일괄로 놓는다

시그니처 절의 항목 중 **아직 없는 것** 전부 — 새 함수 · 새 모듈 · 타입의 새 필드 · 바뀌는 시그니처. 컴파일이 살고 · 신규 테스트만 실패하고 · 나머지는 통과하는 **최소**가 하한이다. 본문을 쓰지 않는다.

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

- **Then 은 한 주장 = 한 단언.** 조건을 `and` 로 잇지 않는다(실패하면 어느 조건인지 안 보인다). 단언은 성질이지 값의 복사가 아니다.
- **Given 은 표대로** — fake · mock 은 손으로 만든 최소 입력, 녹화 replay 는 저장소의 replay 장치, 실제 연결은 저장소가 정한 방식. **모킹은 테스트마다 격리**한다(전역 · 모듈 캐시를 오염시키면 다른 테스트가 깨진다 — 저장소의 `beforeEach`/fixture 관례대로).

### (b) 그것만 돌린다

저장소의 테스트 명령에 필터를 건다 — `pytest -k <이름>` · `go test -run <이름> ./...` · `npx vitest run <파일> -t "<이름>"`. 전체는 마지막에.

### (c) 실패의 종류를 본다

| 실패 | 뜻 | 하는 것 |
|---|---|---|
| stub 의 `NotImplementedError` / `panic` / `not implemented` 에 닿았다 | **의도된 red** — 가장 흔하다 | 다음 행 |
| 단언 실패(`expected X, got Y`) — 기존 코드가 시나리오와 다르게 동작 | **의도된 red** | 다음 행 |
| `ImportError` · `Cannot find module` · 컴파일 오류 · `is not a function` | **red 가 아니다** — 카운트조차 안 됐다. stub 이 모자라거나 시그니처가 안 맞는다 | stub 을 보강한다(§1). 이 상태로 다음 행에 가지 않는다 |
| 문법 오류 · import 경로 오타 · 모킹 설정 실수 | **테스트 표현의 문제** | 테스트를 고친다 — 시나리오를 바꾸는 것이 아니다 |
| **통과했다** | 종류가 `가드` 면 정상. 아니면 **동어반복 후보** — 항상 참인 단언 · stub 이 우연히 만족시키는 단언(`None` 을 돌려주는데 `is None`) · 아무것도 부르지 않는 테스트 · 우연히 맞는 mock 반환값 | 단언을 구체화해 다시 돌린다. 그래도 통과하면 시나리오가 틀린 것 — 사람에게 |

의심스러우면 한 줄 기록해 둔다(결과 코멘트에 들어간다): `#3 — NotImplementedError(parse) 로 실패, 의도 일치`.

## 3. 전체를 한 번 돌린다

- **신규 전부 fail**(`가드` 제외 — 그것은 pass 여야 한다) · **기존 전부 pass**.
- 기존이 깨졌으면 stub 부족 · 시그니처 변경의 호출자 · **모킹 오염** 중 하나다 — 테스트 쪽에서 고친다. 구현 코드로 고치지 않는다.
- 표의 행 수와 쓴 테스트 수를 **1:1 로 대조**한다 — 빠진 행이 없는지.

## 4. 커밋 하나

```bash
git add -A && git commit -m "test(#<N>): red — 시나리오 <k>개 (가드 <g>개)"
```

이 커밋의 소스 diff 가 곧 stub 목록이다 — verifier 와 사람이 읽는다. 테스트와 stub 을 커밋 둘로 나누지 않는다.

## 5. Draft PR 을 연다

```bash
ticket-pr.py <N> --draft --title "<티켓 제목 또는 그 요지>" --body-file tmp/pr/<N>.md
```

본문은 링크와 체크리스트뿐 — 표를 복사하지 않는다(사본은 낡는다). `Closes` 연결은 도구가 덧붙인다.

```markdown
TDD — 시나리오: <시나리오 코멘트 URL>

- [x] red
- [ ] green
- [ ] refactor
- [ ] verify
```

red 커밋의 **CI 는 빨강**이다 — 의도된 것이고 "신규 테스트가 실제로 실패했다" 의 증거다. 머지 게이트는 마지막 커밋의 런을 본다.

## 6. 실행 결과를 코멘트로

티켓에 **새 코멘트**(GitHub 이슈에는 스레드가 없다):

```markdown
### red — <target repo>

커밋 `<sha>` · PR <URL>

| # | 테스트 | 결과 | 실패 이유 |
|---|---|---|---|
| 1 | `test_parse_rejects_empty` | fail | NotImplementedError(parse) — 의도 |
| 2 | `test_token_env_beats_file` | fail | AssertionError — 기존 코드는 파일 우선 |
| 4 | `test_legacy_note_defaults_tags` | pass | 가드 |

기존 <n>개 통과. 실행: `<테스트 명령>`
```

## 7. 멈춘다 — 승인

사람이 **PR diff 에서 테스트 본문**을 읽고 승인한다 — 시나리오 승인은 티켓에서(*무엇을*), red 승인은 PR 에서(*어떻게*).

- **수정 요청** → 고치고 **새 커밋**(`test(#<N>): red — <무엇을 고쳤나>`)으로 — amend 하지 않는다. 승인 전이므로 red 커밋이 둘이어도 된다; verifier 는 green 전의 커밋 전부를 red 로 읽는다.
- **시나리오가 틀렸음**을 여기서 알게 되면(시그니처가 다르다 · 경계가 하나 더 있다) 조용히 고치지 않는다 — 표를 새 코멘트로 다시 내고 [scenarios.md](scenarios.md) 의 승인으로.

## 하지 않는 것

- 소스 본문. "잘 짜였는지 보려고" 잠깐 구현해 보는 것도 — 그것은 green 의 일이고 다른 컨텍스트가 한다.
- `skip` · `xfail` 로 초록을 만드는 것.
- 실패 이유를 안 보고 "빨강이니 됐다" 로 넘어가는 것 — collect 실패는 red 가 아니다.
- 일괄 작성 뒤 한꺼번에 실행.
