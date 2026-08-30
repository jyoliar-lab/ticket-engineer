#!/usr/bin/env python3
"""promql — Prometheus 즉시 조회·구간 조회 (Grafana 데이터소스 프록시, GET 만).

사용:
  promql.py '<PromQL>'                                  즉시 조회 (/api/v1/query)
  promql.py '<PromQL>' --range 1h [--step 60s]           구간 조회 (/api/v1/query_range) — 시계열별 요약
  promql.py '<PromQL>' --range 1h --points               구간 조회 — 시각별 값 전부 (많다 — 파일로 떨어진다)
  promql.py --labels [<selector>]                        레이블 이름 목록 (/api/v1/labels)
  promql.py --label-values <name> [<selector>]           레이블 값 목록 (/api/v1/label/<name>/values)
  promql.py --series '<selector>' [--range 1h]           시계열 목록 (/api/v1/series)

옵션:
  --end <시각>      기준 시각 (now · -10m · unix초 · RFC3339). 기본 now
  --range <기간>    구간 길이 (5m · 1h · 2d). 있으면 query_range
  --step <기간>     구간 해상도. 기본 range/60 에 가까운 값
  --uid <uid>       데이터소스 uid. 기본 prometheus
  --max-lines <n>   stdout 줄 수 상한. 기본 40 — 넘치면 원본은 tmp/obs/ 파일로
  --json            요약 대신 원본을 파일로 떨어뜨리고 경로만 출력

출력은 요약이다 — 즉시 조회는 `값  {레이블}` 한 줄씩, 구간 조회는 시계열마다
`n=점수 min max last {레이블}` 한 줄. 원본이 필요하면 --json.
"""
from __future__ import annotations

import argparse
import os
import sys
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _obs  # noqa: E402

DEFAULT_UID = "prometheus"


def fmt_val(v: str) -> str:
    try:
        f = float(v)
    except ValueError:
        return v
    if f != f:  # NaN
        return "NaN"
    if f == int(f) and abs(f) < 1e15:
        return str(int(f))
    return "%.6g" % f


def instant_lines(data: dict[str, Any]) -> list[str]:
    rtype = data.get("resultType")
    result = data.get("result")
    if rtype in ("scalar", "string"):
        return ["%s" % fmt_val(str(result[1]))]
    lines: list[str] = []
    for item in result or []:
        labels = item.get("metric", {})
        if "value" in item:
            lines.append("%s  %s" % (fmt_val(item["value"][1]), _obs.labels_str(labels)))
        elif "values" in item:   # 즉시 조회에 range vector 를 준 경우
            vals = [fmt_val(v[1]) for v in item["values"]]
            lines.append("[%s]  %s" % (", ".join(vals[:10]) + (" …" if len(vals) > 10 else ""),
                                       _obs.labels_str(labels)))
    if not lines:
        lines.append("(결과 없음)")
    return lines


def range_lines(data: dict[str, Any], points: bool) -> list[str]:
    lines: list[str] = []
    for item in data.get("result") or []:
        labels = _obs.labels_str(item.get("metric", {}))
        vals = item.get("values") or []
        if points:
            lines.append(labels)
            for ts, v in vals:
                lines.append("  %s  %s" % (_obs.fmt_ts(float(ts)), fmt_val(v)))
            continue
        nums = []
        for _, v in vals:
            try:
                nums.append(float(v))
            except ValueError:
                pass
        if not nums:
            lines.append("n=0  %s" % labels)
            continue
        lines.append("n=%d  min=%s  max=%s  first=%s  last=%s  %s" % (
            len(nums), fmt_val(str(min(nums))), fmt_val(str(max(nums))),
            fmt_val(str(nums[0])), fmt_val(str(nums[-1])), labels))
    if not lines:
        lines.append("(결과 없음)")
    return lines


def auto_step(range_sec: float) -> str:
    step = max(15, int(range_sec / 60))
    return "%ds" % step


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("query", nargs="?", help="PromQL (또는 --labels/--label-values/--series 의 selector)")
    ap.add_argument("--end", default=None)
    ap.add_argument("--range", dest="range_", default=None)
    ap.add_argument("--step", default=None)
    ap.add_argument("--points", action="store_true", help="구간 조회에서 시각별 값을 전부 출력")
    ap.add_argument("--labels", action="store_true")
    ap.add_argument("--label-values", metavar="NAME", default=None)
    ap.add_argument("--series", metavar="SELECTOR", default=None)
    ap.add_argument("--uid", default=DEFAULT_UID)
    ap.add_argument("--max-lines", type=int, default=40)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    conn = _obs.conn_from_env()
    end = _obs.parse_time(a.end, _obs.now())
    start = end - _obs.parse_duration(a.range_) if a.range_ else None
    match = a.query

    if a.labels:
        params: dict[str, Any] = {"match[]": match, "start": start, "end": end}
        r = _obs.get(conn, a.uid, "api/v1/labels", params)
        _check(r)
        lines = sorted(r.body.get("data") or [])
        kind = "promql-labels"
    elif a.label_values:
        params = {"match[]": match, "start": start, "end": end}
        r = _obs.get(conn, a.uid, "api/v1/label/%s/values" % a.label_values, params)
        _check(r)
        lines = sorted(r.body.get("data") or [])
        kind = "promql-label-values"
    elif a.series:
        params = {"match[]": a.series, "start": start or end - 3600, "end": end}
        r = _obs.get(conn, a.uid, "api/v1/series", params)
        _check(r)
        lines = [_obs.labels_str(m) for m in r.body.get("data") or []]
        kind = "promql-series"
    elif not match:
        ap.error("PromQL 이 필요하다")
    elif start is not None:
        step = a.step or auto_step(end - start)
        params = {"query": match, "start": start, "end": end, "step": step}
        r = _obs.get(conn, a.uid, "api/v1/query_range", params)
        _check(r)
        lines = range_lines(r.body["data"], a.points)
        kind = "promql-range"
    else:
        r = _obs.get(conn, a.uid, "api/v1/query", {"query": match, "time": end})
        _check(r)
        lines = instant_lines(r.body["data"])
        kind = "promql"

    if not lines:
        lines = ["(결과 없음)"]
    if a.json:
        print("원본 전체: %s" % os.path.relpath(_obs.spill(kind, r.body), _obs.REPO_ROOT))
        return
    _obs.emit(lines, r.body, kind, a.max_lines)


def _check(r: _obs.Result) -> None:
    body = r.body
    if not isinstance(body, dict):
        raise _obs.ObsError("JSON 이 아닌 응답(HTTP %d): %s" % (r.status, str(body)[:300]))
    if body.get("status") == "error":
        raise _obs.ObsError("Prometheus 오류(%s): %s" % (body.get("errorType"), body.get("error")))
    for w in body.get("warnings") or []:
        print("warning: %s" % w, file=sys.stderr)


if __name__ == "__main__":
    _obs.main_guard(main)
