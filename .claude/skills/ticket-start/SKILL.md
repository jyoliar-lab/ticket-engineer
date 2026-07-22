---
name: ticket-start
description: 티켓 착수 절차 — 티켓·근거 문서 읽기, "완료의 모양"·"딸리지 않는 것" 추출, 대상 repo 준비(pull-or-clone), 티켓 브랜치 생성. 사람이 티켓 번호를 지정하면 코드를 만지기 전에 이 절차부터 밟는다.
---

# ticket-start — 착수

낡은 코퍼스·낡은 repo 위에서 일하지 않기 위한 고정 순서다. 판단(티켓 이해·설계)은 네 것이고, 이 skill은 그 전에 밟을 바닥을 깐다.

## 절차

1. **티켓 읽기** — `gh issue view <N> -R jyoliar-lab/ops-workflow --comments`
2. **경계 추출** — 티켓에서 두 절을 **그대로 옮겨 적는다**(요약하지 않는다):
   - **완료의 모양** — 검수 기준이다. 그대로 `ticket-report`의 대조표 행이 된다.
   - **딸리지 않는 것** — 의도적 미결정 축이다. 작업 중 이 축에 닿으면 **멈추고 사람에게**(CLAUDE.md §3).
3. **코퍼스 갱신 후 근거 읽기** — `python3 "$CLAUDE_SKILL_DIR/scripts/prep-repo.py" ops-workflow` → 티켓이 링크한 ADR·discussion을 `workspace/ops-workflow/docs/`에서 읽는다. (읽기 전용 — hook가 강제한다. 저작 규약은 알 필요 없다 — 참고 자료다.)
4. **저장소 준비** — 티켓 본문 **'저장소' 절**에서 목록을 읽는다(산문 추측이 아니다):
   - **target 전부** + 파악에 필요한 **ref**를 `python3 "$CLAUDE_SKILL_DIR/scripts/prep-repo.py" <repo>`로 준비 — 있으면 pull, 없으면 clone. 멱등.
   - **target = (없음)**(신규 저장소 생성 작업)이면 저장소 이름·위치·생성 방식을 **사람과 확인**한 뒤 진행한다.
   - **'저장소' 절이 없는 티켓**(절 도입 전 발행)이면 **사람에게 묻는다** — 추측으로 clone하지 않는다.
   - ref·나열 밖 저장소는 **읽기 전용**이다 — 고쳐야 하게 되면 멈추고 target 갱신 절차부터(CLAUDE.md §3).
5. **브랜치** — `git -C workspace/<repo> switch -c ticket/<N>-<slug>` (slug: 소문자 kebab 3–6단어)
6. **착수 요약** — 경계 2절 + 이해한 작업 계획을 사용자에게 보인다. 계획이 티켓과 어긋날 소지가 보이면 진행 전에 묻는다.

## 스크립트가 막으면

`prep-repo.py`가 ff-pull 실패로 멈추면 로컬 변경·분기가 있다는 뜻이다 — **우회하지 않고**(reset·force 금지) 상태를 읽고 사람과 정리한다.
