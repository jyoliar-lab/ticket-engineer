#!/usr/bin/env python3
"""PreToolUse guard — ticket-engineer의 경계를 구조로 강제한다.

Write/Edit/MultiEdit:
  허용 — $CLAUDE_PROJECT_DIR/workspace/**       (대상 코드 저장소 클론)
  거부 — workspace/ops-workflow/**              (정책·티켓 코퍼스 — 읽기 전용)
  거부 — 그 외 전부. 특히 자기 하네스(CLAUDE.md·.claude/**)는
         steward(+사람)만 개정한다 (CLAUDE.md §4).

Bash:
  거부 — `gh issue close`  (close는 사람의 것 — ops-workflow 규약)
  거부 — `gh pr merge`     (머지는 사람의 것 — CLAUDE.md §2⑦)
"""
import json
import os
import re
import sys


def out_deny(reason):
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": "deny",
        "permissionDecisionReason": reason,
    }}, ensure_ascii=False))
    sys.exit(0)


def allow():
    sys.exit(0)


def norm(p):
    return os.path.realpath(os.path.abspath(p))


def under(path, root):
    if not root:
        return False
    root = norm(root)
    path = norm(path)
    return path == root or path.startswith(root + os.sep)


def main():
    try:
        data = json.load(sys.stdin)
    except Exception:
        allow()  # 입력 파싱 불가 → 가드 불가. 세션을 브릭하지 않는다(fail-open).

    tool = data.get("tool_name", "")
    tool_input = data.get("tool_input") or {}

    if tool == "Bash":
        cmd = tool_input.get("command", "") or ""
        if re.search(r"\bgh\s+issue\s+close\b", cmd):
            out_deny("Issue close는 사람의 것이다 — engineer는 완료 보고 코멘트까지만 남긴다"
                     "(CLAUDE.md §2⑦). 검수·close는 사람이 한다.")
        if re.search(r"\bgh\s+pr\s+merge\b", cmd):
            out_deny("PR 머지는 사람의 것이다 — engineer는 PR을 열고 보고까지만 한다"
                     "(CLAUDE.md §2⑦).")
        allow()

    if tool not in ("Write", "Edit", "MultiEdit"):
        allow()

    fp = tool_input.get("file_path")
    if not fp:
        allow()

    proj = os.environ.get("CLAUDE_PROJECT_DIR")
    if not proj:
        out_deny("CLAUDE_PROJECT_DIR 미설정 — 쓰기 경계를 확인할 수 없어 거부한다.")

    ws = os.path.join(proj, "workspace")

    if under(fp, os.path.join(ws, "ops-workflow")):
        out_deny("workspace/ops-workflow 는 읽기 전용이다(정책·티켓 코퍼스). "
                 "남길 것이 있으면 파일이 아니라 gh 코멘트로(컨트롤 플레인).")

    if under(fp, ws):
        allow()

    out_deny(
        "쓰기 경계 위반: %s — engineer는 workspace/** 에서만 쓴다. "
        "하네스(CLAUDE.md·.claude/**)의 개정 경로는 steward(+사람)다(CLAUDE.md §4)." % fp
    )


if __name__ == "__main__":
    main()
