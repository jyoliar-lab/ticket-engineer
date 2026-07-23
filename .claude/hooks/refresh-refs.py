#!/usr/bin/env python3
"""SessionStart hook — 참조 경로(workspace/ref)의 모든 로컬 저장소를 세션 시작 시 최신화한다.

ref 는 읽기 전용 참조다(ADR-0016) — 낡은 참조로 구조를 오판하지 않기 위한 구조.
  - 정책·티켓 코퍼스(ref/ops-workflow)는 없으면 clone 한다 (항상 필요).
  - 그 외 ref 는 티켓에 따라 agent 가 clone 하고, 이 hook 는 있는 것들을 ff-only pull 로 최신화한다.
실패는 경고만 한다 — 세션을 막지 않는다(fail-open). 쓰기는 guard-write hook 가 거부한다.
"""
import os
import subprocess
import sys

CORPUS_URL = "https://github.com/jyoliar-lab/ops-workflow.git"


def warn(msg):
    print(msg, file=sys.stderr)


def main():
    proj = os.environ.get("CLAUDE_PROJECT_DIR")
    if not proj:
        return
    ref = os.path.join(proj, "workspace", "ref")
    os.makedirs(ref, exist_ok=True)

    corpus = os.path.join(ref, "ops-workflow")
    if not os.path.isdir(os.path.join(corpus, ".git")):
        r = subprocess.run(["git", "clone", CORPUS_URL, corpus],
                           capture_output=True, text=True)
        if r.returncode != 0:
            warn("경고: 코퍼스 clone 실패 — " + r.stderr.strip())

    for name in sorted(os.listdir(ref)):
        dest = os.path.join(ref, name)
        if not os.path.isdir(os.path.join(dest, ".git")):
            continue
        subprocess.run(["git", "-C", dest, "fetch", "--prune"],
                       capture_output=True, text=True)
        r = subprocess.run(["git", "-C", dest, "pull", "--ff-only"],
                           capture_output=True, text=True)
        if r.returncode != 0:
            warn("경고: ref/%s ff-pull 실패 — 로컬 변경/분기가 있다"
                 "(읽기 전용이어야 할 클론이다). 사람에게 알려라." % name)


if __name__ == "__main__":
    main()
    sys.exit(0)   # 어떤 경우에도 세션을 막지 않는다
