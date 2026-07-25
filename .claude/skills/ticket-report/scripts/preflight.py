#!/usr/bin/env python3
"""완료 보고 preflight — 보고 전 기계 확인 5종. 전부 통과해야 보고한다.

사용: preflight.py <ticket-number> [target-repo-dir=.]

  ① 현재 브랜치에 열린 PR이 있다
  ② PR 본문에 jyoliar-lab/ops-workflow#<N> 참조가 있다 (브리지)
  ③ 자동 close 키워드가 없다 (PR 머지 ≠ 티켓 종료)
  ④ 체크가 실패·진행 중이 아니다 (머지 게이트)
  ⑤ 이 저장소가 티켓 '저장소' 절의 수정 대상(target) 목록에 있다 (ADR-0016 파일럿)
     — target은 살아 있는 사실이다. 작업 중 늘었으면 티켓을 먼저 갱신했어야 한다.
     절이 없는 구식 티켓은 통과(경고만).

하나라도 실패 → exit 1. 보고하지 말고 해당 항목을 해결하라.
이 스크립트는 Acceptance Criteria 충족을 판정하지 않는다 — 그것은 의미 판정이다.
"""
import json
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "_lib"))
from repos import parse_section  # noqa: E402  ('저장소' 절 파서 — 표기 원본은 ops-workflow repo_context.py)

FAIL_STATES = {"FAILURE", "ERROR", "CANCELLED", "TIMED_OUT",
               "ACTION_REQUIRED", "STARTUP_FAILURE", "STALE"}
PEND_STATES = {"PENDING", "QUEUED", "IN_PROGRESS", "WAITING",
               "REQUESTED", "EXPECTED"}
CLOSE_KW = re.compile(
    r"\b(clos(?:e|es|ed)|fix(?:es|ed)?|resolv(?:e|es|ed))\b\s*:?\s+\S*#\d+",
    re.IGNORECASE)


def report(results):
    ok = all(p for p, _ in results)
    for p, msg in results:
        print(("✔ " if p else "✘ ") + msg)
    print("== preflight " + ("통과 — 보고를 진행하라"
                             if ok else "실패 — 보고하지 말고 위 항목을 해결하라"))
    sys.exit(0 if ok else 1)


def check_state(c):
    return (c.get("conclusion") or c.get("state") or c.get("status") or "").upper()


def target_repo_check(n, cwd):
    """⑤ 이 저장소 ∈ 티켓 target 목록 (ADR-0016 파일럿). 절이 없으면 통과(구식 티켓)."""
    r = subprocess.run(["gh", "repo", "view", "--json", "nameWithOwner"],
                       cwd=cwd, capture_output=True, text=True)
    if r.returncode != 0:
        return (False, "⑤ 저장소: 현재 저장소를 식별하지 못했다 — "
                + (r.stderr.strip() or "gh repo view 실패"))
    here = json.loads(r.stdout)["nameWithOwner"]

    r = subprocess.run(["gh", "issue", "view", str(n),
                        "-R", "jyoliar-lab/ops-workflow", "--json", "body"],
                       capture_output=True, text=True)
    if r.returncode != 0:
        return (False, f"⑤ 저장소: 티켓 #{n} 본문을 읽지 못했다 — "
                + (r.stderr.strip() or "gh issue view 실패"))
    body = json.loads(r.stdout).get("body") or ""

    try:
        parsed = parse_section(body)
    except ValueError as e:
        return (False, f"⑤ 저장소: '저장소' 절의 표기를 읽을 수 없다 — {e} — 손으로 고치지 말고 "
                "ops-workflow 의 set-repos.py 로 재기입한 뒤 다시.")
    if parsed is None:
        return (True, "⑤ 저장소: 티켓에 '저장소' 절이 없다(절 도입 전 티켓) — 목록 대조 생략")

    targets, no_target, _refs = parsed
    if here.lower() in (t.lower() for t in targets):
        return (True, f"⑤ 저장소: {here} — target 목록에 있음")
    if no_target:
        return (False, f"⑤ 저장소: target이 부재 선언(null)인데 {here} 에서 보고하려 한다 — "
                "저장소가 생겼으면 티켓의 target 목록을 먼저 갱신하라(사람과 합의, 갱신 필수).")
    return (False, f"⑤ 저장소: {here} 가 target 목록({', '.join(targets)})에 없다 — "
            "수정 범위가 늘었으면 티켓을 먼저 갱신하라(사람과 합의, 갱신 필수).")


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(2)
    n = sys.argv[1]
    cwd = sys.argv[2] if len(sys.argv) > 2 else "."

    r = subprocess.run(
        ["gh", "pr", "view", "--json", "url,state,title,body,statusCheckRollup"],
        cwd=cwd, capture_output=True, text=True)
    if r.returncode != 0:
        report([(False, "① PR: 현재 브랜치의 PR을 찾지 못했다 — "
                 + (r.stderr.strip() or "gh pr view 실패"))])

    pr = json.loads(r.stdout)
    results = []
    results.append((pr.get("state") == "OPEN",
                    f"① PR: {pr.get('url')} (state={pr.get('state')})"))

    body = pr.get("body") or ""
    title = pr.get("title") or ""
    ref_ok = re.search(rf"jyoliar-lab/ops-workflow#{n}\b", body) is not None
    results.append((ref_ok, f"② 참조: jyoliar-lab/ops-workflow#{n} "
                    + ("있음" if ref_ok else "없음 — 브리지 규약 위반")))

    kw = CLOSE_KW.search(body + " " + title)
    results.append((kw is None, "③ close 키워드: "
                    + ("없음" if kw is None
                       else f"발견 {kw.group(0)!r} — PR 머지 ≠ 티켓 종료")))

    results.append(target_repo_check(n, cwd))

    checks = pr.get("statusCheckRollup") or []
    if not checks:
        results.append((True, "④ 체크: 없음 (이 저장소에 게이트 미설정)"))
    else:
        def name(c):
            return c.get("name") or c.get("context") or "?"
        bad = [c for c in checks if check_state(c) in FAIL_STATES]
        pend = [c for c in checks
                if check_state(c) in PEND_STATES or not check_state(c)]
        if bad:
            results.append((False, "④ 체크 실패: " + ", ".join(map(name, bad))))
        elif pend:
            results.append((False, "④ 체크 진행 중: "
                            + ", ".join(map(name, pend)) + " — 끝난 뒤 다시"))
        else:
            results.append((True, f"④ 체크: {len(checks)}개 전부 통과"))

    report(results)


if __name__ == "__main__":
    main()
