#!/usr/bin/env python3
"""티켓 진행 — 단일 진입점 (착수 포함). target 저장소마다 원격-우선으로 로컬 worktree를 정렬한다.

사용: ticket-run.py <ticket-number> [--slug <slug>]
  --slug 는 "새 착수"(원격에 티켓 브랜치가 없을 때)에만 필요하다. 소문자 kebab 3–6단어.

원격이 진실의 원천이다:
  - 착수 판별 = 원격에 ticket/<N>-* 브랜치가 있는가. 로컬 상태는 판별·기점에 영향 없음.
  - 새 브랜치는 원격 기본 브랜치 HEAD 기준으로 "원격에", 티켓 이슈의 linked branch 로
    생성된다(Development 필드 연결). linked PR 머지의 자동 close 는 코드가 아니라
    이슈 저장소 설정 해제로 막는다(CLAUDE.md 수동 불변식 — close 는 사람의 것).
로컬은 티켓별 worktree다 (동시 여러 티켓 안전 — 공유 HEAD 없음):
  workspace/target/.bare/<repo>.git      ← bare 저장소. 도구만 만진다 (hook가 Write 거부)
  workspace/target/<repo>/ticket-<N>/    ← 티켓 worktree = 작업 디렉터리
  workspace/ref/<repo>                   ← 참조 저장소(읽기 전용). 티켓에 나열된 ref 는
                                            이 도구가 선제 clone 한다. ref 는 비완전 목록이라
                                            나열 밖 저장소는 agent 가 필요 시 직접 clone.

착수 게이트: 착수 전이 직전에 **계층 전체**(리프 + 부모 컨테이너들)를 검사한다 —
근거 ADR 전부 accepted("결정이 굳었는가" — 발행은 공표만 요구했다) + Status 전부
Todo/In Progress("사람이 확신했는가" — Draft 해제는 사람). 두 조건은 독립이다.
통과 시 Todo 에 머문 부모는 In Progress 로 파생 전이된다(리프의 착수는 묶음의 착수).
게이트와 전이가 한 스크립트에 있으므로 전이가 게이트를 건너뛸 수 없다.

exit 코드 = agent의 다음 행동 (프롬프트 해석에 기대지 않는다):
  0 = 진행하라 (케이스별 정보는 stdout — 읽고 판단·처리)
  1 = 전제 거부 (티켓 닫힘·컨테이너·target 없음·열린 선행(ADR-0017)·착수 게이트(계층의
      미accept 근거·Draft 등) — 우회 금지)
  2 = 승인 대기 — 상태를 파악해 처리 방안을 사람에게 제안하고, 승인 후 진행
  3 = 사람 개입 필요 — 처리를 시도하지 말고 보고만
target 이 여럿이면 저장소마다 판정하고, 전체 exit 는 그중 가장 높은 코드다.

파괴적 정리(reset --hard·stash drop·강제 checkout)는 어떤 경우에도 이 도구가 하지 않는다.
"""
import argparse
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "_lib"))
from _common import (EXIT_APPROVAL, EXIT_HUMAN, EXIT_PROCEED, EXIT_REJECT,  # noqa: E402
                     OPS_REPO, REF_DIR, TARGET_DIR, Reject, block, gh_json,
                     rel, run, run_cli)
import adrs  # noqa: E402  ('근거 ADR' 절 쌍둥이 파서 + 코퍼스 status 조회 — 원본은 ops-workflow adr_context.py)
import comments  # noqa: E402  (코멘트 fetch·출력 — preflight 와 공유. 문구의 원천은 한 곳)
from repos import parse_section  # noqa: E402  ('저장소' 절 파서 — 표기 원본은 ops-workflow repo_context.py)

# 착수 전이: 이 상태에서만 In Progress 로 (§5 — 사람이 지시한 전이의 대행).
# Draft 는 확신 전이라 착수 대상이 아니다 — 해제(→ Todo)는 사람의 판정이다 (ADR-0033).
START_STATUSES = ("Todo",)
IN_PROGRESS = "In Progress"
GATE_OK_STATUSES = ("Todo", IN_PROGRESS)   # 착수 게이트가 계층 전체에 요구하는 Status
CONTAINER_TYPES = ("Epic", "Feature")


def graphql(query, **variables):
    args = ["api", "graphql", "-f", "query=" + query]
    for k, v in variables.items():
        args += ["-F" if isinstance(v, (int, bool)) else "-f", "%s=%s" % (k, v)]
    payload = gh_json(*args)

    if payload.get("errors"):
        raise Reject("거부: GraphQL 오류",
                     *["  " + e.get("message", str(e)) for e in payload["errors"]])

    return payload["data"]


# ── 1. 티켓 로드·전제 검증 ───────────────────────────────────────────────────

_ISSUE_QUERY = (
    "query($o:String!,$r:String!,$n:Int!){repository(owner:$o,name:$r){issue(number:$n){"
    "number state title body issueType{name} parent{number} "
    "blockedBy(first:50){nodes{number state title}} "
    "projectItems(first:10){nodes{id project{id number} "
    "fieldValueByName(name:\"Status\"){... on ProjectV2ItemFieldSingleSelectValue{name}}}}}}}")


def fetch_issue(n):
    """이슈 하나를 계층·게이트 판정에 필요한 필드째 읽는다 (리프·부모 공용)."""
    owner, _, name = OPS_REPO.partition("/")
    data = graphql(_ISSUE_QUERY, o=owner, r=name, n=int(n))
    issue = (data.get("repository") or {}).get("issue")

    if not issue:
        raise Reject("거부: %s#%s 티켓을 찾지 못했다." % (OPS_REPO, n))

    return issue


def load_ticket(n):
    """열린 리프 티켓만 통과한다 — 닫힘·컨테이너는 전제 거부."""
    issue = fetch_issue(n)

    if issue["state"] != "OPEN":
        raise Reject("거부: 티켓 #%s 는 닫혀 있다(%s) — 닫힌 티켓은 집행하지 않는다. 사람에게." % (n, issue["state"]))

    itype = (issue.get("issueType") or {}).get("name") or "?"

    if itype in CONTAINER_TYPES:
        raise Reject("거부: #%s 는 %s(컨테이너)다 — 집행 단위가 아니다. 리프(Task·Bug)를 지정하라." % (n, itype))

    return issue


def current_status(issue):
    """보드 Status 이름 (Project 미등록이면 None)."""
    items = [it for it in issue["projectItems"]["nodes"] if it]
    return (items[0].get("fieldValueByName") or {}).get("name") if items else None


def load_ancestors(issue):
    """부모 계층을 리프에서 위로 걷는다 → [부모, 조부모, ...].
    깊이 상한은 없다(권장 3층 · GitHub 자체 상한 8단) — 끝까지 걷는다. `seen` 이 순환을 막는다."""
    chain, seen = [], {issue.get("number")}
    cur = issue

    while True:
        num = (cur.get("parent") or {}).get("number")

        if not num or num in seen:
            return chain

        seen.add(num)
        cur = fetch_issue(num)
        chain.append(cur)


def check_start_gate(issue, ancestors, n):
    """착수 게이트 — 두 독립 조건을 **계층 전체**(자신 + 부모들)에 요구한다:
      ① 근거 ADR 전부 accepted — "결정이 굳었는가" (기계 판정. 발행 게이트는 공표만 요구했다)
      ② Status 전부 Todo·In Progress — "사람이 확신했는가" (Draft 해제는 사람의 판정)
    리프는 부모의 근거를 되풀이하지 않으므로(사본은 낡는다) 여기서 거슬러 올라 모아야
    Epic 의 근거까지 게이트된다. 부모가 In Review·Done 이어도 거부한다 — 그 밑에 착수할
    리프가 남았다는 것은 사람의 전이 실수 신호다. 되돌림은 사람이 한다(도구는 대신하지 않는다).
    재개(리프가 이미 In Progress)에서 걸리면 보고만(exit 3) — 착수 후 바뀐 전제(supersede 등)다.
    """
    corpus = os.path.join(REF_DIR, OPS_REPO.split("/")[1])
    problems = []

    seen_adrs = set()
    for lvl in [issue] + ancestors:
        try:
            entries = adrs.parse_section(lvl.get("body") or "")
        except ValueError as e:
            raise Reject(
                "거부: #%s 의 '근거 ADR' 절 표기를 읽을 수 없다 — %s" % (lvl["number"], e),
                "  손으로 고치지 않는다 — 재기입은 사람의 것(ops-workflow 의 set-adr.py). 사람에게 알리고 기다린다.")

        for adr_id, path, _sha in entries or []:
            if adr_id in seen_adrs:
                continue

            seen_adrs.add(adr_id)
            status = adrs.adr_status(corpus, adr_id, path)

            if status is None:
                problems.append("   #%s 근거 %s — 코퍼스(ref 사본)에서 찾지 못했다"
                                % (lvl["number"], adr_id))
            elif status != "accepted":
                problems.append("   #%s 근거 %s — status '%s' (accepted 아님)"
                                % (lvl["number"], adr_id, status))

    for a in ancestors:
        status = current_status(a)

        if status is None:
            problems.append("   부모 #%s — Project 미등록 (Status 를 판정할 수 없다 — 사람에게)"
                            % a["number"])
        elif status not in GATE_OK_STATUSES:
            problems.append("   부모 #%s — Status '%s'" % (a["number"], status))

    if not problems:
        return

    if current_status(issue) == IN_PROGRESS:
        raise Reject(
            "!! 진행 중 티켓 #%s 의 착수 전제가 무너져 있다 — 착수 후 바뀐 전제다." % n,
            *problems,
            "   처리를 시도하지 말고 보고만 — 벌어진 작업의 처분은 사람의 판단이다.",
            code=EXIT_HUMAN)

    raise Reject(
        "거부: 티켓 #%s 는 착수 전제가 갖춰지지 않았다 — 착수는 계층 전체에 요구한다:" % n,
        "   ① 근거 ADR(자신+부모) 전부 accepted — 결정이 굳었는가",
        "   ② 자신·부모 Status 전부 Todo·In Progress — 사람이 확신했는가",
        *problems,
        "   accept(결정을 굳힌다)·Draft 해제(확신 판정)·In Review/Done 부모의 되돌림은",
        "   전부 사람의 일이다 — 우회하지 않고 보고하라.",
        "   (근거 ADR status 는 세션 시작 시점의 ref 사본 기준 — 방금 accept 됐다면 새 세션에서.)")


def check_dependencies(issue, n):
    """착수 게이트 (ADR-0017) — 열린 선행(blocked-by) 위에는 착수하지 않는다.
    새 착수: 전제 거부(exit 1). 재개(In Progress): 착수 후 추가된 의존 — 보고만(exit 3)."""
    blockers = [b for b in (issue.get("blockedBy") or {}).get("nodes") or [] if b]

    for b in blockers:
        if b["state"] != "OPEN":
            print("-- 선행 #%s close 확인 — %s" % (b["number"], b["title"]))

    open_blockers = [b for b in blockers if b["state"] == "OPEN"]
    if not open_blockers:
        return

    lines = ["   #%s %s" % (b["number"], b["title"]) for b in open_blockers]

    if current_status(issue) == IN_PROGRESS:
        raise Reject(
            "!! 진행 중 티켓 #%s 에 열린 선행이 있다 — 착수 후 추가된 의존이다." % n,
            *lines,
            "   처리를 시도하지 말고 보고만 — 벌어진 작업의 처분은 사람의 판단이다 (ADR-0017).",
            code=EXIT_HUMAN)

    raise Reject(
        "거부: 티켓 #%s 는 열린 선행에 막혀 있다 — 선행의 close(사람 검수) 전에는 착수하지 않는다." % n,
        *lines,
        "   선행이 close 된 뒤 다시 시도하라. 관계가 실제와 어긋났다고 보이면 사람에게 —",
        "   갱신은 사람의 것(ops-workflow 의 set-deps.py)이다 — agent 는 알리기만 한다.")


def parse_repos(body):
    """티켓 '저장소' 절(YAML 블록) → (target 목록, ref 목록). target 은 필수, ref 는 비완전 힌트."""
    try:
        parsed = parse_section(body or "")
    except ValueError as e:
        raise Reject("거부: 티켓 '저장소' 절의 표기를 읽을 수 없다 — %s" % e,
                     "  손으로 고치지 않는다(본문과 보드 필드가 갈라진다) —",
                     "  재기입은 사람의 것(ops-workflow 의 set-repos.py). 사람에게 알리고 기다린다.")
    if parsed is None:
        raise Reject("거부: 티켓에 '저장소' 절이 없다(절 도입 전 구식 티켓) — 대상을 추측하지 않는다.",
                     "  절 기입은 사람의 것(ops-workflow 의 set-repos.py) — 사람에게 알리고 기다린다.")
    targets, no_target, refs = parsed
    if no_target:
        raise Reject("거부: 수정 대상(target)이 부재 선언(null) — 신규 저장소 생성 등 대상이 아직 없는 작업이다.",
                     "  ① 이름·위치(조직)·공개 여부를 사람과 확인한다 (추측하지 않는다)",
                     "  ② 합의되면 gh repo create 로 생성한다",
                     "  ③ 사람이 ops-workflow 의 set-repos.py 로 티켓의 target 을 기입한다",
                     "  ④ 이 도구를 다시 실행한다.")
    return targets, [r for r in refs if r not in targets]


# ── 2. Status 착수 전이 ──────────────────────────────────────────────────────

def _set_status(item, to_name):
    """Project item 의 Status 를 to_name 으로 (옵션 id 조회 포함). → 성공 여부."""
    proj = graphql(
        "query($id:ID!){node(id:$id){... on ProjectV2{fields(first:30){nodes{"
        "... on ProjectV2SingleSelectField{id name options{id name}}}}}}}",
        id=item["project"]["id"])
    fields = [f for f in proj["node"]["fields"]["nodes"] if f and f.get("name") == "Status"]
    option = next((o for f in fields for o in f["options"] if o["name"] == to_name), None)

    if not option:
        print("!! Status 필드/'%s' 옵션을 찾지 못했다 — 전이 생략. 사람에게 알려라." % to_name,
              file=sys.stderr)
        return False

    graphql(
        "mutation($p:ID!,$i:ID!,$f:ID!,$v:String!){updateProjectV2ItemFieldValue("
        "input:{projectId:$p,itemId:$i,fieldId:$f,value:{singleSelectOptionId:$v}})"
        "{projectV2Item{id}}}",
        p=item["project"]["id"], i=item["id"], f=fields[0]["id"], v=option["id"])
    return True


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
        raise Reject("거부: 티켓 #%s 의 Status가 '%s' — 착수 전이는 %s 에서만 한다."
                     % (n, status, "·".join(START_STATUSES)),
                     "  Draft 면 확신 판정(해제 → Todo)이 먼저다 — 그 판정은 사람의 것이다.",
                     "  보드 오배치일 수도 있다 — 어느 쪽이든 판정은 사람에게.")

    if _set_status(item, IN_PROGRESS):
        print("-- Status: %s → %s (착수 — 사람이 지시한 전이의 대행)" % (status, IN_PROGRESS))


def transition_parents(ancestors):
    """Todo 에 머문 부모를 In Progress 로 — 리프의 착수는 곧 그 묶음의 착수다.
    사람이 지시한 리프 착수의 **파생 전이**다("Status 는 사람의 것" 규범과 충돌하지 않는다).
    방향은 착수(Todo → In Progress)뿐 — 되돌림(In Review·Done → …)은 도구가 대신하지 않는다."""
    for a in ancestors:
        items = [it for it in a["projectItems"]["nodes"] if it]

        if not items:
            continue                    # 미등록은 게이트가 이미 거부했다 — 방어적 생략

        item = items[0]

        if (item.get("fieldValueByName") or {}).get("name") != "Todo":
            continue

        if _set_status(item, IN_PROGRESS):
            print("-- Status: 부모 #%s Todo → %s (파생 전이 — 리프의 착수는 묶음의 착수다)"
                  % (a["number"], IN_PROGRESS))


# ── 3. ref 선제 clone (비완전 목록 — 나열 밖은 agent 가 필요 시 직접) ─────────

def ensure_refs(refs):
    """이미 있으면 건드리지 않는다 — 최신화는 SessionStart hook(refresh-refs.py)의 몫."""
    for repo in refs:
        dest = os.path.join(REF_DIR, repo.split("/")[1])

        if os.path.isdir(os.path.join(dest, ".git")):
            print("-- ref: %s (있음 — 세션 시작 시 최신화됨)" % repo)
            continue

        os.makedirs(REF_DIR, exist_ok=True)
        run(["git", "clone", "https://github.com/%s.git" % repo, dest])
        print("-- ref: %s clone → %s (읽기 전용)" % (repo, rel(dest)))


# ── 4. 원격 브랜치 (착수: 미존재 시 linked branch 로 원격에 생성 — Development 연결) ──

def remote_branch(repo, n, slug):
    """→ (브랜치명, 새로 만들었는가). 존재 판별은 slug 가 아니라 ticket/<N>- 접두로."""
    refs = gh_json("api", "repos/%s/git/matching-refs/heads/ticket/%s-" % (repo, n))
    names = [r["ref"][len("refs/heads/"):] for r in refs]

    if len(names) > 1:
        raise Reject("거부: %s 에 티켓 #%s 브랜치가 여럿이다: %s" % (repo, n, ", ".join(names)),
                     "  어느 것이 유효한지 agent가 판정할 수 없다 — 사람과 정리하라.")

    if names:
        return names[0], False

    if not slug:
        raise Reject("거부: %s 에 티켓 #%s 브랜치가 없다(새 착수) — --slug 가 필요하다." % (repo, n),
                     "  예: --slug fix-webhook-signature  (소문자 kebab 3–6단어)")

    default = gh_json("api", "repos/%s" % repo)["default_branch"]
    branch = "ticket/%s-%s" % (n, slug)

    # linked PR 머지의 자동 close 는 이슈 저장소(ops-workflow)의 설정
    # "Auto-close issues with merged linked pull requests" 해제로 막는다 — 코드 가드 없음.
    run(["gh", "issue", "develop", "%s" % n, "-R", OPS_REPO,
         "--branch-repo", repo, "--name", branch, "--base", default])
    sha = gh_json("api", "repos/%s/git/ref/heads/%s" % (repo, branch))["object"]["sha"]
    print("== 착수: linked branch 생성 %s @ %s (기점: origin/%s %s · Development 연결 %s#%s)"
          % (branch, repo, default, sha[:7], OPS_REPO, n))
    return branch, True


# ── 5. bare + worktree 정렬 ──────────────────────────────────────────────────

def ensure_bare(repo):
    name = repo.split("/")[1]
    bare = os.path.join(TARGET_DIR, ".bare", name + ".git")

    if not os.path.isdir(bare):
        os.makedirs(os.path.dirname(bare), exist_ok=True)
        run(["git", "clone", "--bare", "https://github.com/%s.git" % repo, bare])
        # bare 의 기본 refspec 은 원격 추적을 만들지 않는다 — 일반 클론처럼 동작하게 설정
        run(["git", "-C", bare, "config", "remote.origin.fetch",
             "+refs/heads/*:refs/remotes/origin/*"])

    run(["git", "-C", bare, "fetch", "--prune", "origin"])
    return bare


def report_progress(repo, bare, branch, n):
    """사람·agent가 '이어서/새로'를 판단할 근거. 머지된 PR + 열린 티켓이면 Reject(HUMAN).
    squash 머지로 수확된 커밋(마지막 머지 PR의 head까지)은 진행 커밋과 구분해 보인다 —
    main에 반영 완료된 것을 미반영처럼 읽으면 낡은 브랜치 위 작업을 오판한다."""
    head = run(["git", "-C", bare, "symbolic-ref", "--short", "HEAD"], check=False)
    default = head.stdout.strip() or "main"

    prs = gh_json("pr", "list", "-R", repo, "--head", branch,
                  "--state", "all", "--json", "number,url,state,headRefOid,mergedAt")
    merged = [p for p in prs if p["state"] == "MERGED"]
    latest = max(merged, key=lambda p: p.get("mergedAt") or "") if merged else None
    tip = run(["git", "-C", bare, "rev-parse", "origin/%s" % branch]).stdout.strip()
    cut = (latest["headRefOid"]
           if latest and run(["git", "-C", bare, "merge-base", "--is-ancestor",
                              latest["headRefOid"], tip], check=False).returncode == 0
           else None)

    if cut:
        old = run(["git", "-C", bare, "log", "--oneline",
                   "origin/%s..%s" % (default, cut)]).stdout.strip()

        if old:
            print("-- 수확 완료 커밋 (PR #%s squash 머지로 origin/%s 반영 — 진행분 아님):"
                  % (latest["number"], default))
            print(block(old))

        log = run(["git", "-C", bare, "log", "--oneline",
                   "%s..origin/%s" % (cut, branch)]).stdout.strip()
        print("-- 진행 커밋 (머지 이후):")
    else:
        log = run(["git", "-C", bare, "log", "--oneline",
                   "origin/%s..origin/%s" % (default, branch)]).stdout.strip()
        print("-- 진행 커밋 (origin/%s 이후):" % default)

    print(block(log) if log else "   (없음)")

    for pr in prs:
        print("-- PR: %s (%s)" % (pr["url"], pr["state"]))

    if merged and not any(p["state"] == "OPEN" for p in prs):
        raise Reject(
            "!! PR은 머지됐는데 티켓 #%s 는 열려 있다 — 후속 작업인지 close 대기인지" % n,
            "   agent가 판정할 수 없다. 보고만 하고 사람에게.",
            "   후속 작업으로 확인되면 이 worktree에서 그대로 진행하라 — 낡은 브랜치의",
            "   재정렬(수확 커밋 잘라내기)은 PR 생성 관문(ticket-pr.py)이 한다.",
            code=EXIT_HUMAN)


def create_worktree(bare, branch, wt):
    """새 worktree — 새 디렉터리라 항상 깨끗한 시작이다."""
    os.makedirs(os.path.dirname(wt), exist_ok=True)
    has_local = run(["git", "-C", bare, "branch", "--list", branch]).stdout.strip()

    if has_local:
        run(["git", "-C", bare, "worktree", "add", wt, branch])
    else:
        run(["git", "-C", bare, "worktree", "add", "--track",
             "-b", branch, wt, "origin/%s" % branch])

    print("-- worktree 생성: %s (새 디렉터리 — 깨끗한 시작)" % rel(wt))


def sync_worktree(wt, branch):
    """재개 — 3축(behind ⓐ · ahead ⓒ · dirty ⓑ) 사전 판별 → 분기표.
    pull 을 시도하고 실패를 처리하는 오류 경로가 아니라, 일급 분기다.
    진행 가능하면 그대로 반환, 개입이 필요하면 Reject(APPROVAL/HUMAN)를 던진다."""
    counts = run(["git", "-C", wt, "rev-list", "--left-right", "--count",
                  "origin/%s...HEAD" % branch]).stdout.split()
    behind, ahead = int(counts[0]), int(counts[1])
    dirty = run(["git", "-C", wt, "status", "--porcelain"]).stdout.strip()
    print("-- worktree: %s  (behind %d · ahead %d · dirty %s)" % (
        rel(wt), behind, ahead, "있음" if dirty else "없음"))

    def remote_only_log():
        return run(["git", "-C", wt, "log", "--oneline",
                    "HEAD..origin/%s" % branch]).stdout.strip()

    if behind == 0:
        # 원격에 새 것 없음 — 로컬 상태 그대로 진행
        if ahead:
            print("-- push 안 된 로컬 커밋 %d개 — 작업 흐름대로 push하면 된다." % ahead)

        if dirty:
            print("-- 커밋 안 된 변경 (진행 현황에 포함해 파악하라):")
            print(block(dirty))

        return

    if ahead == 0 and not dirty:
        run(["git", "-C", wt, "pull", "--ff-only"])   # ⓒ=0 이므로 ff 는 항상 성공한다
        print("-- 원격 커밋 %d개 pull 완료 (ff)" % behind)
        return

    if ahead == 0:
        # 원격 커밋 + 로컬 미커밋 변경 — agent 가 파악해 제안하고, 사람 승인 후 진행
        raise Reject(
            "!! 원격에만 있는 커밋 %d개 + 커밋 안 된 로컬 변경 — pull하지 않았다." % behind,
            block(remote_only_log()),
            "   로컬 변경:",
            block(dirty),
            "   → 처리 방안을 사람에게 제안하고, 승인 후 진행하라.",
            code=EXIT_APPROVAL)

    # 양방향 분기 — 처리(merge/rebase)는 사람과. force 금지.
    raise Reject(
        "!! 양방향 분기 — 원격에만 %d개, 로컬에만 %d개. 처리를 시도하지 말고 보고만." % (behind, ahead),
        "   원격에만:",
        block(remote_only_log()),
        "   로컬에만:",
        block(run(["git", "-C", wt, "log", "--oneline",
                   "origin/%s..HEAD" % branch]).stdout.strip()),
        "   → merge/rebase는 사람과 정한다 (force 금지).",
        code=EXIT_HUMAN)


def align_target(repo, n, slug):
    """한 target 저장소의 원격 브랜치·bare·worktree 를 정렬한다.
    진행 가능하면 그대로 반환 — 개입이 필요하면 Reject 가 올라온다."""
    print("\n== %s" % repo)
    branch, created = remote_branch(repo, n, slug)
    bare = ensure_bare(repo)

    if not created:
        report_progress(repo, bare, branch, n)

    wt = os.path.join(TARGET_DIR, repo.split("/")[1], "ticket-%s" % n)

    if not os.path.isdir(wt):
        create_worktree(bare, branch, wt)
    else:
        sync_worktree(wt, branch)


# ── main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(add_help=True)
    parser.add_argument("ticket", help="티켓 번호")
    parser.add_argument("--slug", help="새 착수 시 브랜치 슬러그 (소문자 kebab 3–6단어)")
    args = parser.parse_args()
    n = args.ticket.lstrip("#")

    issue = load_ticket(n)
    print("== 티켓 #%s — %s" % (n, issue["title"]))
    comments.show(comments.fetch_all(n))   # 본문 밖 요구·재개 맥락 — 관문이 실어 나른다
    check_dependencies(issue, n)   # 열린 선행 위에는 착수하지 않는다 (ADR-0017)
    ensure_refs([OPS_REPO])        # 정책·티켓 코퍼스 — 착수 게이트가 근거 ADR status 를 읽는다
    ancestors = load_ancestors(issue)
    check_start_gate(issue, ancestors, n)   # 계층 전체: ADR accepted + 비Draft (착수의 문)
    targets, refs = parse_repos(issue["body"])
    print("== target: %s" % ", ".join(targets))

    if refs:
        print("== ref: %s (비완전 목록 — 나열 밖 참조 허용)" % ", ".join(refs))

    transition_status(issue, n)
    transition_parents(ancestors)  # Todo 부모 → In Progress (리프 착수의 파생 전이)
    ensure_refs(refs)

    # target 마다 정렬한다. 개입 필요(2·3)는 여기서 받아 "다음 target 을 계속" 보고,
    # 전체 exit 는 최악의 코드다. 전제 거부(1)만 즉시 전파한다 — 나머지도 의미가 없다.
    worst = EXIT_PROCEED

    for repo in targets:
        try:
            align_target(repo, n, args.slug)
        except Reject as exc:
            if exc.code == EXIT_REJECT:
                raise

            for line in exc.lines:
                print(line)

            worst = max(worst, exc.code)

    print("\n== 완료 — exit %d" % worst)
    sys.exit(worst)


if __name__ == "__main__":
    run_cli(main)   # 거부(Reject)→exit 1 변환은 여기서만 일어난다
