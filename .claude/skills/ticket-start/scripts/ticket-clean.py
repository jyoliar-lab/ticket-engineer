#!/usr/bin/env python3
"""티켓 뒷정리 — 사람이 티켓 close 를 확인하고 지시했을 때만 실행한다. 자동 실행 금지.

사용: ticket-clean.py <ticket-number>

하는 일 (target 저장소마다):
  - workspace/target/<repo>/ticket-<N>/ worktree 제거 + bare 의 로컬 브랜치 삭제
  - 원격 ticket/<N>-* 브랜치 삭제

거부하는 경우 (유실·조기 정리 방지 — 우회하지 않는다):
  - 티켓이 아직 열려 있다
  - worktree 에 커밋 안 된 변경이 있다
  - 그 브랜치의 PR 이 아직 OPEN 이다
"""
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "_lib"))
from _common import OPS_REPO, TARGET_DIR, Reject, block, gh_json, rel, run, run_cli  # noqa: E402


def ensure_closed(n):
    state = gh_json("issue", "view", n, "-R", OPS_REPO, "--json", "state")["state"]

    if state == "OPEN":
        raise Reject("거부: 티켓 #%s 가 아직 열려 있다 — 뒷정리는 close 후에. close 는 사람이 한다." % n)


def guard_worktree(wt):
    """유실 위험이 있으면 거부(Reject)하고, 아니면 (브랜치, owner/name) 를 돌려준다."""
    dirty = run(["git", "-C", wt, "status", "--porcelain"]).stdout.strip()

    if dirty:
        raise Reject("거부: worktree 에 커밋 안 된 변경이 있다 — 유실 위험. 사람과 정리하라.",
                     block(dirty, "  "))

    branch = run(["git", "-C", wt, "branch", "--show-current"]).stdout.strip()
    url = run(["git", "-C", wt, "remote", "get-url", "origin"]).stdout.strip()
    m = re.search(r"github\.com[:/](.+?)(?:\.git)?$", url)
    repo = m.group(1) if m else None

    if repo and branch:
        prs = gh_json("pr", "list", "-R", repo, "--head", branch,
                      "--state", "open", "--json", "url")

        if prs:
            raise Reject("거부: 열린 PR 이 있다 — %s" % prs[0]["url"],
                         "  머지/닫기는 사람의 것. 정리는 그 뒤에.")

    return branch, repo


def clean_one(wt, bare):
    print("== %s" % rel(wt))
    branch, repo = guard_worktree(wt)

    run(["git", "-C", bare, "worktree", "remove", wt])
    print("-- worktree 제거")

    if branch:
        run(["git", "-C", bare, "branch", "-D", branch], check=False)

        if repo:
            run(["git", "-C", bare, "push", "origin", "--delete", branch], check=False)
            print("-- 브랜치 삭제 (로컬·원격): %s" % branch)


def main():
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(2)

    n = sys.argv[1].lstrip("#")

    ensure_closed(n)

    found = False
    for name in sorted(os.listdir(TARGET_DIR) if os.path.isdir(TARGET_DIR) else []):
        wt = os.path.join(TARGET_DIR, name, "ticket-%s" % n)

        if not os.path.isdir(wt):
            continue

        found = True
        clean_one(wt, os.path.join(TARGET_DIR, ".bare", name + ".git"))

    if not found:
        print("정리할 worktree 가 없다 (ticket-%s)." % n)


if __name__ == "__main__":
    run_cli(main)   # 거부(Reject)→exit 1 변환은 여기서만 일어난다
