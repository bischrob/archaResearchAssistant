from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

DEFAULT_BASE_URL = "http://127.0.0.1:8001"
DEFAULT_DATASET = Path(__file__).resolve().parents[1] / "eval" / "archaeology_query_golden.json"


def _request_json(url: str, *, method: str = "GET", payload: dict[str, Any] | None = None, timeout: int = 180) -> dict[str, Any]:
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=body, method=method)
    req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _run_query(base_url: str, spec: dict[str, Any], poll_interval: float) -> dict[str, Any]:
    start_payload = _request_json(
        f"{base_url}/api/query",
        method="POST",
        payload={
            "query": spec["query"],
            "limit": int(spec.get("limit", 5)),
            "limit_scope": spec.get("limit_scope", "papers"),
            "chunks_per_paper": int(spec.get("chunks_per_paper", 3)),
        },
    )
    request_id = start_payload.get("request_id")
    while True:
        status_payload = _request_json(f"{base_url}/api/query/status")
        if status_payload.get("request_id") == request_id and status_payload.get("status") != "running":
            return status_payload
        time.sleep(poll_interval)


def _evaluate_case(case: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    rows = (((payload or {}).get("result") or {}).get("results") or [])
    citekeys = [str(row.get("article_citekey") or "") for row in rows]
    top_citekeys = citekeys[: int(case.get("limit", len(citekeys)))]
    expected = set(case.get("expected_any_of") or [])
    forbidden = set(case.get("forbid_top_n") or [])
    expected_hit = bool(expected.intersection(top_citekeys)) if expected else True
    forbidden_hit = sorted(forbidden.intersection(top_citekeys))
    ok = payload.get("status") == "completed" and expected_hit and not forbidden_hit
    return {
        "id": case.get("id"),
        "query": case.get("query"),
        "ok": ok,
        "status": payload.get("status"),
        "request_id": payload.get("request_id"),
        "expected_any_of": sorted(expected),
        "forbid_top_n": sorted(forbidden),
        "top_results": [
            {
                "rank": idx + 1,
                "citekey": row.get("article_citekey"),
                "title": row.get("article_title"),
                "paper_score": row.get("paper_score", row.get("rerank_score")),
                "anchor_hits": ((row.get("query_features") or {}).get("anchor_hits")),
                "domain_hits": ((row.get("query_features") or {}).get("domain_hits")),
            }
            for idx, row in enumerate(rows[: int(case.get("limit", 5))])
        ],
        "expected_hit": expected_hit,
        "forbidden_hits": forbidden_hit,
        "notes": case.get("notes"),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run live golden-query checks against /api/query.")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--dataset", default=str(DEFAULT_DATASET))
    parser.add_argument("--poll-interval", type=float, default=1.0)
    parser.add_argument("--json", action="store_true", help="Print full JSON report.")
    args = parser.parse_args()

    dataset = Path(args.dataset)
    cases = json.loads(dataset.read_text(encoding="utf-8"))
    report = {
        "base_url": args.base_url,
        "dataset": str(dataset),
        "cases": [],
    }
    failures = 0
    for case in cases:
        try:
            payload = _run_query(args.base_url, case, args.poll_interval)
            result = _evaluate_case(case, payload)
        except urllib.error.HTTPError as exc:
            result = {
                "id": case.get("id"),
                "query": case.get("query"),
                "ok": False,
                "error": f"HTTP {exc.code}: {exc.reason}",
            }
        except Exception as exc:  # pragma: no cover - live harness
            result = {
                "id": case.get("id"),
                "query": case.get("query"),
                "ok": False,
                "error": str(exc),
            }
        failures += 0 if result.get("ok") else 1
        report["cases"].append(result)

    report["ok"] = failures == 0
    report["failure_count"] = failures

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        for case in report["cases"]:
            status = "PASS" if case.get("ok") else "FAIL"
            print(f"[{status}] {case.get('id')}: {case.get('query')}")
            if case.get("top_results"):
                for row in case["top_results"]:
                    print(
                        f"  {row['rank']}. {row.get('citekey')} | score={row.get('paper_score')} | "
                        f"anchors={row.get('anchor_hits')} | domains={row.get('domain_hits')} | {row.get('title')}"
                    )
            if case.get("forbidden_hits"):
                print(f"  forbidden hits: {', '.join(case['forbidden_hits'])}")
            if case.get("error"):
                print(f"  error: {case['error']}")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
