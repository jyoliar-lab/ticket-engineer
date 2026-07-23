#!/usr/bin/env python3
"""티켓 진행 — 단일 진입점 (착수 포함). target 저장소마다 원격-우선으로 로컬 worktree를 정렬한다.

사용: ticket-run.py <ticket-number> [--slug <slug>]
  --slug 는 "새 착수"(원격에 티켓 브랜치가 없을 때)에만 필요하다. 소문자 kebab 3–6단어.

원격이 진실의 원천이다:
  - 착수 판별 = 원격에 ticket/<N>-* 브랜치가 있는가. 로컬 상태는 판별·기점에 영향 없음.
  - 새 브랜치는 원격 기본 브랜치 HEAD 기준으로 "원격에" 생성된다.
로컬은 티켓별 worktree다 (동시 여러 티켓 안전 — 공유 HEAD 없음):
  workspace/target/.bare/<repo>.git      ← bare 저장소. 도구만 만진다 (hook가 Write 거부)
  workspace/target/<repo>/ticket-<N>/    ← 티켓 worktree = 작업 디렉터리
  workspace/ref/<repo>                   ← 참조 저장소(읽기 전용). 티켓에 나열된 ref 는
                                            이 도구가 선제 clone 한다. ref 는 비완전 목록이라
                                            나열 밖 저장소는 agent 가 필요 시 직접 clone.

exit 코드 = agent의 다음 행동 (프롬프트 해석에 기대지 않는다):
  0 = 진행하라 (케이스별 정보는 stdout — 읽고 판단·처리)
  1 = 전제 거부 (티켓 닫힘·컨테이너·target 없음 등 — 우회 금지)
  2 = 승인 대기 — 상태를 파악해 처리 방안을 사람에게 제안하고, 승인 후 진행
  3 = 사람 개입 필요 — 처리를 시도하지 말고 보고만
target 이 여럿이면 저장소마다 판정하고, 전체 exit 는 그중 가장 높은 코드다.

파괴적 정리(reset --hard·stash drop·강제 checkout)는 어떤 경우에도 이 도구가 하지 않는다.
"""
import argparse
import json
import os
import re
import subprocess
import sys

OPS_REPO = os.environ.get("OPS_REPO", "jyoliar-lab/ops-workflow")
START_STATUSES = ("Backlog", "Todo")   # 이 상태에서만 착수 전이한다
IN_PROGRESS = "In Progress"            # 착수 전이 목적지 (§5: 사람이 지시한 전이의 대행)
CONTAINER_TYPES = ("Epic", "Feature")

ROOT = os.path.realpath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
WS = os.path.join(ROOT, "workspace", "target")   # 수정 권한의 경계
REF = os.path.join(ROOT, "workspace", "ref")     # 읽기 전용 참조 (hook 가 쓰기 거부)


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


def graphql(query, **variables):
    args = ["gh", "api", "graphql", "-f", "query=" + query]
    for k, v in variables.items():
        args += ["-F" if isinstance(v, (int, bool)) else "-f", "%s=%s" % (k, v)]
    payload = json.loads(run(args).stdout)
    if payload.get("errors"):
        die("거부: GraphQL 오류",
            *["  " + e.get("message", str(e)) for e in payload["errors"]])
    return payload["data"]


# ── 1. 전제 검증 ─────────────────────────────────────────────────────────────

def load_ticket(n):
    owner, _, name = OPS_REPO.partition("/")
    data = graphql(
        "query($o:String!,$r:String!,$n:Int!){repository(owner:$o,name:$r){issue(number:$n){"
        "state title body issueType{name} "
        "projectItems(first:10){nodes{id project{id number} "
        "fieldValueByName(name:\"Status\"){... on ProjectV2ItemFieldSingleSelectValue{name}}}}}}}",
        o=owner, r=name, n=int(n))
    issue = (data.get("repository") or {}).get("issue")
    if not issue:
        die("거부: %s#%s 티켓을 찾지 못했다." % (OPS_REPO, n))
    if issue["state"] != "OPEN":
        die("거부: 티켓 #%s 는 닫혀 있다(%s) — 닫힌 티켓은 집행하지 않는다. 사람에게." % (n, issue["state"]))
    itype = (issue.get("issueType") or {}).get("name") or "?"
    if itype in CONTAINER_TYPES:
        die("거부: #%s 는 %s(컨테이너)다 — 집행 단위가 아니다. 리프(Task·Bug)를 지정하라." % (n, itype))
    return issue


def parse_repos(body):
    line = next((ln for ln in (body or "").splitlines() if "수정 대상(target)" in ln), None)
    if line is None:
        die("거부: 티켓에 '저장소' 절이 없다(절 도입 전 구식 티켓) — 대상을 추측하지 않는다. 사람에게.")
    targets = re.findall(r"`([^`\s]+/[^`\s]+)`", line)
    if not targets:
        die("거부: 수정 대상(target)이 '(없음)' — 신규 저장소 생성 등 대상이 아직 없는 작업이다.",
            "  저장소 이름·위치·생성 방식을 사람과 확인한 뒤 진행하라 (ticket-start ④).")
    ref_line = next((ln for ln in (body or "").splitlines() if "참조(ref)" in ln), None)
    refs = re.findall(r"`([^`\s]+/[^`\s]+)`", ref_line or "")
    return targets, [r for r in refs if r not in targets]


def ensure_refs(refs):
    """나열된 ref 를 선제 clone 한다 (비완전 목록 — 나열 밖은 agent 가 필요 시 직접).
    이미 있으면 건드리지 않는다 — 최신화는 SessionStart hook(refresh-refs.py)의 몫."""
    for repo in refs:
        dest = os.path.join(REF, repo.split("/")[1])
        if os.path.isdir(os.path.join(dest, ".git")):
            print("-- ref: %s (있음 — 세션 시작 시 최신화됨)" % repo)
            continue
        os.makedirs(REF, exist_ok=True)
        run(["git", "clone", "https://github.com/%s.git" % repo, dest])
        print("-- ref: %s clone → workspace/ref/%s (읽기 전용)" % (repo, repo.split("/")[1]))


# ── 2. Status 착수 전이 (Backlog·Todo → In Progress 만. 그 외는 §5 — 사람의 것) ──

def transition_status(issue, n):
    items = [it for it in issue["projectItems"]["nodes"] if it]
    if not items:
        print("-- Status: Project 미등록 티켓 — 전이 생략 (등록은 발행 도구·사람의 것)")
        return
    item = items[0]
    status = (item.get("fieldValueByName") or {}).get("name")
    if status == IN_PROGRESS:
        print("-- Status: 이미 In Progress (이전 착수의 흔적)")
        return
    if status not in START_STATUSES:
        die("거부: 티켓 #%s 의 Status가 '%s' — 착수 전이는 %s 에서만 한다." % (
            n, status, "·".join(START_STATUSES)),
            "  보드 오배치일 수 있다 — 판정은 사람에게.")
    proj = graphql(
        "query($id:ID!){node(id:$id){... on ProjectV2{fields(first:30){nodes{"
        "... on ProjectV2SingleSelectField{id name options{id name}}}}}}}",
        id=item["project"]["id"])
    fields = [f for f in proj["node"]["fields"]["nodes"] if f and f.get("name") == "Status"]
    if not fields:
        print("!! Status 필드를 찾지 못했다 — 전이 생략. 사람에게 알려라.", file=sys.stderr)
        return
    opt = next((o for o in fields[0]["options"] if o["name"] == IN_PROGRESS), None)
    if not opt:
        print("!! Status에 '%s' 옵션이 없다 — 전이 생략. 사람에게 알려라." % IN_PROGRESS, file=sys.stderr)
        return
    graphql(
        "mutation($p:ID!,$i:ID!,$f:ID!,$v:String!){updateProjectV2ItemFieldValue("
        "input:{projectId:$p,itemId:$i,fieldId:$f,value:{singleSelectOptionId:$v}})"
        "{projectV2Item{id}}}",
        p=item["project"]["id"], i=item["id"], f=fields[0]["id"], v=opt["id"])
    print("-- Status: %s → %s (착수 — 사람이 지시한 전이의 대행)" % (status, IN_PROGRESS))


# ── 3. 원격 브랜치 (착수: 미존재 시 원격 기본 브랜치 HEAD 기준으로 원격에 생성) ──

def remote_branch(repo, n, slug):
    refs = json.loads(run(["gh", "api",
                           "repos/%s/git/matching-refs/heads/ticket/%s-" % (repo, n)]).stdout)
    names = [r["ref"][len("refs/heads/"):] for r in refs]
    if len(names) > 1:
        die("거부: %s 에 티켓 #%s 브랜치가 여럿이다: %s" % (repo, n, ", ".join(names)),
            "  어느 것이 유효한지 agent가 판정할 수 없다 — 사람과 정리하라.")
    if names:
        return names[0], False
    # 착수 — 원격에 생성
    if not slug:
        die("거부: %s 에 티켓 #%s 브랜치가 없다(새 착수) — --slug 가 필요하다." % (repo, n),
            "  예: --slug fix-webhook-signature  (소문자 kebab 3–6단어)")
    default = json.loads(run(["gh", "api", "repos/%s" % repo]).stdout)["default_branch"]
    sha = json.loads(run(["gh", "api",
                          "repos/%s/git/ref/heads/%s" % (repo, default)]).stdout)["object"]["sha"]
    branch = "ticket/%s-%s" % (n, slug)
    run(["gh", "api", "-X", "POST", "repos/%s/git/refs" % repo,
         "-f", "ref=refs/heads/%s" % branch, "-f", "sha=%s" % sha])
    print("== 착수: 원격 브랜치 생성 %s @ %s (기점: origin/%s %s)" % (branch, repo, default, sha[:7]))
    return branch, True


# ── 4. bare + worktree 정렬 ──────────────────────────────────────────────────

def ensure_bare(repo):
    name = repo.split("/")[1]
    bare = os.path.join(WS, ".bare", name + ".git")
    if not os.path.isdir(bare):
        os.makedirs(os.path.dirname(bare), exist_ok=True)
        run(["git", "clone", "--bare", "https://github.com/%s.git" % repo, bare])
        # bare 의 기본 refspec 은 원격 추적을 만들지 않는다 — 일반 클론처럼 동작하게 설정
        run(["git", "-C", bare, "config", "remote.origin.fetch",
             "+refs/heads/*:refs/remotes/origin/*"])
    run(["git", "-C", bare, "fetch", "--prune", "origin"])
    return bare


def report_progress(repo, bare, branch, n):
    """사람·agent가 '이어서/새로'를 판단할 근거. exit 3 사유(머지된 PR)를 감지한다."""
    default = run(["git", "-C", bare, "symbolic-ref", "--short", "HEAD"], check=False)
    default = (default.stdout.strip() or "main")
    log = run(["git", "-C", bare, "log", "--oneline",
               "origin/%s..origin/%s" % (default, branch)]).stdout.strip()
    print("-- 진행 커밋 (origin/%s 이후):" % default)
    print("   " + log.replace("\n", "\n   ") if log else "   (없음)")
    prs = json.loads(run(["gh", "pr", "list", "-R", repo, "--head", branch,
                          "--state", "all", "--json", "url,state"]).stdout)
    for pr in prs:
        print("-- PR: %s (%s)" % (pr["url"], pr["state"]))
    if any(p["state"] == "MERGED" for p in prs) and not any(p["state"] == "OPEN" for p in prs):
        print("!! PR은 머지됐는데 티켓 #%s 는 열려 있다 — 후속 작업인지 close 대기인지" % n,
              "   agent가 판정할 수 없다. 보고만 하고 사람에게. [exit 3]", sep="\n")
        return 3
    return 0


def align_worktree(repo, bare, branch, n):
    """분기표: (behind ⓐ, ahead ⓒ, dirty ⓑ) → exit 0/2/3."""
    name = repo.split("/")[1]
    wt = os.path.join(WS, name, "ticket-%s" % n)

    if not os.path.isdir(wt):
        os.makedirs(os.path.join(WS, name), exist_ok=True)
        has_local = run(["git", "-C", bare, "branch", "--list", branch]).stdout.strip()
        if has_local:
            run(["git", "-C", bare, "worktree", "add", wt, branch])
        else:
            run(["git", "-C", bare, "worktree", "add", "--track",
                 "-b", branch, wt, "origin/%s" % branch])
        print("-- worktree 생성: %s (새 디렉터리 — 깨끗한 시작)" % os.path.relpath(wt, ROOT))
        return 0

    counts = run(["git", "-C", wt, "rev-list", "--left-right", "--count",
                  "origin/%s...HEAD" % branch]).stdout.split()
    behind, ahead = int(counts[0]), int(counts[1])
    dirty = run(["git", "-C", wt, "status", "--porcelain"]).stdout.strip()
    print("-- worktree: %s  (behind %d · ahead %d · dirty %s)" % (
        os.path.relpath(wt, ROOT), behind, ahead, "있음" if dirty else "없음"))

    if behind == 0:
        if ahead:
            print("-- push 안 된 로컬 커밋 %d개 — 작업 흐름대로 push하면 된다." % ahead)
        if dirty:
            print("-- 커밋 안 된 변경 (진행 현황에 포함해 파악하라):")
            print("   " + dirty.replace("\n", "\n   "))
        return 0
    if ahead == 0 and not dirty:
        run(["git", "-C", wt, "pull", "--ff-only"])   # ⓒ=0 이므로 ff 는 항상 성공한다
        print("-- 원격 커밋 %d개 pull 완료 (ff)" % behind)
        return 0
    if ahead == 0 and dirty:
        print("!! 원격에만 있는 커밋 %d개 + 커밋 안 된 로컬 변경 — pull하지 않았다." % behind)
        print(run(["git", "-C", wt, "log", "--oneline", "HEAD..origin/%s" % branch]).stdout.rstrip())
        print("   로컬 변경:")
        print("   " + dirty.replace("\n", "\n   "))
        print("   → 처리 방안을 사람에게 제안하고, 승인 후 진행하라. [exit 2]")
        return 2
    # behind>0 & ahead>0 — 양방향 분기
    print("!! 양방향 분기 — 원격에만 %d개, 로컬에만 %d개. 처리를 시도하지 말고 보고만." % (behind, ahead))
    print("   원격에만: \n   " + run(["git", "-C", wt, "log", "--oneline",
                                    "HEAD..origin/%s" % branch]).stdout.strip().replace("\n", "\n   "))
    print("   로컬에만: \n   " + run(["git", "-C", wt, "log", "--oneline",
                                    "origin/%s..HEAD" % branch]).stdout.strip().replace("\n", "\n   "))
    print("   → merge/rebase는 사람과 정한다 (force 금지). [exit 3]")
    return 3


# ── main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(add_help=True)
    parser.add_argument("ticket", help="티켓 번호")
    parser.add_argument("--slug", help="새 착수 시 브랜치 슬러그 (소문자 kebab 3–6단어)")
    args = parser.parse_args()
    n = args.ticket.lstrip("#")

    issue = load_ticket(n)
    print("== 티켓 #%s — %s" % (n, issue["title"]))
    targets, refs = parse_repos(issue["body"])
    print("== target: %s" % ", ".join(targets))
    if refs:
        print("== ref: %s (비완전 목록 — 나열 밖 참조 허용)" % ", ".join(refs))
    transition_status(issue, n)
    ensure_refs(refs)

    worst = 0
    for repo in targets:
        print("\n== %s" % repo)
        branch, created = remote_branch(repo, n, args.slug)
        bare = ensure_bare(repo)
        if not created:
            worst = max(worst, report_progress(repo, bare, branch, n))
        worst = max(worst, align_worktree(repo, bare, branch, n))

    print("\n== 완료 — exit %d" % worst)
    sys.exit(worst)


if __name__ == "__main__":
    main()
