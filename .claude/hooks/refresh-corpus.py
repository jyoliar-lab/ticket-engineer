#!/usr/bin/env python3
"""SessionStart hook — 정책·티켓 코퍼스(workspace/ops-workflow)를 세션 시작 시 최신화한다.

낡은 코퍼스로 일하지 않기 위한 구조다: 없으면 clone, 있으면 origin/main 을 ff-only pull.
실패는 경고만 한다 — 코퍼스 최신화 실패로 세션을 막지 않는다(fail-open).
쓰기는 여전히 guard-write hook 가 거부한다(읽기 전용).
"""
import os
import subprocess
import sys

URL = "https://github.com/jyoliar-lab/ops-workflow.git"


def main():
    proj = os.environ.get("CLAUDE_PROJECT_DIR")
    if not proj:
        return
    dest = os.path.join(proj, "workspace", "ops-workflow")

    if not os.path.isdir(os.path.join(dest, ".git")):
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        r = subprocess.run(["git", "clone", URL, dest], capture_output=True, text=True)
        print("코퍼스 clone: " + ("완료" if r.returncode == 0 else "실패 — " + r.stderr.strip()),
              file=sys.stderr)
        return

    subprocess.run(["git", "-C", dest, "fetch", "--prune"], capture_output=True, text=True)
    r = subprocess.run(["git", "-C", dest, "pull", "--ff-only"], capture_output=True, text=True)
    if r.returncode != 0:
        print("경고: 코퍼스 ff-pull 실패 — 로컬 변경/분기가 있다(읽기 전용이어야 할 클론이다). "
              "사람에게 알려라.", file=sys.stderr)


if __name__ == "__main__":
    main()
    sys.exit(0)   # 어떤 경우에도 세션을 막지 않는다
