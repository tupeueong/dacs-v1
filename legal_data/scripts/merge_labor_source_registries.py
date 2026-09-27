"""Merge and validate the official labor-law source registries.

This script does not download, OCR, chunk, or embed documents.  Its output is
the single review queue that controls which sources may enter the canonical
labor-law corpus.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any


LEGAL_DATA_DIR = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE_DIR = LEGAL_DATA_DIR / "external" / "official_labor_2024_2026"
DEFAULT_OUTPUT = DEFAULT_SOURCE_DIR / "source_registry.merged.jsonl"
DEFAULT_REPORT = DEFAULT_SOURCE_DIR / "source_registry.report.json"

REQUIRED_FIELDS = (
    "document_number",
    "title",
    "document_type",
    "status",
    "scope",
    "source_priority",
    "official_page",
    "extraction_status",
    "index_decision",
)


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, raw_line in enumerate(handle, 1):
            line = raw_line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{line_number}: invalid JSON: {exc}") from exc
            if not isinstance(record, dict):
                raise ValueError(f"{path}:{line_number}: record must be a JSON object")
            missing = [field for field in REQUIRED_FIELDS if record.get(field) in (None, "")]
            # issued_date is intentionally not a hard requirement while a source is
            # still in metadata verification, but all registry control fields are.
            if missing:
                raise ValueError(
                    f"{path}:{line_number}: missing required fields: {', '.join(missing)}"
                )
            record["_registry_file"] = path.name
            record["_registry_line"] = line_number
            records.append(record)
    return records


def merge_records(paths: list[Path]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    merged: dict[str, dict[str, Any]] = {}
    conflicts: list[dict[str, Any]] = []

    for path in paths:
        for record in read_jsonl(path):
            key = str(record["document_number"]).strip().upper()
            previous = merged.get(key)
            if previous is not None:
                conflicts.append(
                    {
                        "document_number": key,
                        "kept_from": record["_registry_file"],
                        "replaced_from": previous["_registry_file"],
                    }
                )
            merged[key] = record

    ordered = sorted(
        merged.values(),
        key=lambda item: (
            -int(item.get("source_priority", 0)),
            str(item.get("document_number", "")),
        ),
    )
    return ordered, conflicts


def write_jsonl_atomic(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(path.suffix + ".tmp")
    with temp_path.open("w", encoding="utf-8", newline="\n") as handle:
        for record in records:
            clean = {key: value for key, value in record.items() if not key.startswith("_")}
            handle.write(json.dumps(clean, ensure_ascii=False, sort_keys=True) + "\n")
    temp_path.replace(path)


def write_report_atomic(
    path: Path,
    records: list[dict[str, Any]],
    source_files: list[Path],
    conflicts: list[dict[str, Any]],
) -> None:
    report = {
        "source_files": [item.name for item in source_files],
        "record_count": len(records),
        "duplicate_keys_resolved": conflicts,
        "by_status": dict(Counter(str(item["status"]) for item in records)),
        "by_extraction_status": dict(
            Counter(str(item["extraction_status"]) for item in records)
        ),
        "by_index_decision": dict(
            Counter(str(item["index_decision"]) for item in records)
        ),
        "embedding_blocked_count": sum(
            1
            for item in records
            if item["index_decision"] not in {"include_from_phapdien", "history_only"}
            and item["extraction_status"]
            not in {"native_text_ready", "already_in_phapdien", "qa_passed"}
        ),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(path.suffix + ".tmp")
    temp_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temp_path.replace(path)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-dir", type=Path, default=DEFAULT_SOURCE_DIR)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output_resolved = args.output.resolve()
    paths = sorted(
        path
        for path in args.source_dir.glob("source_registry*.jsonl")
        if path.resolve() != output_resolved
    )
    if not paths:
        raise SystemExit(f"No registry files found in {args.source_dir}")

    records, conflicts = merge_records(paths)
    write_jsonl_atomic(args.output, records)
    write_report_atomic(args.report, records, paths, conflicts)
    print(f"Merged {len(records)} records from {len(paths)} files -> {args.output}")
    print(f"QA report -> {args.report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
