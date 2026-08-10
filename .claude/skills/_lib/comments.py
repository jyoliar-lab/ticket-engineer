"""티켓 코멘트 fetch·출력 — 두 관문(ticket-run·preflight)이 공유한다.

추가 요구·방향 수정은 본문이 아니라 코멘트로 오기도 한다. agent 가 별도로
조회했는가(성실성)에 기대지 않고, 작업 진입(ticket-run: 착수·재개)과 보고 진입
(preflight: 완료 보고)의 관문 스크립트가 코멘트를 직접 실어 나른다 —
이 출력이 곧 코멘트 피드다. 문구·형식이 여기 한 곳에 있어야 두 관문이 갈라지지 않는다.
"""
import json

from _common import OPS_REPO, block, run


def fetch_all(n):
    """티켓의 코멘트 전량 → [{login, date, body}] (시간순).

    REST --paginate 로 전 페이지를 가져온다 — 잘림 축 자체가 없다
    (--slurp: 페이지별 배열을 배열의 배열로 받아 평탄화)."""
    out = run(["gh", "api",
               "repos/%s/issues/%s/comments?per_page=100" % (OPS_REPO, n),
               "--paginate", "--slurp"]).stdout
    return [{"login": (c.get("user") or {}).get("login") or "?",
             "date": (c.get("created_at") or "?")[:10],
             "body": c.get("body") or ""}
            for page in json.loads(out or "[]") for c in page]


def show(comments):
    """코멘트 전문을 출력한다 — 착수·재개·보고 공통 문구."""
    if not comments:
        print("== 코멘트: 없음")
        return

    print("== 코멘트 %d건 — 본문 밖 추가 요구·방향 수정일 수 있다. "
          "경계(AC·Requirements)와 같은 무게로 읽어라:" % len(comments))

    for c in comments:
        print("   ▸ %s (%s)" % (c["login"], c["date"]))
        print(block(c["body"] or "(빈 코멘트)", prefix="   │ "))
