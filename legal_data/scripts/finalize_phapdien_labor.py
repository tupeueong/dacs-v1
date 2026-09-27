"""Hoàn thiện và khóa dữ liệu Pháp điển lao động trước khi chunk.

Chỉ loại các dòng độc lập là tên tệp .doc/.docx còn sót từ portal. Bản
``content_text_raw`` và đầu ra tiền xử lý trước đó không bị thay đổi.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse


LEGAL_DATA = Path(__file__).resolve().parent.parent
FILE_LINE_RE = re.compile(r"(?im)^\s*[^\n]{1,160}\.docx?\s*$")
CONTROL_RE = re.compile(r"[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f]")


def normalized_hash(text: str) -> str:
    normalized = re.sub(r"\s+", " ", text).strip().casefold()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def clean_artifact_lines(text: str) -> tuple[str, list[str]]:
    removed = [match.group(0).strip() for match in FILE_LINE_RE.finditer(text)]
    cleaned = FILE_LINE_RE.sub("", text)
    cleaned = re.sub(r" *\n *", "\n", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()
    return cleaned, removed


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input",
        type=Path,
        default=LEGAL_DATA / "external" / "phapdien_labor" / "processed" / "articles.clean.jsonl",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=LEGAL_DATA / "external" / "phapdien_labor" / "processed" / "articles.final.jsonl",
    )
    args = parser.parse_args()

    records = [json.loads(line) for line in args.input.read_text(encoding="utf-8").splitlines()]
    ids = Counter(record.get("record_id") for record in records)
    duplicate_ids = [key for key, count in ids.items() if not key or count > 1]
    if duplicate_ids:
        raise RuntimeError(f"record_id thiếu hoặc trùng: {duplicate_ids[:10]}")

    removed_count = 0
    changed_records = 0
    for record in records:
        content = record.get("content_text", "")
        cleaned, removed = clean_artifact_lines(content)
        if not cleaned:
            raise RuntimeError(f"Nội dung rỗng sau làm sạch: {record['record_id']}")
        if CONTROL_RE.search(cleaned):
            raise RuntimeError(f"Còn ký tự điều khiển: {record['record_id']}")
        if removed:
            changed_records += 1
            removed_count += len(removed)
            flags = list(record.get("qa_flags", []))
            if "attachment_filename_removed" not in flags:
                flags.append("attachment_filename_removed")
            record["qa_flags"] = flags
        record["removed_attachment_filenames"] = removed
        record["content_text"] = cleaned
        record["content_hash"] = normalized_hash(cleaned)
        record["schema_version"] = "phapdien_labor.article.final.v1"
        if not record.get("source_url") or urlparse(record["source_url"]).scheme not in ("http", "https"):
            raise RuntimeError(f"source_url không hợp lệ: {record['record_id']}")
        if not record.get("origin_document_numbers"):
            raise RuntimeError(f"Thiếu văn bản nguồn: {record['record_id']}")

    groups: dict[str, list[dict]] = defaultdict(list)
    for record in records:
        groups[record["content_hash"]].append(record)
    for group in groups.values():
        canonical = min(item["record_id"] for item in group)
        for record in group:
            record["canonical_record_id"] = canonical
            record["duplicate_group_size"] = len(group)
            record["is_duplicate_content"] = len(group) > 1

    if any(FILE_LINE_RE.search(record["content_text"]) for record in records):
        raise RuntimeError("Vẫn còn dòng tên file .doc/.docx")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_suffix(args.output.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    temporary.replace(args.output)

    lengths = sorted(len(record["content_text"]) for record in records)
    report = {
        "schema_version": "phapdien_labor.finalize.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "input": str(args.input),
        "output": str(args.output),
        "record_count": len(records),
        "changed_records": changed_records,
        "attachment_filename_lines_removed": removed_count,
        "duplicate_content_groups": sum(len(group) > 1 for group in groups.values()),
        "duplicate_content_records": sum(len(group) for group in groups.values() if len(group) > 1),
        "content_length": {
            "min": lengths[0],
            "median": lengths[len(lengths) // 2],
            "p95": lengths[int(0.95 * (len(lengths) - 1))],
            "max": lengths[-1],
        },
        "validation": {
            "unique_record_ids": True,
            "no_empty_content": True,
            "no_attachment_filename_lines": True,
            "all_source_urls_valid": True,
            "all_records_have_origin_document": True,
        },
    }
    report_path = args.output.with_name("finalize_report.json")
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=True, indent=2))


if __name__ == "__main__":
    main()
