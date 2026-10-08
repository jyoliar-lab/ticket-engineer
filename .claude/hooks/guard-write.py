#!/usr/bin/env python3
"""PreToolUse guard — ticket-engineer의 경계를 구조로 강제한다.

Write/Edit/MultiEdit:
  허용 — workspace/target/**                    (티켓 worktree — 수정 권한의 경계)
  허용 — tmp/**                                 (초안 인박스 — tmp/staging·tmp/pr·
         tmp/github-issues. CLAUDE.md §1·§4)
  거부 — workspace/ref/**                       (참조 저장소·정책 코퍼스 — 읽기 전용. ADR-0016의 ref)
  거부 — workspace/target/.bare/**              (bare 저장소 — 도구만 만진다)
  거부 — 그 외 전부. 특히 자기 하네스(CLAUDE.md·.claude/**)는
         사람만 개정한다 (CLAUDE.md §4).

Bash:
  거부 — `gh issue close`  (close는 사람의 것 — ops-workflow 규약)
  거부 — `gh pr merge`     (머지는 사람의 것 — CLAUDE.md §2③)
  거부 — `gh pr create`    (PR 생성은 ticket-pr.py 관문으로 — CLAUDE.md §2①.
         본문 규약 검증·squash 머지 후 브랜치 재정렬이 그 안에 있다)
  거부 — `git push` + force 계열 플래그 (재정렬 push는 ticket-pr.py 안의
         --force-with-lease 뿐 — agent가 직접 force하지 않는다)
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
                     "(CLAUDE.md §2③). 검수·close는 사람이 한다.")
        if re.search(r"\bgh\s+pr\s+merge\b", cmd):
            out_deny("PR 머지는 사람의 것이다 — engineer는 PR을 열고 보고까지만 한다"
                     "(CLAUDE.md §2③).")
        if re.search(r"\bgh\s+pr\s+create\b", cmd):
            out_deny("PR 생성은 ticket-pr.py 관문으로 한다(CLAUDE.md §2①) — squash 머지 뒤 "
                     "낡은 브랜치 재정렬과 본문 규약(티켓 Closes 연결 자동 부여 = Development "
                     "연결 · 타 이슈 close 키워드 거부)을 그 도구가 수행한다. "
                     "사용: ticket-pr.py <N> --title <제목> --body-file <tmp/pr/...> [--repo <owner/name>]")
        if (re.search(r"\bgit\b[^|;&]*\bpush\b", cmd)
                and re.search(r"(^|\s)(-f|--force|--force-with-lease(=\S+)?)(\s|$)", cmd)):
            out_deny("force push는 agent가 직접 하지 않는다 — 수확된 브랜치의 재정렬 push는 "
                     "ticket-pr.py 관문 안의 --force-with-lease 뿐이다(CLAUDE.md §2①). "
                     "그 밖에 force가 필요해 보이면 멈추고 사람에게.")
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

    if under(fp, os.path.join(ws, "ref")):
        out_deny("workspace/ref 는 읽기 전용이다(참조 저장소·정책 코퍼스 — ADR-0016의 ref). "
                 "고쳐야 하면 멈추고 사람에게 알려라(CLAUDE.md §3) — 티켓의 target 갱신은 사람의 것이고, 그 뒤 target worktree에서 한다. "
                 "ops-workflow에 남길 것은 파일이 아니라 gh 코멘트로(컨트롤 플레인).")

    if under(fp, os.path.join(ws, "target", ".bare")):
        out_deny("workspace/target/.bare 는 도구(ticket-run.py)만 만진다 — "
                 "작업은 티켓 worktree(workspace/target/<repo>/ticket-<N>/)에서 하라.")

    if under(fp, os.path.join(ws, "target")):
        allow()

    if under(fp, ws):
        out_deny("workspace 직속에는 쓰지 않는다 — 작업은 workspace/target/<repo>/ticket-<N>/, "
                 "참조는 workspace/ref/<repo>(읽기 전용)다.")

    if under(fp, os.path.join(proj, "tmp")):
        allow()

    out_deny(
        "쓰기 경계 위반: %s — engineer는 티켓 worktree(workspace/target/<repo>/ticket-<N>/)와 tmp/** 에서만 쓴다. "
        "하네스(CLAUDE.md·.claude/**)는 agent가 고치지 않는다 — "
        "개정 제안은 tmp/staging/에 써서 사람에게 넘겨라(CLAUDE.md §4)." % fp
    )


if __name__ == "__main__":
    main()
