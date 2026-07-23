"""티켓 '저장소' 절(YAML 펜스 블록) 파서 — ticket-run(착수)·preflight(보고)가 함께 쓴다. 표준 라이브러리만.

★ 이 표기의 **원본(emitter)은 ops-workflow 쪽**이다:
  `.claude/skills/ticket/scripts/repo_context.py` (발행 create.py · 기입/갱신 set-repos.py).
  여기는 **쌍둥이 파서** — 표기가 바뀌면 함께 바뀐다. 그 정합은 steward 의 conformance 감사 대상이다.

블록은 도구만 쓴다(원본이 emit 하고 쌍둥이가 읽는다) — 그래서 파서는 엄격하다.
관대한 파서는 손편집을 조용히 받아들여 본문과 보드 필드를 가른다. 이탈은 ValueError 로 던지고,
호출자가 자기 방식(Reject·검사 실패)으로 감싼다 — 갱신은 손이 아니라 set-repos.py 로.

  - target-repos — 권위 있는 사실. 목록 XOR `null`(명시적 부재 — 신규 저장소 생성 등).
  - ref-repos    — 비완전한 힌트. `[]` 허용.
"""
import re

SECTION_HEADER = "### 저장소"

_KEYS = ("target-repos", "ref-repos")

_SEC_YAML_RE = re.compile(
    r"^### 저장소[ \t]*\n(?:[ \t]*\n)*```yaml\n(.*?)\n```[ \t]*\n?", re.M | re.S)


def parse_section(body):
    """본문 → (target 목록, 부재 선언 여부, ref 목록). 절이 없으면 None. 형식 이탈은 ValueError.

    ★ ops-workflow `.claude/skills/ticket/scripts/repo_context.py` 의 parse_section 과 쌍둥이.
    """
    if SECTION_HEADER not in body:
        return None
    m = _SEC_YAML_RE.search(body)
    if m is None:
        raise ValueError("'저장소' 절은 있는데 YAML 블록이 아니다 — 구식(산문) 또는 손상된 표기. "
                         "set-repos.py 로 다시 기입한다.")
    found, key = {}, None
    for raw in m.group(1).splitlines():
        line = raw.rstrip()
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if line.startswith("  - "):
            if key is None:
                raise ValueError("목록 항목이 키 밖에 있다: %r" % line)
            found[key].append(line[4:].split("#", 1)[0].strip())
            continue
        head, sep, rest = line.partition(":")
        if not sep or head not in _KEYS or head in found:
            raise ValueError("모르는·중복된 줄: %r" % line)
        val = rest.split("#", 1)[0].strip()
        if val == "":                                   # 블록 목록이 이어진다
            found[head], key = [], head
        elif val == "[]":
            found[head], key = [], None
        elif val == "null" and head == "target-repos":  # 명시적 부재 선언
            found[head], key = None, None
        else:
            raise ValueError("받을 수 없는 값: %r" % line)
    if set(found) != set(_KEYS):
        raise ValueError("target-repos·ref-repos 두 키가 다 있어야 한다 (있는 키: %s)" % sorted(found))
    targets = found["target-repos"]
    if targets == []:
        raise ValueError("target-repos 가 비었다 — 목록이거나 null(명시적 부재)이어야 한다. 침묵은 없다.")
    for r in (targets or []) + found["ref-repos"]:
        if "/" not in r:
            raise ValueError("저장소는 owner/name 꼴이다 (받은 값: %r)" % r)
    return (targets or [], targets is None, found["ref-repos"])
