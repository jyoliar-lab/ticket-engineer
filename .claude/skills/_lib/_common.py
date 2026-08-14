"""skill 스크립트 공용 — 경로·거부 예외·명령 실행. 표준 라이브러리만 쓴다.
(ticket-start·ticket-report 가 함께 쓴다 — 그래서 _lib 에 산다.)

레이아웃 상수는 여기 한 곳에만 둔다 — 경로가 바뀌면 여기만 고친다.

프로세스 종료는 함수 깊숙한 곳에서 하지 않는다: 거부는 Reject 예외로 던지고,
exit 는 진입점(run_cli)에서만 일어난다 — 호출부가 제어 흐름을 예상할 수 있게.
"""
import json
import os
import re
import subprocess
import sys

OPS_REPO = os.environ.get("OPS_REPO", "jyoliar-lab/ops-workflow")

# PR 제목·본문의 close 키워드 — group(2) 가 겨눈 이슈다. 허용되는 것은 티켓 연결
# (`Closes <OPS_REPO>#<N>` — ticket-pr 관문이 덧붙인다. Development 연결의 유일한 API
# 경로이며, 티켓의 자동 close 는 ops-workflow 저장소 설정 해제가 막는다 — discussion
# 260727_1608 수동 불변식) 뿐이고, 그 밖의 이슈를 겨눈 키워드는 거부한다 — 설정 보호가
# 없는 저장소의 이슈는 머지 시 정말 닫힌다.
# ticket-pr(생성 관문)·preflight(보고 관문)가 함께 쓴다 — 문구의 원천은 여기 한 곳.
CLOSE_KW = re.compile(
    r"\b(clos(?:e|es|ed)|fix(?:es|ed)?|resolv(?:e|es|ed))\b\s*:?\s+(\S*#\d+)",
    re.IGNORECASE)


def close_kw_targets(text: str) -> "list[str]":
    """text 의 close 키워드가 겨눈 이슈들 (소문자) — 허용 판정은 호출자가 한다."""
    return [m.group(2).lower() for m in CLOSE_KW.finditer(text)]

ROOT = os.path.realpath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
TARGET_DIR = os.path.join(ROOT, "workspace", "target")   # 수정 권한의 경계 (worktree·bare)
REF_DIR = os.path.join(ROOT, "workspace", "ref")         # 읽기 전용 참조 (hook 가 쓰기 거부)


# exit 코드 = agent 의 다음 행동 (ticket-run docstring 의 규약과 동일)
EXIT_PROCEED, EXIT_REJECT, EXIT_APPROVAL, EXIT_HUMAN = 0, 1, 2, 3


class Reject(Exception):
    """거부·사람 개입 — 사유 줄들과 exit 코드를 담는다.

    code 만 보고도 원인의 종류를 안다 (run_cli 로 감싸지 않은 호출자도):
      EXIT_REJECT(1)   = 전제 거부 — 우회 금지
      EXIT_APPROVAL(2) = 승인 대기 — 처리 방안을 제안하고 승인 후 진행
      EXIT_HUMAN(3)    = 사람 개입 필요 — 처리를 시도하지 말고 보고만
    """

    def __init__(self, *lines, code=EXIT_REJECT):
        super().__init__("\n".join(lines))
        self.lines = lines
        self.code = code


def run_cli(main):
    """스크립트 진입점 래퍼 — 프로세스를 끝내는 곳은 여기 하나다."""
    try:
        main()
    except Reject as exc:
        for line in exc.lines:
            print(line, file=sys.stderr)

        sys.exit(exc.code)


def run(args, cwd=None, check=True):
    """명령 실행. check=True 면 실패 시 Reject 를 던진다 (실패를 조용히 삼키지 않는다)."""
    p = subprocess.run(args, cwd=cwd, capture_output=True, text=True)

    if check and p.returncode != 0:
        raise Reject("거부: 명령 실패 — %s" % " ".join(args[:5]),
                     (p.stderr or p.stdout or "").strip())

    return p


def gh_json(*args):
    """gh 를 부르고 JSON 으로 돌려받는다."""
    return json.loads(run(["gh", *args]).stdout)


def rel(path):
    """출력용 상대 경로 (ROOT 기준)."""
    return os.path.relpath(path, ROOT)


def block(text, prefix="   "):
    """여러 줄 출력을 들여쓴 블록으로."""
    return prefix + text.strip().replace("\n", "\n" + prefix)
