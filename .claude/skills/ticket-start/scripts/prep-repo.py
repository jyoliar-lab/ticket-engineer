#!/usr/bin/env python3
"""workspace/<repo> 준비 — 있으면 pull(ff-only), 없으면 clone. 멱등.

사용: prep-repo.py <repo-name> [clone-url]
  clone-url 생략 시 https://github.com/jyoliar-lab/<repo-name>.git

기본 브랜치가 아닌(작업 브랜치) 상태면 fetch만 하고 알린다 — 병합 판단은 사람·세션의 것.
ff-pull이 실패하면 exit 1 — 로컬 변경/분기 존재. 우회하지 말고 상태를 읽어라.
"""
import os
import subprocess
import sys


def git(dest, *args, capture=False):
    r = subprocess.run(["git", "-C", dest, *args],
                       capture_output=capture, text=True)
    return r


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(2)
    repo = sys.argv[1]
    url = sys.argv[2] if len(sys.argv) > 2 else f"https://github.com/jyoliar-lab/{repo}.git"

    root = os.path.realpath(os.path.join(os.path.dirname(__file__),
                                         "..", "..", "..", ".."))
    ws = os.path.join(root, "workspace")
    dest = os.path.join(ws, repo)
    os.makedirs(ws, exist_ok=True)

    if os.path.isdir(os.path.join(dest, ".git")):
        print(f"== pull: {repo}")
        git(dest, "fetch", "--prune")
        cur = git(dest, "branch", "--show-current", capture=True).stdout.strip()
        head = git(dest, "symbolic-ref", "--short",
                   "refs/remotes/origin/HEAD", capture=True).stdout.strip()
        default = head.split("/", 1)[1] if "/" in head else "main"
        if cur == default:
            if git(dest, "pull", "--ff-only").returncode != 0:
                print("!! ff-pull 실패 — 로컬 변경/분기가 있다. "
                      "우회(reset·force)하지 말고 상태를 읽고 사람과 정리하라.",
                      file=sys.stderr)
                sys.exit(1)
        else:
            print(f"-- 작업 브랜치({cur}) — fetch만 수행. "
                  f"기본 브랜치({default}) 반영은 병합 판단이 필요하다.")
    else:
        print(f"== clone: {url}")
        if subprocess.run(["git", "clone", url, dest]).returncode != 0:
            sys.exit(1)

    git(dest, "status", "--short", "--branch")


if __name__ == "__main__":
    main()
