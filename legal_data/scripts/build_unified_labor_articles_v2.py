"""Promote the 2026 consolidated Labor Code and Social Insurance Law into the corpus."""

from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from rag_config import SETTINGS


CORPUS = SETTINGS.articles_path
NEW_SOURCE = (
    SETTINGS.legal_data
    / "external"
    / "official_labor_2024_2026"
    / "processed"
    / "articles.consolidated_2026.jsonl"
)
REPORT = SETTINGS.legal_data / "rag_corpus" / "articles_qa_report_v2.json"
REPLACED_CURRENT_SOURCES = {"45/2019/QH14", "58/VBHN-VPQH"}


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.open(encoding="utf-8") if line.strip()]


def main() -> int:
    base = read_jsonl(CORPUS)
    consolidated = read_jsonl(NEW_SOURCE)
    kept, removed = [], []
    for record in base:
        origins = set(record.get("origin_document_numbers", []))
        if origins.intersection(REPLACED_CURRENT_SOURCES):
            removed.append(record)
        else:
            kept.append(record)
    records = kept + consolidated
    ids = [record["record_id"] for record in records]
    legal_keys = [
        ((record.get("origin_document_numbers") or [""])[0], record["article_id"])
        for record in records
    ]
    if len(ids) != len(set(ids)):
        raise RuntimeError("Duplicate record_id after v2 consolidation")
    if len(legal_keys) != len(set(legal_keys)):
        raise RuntimeError("Duplicate document/article legal key after v2 consolidation")
    records.sort(
        key=lambda record: (
            record.get("topic_number", 0),
            record.get("subject_title", ""),
            (record.get("origin_document_numbers") or [""])[0],
            record.get("article_id", ""),
        )
    )
    temp = CORPUS.with_suffix(".jsonl.tmp")
    with temp.open("w", encoding="utf-8", newline="\n") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    temp.replace(CORPUS)
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "schema_version": "unified_labor.articles.v2",
        "as_of_date": "2026-09-28",
        "base_count": len(base),
        "removed_superseded_count": len(removed),
        "removed_by_document": dict(
            Counter((record.get("origin_document_numbers") or [""])[0] for record in removed)
        ),
        "added_consolidated_count": len(consolidated),
        "final_count": len(records),
        "source_type_counts": dict(Counter(record["source_type"] for record in records)),
        "validation": {
            "unique_record_ids": True,
            "unique_legal_keys": True,
            "all_records_have_source_url": all(bool(record.get("source_url")) for record in records),
            "superseded_sources_remaining": sum(
                bool(set(record.get("origin_document_numbers", [])).intersection(REPLACED_CURRENT_SOURCES))
                for record in records
            ),
        },
    }
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

