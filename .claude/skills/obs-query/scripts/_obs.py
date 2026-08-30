"""obs-query 공용 — Grafana 데이터소스 프록시 GET · 시간 인자 · 출력 절제(spill).

세 스크립트(promql·logql·traceql)가 함께 쓴다. 표준 라이브러리만 쓴다.

구조로 거는 것:
  - HTTP 메서드는 GET 뿐이다 — 이 모듈에 다른 메서드를 만드는 함수가 없다.
    (게이트웨이도 GET 만 통과시키고, Grafana 도 Prom·Loki 프록시에 POST/PUT/DELETE 를
    거부한다 — 스킬은 그 위에서 GET 만 쓴다.)
  - 토큰은 env(OBS_GRAFANA_TOKEN)에서만 읽는다 — 인자·파일로 받지 않는다.
  - 출력은 max_lines 로 자르고, 원본 전체는 tmp/obs/ 파일로 떨어뜨려 경로만 돌려준다 —
    주 컨텍스트에 원본을 쏟지 않는다.

env:
  OBS_GRAFANA_TOKEN  Grafana SA 토큰(Bearer) — 필수. settings.local.json 의 env 에 둔다.
  OBS_GRAFANA_URL    게이트웨이 base URL. 기본 https://obs.mg.jyo-liar.com
"""
from __future__ import annotations

import datetime as _dt
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

DEFAULT_URL = "https://obs.mg.jyo-liar.com"
PROXY_PREFIX = "/api/datasources/proxy/uid"

# 스크립트 위치(.claude/skills/obs-query/scripts) 기준 저장소 루트 — cwd 에 의존하지 않는다.
REPO_ROOT = Path(__file__).resolve().parents[4]
SPILL_DIR = REPO_ROOT / "tmp" / "obs"

TIMEOUT_SEC = 30
MAX_SPILL_FILES = 50   # tmp/obs 에 남기는 최대 파일 수 — 오래된 것부터 지운다


class ObsError(Exception):
    """사용자에게 보일 실패 — 메시지만 찍고 exit 1."""


@dataclass(frozen=True)
class Conn:
    base_url: str
    token: str


@dataclass(frozen=True)
class Result:
    url: str
    status: int
    body: Any


def conn_from_env() -> Conn:
    token = os.environ.get("OBS_GRAFANA_TOKEN", "").strip()
    if not token:
        raise ObsError(
            "OBS_GRAFANA_TOKEN 이 비어 있다 — Grafana SA 토큰은 사람이 Secret 에서 꺼내 "
            ".claude/settings.local.json 의 env 에 둔다(gitignored). 커밋하지 않는다.")
    base = os.environ.get("OBS_GRAFANA_URL", DEFAULT_URL).rstrip("/")
    return Conn(base_url=base, token=token)


def get(conn: Conn, uid: str, path: str, params: dict[str, Any] | None = None) -> Result:
    """GET <base>/api/datasources/proxy/uid/<uid>/<path>?params — 유일한 HTTP 진입점."""
    query = {k: v for k, v in (params or {}).items() if v is not None and v != ""}
    url = "%s%s/%s/%s" % (conn.base_url, PROXY_PREFIX, uid, path.lstrip("/"))
    if query:
        url += "?" + urllib.parse.urlencode(query, doseq=True)
    req = urllib.request.Request(url, headers={
        "Authorization": "Bearer " + conn.token,
        "Accept": "application/json",
    })  # method 를 주지 않는다 — urllib 기본 = GET
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_SEC) as resp:
            raw = resp.read()
            status = resp.status
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:400]
        raise ObsError("HTTP %d %s — %s\n%s" % (e.code, e.reason, url, detail))
    except urllib.error.URLError as e:
        raise ObsError("연결 실패 — %s\n%s" % (url, e.reason))
    try:
        body: Any = json.loads(raw) if raw else {}
    except ValueError:
        body = raw.decode("utf-8", "replace")
    return Result(url=url, status=status, body=body)



# ── 시간 인자 ────────────────────────────────────────────────────────────────

_DUR = re.compile(r"^(\d+(?:\.\d+)?)([smhdw])$")
_UNIT = {"s": 1, "m": 60, "h": 3600, "d": 86400, "w": 604800}


def parse_duration(text: str) -> float:
    """'30s' '5m' '1h' '2d' → 초. Prometheus/Loki 표기와 같다."""
    m = _DUR.match(text.strip())
    if not m:
        raise ObsError("기간 표기가 아니다: %r (예: 30s, 5m, 1h, 2d)" % text)
    return float(m.group(1)) * _UNIT[m.group(2)]


def parse_time(text: str | None, default: float) -> float:
    """'now' · '-1h'(now 기준 상대) · unix 초 · RFC3339 → unix 초."""
    if text is None or text.strip() in ("", "now"):
        return default
    t = text.strip()
    if t.startswith("-") and _DUR.match(t[1:]):
        return default - parse_duration(t[1:])
    if re.match(r"^\d+(\.\d+)?$", t):
        return float(t)
    try:
        dt = _dt.datetime.fromisoformat(t.replace("Z", "+00:00"))
    except ValueError:
        raise ObsError("시각 표기가 아니다: %r (now · -1h · unix초 · RFC3339)" % t)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=_dt.timezone.utc)
    return dt.timestamp()


def now() -> float:
    return _dt.datetime.now(_dt.timezone.utc).timestamp()


def fmt_ts(unix_sec: float) -> str:
    return _dt.datetime.fromtimestamp(unix_sec, _dt.timezone.utc).strftime("%m-%d %H:%M:%S")


# ── 출력 절제 ────────────────────────────────────────────────────────────────

def spill(kind: str, payload: Any) -> Path:
    """원본 전체를 tmp/obs/<UTC시각>-<kind>.json 으로 떨어뜨리고 경로를 돌려준다."""
    SPILL_DIR.mkdir(parents=True, exist_ok=True)
    stamp = _dt.datetime.now(_dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = SPILL_DIR / ("%s-%s.json" % (stamp, kind))
    n = 1
    while path.exists():
        n += 1
        path = SPILL_DIR / ("%s-%s-%d.json" % (stamp, kind, n))
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    _prune()
    return path


def _prune() -> None:
    files = sorted(SPILL_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime)
    for old in files[:-MAX_SPILL_FILES]:
        try:
            old.unlink()
        except OSError:
            pass


def emit(lines: list[str], full: Any, kind: str, max_lines: int, force_spill: bool = False) -> None:
    """앞 max_lines 줄만 stdout 에. 잘렸거나 force_spill 이면 원본을 파일로 떨어뜨리고 경로를 알린다."""
    shown = lines[:max_lines]
    for line in shown:
        print(line)
    cut = len(lines) - len(shown)
    if cut > 0 or force_spill:
        path = spill(kind, full)
        rel = os.path.relpath(path, REPO_ROOT)
        if cut > 0:
            print("… %d줄 더 있음 (총 %d줄). 원본 전체: %s" % (cut, len(lines), rel))
        else:
            print("원본 전체: %s" % rel)


def clip(text: str, width: int) -> str:
    text = text.replace("\n", "⏎")
    return text if len(text) <= width else text[: width - 1] + "…"


def labels_str(labels: dict[str, str], drop: tuple[str, ...] = ()) -> str:
    items = ["%s=%s" % (k, v) for k, v in sorted(labels.items()) if k not in drop]
    return "{" + ", ".join(items) + "}"


def main_guard(fn: Any) -> None:
    """진입점 — ObsError 는 메시지만, 그 외는 그대로. exit 는 여기서만."""
    try:
        fn()
    except ObsError as e:
        print(str(e), file=sys.stderr)
        sys.exit(1)
