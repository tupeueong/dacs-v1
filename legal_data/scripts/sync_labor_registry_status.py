"""Create an operational registry whose extraction status reflects local artifacts."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from rag_config import SETTINGS


SOURCE_DIR = SETTINGS.legal_data / "external" / "official_labor_2024_2026"
INPUT = SOURCE_DIR / "source_registry.merged.jsonl"
OUTPUT = SOURCE_DIR / "source_registry.current.jsonl"
REPORT = SOURCE_DIR / "source_registry.current.report.json"


def main() -> int:
    rows = [json.loads(line) for line in INPUT.open(encoding="utf-8") if line.strip()]
    official_path = SOURCE_DIR / "processed" / "articles.official.jsonl"
    consolidated_path = SOURCE_DIR / "processed" / "articles.consolidated_2026.jsonl"
    processed = set()
    for path in (official_path, consolidated_path):
        if not path.exists():
            continue
        for line in path.open(encoding="utf-8"):
            if not line.strip():
                continue
            record = json.loads(line)
            processed.update(record.get("origin_document_numbers", []))
    for row in rows:
        base_number = row["document_number"].split(":", 1)[0]
        if base_number in processed:
            row["extraction_status"] = "processed_qa_passed"
            row["processed_at"] = datetime.now(timezone.utc).isoformat()
    temp = OUTPUT.with_suffix(".jsonl.tmp")
    with temp.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    temp.replace(OUTPUT)
    pending = [
        row["document_number"]
        for row in rows
        if row["status"].startswith("current")
        and row["index_decision"] == "include_after_qa"
        and row["extraction_status"] != "processed_qa_passed"
        and row["extraction_status"] != "already_in_phapdien"
    ]
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "record_count": len(rows),
        "processed_document_count": sum(
            row["extraction_status"] == "processed_qa_passed" for row in rows
        ),
        "pending_current_documents": pending,
        "pending_current_count": len(pending),
    }
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

