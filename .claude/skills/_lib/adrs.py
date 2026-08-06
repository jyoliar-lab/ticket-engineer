"""티켓 '근거 ADR' 절(YAML 블록) 파서 + ADR 코퍼스 status 조회 — 착수 게이트가 쓴다. 표준 라이브러리만.

★ 절 표기의 **원본(emitter)은 ops-workflow 쪽**이다:
  `.claude/skills/ticket/scripts/adr_context.py` (발행 create.py · 기입/갱신 set-adr.py).
  여기는 **쌍둥이 파서** — 표기가 바뀌면 함께 바뀐다. 그 정합은 steward 의 conformance 감사 대상이다.

블록은 도구만 쓴다(원본이 emit 하고 쌍둥이가 읽는다) — 그래서 파서는 엄격하다(repos.py 와 같은 규약).
관대한 파서는 손편집을 조용히 받아들여 본문과 코퍼스를 가른다. 이탈은 ValueError 로 던지고,
호출자가 자기 방식(Reject)으로 감싼다 — 갱신은 손이 아니라 set-adr.py 로.
"""
import os
import re

SECTION_HEADER = "### 근거 ADR"

# YAML 블록만 — 링크 불릿은 사람의 자리라 기계가 읽지 않는다
_SEC_YAML_RE = re.compile(
    r"^### 근거 ADR[ \t]*\n(?:[ \t]*\n)*```yaml\n(.*?)\n```", re.M | re.S)


def parse_section(body):
    """본문 → [(adr_id, path, sha), ...]. 절이 없으면 None. 형식 이탈은 ValueError.

    ★ ops-workflow `.claude/skills/ticket/scripts/adr_context.py` 의 parse_section 과 쌍둥이.
    """
    if SECTION_HEADER not in body:
        return None
    m = _SEC_YAML_RE.search(body)
    if m is None:
        raise ValueError("'근거 ADR' 절은 있는데 YAML 블록이 아니다 — 손상된 표기. "
                         "set-adr.py 로 다시 기입한다.")
    lines = [ln for ln in m.group(1).splitlines() if ln.strip()]
    if not lines or lines[0].strip() != "adrs:":
        raise ValueError("YAML 블록은 'adrs:' 로 시작해야 한다 (첫 줄: %r)"
                         % (lines[0] if lines else ""))
    entries, cur = [], None
    for line in lines[1:]:
        if line.startswith("  - id: "):
            cur = {"id": line[len("  - id: "):].strip()}
            entries.append(cur)
        elif line.startswith("    ") and cur is not None:
            key, sep, val = line.strip().partition(": ")
            if not sep or key not in ("path", "sha") or key in cur:
                raise ValueError("모르는·중복된 줄: %r" % line)
            cur[key] = val.strip()
        else:
            raise ValueError("받을 수 없는 줄: %r" % line)
    if not entries or any(set(e) != {"id", "path", "sha"} for e in entries):
        raise ValueError("항목마다 id·path·sha 세 키가 다 있어야 한다")
    return [(e["id"], e["path"], e["sha"]) for e in entries]


def _frontmatter(path):
    """문서 파일 → frontmatter dict (최상위 스칼라만). 파일이 없거나 frontmatter 가 아니면 {}."""
    try:
        with open(path, encoding="utf-8") as f:
            text = f.read()
    except OSError:
        return {}
    if not text.startswith("---\n"):
        return {}
    end = text.find("\n---", 4)
    if end < 0:
        return {}
    fm = {}
    for line in text[4:end].splitlines():
        if line.startswith((" ", "\t")):
            continue
        key, sep, val = line.partition(":")
        if sep:
            fm[key.strip()] = val.strip()
    return fm


def adr_status(corpus_root, adr_id, path_hint=None):
    """ADR id → frontmatter status. 로컬 코퍼스 사본(ref 클론)에서 읽는다. 못 찾으면 None.

    티켓의 path 는 발행 시점 값이라 힌트일 뿐이다 — 경로는 동결이 아니라 이동할 수 있다.
    힌트가 빗나가면 docs/ 전체를 id 로 스캔한다.
    """
    if path_hint:
        fm = _frontmatter(os.path.join(corpus_root, path_hint))
        if fm.get("type") == "adr" and fm.get("id") == adr_id:
            return fm.get("status") or None
    docs = os.path.join(corpus_root, "docs")
    for dirpath, _dirs, files in os.walk(docs):
        for name in files:
            if not name.endswith(".md"):
                continue
            fm = _frontmatter(os.path.join(dirpath, name))
            if fm.get("type") == "adr" and fm.get("id") == adr_id:
                return fm.get("status") or None
    return None
