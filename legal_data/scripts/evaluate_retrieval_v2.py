"""Run the fixed retrieval regression suite and emit a machine-readable report."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from rag_config import SETTINGS
from retrieve_v2 import SafeRetriever


DEFAULT_CASES = SETTINGS.legal_data / "eval" / "retrieval_cases.jsonl"
DEFAULT_REPORT = SETTINGS.legal_data / "eval" / "retrieval_report.json"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--min-in-domain-hit-rate", type=float, default=0.75)
    parser.add_argument("--min-ood-rejection-rate", type=float, default=1.0)
    args = parser.parse_args()

    cases = [json.loads(line) for line in args.cases.open(encoding="utf-8") if line.strip()]
    retriever = SafeRetriever()
    rows = []
    for case in cases:
        result = retriever.search(case["query"], top_k=args.top_k)
        returned_docs = [hit["doc_number"] for hit in result["hits"]]
        expected_docs = set(case["expected_doc_numbers"])
        hit = bool(expected_docs.intersection(returned_docs)) if case["accepted"] else not result["accepted"]
        rows.append(
            {
                **case,
                "actual_accepted": result["accepted"],
                "reason": result["reason"],
                "top_score": result.get("top_score"),
                "returned_doc_numbers": returned_docs,
                "passed": result["accepted"] == case["accepted"] and hit,
            }
        )
        print(f"{case['id']}: passed={rows[-1]['passed']} score={result.get('top_score')}", flush=True)

    in_domain = [row for row in rows if row["accepted"]]
    out_domain = [row for row in rows if not row["accepted"]]
    in_rate = sum(row["passed"] for row in in_domain) / len(in_domain)
    out_rate = sum(row["passed"] for row in out_domain) / len(out_domain)
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "index_dir": str(retriever.index_dir),
        "case_count": len(rows),
        "in_domain_hit_rate": in_rate,
        "out_of_domain_rejection_rate": out_rate,
        "thresholds": {
            "min_in_domain_hit_rate": args.min_in_domain_hit_rate,
            "min_ood_rejection_rate": args.min_ood_rejection_rate,
        },
        "passed": in_rate >= args.min_in_domain_hit_rate and out_rate >= args.min_ood_rejection_rate,
        "cases": rows,
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in report.items() if key != "cases"}, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

