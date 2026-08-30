#!/usr/bin/env python3
"""logql — Loki 로그 조회 (Grafana 데이터소스 프록시, GET 만).

사용:
  logql.py '<LogQL>' [--since 1h] [--limit 30]           로그 줄 (/loki/api/v1/query_range)
  logql.py '<metric LogQL>' --since 1h                    메트릭 질의(count_over_time 등) — 시계열 요약
  logql.py --labels                                       레이블 이름 (/loki/api/v1/labels)
  logql.py --label-values <name> [--since 1h]             레이블 값 (/loki/api/v1/label/<name>/values)
  logql.py --series '<selector>' [--since 1h]             스트림 목록 (/loki/api/v1/series)

옵션:
  --since <기간>     조회 구간 길이 (5m · 1h · 2d). 기본 1h
  --end <시각>       구간 끝 (now · -10m · unix초 · RFC3339). 기본 now
  --limit <n>        돌려받을 최대 줄 수. 기본 30 — 낮게 둔다. 더 필요하면 명시적으로 올린다
  --direction        backward(최신부터, 기본) · forward
  --width <n>        한 줄 표시 폭. 기본 200 — 넘치면 자른다
  --uid <uid>        데이터소스 uid. 기본 loki-careerhub
  --max-lines <n>    stdout 줄 수 상한. 기본 40 — 넘치면 원본은 tmp/obs/ 파일로
  --json             원본을 파일로 떨어뜨리고 경로만 출력

테넌트(X-Scope-OrgID)는 Grafana 데이터소스가 얹는다 — 여기서 다루지 않는다.
출력은 `시각  {스트림 레이블 차이}  줄` — 모든 스트림에 공통인 레이블은 머리에 한 번만 찍는다.
"""
from __future__ import annotations

import argparse
import os
import sys
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _obs  # noqa: E402

DEFAULT_UID = "loki-careerhub"
DEFAULT_LIMIT = 30


def common_labels(streams: list[dict[str, Any]]) -> dict[str, str]:
    sets = [s.get("stream", {}) for s in streams]
    if not sets:
        return {}
    common = dict(sets[0])
    for labels in sets[1:]:
        for k in list(common):
            if labels.get(k) != common[k]:
                del common[k]
    return common


def stream_lines(data: dict[str, Any], direction: str, width: int) -> list[str]:
    streams = data.get("result") or []
    common = common_labels(streams)
    entries: list[tuple[int, dict[str, str], str]] = []
    for s in streams:
        labels = {k: v for k, v in s.get("stream", {}).items() if k not in common}
        for ts, line in s.get("values") or []:
            entries.append((int(ts), labels, line))
    entries.sort(key=lambda e: e[0], reverse=(direction == "backward"))
    lines: list[str] = []
    if common:
        lines.append("공통 레이블 %s" % _obs.labels_str(common))
    for ts, labels, line in entries:
        tag = (" " + _obs.labels_str(labels)) if labels else ""
        lines.append("%s%s  %s" % (_obs.fmt_ts(ts / 1e9), tag, _obs.clip(line, width)))
    if not entries:
        lines.append("(결과 없음)")
    return lines


def matrix_lines(data: dict[str, Any]) -> list[str]:
    lines: list[str] = []
    for item in data.get("result") or []:
        nums = []
        for _, v in item.get("values") or []:
            try:
                nums.append(float(v))
            except ValueError:
                pass
        labels = _obs.labels_str(item.get("metric", {}))
        if nums:
            lines.append("n=%d  min=%g  max=%g  last=%g  %s" % (len(nums), min(nums), max(nums), nums[-1], labels))
        else:
            lines.append("n=0  %s" % labels)
    return lines or ["(결과 없음)"]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("query", nargs="?", help="LogQL")
    ap.add_argument("--since", default="1h")
    ap.add_argument("--end", default=None)
    ap.add_argument("--limit", type=int, default=DEFAULT_LIMIT)
    ap.add_argument("--direction", choices=("backward", "forward"), default="backward")
    ap.add_argument("--width", type=int, default=200)
    ap.add_argument("--labels", action="store_true")
    ap.add_argument("--label-values", metavar="NAME", default=None)
    ap.add_argument("--series", metavar="SELECTOR", default=None)
    ap.add_argument("--uid", default=DEFAULT_UID)
    ap.add_argument("--max-lines", type=int, default=40)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    conn = _obs.conn_from_env()
    end = _obs.parse_time(a.end, _obs.now())
    start = end - _obs.parse_duration(a.since)
    ns = {"start": int(start * 1e9), "end": int(end * 1e9)}

    if a.labels:
        r = _obs.get(conn, a.uid, "loki/api/v1/labels", ns)
        _check(r)
        lines = sorted(r.body.get("data") or [])
        kind = "logql-labels"
    elif a.label_values:
        r = _obs.get(conn, a.uid, "loki/api/v1/label/%s/values" % a.label_values, ns)
        _check(r)
        lines = sorted(r.body.get("data") or [])
        kind = "logql-label-values"
    elif a.series:
        r = _obs.get(conn, a.uid, "loki/api/v1/series", {**ns, "match[]": a.series})
        _check(r)
        lines = [_obs.labels_str(m) for m in r.body.get("data") or []]
        kind = "logql-series"
    elif not a.query:
        ap.error("LogQL 이 필요하다")
    else:
        params: dict[str, Any] = {**ns, "query": a.query, "limit": a.limit, "direction": a.direction}
        r = _obs.get(conn, a.uid, "loki/api/v1/query_range", params)
        _check(r)
        data = r.body.get("data") or {}
        if data.get("resultType") == "matrix":
            lines = matrix_lines(data)
        else:
            lines = stream_lines(data, a.direction, a.width)
        kind = "logql"

    if a.json:
        print("원본 전체: %s" % os.path.relpath(_obs.spill(kind, r.body), _obs.REPO_ROOT))
        return
    _obs.emit(lines or ["(결과 없음)"], r.body, kind, a.max_lines)


def _check(r: _obs.Result) -> None:
    body = r.body
    if not isinstance(body, dict):
        raise _obs.ObsError("JSON 이 아닌 응답(HTTP %d): %s" % (r.status, str(body)[:300]))
    if body.get("status") == "error":
        raise _obs.ObsError("Loki 오류(%s): %s" % (body.get("errorType"), body.get("error")))


if __name__ == "__main__":
    _obs.main_guard(main)
