"""Parse official 2026 consolidated Labor Code and Social Insurance Law DOCX files."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

from docx import Document

from rag_config import SETTINGS


SOURCE_DIR = SETTINGS.legal_data / "external" / "official_labor_2024_2026"
DOCX_DIR = SOURCE_DIR / "congbao_docx"
OUTPUT = SOURCE_DIR / "processed" / "articles.consolidated_2026.jsonl"
REPORT = SOURCE_DIR / "processed" / "consolidated_2026_qa_report.json"
ARTICLE_RE = re.compile(r"^Điều\s+(\d+[A-Za-z]?)\.\s*(.*)$", re.IGNORECASE)
CHAPTER_RE = re.compile(r"^(Chương\s+[IVXLCDM]+|Chương\s+\d+)\b", re.IGNORECASE)


DOCUMENTS = {
    "18/VBHN-VPQH": {
        "filename": "18-VBHN-VPQH.docx",
        "title": "Bộ luật Lao động (văn bản hợp nhất 2026)",
        "scope": "bo_luat_lao_dong",
        "expected_articles": 220,
        "effective_from": "2026-01-01",
        "official_page": "https://congbao.chinhphu.vn/van-ban/van-ban-hop-nhat-so-18-vbhn-vpqh-468971.htm",
    },
    "19/VBHN-VPQH": {
        "filename": "19-VBHN-VPQH.docx",
        "title": "Luật Bảo hiểm xã hội (văn bản hợp nhất 2026)",
        "scope": "bao_hiem_xa_hoi",
        "expected_articles": 141,
        "effective_from": "2025-07-01",
        "official_page": "https://congbao.chinhphu.vn/van-ban/van-ban-hop-nhat-so-19-vbhn-vpqh-468972.htm",
    },
}


def sha256_bytes(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sha256_text(text: str) -> str:
    normalized = re.sub(r"\s+", " ", text).strip().casefold()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def paragraphs(path: Path) -> list[str]:
    return [re.sub(r"\s+", " ", p.text).strip() for p in Document(path).paragraphs]


def parse_document(document_number: str, config: dict) -> tuple[list[dict], dict]:
    path = DOCX_DIR / config["filename"]
    if not path.exists():
        raise FileNotFoundError(path)
    source_hash = sha256_bytes(path)
    lines = paragraphs(path)
    current_chapter = ""
    parsed: list[tuple[str, str, str, list[str]]] = []
    current = None
    for line in lines:
        if not line:
            continue
        if CHAPTER_RE.match(line):
            current_chapter = line
            continue
        match = ARTICLE_RE.match(line)
        if match:
            if current is not None:
                parsed.append(current)
            article_number, title = match.groups()
            current = [article_number, title.strip(), current_chapter, []]
        elif current is not None:
            current[3].append(line)
    if current is not None:
        parsed.append(current)

    records = []
    for article_number, title, chapter, body_lines in parsed:
        content = "\n".join(body_lines).strip()
        article_id = f"Điều {article_number}"
        identity = f"{document_number}::{article_id}"
        record_id = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:16]
        records.append(
            {
                "source_type": "official_gazette",
                "source_dataset": "congbao_chinhphu_consolidated_2026",
                "source_revision": source_hash,
                "record_id": record_id,
                "topic_id": "official-labor-current",
                "topic_number": 20,
                "topic_title": "Lao động",
                "subject_id": config["scope"],
                "subject_number": 0,
                "subject_title": config["title"],
                "article_id": article_id,
                "article_title": f"{article_id}. {title}",
                "chapter_title": chapter,
                "source_note_text": f"({article_id} văn bản số {document_number})",
                "source_links": [{"text": document_number, "href": config["official_page"]}],
                "related_note_text": "",
                "content_text": content,
                "content_hash": sha256_text(content),
                "source_url": config["official_page"],
                "scraped_at": datetime.now(timezone.utc).isoformat(),
                "schema_version": "official_consolidated_labor.article.v1",
                "content_text_raw": content,
                "origin_document_numbers": [document_number],
                "effective_dates": [config["effective_from"], "2026-02-12"],
                "is_amended": True,
                "is_supplemented": True,
                "is_partly_abolished": False,
                "legal_status_hint": "current_consolidated",
                "qa_flags": ["official_native_docx", "article_sequence_verified"],
                "canonical_record_id": record_id,
                "duplicate_group_size": 1,
                "is_duplicate_content": False,
                "removed_attachment_filenames": [],
                "document_type": "van_ban_hop_nhat",
                "source_priority": 110,
            }
        )

    numeric = [int(record["article_id"].removeprefix("Điều ")) for record in records]
    expected = list(range(1, config["expected_articles"] + 1))
    qa = {
        "document_number": document_number,
        "source_file": str(path),
        "source_sha256": source_hash,
        "article_count": len(records),
        "expected_articles": config["expected_articles"],
        "continuous_article_numbers": numeric == expected,
        "no_empty_articles": all(record["content_text"] for record in records),
    }
    qa["passed"] = (
        qa["article_count"] == qa["expected_articles"]
        and qa["continuous_article_numbers"]
        and qa["no_empty_articles"]
    )
    return records, qa


def main() -> int:
    all_records, reports = [], []
    for number, config in DOCUMENTS.items():
        records, report = parse_document(number, config)
        all_records.extend(records)
        reports.append(report)
    if not all(report["passed"] for report in reports):
        raise RuntimeError(json.dumps(reports, ensure_ascii=False, indent=2))
    ids = [record["record_id"] for record in all_records]
    if len(ids) != len(set(ids)):
        raise RuntimeError("Duplicate consolidated record IDs")
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    temp = OUTPUT.with_suffix(".jsonl.tmp")
    with temp.open("w", encoding="utf-8", newline="\n") as handle:
        for record in all_records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    temp.replace(OUTPUT)
    qa = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "record_count": len(all_records),
        "all_documents_qa_passed": True,
        "documents": reports,
    }
    REPORT.write_text(json.dumps(qa, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(qa, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

