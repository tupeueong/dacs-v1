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
    article_report = load(SETTINGS.legal_data / "rag_corpus" / "articles_qa_report_v2.json")
    chunk_report = load(SETTINGS.legal_data / "rag_corpus" / "chunks_qa_report.json")
    registry_report = load(
        SETTINGS.legal_data
        / "external"
        / "official_labor_2024_2026"
        / "source_registry.current.report.json"
    )
    checks["articles_v2"] = (
        article_report["validation"]["unique_record_ids"]
        and article_report["validation"]["unique_legal_keys"]
        and article_report["validation"]["superseded_sources_remaining"] == 0
    )
    checks["chunks_v2"] = (
        chunk_report["schema_version"] == "unified_labor.chunks.v2"
        and chunk_report["validation"]["unique_chunk_ids"]
        and chunk_report["validation"]["all_articles_covered"]
        and chunk_report["token_length"]["over_hard_max"] == 0
    )
    checks["priority_sources_complete"] = registry_report["pending_current_count"] == 0

    if SETTINGS.current_pointer.exists():
        index_dir = resolve_index(SETTINGS.current_pointer)
        chunks = load_chunks(SETTINGS.chunks_path)
        index_result = verify_index(index_dir, [chunk["chunk_id"] for chunk in chunks])
        manifest = load(index_dir / "index_manifest.json")
        checks["index_integrity"] = (
            index_result["distance_metric"] == "cosine"
            and manifest["corpus_sha256"] == file_sha256(SETTINGS.chunks_path)
        )
    else:
        index_result = None
        checks["index_integrity"] = False

    eval_path = SETTINGS.legal_data / "eval" / "retrieval_report.json"
    checks["retrieval_evaluation"] = eval_path.exists() and load(eval_path).get("passed", False)

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
        "pending_current_documents": registry_report["pending_current_documents"],
        "index": index_result,
        "unit_test_output": (tests.stdout + tests.stderr).strip(),
    }
    output = SETTINGS.legal_data / "pre_backend_gate_report.json"
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["ready_for_backend"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

