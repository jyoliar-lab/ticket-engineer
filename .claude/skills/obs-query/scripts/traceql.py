#!/usr/bin/env python3
"""traceql — Tempo 트레이스 검색·조회 (Grafana 데이터소스 프록시, GET 만).

사용:
  traceql.py search [--q '<TraceQL>'] [--since 1h] [--limit 20]     최근 트레이스 목록 (/api/search)
  traceql.py trace <traceID>                                        트레이스 하나 — 요약 (/api/traces/<id>)
  traceql.py tags [--scope span|resource|intrinsic]                 검색 가능한 태그 (/api/v2/search/tags)
  traceql.py tag-values <tag> [--q '<TraceQL>']                     태그 값 (/api/v2/search/tag/<tag>/values)

옵션:
  --q <TraceQL>      검색식. 예: '{ resource.service.name = "posting-service" && status = error }'
                     비우면 구간 안의 모든 트레이스(최근순)
  --since <기간>     조회 구간 길이. 기본 1h        --end <시각>  구간 끝. 기본 now
  --limit <n>        search 결과 상한. 기본 20
  --min-duration     예: 500ms · 2s (search)
  --top <n>          trace 요약에서 보이는 느린 span 수. 기본 15
  --uid <uid>        데이터소스 uid. 기본 tempo-careerhub
  --max-lines <n>    stdout 줄 수 상한. 기본 40 — 넘치면 원본은 tmp/obs/ 파일로
  --json             원본을 파일로 떨어뜨리고 경로만 출력

Tempo 프록시는 Grafana 쪽 메서드 검증이 없다 — 이 스크립트가 GET 만 쓰는 것이 그 자리의 보장이다
(게이트웨이가 한 겹 더 막는다).
trace 는 원본이 항상 크므로 요약(서비스·span 수·오류·느린 span)만 찍고 원본은 늘 파일로 떨어진다.
"""
from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass, field
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _obs  # noqa: E402

DEFAULT_UID = "tempo-careerhub"


# ── search ──────────────────────────────────────────────────────────────────

def search_lines(body: dict[str, Any]) -> list[str]:
    traces = body.get("traces") or []
    lines: list[str] = []
    for t in traces:
        start_ns = int(t.get("startTimeUnixNano") or 0)
        lines.append("%s  %6sms  %s  %s / %s" % (
            t.get("traceID", "?"),
            t.get("durationMs", "?"),
            _obs.fmt_ts(start_ns / 1e9) if start_ns else "?",
            t.get("rootServiceName", "?"),
            t.get("rootTraceName", "?")))
    return lines or ["(결과 없음)"]


# ── trace ───────────────────────────────────────────────────────────────────

@dataclass
class Span:
    service: str
    name: str
    span_id: str
    parent_id: str
    start_ns: int
    end_ns: int
    status_code: str      # STATUS_CODE_ERROR / 2 / ""
    attrs: dict[str, str] = field(default_factory=dict)

    @property
    def duration_ms(self) -> float:
        return (self.end_ns - self.start_ns) / 1e6

    @property
    def is_error(self) -> bool:
        return self.status_code in ("STATUS_CODE_ERROR", "2")


def _attr_value(v: dict[str, Any]) -> str:
    for k in ("stringValue", "intValue", "doubleValue", "boolValue"):
        if k in v:
            return str(v[k])
    return str(v)


def _attrs(items: list[dict[str, Any]] | None) -> dict[str, str]:
    return {a.get("key", "?"): _attr_value(a.get("value") or {}) for a in items or []}


def parse_spans(body: dict[str, Any]) -> list[Span]:
    """OTLP JSON — Tempo 는 `batches`(v1) 또는 `resourceSpans`(v2) 로 준다."""
    batches = body.get("batches") or body.get("resourceSpans") or (body.get("trace") or {}).get("resourceSpans") or []
    spans: list[Span] = []
    for b in batches:
        res_attrs = _attrs((b.get("resource") or {}).get("attributes"))
        service = res_attrs.get("service.name", "?")
        for ss in b.get("scopeSpans") or b.get("instrumentationLibrarySpans") or []:
            for s in ss.get("spans") or []:
                status = s.get("status") or {}
                spans.append(Span(
                    service=service,
                    name=s.get("name", "?"),
                    span_id=s.get("spanId", ""),
                    parent_id=s.get("parentSpanId", "") or "",
                    start_ns=int(s.get("startTimeUnixNano") or 0),
                    end_ns=int(s.get("endTimeUnixNano") or 0),
                    status_code=str(status.get("code", "")),
                    attrs=_attrs(s.get("attributes")),
                ))
    return spans


def trace_lines(trace_id: str, spans: list[Span], top: int) -> list[str]:
    if not spans:
        return ["트레이스 %s — span 없음" % trace_id]
    start = min(s.start_ns for s in spans)
    end = max(s.end_ns for s in spans)
    roots = [s for s in spans if not s.parent_id]
    errors = [s for s in spans if s.is_error]
    services: dict[str, int] = {}
    for s in spans:
        services[s.service] = services.get(s.service, 0) + 1
    lines = [
        "트레이스 %s  총 %.1fms  span %d개  시작 %s" % (trace_id, (end - start) / 1e6, len(spans), _obs.fmt_ts(start / 1e9)),
        "루트: " + ("; ".join("%s / %s" % (r.service, r.name) for r in roots) or "(없음)"),
        "서비스: " + ", ".join("%s(%d)" % kv for kv in sorted(services.items(), key=lambda kv: -kv[1])),
        "오류 span: %d" % len(errors),
    ]
    for s in errors[:10]:
        msg = s.attrs.get("exception.message") or s.attrs.get("error.message") or s.attrs.get("http.status_code") or ""
        lines.append("  ✗ %s / %s  %.1fms  %s" % (s.service, s.name, s.duration_ms, _obs.clip(msg, 120)))
    lines.append("느린 span top %d:" % top)
    for s in sorted(spans, key=lambda s: -s.duration_ms)[:top]:
        offset = (s.start_ns - start) / 1e6
        lines.append("  %8.1fms  +%7.1fms  %s / %s" % (s.duration_ms, offset, s.service, _obs.clip(s.name, 80)))
    return lines


# ── main ────────────────────────────────────────────────────────────────────

def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=("search", "trace", "tags", "tag-values"))
    ap.add_argument("arg", nargs="?", help="trace: traceID · tag-values: 태그 이름")
    ap.add_argument("--q", default=None)
    ap.add_argument("--since", default="1h")
    ap.add_argument("--end", default=None)
    ap.add_argument("--limit", type=int, default=20)
    ap.add_argument("--min-duration", default=None)
    ap.add_argument("--scope", choices=("span", "resource", "intrinsic"), default=None)
    ap.add_argument("--top", type=int, default=15)
    ap.add_argument("--uid", default=DEFAULT_UID)
    ap.add_argument("--max-lines", type=int, default=40)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    conn = _obs.conn_from_env()
    end = _obs.parse_time(a.end, _obs.now())
    start = end - _obs.parse_duration(a.since)
    window: dict[str, Any] = {"start": int(start), "end": int(end)}

    if a.cmd == "search":
        params: dict[str, Any] = {**window, "limit": a.limit, "q": a.q, "minDuration": a.min_duration}
        r = _obs.get(conn, a.uid, "api/search", params)
        _check(r)
        lines = search_lines(r.body)
        kind = "traceql-search"
    elif a.cmd == "trace":
        if not a.arg:
            ap.error("traceID 가 필요하다")
        r = _obs.get(conn, a.uid, "api/traces/%s" % a.arg)
        _check(r)
        lines = trace_lines(a.arg, parse_spans(r.body), a.top)
        kind = "traceql-trace"
    elif a.cmd == "tags":
        r = _obs.get(conn, a.uid, "api/v2/search/tags", {**window, "scope": a.scope})
        _check(r)
        lines = []
        for sc in r.body.get("scopes") or []:
            lines.append("[%s] %s" % (sc.get("name"), ", ".join(sorted(sc.get("tags") or []))))
        kind = "traceql-tags"
    else:
        if not a.arg:
            ap.error("태그 이름이 필요하다")
        r = _obs.get(conn, a.uid, "api/v2/search/tag/%s/values" % a.arg, {**window, "q": a.q})
        _check(r)
        lines = sorted(str(v.get("value")) for v in r.body.get("tagValues") or [])
        kind = "traceql-tag-values"

    if a.json:
        print("원본 전체: %s" % os.path.relpath(_obs.spill(kind, r.body), _obs.REPO_ROOT))
        return
    _obs.emit(lines or ["(결과 없음)"], r.body, kind, a.max_lines, force_spill=(a.cmd == "trace"))


def _check(r: _obs.Result) -> None:
    if not isinstance(r.body, dict):
        raise _obs.ObsError("JSON 이 아닌 응답(HTTP %d): %s" % (r.status, str(r.body)[:300]))


if __name__ == "__main__":
    _obs.main_guard(main)
