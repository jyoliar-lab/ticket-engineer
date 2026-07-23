#!/usr/bin/env python3
"""티켓 뒷정리 — 사람이 티켓 close 를 확인하고 지시했을 때만 실행한다. 자동 실행 금지.

사용: ticket-clean.py <ticket-number>

하는 일 (target 저장소마다):
  - workspace/<repo>/ticket-<N>/ worktree 제거 + bare 의 로컬 브랜치 삭제
  - 원격 ticket/<N>-* 브랜치 삭제

거부하는 경우 (유실·조기 정리 방지 — 우회하지 않는다):
  - 티켓이 아직 열려 있다
  - worktree 에 커밋 안 된 변경이 있다
  - 그 브랜치의 PR 이 아직 OPEN 이다
"""
import json
import os
import re
import subprocess
import sys

OPS_REPO = os.environ.get("OPS_REPO", "jyoliar-lab/ops-workflow")
ROOT = os.path.realpath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
WS = os.path.join(ROOT, "workspace")


def die(*lines):
    for ln in lines:
        print(ln, file=sys.stderr)
    sys.exit(1)


def run(args, cwd=None, check=True):
    p = subprocess.run(args, cwd=cwd, capture_output=True, text=True)
    if check and p.returncode != 0:
        die("거부: 명령 실패 — %s" % " ".join(args[:5]),
            (p.stderr or p.stdout or "").strip())
    return p


def main():
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(2)
    n = sys.argv[1].lstrip("#")

    state = json.loads(run(["gh", "issue", "view", n, "-R", OPS_REPO,
                            "--json", "state"]).stdout)["state"]
    if state == "OPEN":
        die("거부: 티켓 #%s 가 아직 열려 있다 — 뒷정리는 close 후에. close 는 사람이 한다." % n)

    found = False
    for name in sorted(os.listdir(WS)):
        wt = os.path.join(WS, name, "ticket-%s" % n)
        bare = os.path.join(WS, ".bare", name + ".git")
        if not os.path.isdir(wt):
            continue
        found = True
        print("== %s" % os.path.relpath(wt, ROOT))

        dirty = run(["git", "-C", wt, "status", "--porcelain"]).stdout.strip()
        if dirty:
            die("거부: worktree 에 커밋 안 된 변경이 있다 — 유실 위험. 사람과 정리하라.",
                "  " + dirty.replace("\n", "\n  "))

        branch = run(["git", "-C", wt, "branch", "--show-current"]).stdout.strip()
        repo_url = run(["git", "-C", wt, "remote", "get-url", "origin"]).stdout.strip()
        m = re.search(r"github\.com[:/](.+?)(?:\.git)?$", repo_url)
        repo = m.group(1) if m else None
        if repo and branch:
            prs = json.loads(run(["gh", "pr", "list", "-R", repo, "--head", branch,
                                  "--state", "open", "--json", "url"]).stdout)
            if prs:
                die("거부: 열린 PR 이 있다 — %s" % prs[0]["url"],
                    "  머지/닫기는 사람의 것. 정리는 그 뒤에.")

        run(["git", "-C", bare, "worktree", "remove", wt])
        print("-- worktree 제거")
        if branch:
            run(["git", "-C", bare, "branch", "-D", branch], check=False)
            if repo:
                run(["git", "-C", bare, "push", "origin", "--delete", branch], check=False)
                print("-- 브랜치 삭제 (로컬·원격): %s" % branch)

    if not found:
        print("정리할 worktree 가 없다 (ticket-%s)." % n)


if __name__ == "__main__":
    main()
