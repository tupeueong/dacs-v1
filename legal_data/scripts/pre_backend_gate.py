"""Fail-fast readiness gate that must pass before backend/frontend integration."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from build_index_v2 import file_sha256, load_chunks, verify_index
from rag_config import SETTINGS
from verify_index_v2 import resolve_index


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    checks = {}
    article_report = load(SETTINGS.legal_data / "rag_corpus" / "articles_qa_report.json")
    chunk_report = load(SETTINGS.legal_data / "rag_corpus" / "chunks_qa_report.json")
    priority_report = load(
        SETTINGS.legal_data
        / "external"
        / "official_labor_2024_2026"
        / "processed"
        / "priority_qa_report.json"
    )
    article_validation = article_report["validation"]
    checks["articles_canonical"] = (
        article_validation["official_qa_passed"]
        and article_validation["consolidated_2026_qa_passed"]
        and article_validation["priority_sources_qa_passed"]
        and article_validation["unique_record_ids"]
        and article_validation["all_records_have_source_url"]
        and article_validation["ocr_records"] == 0
    )
    checks["chunks_v2"] = (
        chunk_report["schema_version"] == "unified_labor.chunks.v2"
        and chunk_report["validation"]["unique_chunk_ids"]
        and chunk_report["validation"]["all_articles_covered"]
        and chunk_report["token_length"]["over_hard_max"] == 0
    )
    required_priority_documents = {
        "11/2025/TT-BNV",
        "12/2025/TT-BNV",
        "56/2025/TT-BYT",
    }
    priority_documents = {
        item["document_number"]
        for item in priority_report.get("documents", [])
        if item.get("passed")
    }
    pending_priority_documents = sorted(required_priority_documents - priority_documents)
    checks["priority_sources_complete"] = (
        priority_report.get("all_documents_qa_passed", False)
        and priority_report.get("unique_record_ids", False)
        and not pending_priority_documents
    )

    index_error = None
    manifest = None
    if SETTINGS.current_pointer.exists():
        try:
            index_dir = resolve_index(SETTINGS.current_pointer)
            chunks = load_chunks(SETTINGS.chunks_path)
            index_result = verify_index(index_dir, [chunk["chunk_id"] for chunk in chunks])
            manifest = load(index_dir / "index_manifest.json")
            checks["index_integrity"] = (
                index_result["distance_metric"] == "cosine"
                and manifest["corpus_sha256"] == file_sha256(SETTINGS.chunks_path)
            )
        except (FileNotFoundError, KeyError, RuntimeError, ValueError) as exc:
            index_result = None
            index_error = f"{type(exc).__name__}: {exc}"
            checks["index_integrity"] = False
    else:
        index_result = None
        index_error = "Current index pointer does not exist"
        checks["index_integrity"] = False

    eval_path = SETTINGS.legal_data / "eval" / "retrieval_report.json"
    cases_path = SETTINGS.legal_data / "eval" / "retrieval_cases.jsonl"
    eval_report = load(eval_path) if eval_path.exists() else {}
    checks["retrieval_evaluation"] = (
        eval_report.get("passed", False)
        and manifest is not None
        and eval_report.get("corpus_sha256") == manifest.get("corpus_sha256")
        and eval_report.get("index_version")
        == (manifest.get("index_version") or manifest.get("version"))
        and eval_report.get("cases_sha256") == file_sha256(cases_path)
    )

    tests = subprocess.run(
        [
            sys.executable,
            "-X",
            "utf8",
            "-m",
            "unittest",
            "discover",
            "-s",
            str(SETTINGS.legal_data / "tests"),
            "-p",
            "test_*.py",
        ],
        cwd=SETTINGS.root,
        capture_output=True,
        text=True,
    )
    checks["unit_tests"] = tests.returncode == 0
    report = {
        "ready_for_backend": all(checks.values()),
        "checks": checks,
        "pending_priority_documents": pending_priority_documents,
        "index": index_result,
        "index_error": index_error,
        "unit_test_output": (tests.stdout + tests.stderr).strip(),
    }
    output = SETTINGS.legal_data / "pre_backend_gate_report.json"
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["ready_for_backend"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

