### TDD 시나리오 — jyoliar-lab/obs-toolkit

#### 타입 · 상수

```python
# obs/core.py — 변경. config_file_candidates · load_config 는 이름 · 형태 불변

@dataclass
class Config:
    config_path: Path | None                  # None = 설정 파일 없이 기본값
```

관례: 깨진 JSON 과 같은 결 — `_read_config_file` 의 `ObsError("… — 사람에게")`. 공개 이름은 바뀌지 않는다.

#### 인터페이스

```
env OBS_CONFIG=<path>     의미 불변 — 이제 부재가 오류
bin/obs-doctor.py         같은 오류로 exit 1 (main_guard 그대로)
```

---

#### load_config

```python
def load_config(env: Mapping[str, str] | None = None, home: Path | None = None) -> Config: ...
    # ObsError: OBS_CONFIG 가 비어 있지 않은데 그 경로가 파일이 아니다(없음 · 디렉터리) — 문구에 경로 · OBS_CONFIG
    # no-op: 암묵 후보(${CLAUDE_PLUGIN_DATA}/config.json · ~/.config/obs-toolkit/config.json)가 없는 것 · OBS_CONFIG 가 공백뿐
```

- 더하는 것: 명시 경로(`OBS_CONFIG`)와 암묵 후보를 다르게 다룬다

**예외**

| # | Given | When | Then | 출처 | 테스트 이름 | 티어 | 의존성 |
|---|---|---|---|---|---|---|---|
| 1 | `OBS_CONFIG` 가 없는 경로 / 디렉터리 | `load_config(env, home)` | `ObsError` · 문구에 그 경로 · 문구에 `OBS_CONFIG` · 기본값으로 가지 않는다 (재현) | AC-1 | `test_missing_explicit_config_is_an_error[missing·directory]` | contracts | fake(env · tmp) |
| 2 | `OBS_CONFIG` 는 없는 경로 · 암묵 후보에는 유효 파일 | `load_config(env, home)` | `ObsError` — 암묵 후보로 넘어가지 않는다 | 추가 | `test_missing_explicit_config_does_not_fall_back` | contracts | fake(env · tmp) |

**가드**

| # | Given | When | Then | 출처 | 테스트 이름 | 티어 | 의존성 |
|---|---|---|---|---|---|---|---|
| 3 | `OBS_CONFIG` 없음 · 암묵 후보 전부 없음 | `load_config(env, home)` | 기본값 · `config_path is None` | AC-2 | 기존: `test_defaults_when_nothing_set` | contracts | — |
| 4 | `OBS_CONFIG` 가 공백뿐 · 암묵 후보 전부 없음 | `load_config(env, home)` | 미설정과 같다 — 기본값 | 추가 | `test_blank_explicit_config_is_unset` | contracts | fake(env · tmp) |

---

#### doctor_main (+ main_guard)

```python
def doctor_main(argv: Sequence[str] | None = None) -> None: ...    # 변경 없음 — ObsError 는 main_guard 가 exit 1
```

- 더하는 것: `load_config` 의 `ObsError` 를 삼키지 않는다 → exit 1. 문구는 다시 검사하지 않는다(1 의 것)

**예외**

| # | Given | When | Then | 출처 | 테스트 이름 | 티어 | 의존성 |
|---|---|---|---|---|---|---|---|
| 5 | os.environ 의 `OBS_CONFIG` 가 없는 경로 · `doctor` 는 정상 보고서 대역 | `main_guard(lambda: doctor_main([]))` | exit 1 | AC-3 | `test_doctor_main_exits_1_on_missing_explicit_config` | contracts | fake(env · doctor) |

---

티어 · 의존성 — 단언이 전부 예외 · dataclass 값 · exit 코드라 contracts. 5 에서 `doctor` 를 대역으로 바꾸는 이유: 지금 코드에서 red 가 exit 0 으로 실패해야 재현이고, 대역이 없으면 실 게이트웨이로 probe 가 나간다.

#### AC 커버리지

| AC | 시나리오 # |
|---|---|
| AC-1 `OBS_CONFIG` 가 없는 파일이면 `ObsError`, 문구에 경로와 `OBS_CONFIG` | 1 (+ 2) |
| AC-2 암묵 후보가 전부 없으면 여전히 기본값 | 3 (+ 4) |
| AC-3 `obs-doctor.py` 도 같은 오류로 exit 1 | 5 |
