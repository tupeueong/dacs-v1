"""Run the retrieval regression suite and emit a machine-readable report."""

from __future__ import annotations

import argparse
import json
import math
import os
import statistics
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

from rag_config import SETTINGS
from retrieve_v2 import SafeRetriever


DEFAULT_CASES = SETTINGS.legal_data / "eval" / "retrieval_cases.jsonl"
DEFAULT_REPORT = SETTINGS.legal_data / "eval" / "retrieval_report.json"
REQUIRED_FIELDS = {
    "id",
    "query",
    "retrievable",
    "answerable",
    "out_of_domain",
    "ambiguous",
    "adversarial",
    "expected_doc_numbers",
    "expected_article_numbers",
    "forbidden_doc_numbers",
}
LIST_FIELDS = (
    "expected_doc_numbers",
    "expected_article_numbers",
    "forbidden_doc_numbers",
)
OOD_CATEGORY = "near_out_of_domain"
CLASSIFICATION_FIELDS = (
    "retrievable",
    "answerable",
    "out_of_domain",
    "ambiguous",
    "adversarial",
)


class RemoteRetriever:
    """Small adapter that makes the HTTP service look like SafeRetriever."""

    def __init__(self, api_url: str, api_key: str, timeout_seconds: float) -> None:
        self.api_url = api_url.rstrip("/")
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds
        self.session = requests.Session()
        health = self.session.get(
            f"{self.api_url}/health",
            timeout=self.timeout_seconds,
        )
        health.raise_for_status()
        payload = health.json()
        if payload.get("status") != "ok":
            raise RuntimeError(f"Remote retrieval service is unhealthy: {payload!r}")
        self.index_dir = payload.get("index_dir", self.api_url)

    def search(
        self,
        query: str,
        *,
        top_k: int = 5,
        filters: dict | None = None,
        current_only: bool = True,
    ) -> dict:
        if not current_only:
            raise ValueError("Remote evaluator only supports current_only=True")
        response = self.session.post(
            f"{self.api_url}/retrieve",
            headers={"X-API-Key": self.api_key},
            json={"query": query, "top_k": top_k, "filters": filters},
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict) or not isinstance(payload.get("hits"), list):
            raise RuntimeError("Remote retrieval response has an invalid schema")
        return payload


def _validate_string_list(case_id: str, field: str, value: Any) -> list[str]:
    if not isinstance(value, list):
        raise ValueError(f"{case_id}: {field} must be a list")
    if not all(isinstance(item, str) and item.strip() for item in value):
        raise ValueError(f"{case_id}: {field} must contain non-empty strings")
    if len(value) != len(set(value)):
        raise ValueError(f"{case_id}: {field} contains duplicates")
    return value


def validate_case(raw: Any, line_number: int) -> dict:
    if not isinstance(raw, dict):
        raise ValueError(f"line {line_number}: case must be an object")
    missing = sorted(REQUIRED_FIELDS - set(raw))
    if missing:
        raise ValueError(f"line {line_number}: missing fields: {', '.join(missing)}")

    case_id = raw["id"]
    if not isinstance(case_id, str) or not case_id.strip():
        raise ValueError(f"line {line_number}: id must be a non-empty string")
    if not isinstance(raw["query"], str) or not raw["query"].strip():
        raise ValueError(f"{case_id}: query must be a non-empty string")
    for field in CLASSIFICATION_FIELDS:
        if type(raw[field]) is not bool:
            raise ValueError(f"{case_id}: {field} must be a boolean")
    for field in LIST_FIELDS:
        _validate_string_list(case_id, field, raw[field])

    expected_docs = set(raw["expected_doc_numbers"])
    forbidden_docs = set(raw["forbidden_doc_numbers"])
    if expected_docs & forbidden_docs:
        raise ValueError(f"{case_id}: expected and forbidden documents overlap")
    if raw["answerable"] and not raw["retrievable"]:
        raise ValueError(f"{case_id}: answerable=true requires retrievable=true")
    if raw["out_of_domain"] and raw["retrievable"]:
        raise ValueError(f"{case_id}: out_of_domain=true requires retrievable=false")
    if raw["ambiguous"] and raw["retrievable"]:
        raise ValueError(f"{case_id}: ambiguous=true requires retrievable=false")
    if raw["out_of_domain"] and raw["ambiguous"]:
        raise ValueError(f"{case_id}: query cannot be both out_of_domain and ambiguous")
    if raw["answerable"] and not expected_docs:
        raise ValueError(f"{case_id}: answerable case needs expected_doc_numbers")
    if not raw["retrievable"] and (
        raw["expected_doc_numbers"] or raw["expected_article_numbers"]
    ):
        raise ValueError(f"{case_id}: non-retrievable case cannot contain expected sources")
    if "category" in raw and (
        not isinstance(raw["category"], str) or not raw["category"].strip()
    ):
        raise ValueError(f"{case_id}: category must be a non-empty string")
    return raw


def load_cases(path: Path) -> list[dict]:
    cases = []
    seen_ids = set()
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            try:
                raw = json.loads(line)
            except json.JSONDecodeError as error:
                raise ValueError(f"line {line_number}: invalid JSON: {error.msg}") from error
            case = validate_case(raw, line_number)
            if case["id"] in seen_ids:
                raise ValueError(f"line {line_number}: duplicate id {case['id']!r}")
            seen_ids.add(case["id"])
            cases.append(case)
    if not cases:
        raise ValueError("evaluation suite is empty")
    return cases


def _mean(values: list[float]) -> float:
    return statistics.fmean(values) if values else 0.0


def _nearest_rank_percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    rank = max(1, math.ceil(percentile * len(ordered)))
    return ordered[rank - 1]


def _recall(expected: set[str], returned: list[str]) -> float | None:
    if not expected:
        return None
    return len(expected.intersection(returned)) / len(expected)


def _first_doc_rank(expected_docs: set[str], hits: list[dict]) -> int | None:
    for rank, hit in enumerate(hits, 1):
        if hit.get("doc_number") in expected_docs:
            return rank
    return None


def _category_metrics(rows: list[dict]) -> dict[str, dict]:
    groups: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        groups[row.get("category", "uncategorized")].append(row)
    return {
        category: {
            "case_count": len(group),
            "retrievable_accuracy": _mean(
                [float(row["retrieval_correct"]) for row in group]
            ),
            "case_pass_rate": _mean([float(row["passed"]) for row in group]),
            "median_latency_ms": statistics.median(
                [row["latency_ms"] for row in group]
            ),
        }
        for category, group in sorted(groups.items())
    }


def evaluate_case(retriever: SafeRetriever, case: dict, top_k: int) -> dict:
    started = time.perf_counter()
    result = retriever.search(case["query"], top_k=top_k)
    latency_ms = (time.perf_counter() - started) * 1000.0

    hits = result["hits"]
    returned_docs = [str(hit.get("doc_number", "")) for hit in hits]
    returned_articles = [str(hit.get("article_number", "")) for hit in hits]
    expected_docs = set(case["expected_doc_numbers"])
    expected_articles = set(case["expected_article_numbers"])
    forbidden_docs = set(case["forbidden_doc_numbers"])

    doc_recall = _recall(expected_docs, returned_docs)
    relevant_articles = [
        str(hit.get("article_number", ""))
        for hit in hits
        if hit.get("doc_number") in expected_docs
    ]
    article_recall = _recall(expected_articles, relevant_articles)
    first_rank = _first_doc_rank(expected_docs, hits)
    forbidden_returned = sorted(forbidden_docs.intersection(returned_docs))
    actual_classification = {
        field: bool(result.get(field, result["accepted"] if field == "retrievable" else False))
        for field in CLASSIFICATION_FIELDS
    }
    classification_correct = {
        field: actual_classification[field] == case[field]
        for field in CLASSIFICATION_FIELDS
    }
    retrieval_correct = result["accepted"] == case["retrievable"]

    if case["answerable"]:
        evidence_correct = doc_recall == 1.0 and (
            article_recall is None or article_recall == 1.0
        )
        passed = (
            retrieval_correct
            and all(classification_correct.values())
            and evidence_correct
            and not forbidden_returned
        )
    else:
        passed = (
            retrieval_correct
            and all(classification_correct.values())
            and not forbidden_returned
        )

    return {
        **case,
        "actual_accepted": result["accepted"],
        "actual_classification": actual_classification,
        "reason": result["reason"],
        "top_score": result.get("top_score"),
        "latency_ms": round(latency_ms, 3),
        "returned_doc_numbers": returned_docs,
        "returned_article_numbers": returned_articles,
        "doc_recall_at_k": doc_recall,
        "article_recall_at_k": article_recall,
        "first_relevant_doc_rank": first_rank,
        "reciprocal_rank": 1.0 / first_rank if first_rank else 0.0,
        "forbidden_doc_numbers_returned": forbidden_returned,
        "classification_correct": classification_correct,
        "retrieval_correct": retrieval_correct,
        "passed": passed,
    }


def build_report(
    rows: list[dict],
    retriever: SafeRetriever,
    args: argparse.Namespace,
) -> dict:
    retrievable_rows = [row for row in rows if row["retrievable"]]
    non_retrievable_rows = [row for row in rows if not row["retrievable"]]
    answerable_rows = [row for row in rows if row["answerable"]]
    ood_rows = [row for row in rows if row.get("category") == OOD_CATEGORY]
    article_rows = [
        row for row in answerable_rows if row["expected_article_numbers"]
    ]
    forbidden_rows = [row for row in rows if row["forbidden_doc_numbers"]]
    latencies = [row["latency_ms"] for row in rows]

    metrics = {
        **{
            f"{field}_accuracy": _mean(
                [float(row["classification_correct"][field]) for row in rows]
            )
            for field in CLASSIFICATION_FIELDS
            if field != "retrievable"
        },
        "retrievable_accuracy": _mean(
            [float(row["retrieval_correct"]) for row in rows]
        ),
        "retrievable_gate_accuracy": _mean(
            [float(row["classification_correct"]["retrievable"]) for row in rows]
        ),
        "document_recall_at_5": _mean(
            [float(row["doc_recall_at_k"]) for row in answerable_rows]
        ),
        "article_recall_at_5": _mean(
            [float(row["article_recall_at_k"]) for row in article_rows]
        ),
        "mean_reciprocal_rank": _mean(
            [float(row["reciprocal_rank"]) for row in answerable_rows]
        ),
        "non_retrievable_rejection_rate": _mean(
            [float(not row["actual_accepted"]) for row in non_retrievable_rows]
        ),
        "out_of_domain_rejection_rate": _mean(
            [float(row["actual_classification"]["out_of_domain"]) for row in ood_rows]
        ),
        "forbidden_document_retrieval_rate": _mean(
            [float(bool(row["forbidden_doc_numbers_returned"])) for row in forbidden_rows]
        ),
        "forbidden_document_hit_count": sum(
            len(row["forbidden_doc_numbers_returned"]) for row in rows
        ),
        "latency_ms": {
            "median": round(statistics.median(latencies), 3),
            "p95": round(_nearest_rank_percentile(latencies, 0.95), 3),
            "max": round(max(latencies), 3),
        },
    }
    thresholds = {
        "min_acceptance_accuracy": args.min_acceptance_accuracy,
        "min_document_recall_at_5": args.min_doc_recall_at_5,
        "min_article_recall_at_5": args.min_article_recall_at_5,
        "min_out_of_domain_rejection_rate": args.min_ood_rejection_rate,
        "max_forbidden_document_retrieval_rate": 0.0,
        "max_retrieval_p95_ms": args.max_p95_ms,
    }
    checks = {
        "retrievable_accuracy": (
            metrics["retrievable_accuracy"] >= thresholds["min_acceptance_accuracy"]
        ),
        "answerable_accuracy": metrics["answerable_accuracy"] >= 0.90,
        "ambiguous_accuracy": metrics["ambiguous_accuracy"] >= 0.95,
        "adversarial_accuracy": metrics["adversarial_accuracy"] >= 0.95,
        "document_recall_at_5": (
            metrics["document_recall_at_5"] >= thresholds["min_document_recall_at_5"]
        ),
        "article_recall_at_5": (
            metrics["article_recall_at_5"] >= thresholds["min_article_recall_at_5"]
        ),
        "out_of_domain_rejection_rate": (
            metrics["out_of_domain_rejection_rate"]
            >= thresholds["min_out_of_domain_rejection_rate"]
        ),
        "forbidden_document_retrieval_rate": (
            metrics["forbidden_document_retrieval_rate"] == 0.0
        ),
        "retrieval_p95_ms": (
            metrics["latency_ms"]["p95"] <= thresholds["max_retrieval_p95_ms"]
        ),
    }
    return {
        "schema_version": "labor_retrieval_eval.v3",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "index_dir": str(retriever.index_dir),
        "top_k": args.top_k,
        "case_count": len(rows),
        "retrievable_case_count": len(retrievable_rows),
        "non_retrievable_case_count": len(non_retrievable_rows),
        "answerable_case_count": len(answerable_rows),
        "category_counts": dict(
            sorted(Counter(row.get("category", "uncategorized") for row in rows).items())
        ),
        "metrics": metrics,
        # Backward-compatible summaries for existing report consumers.
        "in_domain_hit_rate": metrics["document_recall_at_5"],
        "out_of_domain_rejection_rate": metrics["out_of_domain_rejection_rate"],
        "thresholds": thresholds,
        "checks": checks,
        "category_metrics": _category_metrics(rows),
        "passed": all(checks.values()),
        "cases": rows,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--min-acceptance-accuracy", type=float, default=0.90)
    parser.add_argument("--min-doc-recall-at-5", type=float, default=0.90)
    parser.add_argument("--min-article-recall-at-5", type=float, default=0.80)
    parser.add_argument("--min-ood-rejection-rate", type=float, default=0.95)
    parser.add_argument("--max-p95-ms", type=float, default=3_000.0)
    parser.add_argument("--api-url", help="evaluate a running retrieval HTTP service")
    parser.add_argument(
        "--api-key-env",
        default="LEGAL_RAG_API_KEY",
        help="environment variable containing the retrieval API key",
    )
    parser.add_argument("--request-timeout", type=float, default=120.0)
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="validate the JSONL suite without loading the retrieval models",
    )
    args = parser.parse_args()
    if args.top_k <= 0:
        parser.error("--top-k must be greater than zero")
    for name in (
        "min_acceptance_accuracy",
        "min_doc_recall_at_5",
        "min_article_recall_at_5",
        "min_ood_rejection_rate",
    ):
        if not 0.0 <= getattr(args, name) <= 1.0:
            parser.error(f"--{name.replace('_', '-')} must be between 0 and 1")
    if args.max_p95_ms <= 0:
        parser.error("--max-p95-ms must be greater than zero")
    if args.request_timeout <= 0:
        parser.error("--request-timeout must be greater than zero")
    return args


def main() -> int:
    args = parse_args()
    try:
        cases = load_cases(args.cases)
    except (OSError, ValueError) as error:
        raise SystemExit(f"Invalid evaluation suite: {error}") from error

    if args.validate_only:
        summary = {
            "valid": True,
            "case_count": len(cases),
            "category_counts": dict(
                sorted(Counter(case.get("category", "uncategorized") for case in cases).items())
            ),
        }
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0

    if args.api_url:
        api_key = os.getenv(args.api_key_env, "")
        if not api_key:
            raise SystemExit(
                f"Missing retrieval API key in environment variable {args.api_key_env}"
            )
        retriever = RemoteRetriever(args.api_url, api_key, args.request_timeout)
    else:
        retriever = SafeRetriever(k_candidates=max(20, args.top_k))
    rows = []
    for case in cases:
        row = evaluate_case(retriever, case, args.top_k)
        rows.append(row)
        print(
            f"{case['id']}: passed={row['passed']} "
            f"accepted={row['actual_accepted']} latency_ms={row['latency_ms']:.1f}",
            flush=True,
        )

    report = build_report(rows, retriever, args)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    summary = {key: value for key, value in report.items() if key != "cases"}
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
