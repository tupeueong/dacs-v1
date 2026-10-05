"""Build the canonical current labor-law article corpus.

Priority: official current Gazette > current Phapdien > locally held documents
whose current status was verified against the national legal database.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


LEGAL_DATA = Path(__file__).resolve().parents[1]
PHAPDIEN = LEGAL_DATA / "external" / "phapdien_labor" / "processed" / "articles.final.jsonl"
OFFICIAL = (
    LEGAL_DATA
    / "external"
    / "official_labor_2024_2026"
    / "processed"
    / "articles.official.jsonl"
)
CONSOLIDATED = (
    LEGAL_DATA
    / "external"
    / "official_labor_2024_2026"
    / "processed"
    / "articles.consolidated_2026.jsonl"
)
PRIORITY = (
    LEGAL_DATA
    / "external"
    / "official_labor_2024_2026"
    / "processed"
    / "articles.priority.jsonl"
)
OUTPUT_DIR = LEGAL_DATA / "rag_corpus"
LEGACY_VERIFIED_AT = "2026-09-27T17:53:17+00:00"

FULLY_REPEALED_OR_REPLACED = {
    "01/2016/TT-BLĐTBXH": "11/2025/TT-BNV",
    "59/2015/TT-BLĐTBXH": "12/2025/TT-BNV",
    "06/2021/TT-BLĐTBXH": "12/2025/TT-BNV",
    "28/2016/TT-BYT": "56/2025/TT-BYT",
    "45/2019/QH14": "18/VBHN-VPQH",
    "58/VBHN-VPQH": "19/VBHN-VPQH",
    "38/2013/QH13": "74/2025/QH15",
    "58/2014/QH13": "58/VBHN-VPQH",
    "33/2016/NĐ-CP": "157/2025/NĐ-CP",
    "105/2016/TTLT-BQP-BCA-BLĐTBXH": "157/2025/NĐ-CP",
    "115/2015/NĐ-CP": "158/2025/NĐ-CP",
    "143/2018/NĐ-CP": "158/2025/NĐ-CP",
    "134/2015/NĐ-CP": "159/2025/NĐ-CP",
    "61/2015/NĐ-CP": "338/2025/NĐ-CP",
    "74/2019/NĐ-CP": "338/2025/NĐ-CP",
    "23/2021/NĐ-CP": "352/2025/NĐ-CP",
    "28/2015/NĐ-CP": "374/2025/NĐ-CP",
    "61/2020/NĐ-CP": "374/2025/NĐ-CP",
}

# Nghị định 158/2025/NĐ-CP repeals only selected provisions of Nghị định
# 135/2020/NĐ-CP.  Excluding those complete source records is safer than
# returning clauses known to be partly obsolete; the remaining six articles
# stay searchable.
PARTIAL_RECORD_EXCLUSIONS = {
    ("135/2020/NĐ-CP", "Điều 20.2.NĐ.2.3"),
    ("135/2020/NĐ-CP", "Điều 20.2.NĐ.2.7"),
    ("135/2020/NĐ-CP", "Điều 20.2.NĐ.2.8"),
}

VERIFIED_LEGACY = {
    "Nghị-định-12-2022-NĐ-CP.json": {
        "official_url": "https://vbpl.vn/bolaodong/Pages/ivbpq-thuoctinh.aspx?ItemID=153913",
        "scope": "xu_phat_vi_pham_hanh_chinh_lao_dong",
    },
    "Nghị-định-191-2013-NĐ-CP.json": {
        "official_url": "https://vbpl.vn/thanhhoa/Pages/ivbpq-thuoctinh.aspx?ItemID=32634&Keyword=",
        "scope": "tai_chinh_cong_doan",
    },
    "Nghị-định-43-2013-NĐ-CP.json": {
        "official_url": "https://vbpl.vn/tw/Pages/vbpq-thuoctinh.aspx?ItemID=32525",
        "scope": "quyen_trach_nhiem_cong_doan",
    },
}


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.open(encoding="utf-8") if line.strip()]


def text_hash(text: str) -> str:
    normalized = re.sub(r"\s+", " ", text).strip().casefold()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def convert_legacy(path: Path, config: dict) -> list[dict]:
    document = json.loads(path.read_text(encoding="utf-8"))
    metadata = document["metadata"]
    document_number = metadata["doc_number"]
    records = []
    for article in document.get("articles", []):
        article_id = f"Điều {article['article_number']}"
        content = article.get("content", "").strip()
        lines = content.splitlines()
        if lines and re.match(r"^Điều\s+[^.]+\.", lines[0], re.IGNORECASE):
            content = "\n".join(lines[1:]).strip()
        if not content:
            continue
        key = f"{document_number}::{article_id}"
        record_id = hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]
        records.append(
            {
                "source_type": "legacy_verified_current",
                "source_dataset": "local_legacy_verified_against_vbpl",
                "source_revision": text_hash(path.read_text(encoding="utf-8")),
                "record_id": record_id,
                "topic_id": "official-labor-current",
                "topic_number": 20,
                "topic_title": "Lao động",
                "subject_id": config["scope"],
                "subject_number": 0,
                "subject_title": metadata["doc_title"],
                "article_id": article_id,
                "article_title": f"{article_id}. {article.get('title', '').strip()}",
                "chapter_title": article.get("hierarchy_path", ""),
                "source_note_text": f"({article_id} văn bản số {document_number})",
                "source_links": [{"text": document_number, "href": config["official_url"]}],
                "related_note_text": "",
                "content_text": content,
                "content_hash": text_hash(content),
                "source_url": config["official_url"],
                "scraped_at": LEGACY_VERIFIED_AT,
                "schema_version": "legacy_verified_labor.article.v1",
                "content_text_raw": content,
                "origin_document_numbers": [document_number],
                "effective_dates": [
                    value
                    for value in (metadata.get("issue_date"), metadata.get("effective_date"))
                    if value
                ],
                "is_amended": False,
                "is_supplemented": False,
                "is_partly_abolished": False,
                "legal_status_hint": "current_verified_2026-09-27",
                "qa_flags": ["legacy_text_official_status_verified"],
                "canonical_record_id": record_id,
                "duplicate_group_size": 1,
                "is_duplicate_content": False,
                "removed_attachment_filenames": [],
                "document_type": metadata["doc_type"],
                "source_priority": 70,
            }
        )
    return records


def phapdien_is_current(record: dict) -> tuple[bool, str | None]:
    origins = set(record.get("origin_document_numbers", []))
    replaced = sorted(origins & FULLY_REPEALED_OR_REPLACED.keys())
    if replaced:
        return False, "fully_repealed_or_replaced:" + ",".join(replaced)
    for origin in origins:
        if (origin, record.get("article_id")) in PARTIAL_RECORD_EXCLUSIONS:
            return False, f"partly_repealed_record:{origin}:{record.get('article_id')}"
    return True, None


def filter_current(records: list[dict], source_name: str) -> tuple[list[dict], list[dict]]:
    kept: list[dict] = []
    removed: list[dict] = []
    for record in records:
        keep, reason = phapdien_is_current(record)
        if keep:
            kept.append(record)
        else:
            removed.append(
                {
                    "source": source_name,
                    "record_id": record["record_id"],
                    "article_id": record["article_id"],
                    "origin_document_numbers": record.get("origin_document_numbers", []),
                    "reason": reason,
                }
            )
    return kept, removed


def priority(record: dict) -> int:
    if record.get("source_type") == "official_gazette":
        return int(record.get("source_priority", 95))
    if record.get("source_type") == "phapdien":
        return 80
    return int(record.get("source_priority", 60))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=OUTPUT_DIR / "articles.jsonl")
    parser.add_argument(
        "--report", type=Path, default=OUTPUT_DIR / "articles_qa_report.json"
    )
    parser.add_argument("--as-of-date", default=datetime.now(timezone.utc).date().isoformat())
    args = parser.parse_args()

    official_report_path = OFFICIAL.parent / "official_qa_report.json"
    official_report = json.loads(official_report_path.read_text(encoding="utf-8"))
    if not official_report.get("all_documents_qa_passed"):
        raise RuntimeError("Official Gazette QA has not passed")
    consolidated_report_path = CONSOLIDATED.parent / "consolidated_2026_qa_report.json"
    consolidated_report = json.loads(consolidated_report_path.read_text(encoding="utf-8"))
    if not consolidated_report.get("all_documents_qa_passed"):
        raise RuntimeError("Consolidated 2026 QA has not passed")
    priority_report_path = PRIORITY.parent / "priority_qa_report.json"
    priority_report = json.loads(priority_report_path.read_text(encoding="utf-8"))
    if not priority_report.get("all_documents_qa_passed"):
        raise RuntimeError("Priority source QA has not passed")

    phapdien_all = read_jsonl(PHAPDIEN)
    phapdien_kept, exclusions = filter_current(phapdien_all, "phapdien")
    for record in phapdien_kept:
        record["source_priority"] = 80

    official_all = read_jsonl(OFFICIAL)
    official, official_exclusions = filter_current(official_all, "official_gazette")
    consolidated_all = read_jsonl(CONSOLIDATED)
    consolidated, consolidated_exclusions = filter_current(
        consolidated_all, "official_consolidated_2026"
    )
    priority_all = read_jsonl(PRIORITY)
    priority_records, priority_exclusions = filter_current(
        priority_all, "official_registry_mirror"
    )
    exclusions.extend(official_exclusions)
    exclusions.extend(consolidated_exclusions)
    exclusions.extend(priority_exclusions)
    legacy = []
    for filename, config in VERIFIED_LEGACY.items():
        legacy.extend(convert_legacy(LEGAL_DATA / "json" / filename, config))

    candidates = phapdien_kept + official + consolidated + priority_records + legacy
    by_legal_key: dict[tuple[str, str], dict] = {}
    conflicts = []
    for record in candidates:
        origins = record.get("origin_document_numbers", [])
        doc_number = origins[0] if origins else ""
        key = (doc_number.upper(), record["article_id"].casefold())
        previous = by_legal_key.get(key)
        if previous is None or priority(record) > priority(previous):
            if previous is not None:
                conflicts.append(
                    {
                        "key": key,
                        "kept": record["record_id"],
                        "discarded": previous["record_id"],
                    }
                )
            by_legal_key[key] = record
        else:
            conflicts.append(
                {"key": key, "kept": previous["record_id"], "discarded": record["record_id"]}
            )

    by_hash: dict[str, dict] = {}
    hash_duplicates = []
    for record in by_legal_key.values():
        key = record["content_hash"]
        previous = by_hash.get(key)
        if previous is None or priority(record) > priority(previous):
            if previous is not None:
                hash_duplicates.append(
                    {"hash": key, "kept": record["record_id"], "discarded": previous["record_id"]}
                )
            by_hash[key] = record
        else:
            hash_duplicates.append(
                {"hash": key, "kept": previous["record_id"], "discarded": record["record_id"]}
            )

    records = sorted(
        by_hash.values(),
        key=lambda item: (
            item.get("topic_number", 0),
            item.get("subject_title", ""),
            item.get("origin_document_numbers", [""])[0],
            item.get("article_id", ""),
        ),
    )
    record_ids = [item["record_id"] for item in records]
    if len(record_ids) != len(set(record_ids)):
        raise RuntimeError("Duplicate record_id in unified articles")
    if any(not item.get("source_url") for item in records):
        raise RuntimeError("Missing source_url in unified articles")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    output_path = args.output
    temp_path = output_path.with_suffix(".jsonl.tmp")
    with temp_path.open("w", encoding="utf-8", newline="\n") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    temp_path.replace(output_path)

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "as_of_date": args.as_of_date,
        "inputs": {
            "phapdien": len(phapdien_all),
            "official_gazette": len(official_all),
            "official_consolidated_2026": len(consolidated_all),
            "official_registry_mirror": len(priority_all),
            "legacy_verified_current": len(legacy),
        },
        "phapdien_kept": len(phapdien_kept),
        "excluded_by_source": dict(Counter(item["source"] for item in exclusions)),
        "official_gazette_kept": len(official),
        "official_consolidated_2026_kept": len(consolidated),
        "official_registry_mirror_kept": len(priority_records),
        "canonical_article_count": len(records),
        "source_type_counts": dict(Counter(item["source_type"] for item in records)),
        "legal_key_conflicts": conflicts,
        "exact_content_duplicates": hash_duplicates,
        "fully_repealed_or_replaced_documents": FULLY_REPEALED_OR_REPLACED,
        "partial_record_exclusions": sorted([list(item) for item in PARTIAL_RECORD_EXCLUSIONS]),
        "excluded_records": exclusions,
        "validation": {
            "official_qa_passed": True,
            "consolidated_2026_qa_passed": True,
            "priority_sources_qa_passed": True,
            "unique_record_ids": True,
            "all_records_have_source_url": True,
            "ocr_records": sum(item["source_type"] == "ocr" for item in records),
        },
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({key: value for key, value in report.items() if key != "excluded_records"}, ensure_ascii=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
