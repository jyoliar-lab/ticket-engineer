#!/usr/bin/env python3
"""PR 생성 — 단일 관문. squash 머지로 수확된 낡은 브랜치를 재정렬한 뒤 PR을 연다.

사용: ticket-pr.py <ticket-number> --title <제목> --body-file <경로> [--repo <owner/name>] [--draft]
  --draft 는 TDD 흐름(tdd-loop)에서 red 커밋 직후 Draft 로 열 때. ready 전환은 사람 승인 뒤
  agent 가 `gh pr ready` 로 한다 — 이 도구는 열기만 한다.
  worktree 는 workspace/target/<repo>/ticket-<N>/ 에서 스스로 찾는다 — target 이
  여럿이면 --repo 로 지정한다. 본문은 파일로 받는다(긴 본문 안전). 티켓 연결
  (`Closes jyoliar-lab/ops-workflow#<N>` — 브리지 + 이슈 Development 연결)은 본문에
  없으면 스크립트가 덧붙인다. 자동 close 는 ops-workflow 저장소 설정이 막는다.

왜 관문인가 (직접 `gh pr create` 는 hook 가 거부한다):
  Squash and Merge 는 브랜치 커밋들을 새 커밋 하나로 다시 써서 main 에 얹는다 —
  내용은 같지만 히스토리는 남남이라, 낡은 브랜치로 새 PR 을 열면 이미 반영된
  변경이 diff 에 다시 실려 충돌한다. 이 도구는 머지된 PR 의 head SHA(GitHub 의
  사실)를 기준으로 수확된 커밋을 잘라내고, 새 커밋만 최신 기본 브랜치 위에
  재생한다:  git rebase --onto origin/<default> <머지된 head>
  수확 커밋은 머지된 PR 에 영구 보존되므로 유실이 없다. push 는
  --force-with-lease=<branch>:<fetch 시점 원격 SHA> — 그 사이 원격에 올라온
  모르는 커밋은 덮을 수 없다. 이 밖의 force push 를 이 도구는 하지 않는다.

거부하는 경우:
  exit 1 — 커밋 안 된 변경(커밋부터) · 이미 열린 PR(그 브랜치에 일반 push 로) ·
           PR 로 낼 새 커밋이 없다 · 티켓 밖 이슈를 겨눈 close 키워드
  exit 3 — rebase 충돌(기본 브랜치가 새 커밋과 같은 부분을 실제로 바꿈 — abort 후
           보고만, 처리는 사람과) · 원격과 양방향 분기(ticket-run 으로 정렬부터)
"""
import argparse
import os
import re
import sys
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "_lib"))
from _common import (EXIT_HUMAN, OPS_REPO, TARGET_DIR, Reject, block,  # noqa: E402
                     close_kw_targets, gh_json, rel, run, run_cli)


@dataclass(frozen=True)
class MergedPr:
    """이 브랜치로 머지 완료된 PR — head SHA 가 '어디까지 수확됐는가'의 사실이다."""
    number: int
    url: str
    head_sha: str
    merged_at: str


# ── 1. worktree·브랜치 확인 ──────────────────────────────────────────────────

def repo_of(wt: str) -> Optional[str]:
    """worktree 의 origin URL → owner/name (식별 불가면 None)."""
    p = run(["git", "-C", wt, "remote", "get-url", "origin"], check=False)
    m = re.search(r"github\.com[:/](.+?)(?:\.git)?$", p.stdout.strip())
    return m.group(1) if m else None


def find_worktree(n: str, repo_arg: Optional[str]) -> Tuple[str, str]:
    """workspace/target/<name>/ticket-<N> 스캔 → (worktree, owner/name). 여럿이면 --repo 필수."""
    found: Dict[str, str] = {}

    for name in sorted(os.listdir(TARGET_DIR) if os.path.isdir(TARGET_DIR) else []):
        wt = os.path.join(TARGET_DIR, name, "ticket-%s" % n)

        if name == ".bare" or not os.path.isdir(wt):
            continue

        repo = repo_of(wt)

        if repo:
            found[repo] = wt

    if not found:
        raise Reject("거부: 티켓 #%s 의 worktree 가 없다 (%s) — ticket-run 으로 착수했는가?"
                     % (n, rel(TARGET_DIR)))

    if repo_arg:
        for repo, wt in found.items():
            if repo.lower() == repo_arg.lower():
                return wt, repo

        raise Reject("거부: --repo %s 의 worktree 를 찾지 못했다. 있는 것: %s"
                     % (repo_arg, ", ".join(found)))

    if len(found) > 1:
        raise Reject("거부: 이 티켓의 worktree 가 여럿이다 — --repo 로 지정하라: %s"
                     % ", ".join(found))

    repo, wt = next(iter(found.items()))
    return wt, repo


def check_worktree(wt: str, n: str) -> str:
    """dirty 거부 · 티켓 브랜치 확인 → 브랜치명."""
    dirty = run(["git", "-C", wt, "status", "--porcelain"]).stdout.strip()

    if dirty:
        raise Reject("거부: 커밋 안 된 변경이 있다 — PR 로 낼 것을 먼저 커밋하라.",
                     block(dirty))

    branch = run(["git", "-C", wt, "branch", "--show-current"]).stdout.strip()

    if not branch.startswith("ticket/%s-" % n):
        raise Reject("거부: worktree 의 브랜치가 '%s' — 티켓 #%s 의 브랜치(ticket/%s-*)가 아니다."
                     % (branch or "(detached)", n, n),
                     "  ticket-run 으로 정렬한 worktree 에서만 PR 을 연다.")

    return branch


# ── 2. PR 상태 (열린 PR 거부 · 마지막 머지 PR = 수확 기준점) ─────────────────

def latest_merged(repo: str, branch: str) -> Optional[MergedPr]:
    prs = gh_json("pr", "list", "-R", repo, "--head", branch, "--state", "all",
                  "--json", "number,url,state,headRefOid,mergedAt")
    open_prs = [p for p in prs if p["state"] == "OPEN"]

    if open_prs:
        raise Reject("거부: 이미 열린 PR 이 있다 — %s" % open_prs[0]["url"],
                     "  새로 열지 말고 그 PR 의 브랜치에 커밋을 push 하라(일반 push — 관문 불필요).")

    merged = [p for p in prs if p["state"] == "MERGED"]

    if not merged:
        return None

    p = max(merged, key=lambda x: x.get("mergedAt") or "")
    return MergedPr(number=p["number"], url=p["url"],
                    head_sha=p["headRefOid"], merged_at=p.get("mergedAt") or "")


# ── 3. 정렬·push (수확 커밋 잘라내기 → 새 커밋만 기본 브랜치 위로) ───────────

def realign_and_push(wt: str, branch: str, default: str, mp: Optional[MergedPr]) -> None:
    remote_tip = run(["git", "-C", wt, "rev-parse", "origin/%s" % branch],
                     check=False).stdout.strip() or None
    harvested = (mp is not None and run(
        ["git", "-C", wt, "merge-base", "--is-ancestor", mp.head_sha, "HEAD"],
        check=False).returncode == 0)

    if not harvested:
        push_plain(wt, branch, default, remote_tip)
        return

    assert mp is not None
    new_log = run(["git", "-C", wt, "log", "--oneline",
                   "%s..HEAD" % mp.head_sha]).stdout.strip()

    if not new_log:
        raise Reject("거부: PR #%s 머지 이후 새 커밋이 없다 — PR 로 낼 것이 없다." % mp.number,
                     "  후속 작업을 커밋한 뒤 다시 실행하라.")

    old_log = run(["git", "-C", wt, "log", "--oneline",
                   "origin/%s..%s" % (default, mp.head_sha)]).stdout.strip()

    if old_log:
        print("-- 수확 완료 커밋 (PR #%s squash 머지로 origin/%s 반영 — 히스토리에서 잘라낸다):"
              % (mp.number, default))
        print(block(old_log))

    print("-- 재생할 새 커밋 (origin/%s 위로):" % default)
    print(block(new_log))

    p = run(["git", "-C", wt, "rebase", "--onto", "origin/%s" % default, mp.head_sha],
            check=False)

    if p.returncode != 0:
        run(["git", "-C", wt, "rebase", "--abort"], check=False)
        raise Reject(
            "!! rebase 충돌 — origin/%s 가 새 커밋과 같은 부분을 바꿨다" % default,
            "   (squash 가 만든 가짜 충돌이 아니라 진짜 내용 충돌이다).",
            block((p.stderr or p.stdout or "").strip()),
            "   worktree 는 rebase 이전으로 되돌렸다(abort). 처리를 시도하지 말고 사람과 정하라.",
            code=EXIT_HUMAN)

    if not run(["git", "-C", wt, "log", "--oneline",
                "origin/%s..HEAD" % default]).stdout.strip():
        raise Reject("거부: 재생 결과 남는 변경이 없다 — 새 커밋의 내용이 이미 origin/%s 에 있다."
                     % default, "  PR 로 낼 것이 없다. 브랜치는 origin/%s 와 같아졌다." % default)

    if remote_tip:
        # lease = fetch 시점의 원격 SHA — 그 사이 올라온 모르는 커밋은 덮지 못한다
        run(["git", "-C", wt, "push",
             "--force-with-lease=%s:%s" % (branch, remote_tip), "origin", branch])
        print("-- push (--force-with-lease · 기대 원격 %s): 재정렬된 브랜치로 교체" % remote_tip[:7])
    else:
        run(["git", "-C", wt, "push", "-u", "origin", branch])
        print("-- push: 원격에 브랜치 생성")


def push_plain(wt: str, branch: str, default: str, remote_tip: Optional[str]) -> None:
    """수확 커밋 없음 — 일반 경로. 원격과의 분기만 판별하고 push 한다."""
    if not run(["git", "-C", wt, "log", "--oneline",
                "origin/%s..HEAD" % default]).stdout.strip():
        raise Reject("거부: origin/%s 에 없는 커밋이 없다 — PR 로 낼 것이 없다." % default)

    if remote_tip:
        counts = run(["git", "-C", wt, "rev-list", "--left-right", "--count",
                      "origin/%s...HEAD" % branch]).stdout.split()
        behind, ahead = int(counts[0]), int(counts[1])

        if behind:
            raise Reject(
                "!! 원격 브랜치와 분기 상태다 (원격에만 %d개 · 로컬에만 %d개) —" % (behind, ahead),
                "   push 하지 않았다. ticket-run 으로 정렬부터 하라. 처리는 사람과.",
                code=EXIT_HUMAN)

        if ahead:
            run(["git", "-C", wt, "push", "origin", branch])
            print("-- push: 커밋 %d개" % ahead)
    else:
        run(["git", "-C", wt, "push", "-u", "origin", branch])
        print("-- push: 원격에 브랜치 생성")


# ── 4. 본문 규약 → PR 생성 ───────────────────────────────────────────────────

def build_body(n: str, title: str, body_path: str) -> str:
    """close 키워드는 티켓 연결(`Closes <OPS_REPO>#<N>`) 하나만 산다 — 이 도구가 덧붙인다.
    이 키워드가 PR 을 이슈의 Development 절에 연결한다(수동 gear 연결과 같은 효과 —
    기존 PR 연결 API 는 없어 이것이 유일한 자동화 경로다). 티켓의 자동 close 는
    ops-workflow 저장소 설정 해제(수동 불변식)가 막는다. 그 밖의 이슈를 겨눈 키워드는
    거부한다 — 설정 보호가 없는 저장소(target 등)의 이슈는 머지 시 정말 닫힌다."""
    if not os.path.isfile(body_path):
        raise Reject("거부: --body-file 을 읽을 수 없다 — %s" % body_path)

    with open(body_path, encoding="utf-8") as f:
        body = f.read().strip()

    canonical = ("%s#%s" % (OPS_REPO, n)).lower()

    if close_kw_targets(title):
        raise Reject("거부: 제목에 close 키워드가 있다 — 제목에는 쓰지 않는다.")

    stray = [t for t in close_kw_targets(body) if t != canonical]

    if stray:
        raise Reject("거부: 티켓 밖 이슈를 겨눈 close 키워드 — %s" % ", ".join(stray),
                     "  자동 close 차단 설정은 ops-workflow 에만 있다 — 다른 저장소의",
                     "  이슈는 머지 시 정말 닫힌다. 참조는 키워드 없이 남겨라.",
                     "  티켓 연결(Closes %s#%s)은 이 도구가 덧붙인다." % (OPS_REPO, n))

    if canonical not in close_kw_targets(body):
        body += "\n\nCloses %s#%s" % (OPS_REPO, n)
        print("-- 티켓 연결을 덧붙였다: Closes %s#%s (브리지 + Development 연결 — "
              "자동 close 는 저장소 설정이 막는다)" % (OPS_REPO, n))

    return body


# ── main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(add_help=True)
    parser.add_argument("ticket", help="티켓 번호")
    parser.add_argument("--title", required=True, help="PR 제목")
    parser.add_argument("--body-file", required=True, help="PR 본문 파일 (tmp/pr/)")
    parser.add_argument("--repo", help="owner/name — 이 티켓의 worktree 가 여럿일 때 지정")
    parser.add_argument("--draft", action="store_true",
                        help="Draft 로 연다 — TDD 흐름(tdd-loop)에서 red 커밋 직후. "
                             "ready 전환(gh pr ready)은 사람 승인 뒤")
    args = parser.parse_args()
    n: str = args.ticket.lstrip("#")

    wt, repo = find_worktree(n, args.repo)
    print("== %s (%s)" % (repo, rel(wt)))
    branch = check_worktree(wt, n)
    run(["git", "-C", wt, "fetch", "--prune", "origin"])

    default: str = gh_json("api", "repos/%s" % repo)["default_branch"]
    mp = latest_merged(repo, branch)
    realign_and_push(wt, branch, default, mp)

    body = build_body(n, args.title, args.body_file)
    create_args: List[str] = ["gh", "pr", "create", "-R", repo, "--head", branch,
                              "--base", default, "--title", args.title, "--body", body]

    if args.draft:
        create_args.append("--draft")

    url = run(create_args).stdout.strip()
    print("== PR 생성%s: %s" % (" (Draft)" if args.draft else "", url))


if __name__ == "__main__":
    run_cli(main)   # 거부(Reject)→exit 변환은 여기서만 일어난다
