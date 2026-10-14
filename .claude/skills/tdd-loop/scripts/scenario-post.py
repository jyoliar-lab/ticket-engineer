#!/usr/bin/env python3
"""시나리오 코멘트의 게시 · 제자리 갱신 · 승인 표식 · 진행 칸 — tdd-loop 의 관문.

사용:
  scenario-post.py <N> --repo <owner/repo> <file> [<file> …]              게시 또는 갱신
  scenario-post.py <N> --repo <owner/repo> --approve "<단위>"              승인 표식
  scenario-post.py <N> --repo <owner/repo> --progress "<단위>" <단계> "<한 줄>"   진행 행 덧붙이기 (red · green · verify)

파일은 tmp/github-issues/ 의 시나리오 초안이다. 첫 줄이 머리다:
  ### TDD 시나리오 — <owner/repo> — <단위>        (색인은 단위 자리에 `공통 · 색인`)

머리가 곧 코멘트의 열쇠다 — 같은 머리의 코멘트가 이미 있으면 새 코멘트를 내지 않고
그 코멘트를 PATCH 한다. 세션이 바뀌어 코멘트 ID 를 잃어도 같은 자리로 간다.
변경은 GitHub 의 편집 이력이 보인다 — 산문 요약을 머리에 쓰지 않는다.

머리 아래 두 자리는 스크립트가 쓴다 — 파일에 있으면 거부한다:
  > v3 · 승인 v2 — 2026-10-11          판 · 승인. 본문이 바뀌면 판이 오르고 승인은 그 판에 붙은 채 남는다
                                        — 승인 뒤 바뀌었음이 보인다. --approve 는 현행 판에 붙는다(판 불변).
  | 단계 | 흔적 |  … red · green · verify     단위 하나의 진행이 한 코멘트에 모인다 — 단계를 지날 때마다 행 하나를
                                        덧붙인다(판 불변). 되감기(red → green → verify → red → …)가 행 순서로 보인다.
                                        green 행은 green + refactor 둘을 담는다(tdd-green 이 한 번에 한다). 코멘트가 곧
                                        그 단위의 스레드다.

색인 파일의 `{url:<단위>}` 는 그 단위 코멘트의 URL 로 바뀐다 — 단위 파일을 먼저(같은 호출에
함께) 넘긴다. 색인은 언제나 단위들 뒤에 게시된다.

거부(exit 1): 머리 없음 · 저장소 불일치 · 머리 중복 · 손으로 쓴 판 줄 · 진행 표 · 풀 수 없는 {url:} ·
승인 전 진행 · 코멘트 한도(65k) 초과 — 단위가 너무 크다는 신호다, 더 가른다.
"""
import argparse
import datetime as dt
import os
import re
import sys
from dataclasses import dataclass, field

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "_lib"))
import comments  # noqa: E402
from _common import OPS_REPO, Reject, gh_json, run_cli  # noqa: E402

HEADING = re.compile(r"^### TDD 시나리오 — (?P<repo>[\w.-]+/[\w.-]+) — (?P<unit>.+?)\s*$")
META = re.compile(r"^> v(?P<v>\d+)(?: · 승인 v(?P<av>\d+) — (?P<ad>\d{4}-\d{2}-\d{2}))?\s*$")
PROGRESS_HEAD = "| 단계 | 흔적 |"
PROGRESS_ROW = re.compile(r"^\| (?P<stage>red|green|verify) \| (?P<text>.*) \|\s*$")
PLACEHOLDER = re.compile(r"\{url:(?P<unit>[^}]+)\}")
STAGES = ("red", "green", "verify")
INDEX_UNIT = "공통 · 색인"
COMMENT_LIMIT = 65000


@dataclass(frozen=True)
class Draft:
    """초안 파일 하나 — 머리와 본문(머리 제외)."""
    path: str
    repo: str
    unit: str
    body: str                      # 머리 · 판 줄 · 진행 표를 뺀 본문

    @property
    def is_index(self) -> bool:
        return self.unit == INDEX_UNIT


@dataclass
class Posted:
    """이슈에 있는 시나리오 코멘트 하나."""
    comment_id: int
    url: str
    unit: str
    version: int
    approved_version: int | None
    approved_date: str | None
    body: str                      # 머리 · 판 줄 · 진행 표를 뺀 본문
    progress: list[tuple[str, str]] = field(default_factory=list)   # (단계, 한 줄) — 지난 순서대로


def read_draft(path: str, repo: str) -> Draft:
    if not os.path.isfile(path):
        raise Reject("거부: 파일을 읽을 수 없다 — %s" % path)
    with open(path, encoding="utf-8") as f:
        lines = f.read().splitlines()
    if not lines or not HEADING.match(lines[0]):
        raise Reject("거부: %s — 첫 줄이 머리가 아니다." % path,
                     "   머리: `### TDD 시나리오 — <owner/repo> — <단위>` (색인은 `— %s`)." % INDEX_UNIT,
                     "   머리가 코멘트의 열쇠다 — 같은 머리면 같은 코멘트를 갱신한다(scenarios.md §4).")
    m = HEADING.match(lines[0])
    assert m is not None
    if m.group("repo").lower() != repo.lower():
        raise Reject("거부: %s — 머리의 저장소 %s 가 --repo %s 와 다르다." % (path, m.group("repo"), repo))
    for line in lines[1:]:
        if META.match(line):
            raise Reject("거부: %s — 판 · 승인 줄(`%s`)은 스크립트가 쓴다. 파일에서 지워라." % (path, line.strip()))
        if line.strip() == PROGRESS_HEAD:
            raise Reject("거부: %s — 진행 표(`%s`)는 스크립트가 쓴다(--progress). 파일에서 지워라." % (path, PROGRESS_HEAD))
    return Draft(path, m.group("repo"), m.group("unit"), "\n".join(lines[1:]).strip("\n"))


def split_comment(body: str) -> tuple[str, int, int | None, str | None, list[tuple[str, str]], str] | None:
    """코멘트 본문 → (단위, 판, 승인 판, 승인일, 진행, 나머지 본문). 시나리오 코멘트가 아니면 None."""
    lines = body.splitlines()
    if not lines:
        return None
    h = HEADING.match(lines[0])
    if not h:
        return None
    rest = lines[1:]

    def skip_blank() -> None:
        while rest and not rest[0].strip():
            rest.pop(0)

    skip_blank()
    version, av, ad = 1, None, None
    if rest and META.match(rest[0]):
        mm = META.match(rest[0])
        assert mm is not None
        version = int(mm.group("v"))
        av = int(mm.group("av")) if mm.group("av") else None
        ad = mm.group("ad")
        rest.pop(0)
    skip_blank()
    progress: list[tuple[str, str]] = []
    if rest and rest[0].strip() == PROGRESS_HEAD:
        rest.pop(0)
        if rest and rest[0].startswith("|---"):
            rest.pop(0)
        while rest and PROGRESS_ROW.match(rest[0]):
            pm = PROGRESS_ROW.match(rest[0])
            assert pm is not None
            progress.append((pm.group("stage"), pm.group("text").strip()))
            rest.pop(0)
    return h.group("unit"), version, av, ad, progress, "\n".join(rest).strip("\n")


def find_posted(n: str, repo: str) -> dict[str, Posted]:
    """이슈의 시나리오 코멘트 전부 — 단위 → Posted. 같은 단위가 둘이면 마지막 것."""
    out: dict[str, Posted] = {}
    for c in comments.fetch_all(n):
        body = str(c["body"])
        parsed = split_comment(body)
        if parsed is None:
            continue
        h = HEADING.match(body.splitlines()[0])
        assert h is not None
        if h.group("repo").lower() != repo.lower():
            continue
        unit, version, av, ad, progress, rest = parsed
        out[unit] = Posted(int(str(c["id"])), str(c["url"]), unit, version, av, ad, rest, progress)
    return out


def meta_line(version: int, av: int | None, ad: str | None) -> str:
    line = "> v%d" % version
    if av is not None and ad is not None:
        line += " · 승인 v%d — %s" % (av, ad)
    return line


def progress_block(progress: list[tuple[str, str]]) -> str:
    if not progress:
        return ""
    rows = ["| %s | %s |" % (stage, text) for stage, text in progress]
    return PROGRESS_HEAD + "\n|---|---|\n" + "\n".join(rows) + "\n\n"


def compose(p: Posted, repo: str) -> str:
    return "### TDD 시나리오 — %s — %s\n\n%s\n\n%s%s\n" % (
        repo, p.unit, meta_line(p.version, p.approved_version, p.approved_date),
        progress_block(p.progress), p.body)


def resolve(body: str, path: str, known: dict[str, Posted]) -> str:
    def sub(m: "re.Match[str]") -> str:
        unit = m.group("unit").strip()
        if unit not in known:
            raise Reject("거부: %s — `{url:%s}` 를 풀 수 없다. 그 단위의 코멘트가 아직 없다." % (path, unit),
                         "   단위 파일을 먼저(또는 같은 호출에 함께) 넘긴다 — 색인은 언제나 단위들 뒤에 간다.")
        return known[unit].url
    return PLACEHOLDER.sub(sub, body)


def post_create(n: str, body: str) -> tuple[int, str]:
    j = gh_json("api", "-X", "POST", "repos/%s/issues/%s/comments" % (OPS_REPO, n), "-f", "body=" + body)
    return int(j["id"]), j["html_url"]


def post_patch(comment_id: int, body: str) -> str:
    j = gh_json("api", "-X", "PATCH", "repos/%s/issues/comments/%d" % (OPS_REPO, comment_id), "-f", "body=" + body)
    return j["html_url"]


def check_size(where: str, body: str) -> None:
    if len(body) > COMMENT_LIMIT:
        raise Reject("거부: %s — %d자, 코멘트 한도(%d)를 넘는다." % (where, len(body), COMMENT_LIMIT),
                     "   단위가 너무 크다는 신호다 — 단위를 더 가른다(scenarios.md §1.6).")


def publish(n: str, repo: str, paths: list[str]) -> None:
    drafts = [read_draft(p, repo) for p in paths]
    seen: set[str] = set()
    for d in drafts:
        if d.unit in seen:
            raise Reject("거부: 머리가 겹친다 — `%s` 가 둘 이상이다. 단위 이름은 코멘트의 열쇠라 하나여야 한다." % d.unit)
        seen.add(d.unit)

    known = find_posted(n, repo)
    ordered = [d for d in drafts if not d.is_index] + [d for d in drafts if d.is_index]
    rows: list[tuple[str, str, str, str]] = []

    for d in ordered:
        body = resolve(d.body, d.path, known)
        prev = known.get(d.unit)
        if prev is None:
            new = Posted(0, "", d.unit, 1, None, None, body)
            full = compose(new, repo)
            check_size(d.path, full)
            new.comment_id, new.url = post_create(n, full)
            known[d.unit] = new
            rows.append((d.unit, "v1", "게시", new.url))
        elif prev.body == body:
            rows.append((d.unit, "v%d" % prev.version, "변경 없음", prev.url))
        else:
            prev.version += 1
            prev.body = body
            full = compose(prev, repo)
            check_size(d.path, full)
            prev.url = post_patch(prev.comment_id, full)
            rows.append((d.unit, "v%d" % prev.version, "갱신(PATCH)", prev.url))

    print("== 시나리오 코멘트 — %s" % repo)
    for unit, v, what, url in rows:
        print("   ▸ %s · %s · %s\n     %s" % (unit, v, what, url))
    print("승인이 오면: scenario-post.py %s --repo %s --approve \"<단위>\"" % (n, repo))


def need(n: str, repo: str, unit: str) -> Posted:
    known = find_posted(n, repo)
    prev = known.get(unit)
    if prev is None:
        raise Reject("거부: `%s` 의 시나리오 코멘트가 #%s 에 없다 — 있는 단위: %s"
                     % (unit, n, ", ".join(known) or "없음"))
    return prev


def approve(n: str, repo: str, unit: str) -> None:
    prev = need(n, repo, unit)
    prev.approved_version, prev.approved_date = prev.version, dt.date.today().isoformat()
    url = post_patch(prev.comment_id, compose(prev, repo))
    print("== 승인 표식 — %s · v%d · %s\n   %s" % (unit, prev.version, prev.approved_date, url))


def progress(n: str, repo: str, unit: str, stage: str, text: str) -> None:
    if stage not in STAGES:
        raise Reject("거부: 단계는 %s 중 하나다 — `%s` (refactor 는 green 행에 함께 적는다)" % (" · ".join(STAGES), stage))
    if not text.strip() or "\n" in text or "|" in text:
        raise Reject("거부: 진행은 표의 한 칸이다 — 한 줄, `|` 없이, 수와 예외만. 길면 별도 코멘트를 내고 여기엔 링크.")
    prev = need(n, repo, unit)
    if prev.approved_version is None:
        raise Reject("거부: `%s` 는 아직 승인되지 않았다 — 진행은 승인된 표 위에서만 쌓인다(scenarios.md §5)." % unit)
    prev.progress.append((stage, text.strip()))
    full = compose(prev, repo)
    check_size("%s 진행" % unit, full)
    url = post_patch(prev.comment_id, full)
    print("== 진행 — %s · %d번째 행 · %s\n   %s\n   %s" % (unit, len(prev.progress), stage, text.strip(), url))


def main() -> None:
    parser = argparse.ArgumentParser(add_help=True)
    parser.add_argument("ticket", help="티켓 번호")
    parser.add_argument("--repo", required=True, help="target 저장소 (owner/repo)")
    parser.add_argument("--approve", metavar="단위", help="그 단위의 현행 판에 승인 표식을 붙인다")
    parser.add_argument("--progress", nargs=3, metavar=("단위", "단계", "한줄"),
                        help="그 단위의 진행 표에 행 하나(red · green · verify)를 덧붙인다")
    parser.add_argument("files", nargs="*", help="시나리오 초안 파일(들)")
    args = parser.parse_args()
    n = args.ticket.lstrip("#")

    if args.approve or args.progress:
        if args.files or (args.approve and args.progress):
            raise Reject("거부: --approve · --progress 는 각각 따로, 파일 없이 쓴다 — 게시된 코멘트를 고치는 동작이다.")
        if args.approve:
            approve(n, args.repo, args.approve)
        else:
            unit, stage, text = args.progress
            progress(n, args.repo, unit, stage, text)
        return
    if not args.files:
        raise Reject("거부: 게시할 파일이 없다 — tmp/github-issues/<N>-scenarios-<repo>-<단위>.md")
    publish(n, args.repo, args.files)


if __name__ == "__main__":
    run_cli(main)
