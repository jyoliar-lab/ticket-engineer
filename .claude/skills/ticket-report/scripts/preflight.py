#!/usr/bin/env python3
"""완료 보고 preflight — 한 번의 실행으로 티켓 스코프 전부를 검토한다.

사용: preflight.py <ticket-number>
  (target 저장소를 인자로 받지 않는다 — 이 티켓의 worktree 전부를 스스로 찾아 순회한다.)

티켓 스코프 (1회):
  · 코멘트 전문 출력 — 본문 밖 추가 요구·방향 수정·재개 맥락. 미반영 요구가 있으면
    보고가 아니라 사람과 논의가 먼저다 (반영 여부는 의미 판정 — 이 스크립트는 못 한다).
  · 티켓 '저장소' 절의 target 목록 ↔ 이 티켓의 worktree 전수 대조 (ADR-0016 파일럿
    — target 은 살아 있는 사실이다. 작업 중 늘었으면 티켓을 먼저 갱신했어야 한다):
  ⑤ worktree 의 저장소가 전부 target 목록에 있다 (목록 밖 worktree = 범위 확장 미신고)
  ⑥ target 마다 worktree 가 있다 (없으면 그 저장소 작업이 시작되지 않았다)
     절이 없는 구식 티켓은 목록 대조 생략(경고만).

worktree(저장소) 스코프 (worktree 마다):
  ① 현재 브랜치의 PR이 열려 있거나 머지됐다 (머지 후 보고는 정상 순서 — gitops처럼
     배포 뒤에야 검증되는 티켓. 머지됨이면 HEAD가 머지된 head와 같은지도 본다 —
     머지 뒤 커밋은 기본 브랜치에 없다. CLOSED는 실패)
  ② PR 본문에 jyoliar-lab/ops-workflow#<N> 참조가 있다 (브리지)
  ③ close 키워드가 티켓 연결(Closes 이슈repo#N — Development 연결·자동 close 는
     저장소 설정이 차단)뿐이다 — 티켓 밖 이슈를 겨눈 키워드는 실패(그 이슈는 정말 닫힌다)
  ④ 체크가 실패·진행 중이 아니다 (머지 게이트)
     PR이 없어도 기본 브랜치 대비 커밋 0개 + working tree 깨끗이면 정보성 통과
     (태그 발행 등 커밋 외 기여 — ②–④ 생략. 커밋이 있거나 더러우면 그대로 실패)

하나라도 실패 → exit 1. 보고하지 말고 해당 항목을 해결하라.
이 스크립트는 Acceptance Criteria 충족을 판정하지 않는다 — 그것은 의미 판정이다.
"""
import argparse
import json
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "_lib"))
import comments  # noqa: E402  (코멘트 fetch·출력 — ticket-run 과 공유. 문구의 원천은 한 곳)
from _common import OPS_REPO, TARGET_DIR, close_kw_targets, rel, run_cli  # noqa: E402
from repos import parse_section  # noqa: E402  ('저장소' 절 파서 — 표기 원본은 ops-workflow repo_context.py)

FAIL_STATES = {"FAILURE", "ERROR", "CANCELLED", "TIMED_OUT",
               "ACTION_REQUIRED", "STARTUP_FAILURE", "STALE"}
PEND_STATES = {"PENDING", "QUEUED", "IN_PROGRESS", "WAITING",
               "REQUESTED", "EXPECTED"}


def emit(results):
    """결과 줄들을 그 자리에서 출력하고 전부 통과했는지 돌려준다."""
    for p, msg in results:
        print(("✔ " if p else "✘ ") + msg)
    return all(p for p, _ in results)


def check_state(c):
    return (c.get("conclusion") or c.get("state") or c.get("status") or "").upper()


# ── 티켓 스코프 ──────────────────────────────────────────────────────────────

def find_worktrees(n):
    """workspace/target/<name>/ticket-<N> 전수 스캔 → {repo nameWithOwner: 경로}.
    저장소 신원은 디렉터리명이 아니라 worktree 안에서 gh 로 확인한다."""
    found = {}

    for name in sorted(os.listdir(TARGET_DIR) if os.path.isdir(TARGET_DIR) else []):
        wt = os.path.join(TARGET_DIR, name, "ticket-%s" % n)

        if name == ".bare" or not os.path.isdir(wt):
            continue

        r = subprocess.run(["gh", "repo", "view", "--json", "nameWithOwner"],
                           cwd=wt, capture_output=True, text=True)

        if r.returncode != 0:
            print("✘ %s: 저장소를 식별하지 못했다 — %s"
                  % (rel(wt), r.stderr.strip() or "gh repo view 실패"))
            sys.exit(1)

        found[json.loads(r.stdout)["nameWithOwner"]] = wt

    return found


def scope_checks(n, worktrees):
    """⑤·⑥ — 티켓 target 목록 ↔ worktree 전수 대조. → 결과 목록."""
    r = subprocess.run(["gh", "issue", "view", str(n), "-R", OPS_REPO, "--json", "body"],
                       capture_output=True, text=True)
    if r.returncode != 0:
        return [(False, "⑤ 저장소: 티켓 #%s 본문을 읽지 못했다 — %s"
                 % (n, r.stderr.strip() or "gh issue view 실패"))]

    try:
        parsed = parse_section(json.loads(r.stdout).get("body") or "")
    except ValueError as e:
        return [(False, "⑤ 저장소: '저장소' 절의 표기를 읽을 수 없다 — %s — 손으로 고치지 말고 "
                 "ops-workflow 의 set-repos.py 로 재기입한 뒤 다시." % e)]

    if parsed is None:
        return [(True, "⑤ 저장소: 티켓에 '저장소' 절이 없다(절 도입 전 티켓) — 목록 대조 생략")]

    targets, no_target, _refs = parsed

    if no_target:
        return [(False, "⑤ 저장소: target이 부재 선언(null)인데 worktree(%s)가 있다 — "
                 "저장소가 생겼으면 티켓의 target 목록을 먼저 갱신하라(사람과 합의, 갱신 필수)."
                 % ", ".join(worktrees))]

    low = {t.lower(): t for t in targets}
    results = []

    for repo in worktrees:
        results.append((repo.lower() in low,
                        "⑤ %s: target 목록에 %s" % (repo, "있음" if repo.lower() in low
                                                    else "없다 — 수정 범위가 늘었으면 티켓을 먼저 갱신하라(사람과 합의, 갱신 필수)")))

    seen = {repo.lower() for repo in worktrees}

    for t in targets:
        if t.lower() not in seen:
            results.append((False, "⑥ %s: target 인데 이 티켓의 worktree 가 없다 — "
                            "그 저장소 작업이 시작되지 않았다. 전 target 완료 후 보고하라 "
                            "(대상에서 빠졌으면 티켓 갱신이 먼저다 — 사람과 합의)." % t))

    return results


# ── worktree 스코프 (①–④) ───────────────────────────────────────────────────

def pr_state_check(pr, cwd):
    """① PR 상태. OPEN 통과 · MERGED는 HEAD 일치 조건부 통과 · 그 외 실패."""
    state = pr.get("state")
    where = f"① PR: {pr.get('url')} (state={state}"

    if state == "OPEN":
        return (True, where + ")")
    if state != "MERGED":
        return (False, where + ") — 머지 없이 닫힌 PR로는 보고하지 않는다")

    r = subprocess.run(["git", "rev-parse", "HEAD"],
                       cwd=cwd, capture_output=True, text=True)
    if r.returncode != 0:
        return (False, where + ") — worktree의 HEAD를 읽지 못했다 — "
                + (r.stderr.strip() or "git rev-parse 실패"))

    head, merged_head = r.stdout.strip(), pr.get("headRefOid")
    if head == merged_head:
        return (True, where + " — 머지 완료)")
    return (False, where + f") — 머지 후 브랜치에 커밋이 더 있다 "
            f"(HEAD {head[:7]} ≠ 머지된 head {(merged_head or '?')[:7]}) — "
            "그 변경은 기본 브랜치에 없다. 새 PR로 올려 머지받은 뒤 다시.")


def _no_local_work(repo: str, cwd: str) -> bool:
    """기본 브랜치 대비 커밋 0개 + working tree 깨끗 → True (태그 발행 등 커밋 외 기여).
    PR 부재 시의 fallback 판정에만 쓴다 — 판정에 실패하면 False 를 돌려
    기존 실패 경로로 떨어진다 (관문을 느슨하게 하지 않는다)."""
    base = subprocess.run(["gh", "api", "repos/%s" % repo, "--jq", ".default_branch"],
                          cwd=cwd, capture_output=True, text=True)
    if base.returncode != 0 or not base.stdout.strip():
        return False

    ahead = subprocess.run(["git", "rev-list", "--count",
                            "origin/%s..HEAD" % base.stdout.strip()],
                           cwd=cwd, capture_output=True, text=True)
    dirty = subprocess.run(["git", "status", "--porcelain"],
                           cwd=cwd, capture_output=True, text=True)
    if ahead.returncode != 0 or dirty.returncode != 0:
        return False

    return ahead.stdout.strip() == "0" and dirty.stdout.strip() == ""


def worktree_checks(n, repo, cwd):
    """①–④ — 한 worktree 의 PR·참조·close 키워드·체크. → 결과 목록."""
    r = subprocess.run(
        ["gh", "pr", "view", "--json",
         "url,state,title,body,headRefOid,statusCheckRollup"],
        cwd=cwd, capture_output=True, text=True)
    if r.returncode != 0:
        if _no_local_work(repo, cwd):
            return [(True, "① PR: 없음 — %s 는 이 티켓에서 커밋을 만들지 않았다 "
                     "(기본 브랜치 대비 0 커밋·깨끗한 working tree — "
                     "태그 발행 등 커밋 외 기여) — ②–④ 생략" % repo)]
        return [(False, "① PR: %s 의 현재 브랜치 PR을 찾지 못했다 — %s"
                 % (repo, r.stderr.strip() or "gh pr view 실패"))]

    pr = json.loads(r.stdout)
    results = [pr_state_check(pr, cwd)]

    body = pr.get("body") or ""
    title = pr.get("title") or ""
    ref_ok = re.search(rf"{re.escape(OPS_REPO)}#{n}\b", body) is not None
    results.append((ref_ok, f"② 참조: {OPS_REPO}#{n} "
                    + ("있음" if ref_ok else "없음 — 브리지 규약 위반")))

    # 허용되는 close 키워드는 티켓 연결(Closes OPS_REPO#N — Development 연결) 하나뿐.
    # 티켓의 자동 close 는 ops-workflow 저장소 설정 해제가 막지만, 다른 저장소의
    # 이슈를 겨눈 키워드는 머지 시 그 이슈를 정말 닫는다 — 실패.
    canonical = f"{OPS_REPO}#{n}".lower()
    stray = [t for t in close_kw_targets(body + " " + title) if t != canonical]
    results.append((not stray, "③ close 키워드: "
                    + (f"발견 {', '.join(stray)} — 티켓 밖 이슈를 닫는 키워드" if stray
                       else "티켓 연결뿐 (혹은 없음)")))

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

    return results


# ── main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(add_help=True)
    parser.add_argument("ticket", help="티켓 번호")
    args = parser.parse_args()
    n = args.ticket.lstrip("#")

    comments.show(comments.fetch_all(n))   # 본문 밖 요구·방향 수정 — 보고 관문이 실어 나른다

    worktrees = find_worktrees(n)

    if not worktrees:
        print("✘ 티켓 #%s 의 worktree 가 없다 (%s) — 보고할 작업이 없다. "
              "ticket-run 으로 착수했는가?" % (n, rel(TARGET_DIR)))
        sys.exit(1)

    print("\n== 티켓 스코프 — target 목록 ↔ worktree 대조")
    ok = emit(scope_checks(n, worktrees))

    for repo, wt in worktrees.items():
        print("\n== %s (%s)" % (repo, rel(wt)))
        ok = emit(worktree_checks(n, repo, wt)) and ok

    print("\n== preflight " + ("통과 — 보고를 진행하라"
                               if ok else "실패 — 보고하지 말고 위 항목을 해결하라"))
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    run_cli(main)   # 코멘트 fetch 실패(Reject) 등의 exit 변환은 여기서만 일어난다
