"""Ingest three current labor-law circulars with explicit source provenance.

VBPL is the authority for identity, status, and effective dates.  The public
LSU mirror is used only as the machine-readable carrier because VBPL redirects
automated clients to its cookie page.  Article counts and sequences are hard
gates so a partial page can never enter the corpus.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

import requests
from bs4 import BeautifulSoup


LEGAL_DATA = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = (
    LEGAL_DATA
    / "external"
    / "official_labor_2024_2026"
    / "processed"
    / "articles.priority.jsonl"
)
DEFAULT_REPORT = DEFAULT_OUTPUT.with_name("priority_qa_report.json")
VERIFIED_AT = "2026-09-29T08:00:00+00:00"
ARTICLE_RE = re.compile(r"^Điều\s+(\d+)[a-zđ]?\.(?:\s*(.*))?$", re.IGNORECASE)
HIERARCHY_RE = re.compile(r"^(Chương|Mục)\s+[IVXLCDM\d]+\.?$", re.IGNORECASE)


DOCUMENTS = (
    {
        "doc_number": "11/2025/TT-BNV",
        "title": "Quy định chi tiết một số điều của Luật Bảo hiểm xã hội về bảo hiểm xã hội tự nguyện",
        "subject_id": "bao_hiem_xa_hoi_tu_nguyen_2025",
        "expected_articles": 7,
        "issued_date": "2025-06-30",
        "effective_date": "2025-07-01",
        "official_item_id": 179767,
        "official_url": "https://vbpl.vn/bonoivu/Pages/vbpq-toanvan.aspx?ItemID=179767&dvid=320",
        "mirror_url": "https://lsu.vn/van-ban/thong-tu-11-2025-tt-bnv-bo-noi-vu",
    },
    {
        "doc_number": "12/2025/TT-BNV",
        "title": "Quy định chi tiết một số điều của Luật Bảo hiểm xã hội về bảo hiểm xã hội bắt buộc",
        "subject_id": "bao_hiem_xa_hoi_bat_buoc_2025",
        "expected_articles": 21,
        "issued_date": "2025-06-30",
        "effective_date": "2025-07-01",
        "official_item_id": 179089,
        "official_url": "https://vbpl.vn/bonoivu/Pages/vbpq-toanvan.aspx?ItemID=179089&dvid=320",
        "mirror_url": "https://lsu.vn/van-ban/thong-tu-12-2025-tt-bnv-bo-noi-vu",
    },
    {
        "doc_number": "56/2025/TT-BYT",
        "title": "Hướng dẫn quản lý bệnh nghề nghiệp",
        "subject_id": "quan_ly_benh_nghe_nghiep_2025",
        "expected_articles": 24,
        "issued_date": "2025-12-31",
        "effective_date": "2026-02-15",
        "official_item_id": 185610,
        "official_url": "https://vbpl.vn/boyte/Pages/vbpq-thuoctinh.aspx?ItemID=185610",
        "mirror_url": "https://lsu.vn/van-ban/thong-tu-56-2025-tt-byt-bo-y-te",
    },
)


def compact(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def content_lines(url: str) -> tuple[list[str], str]:
    response = requests.get(
        url,
        headers={"User-Agent": "labor-rag-corpus-builder/1.0"},
        timeout=60,
    )
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    heading = next(
        (
            item
            for item in soup.find_all(["h2", "h3"])
            if "Nội dung toàn văn" in item.get_text(" ", strip=True)
        ),
        None,
    )
    if heading is None or heading.parent is None:
        raise RuntimeError(f"Missing full-text section: {url}")
    lines = [
        compact(value)
        for value in heading.parent.get_text("\n", strip=True).splitlines()
        if compact(value)
    ]
    normalized = "\n".join(lines)
    return lines, digest(normalized)


def combine_split_article_titles(lines: list[str]) -> list[str]:
    combined: list[str] = []
    index = 0
    while index < len(lines):
        line = lines[index]
        match = ARTICLE_RE.match(line)
        if match and not (match.group(2) or "").strip() and index + 1 < len(lines):
            following = lines[index + 1]
            if not ARTICLE_RE.match(following) and not HIERARCHY_RE.match(following):
                combined.append(f"{line} {following}")
                index += 2
                continue
        combined.append(line)
        index += 1
    return combined


def split_articles(lines: list[str]) -> list[dict]:
    lines = combine_split_article_titles(lines)
    articles: list[dict] = []
    current: dict | None = None
    hierarchy: list[str] = []
    pending_hierarchy: str | None = None

    def finish() -> None:
        nonlocal current
        if current is None:
            return
        current["content_text"] = "\n".join(current.pop("body")).strip()
        articles.append(current)
        current = None

    for line in lines:
        if line.casefold().startswith("nơi nhận:"):
            break
        if current is not None and line in {"BỘ TRƯỞNG", "KT. BỘ TRƯỞNG"}:
            break
        if HIERARCHY_RE.match(line):
            pending_hierarchy = line
            continue
        if pending_hierarchy is not None:
            if line.isupper() and not ARTICLE_RE.match(line):
                label = f"{pending_hierarchy} - {line}"
                if pending_hierarchy.casefold().startswith("chương"):
                    hierarchy = [label]
                else:
                    hierarchy = hierarchy[:1] + [label]
                pending_hierarchy = None
                continue
            pending_hierarchy = None
        match = ARTICLE_RE.match(line)
        if match:
            finish()
            number = int(match.group(1))
            current = {
                "article_number": number,
                "article_id": f"Điều {number}",
                "article_title": line,
                "chapter_title": " > ".join(hierarchy),
                "body": [],
            }
        elif current is not None:
            current["body"].append(line)
    finish()
    return articles


def build_records(config: dict) -> tuple[list[dict], dict]:
    lines, source_revision = content_lines(config["mirror_url"])
    articles = split_articles(lines)
    numbers = [item["article_number"] for item in articles]
    expected = list(range(1, config["expected_articles"] + 1))
    no_empty = all(bool(item["content_text"]) for item in articles)
    passed = numbers == expected and no_empty
    if not passed:
        raise RuntimeError(
            f"QA failed for {config['doc_number']}: numbers={numbers}, no_empty={no_empty}"
        )

    records = []
    for article in articles:
        legal_key = f"{config['doc_number']}::{article['article_id']}"
        record_id = digest(legal_key)[:16]
        content_hash = digest(compact(article["content_text"]).casefold())
        records.append(
            {
                "source_type": "official_registry_mirror",
                "source_dataset": "vbpl_metadata_lsu_full_text_verified",
                "source_revision": source_revision,
                "record_id": record_id,
                "topic_id": "official-labor-current",
                "topic_number": 20,
                "topic_title": "Lao động",
                "subject_id": config["subject_id"],
                "subject_number": 0,
                "subject_title": config["title"],
                "article_id": article["article_id"],
                "article_title": article["article_title"],
                "chapter_title": article["chapter_title"],
                "source_note_text": (
                    f"({article['article_id']} văn bản số {config['doc_number']})"
                ),
                "source_links": [
                    {"text": config["doc_number"], "href": config["official_url"]}
                ],
                "related_note_text": "",
                "content_text": article["content_text"],
                "content_hash": content_hash,
                "source_url": config["official_url"],
                "mirror_url": config["mirror_url"],
                "official_item_id": config["official_item_id"],
                "scraped_at": VERIFIED_AT,
                "schema_version": "priority_labor.article.v1",
                "content_text_raw": article["content_text"],
                "origin_document_numbers": [config["doc_number"]],
                "effective_dates": [config["issued_date"], config["effective_date"]],
                "is_amended": False,
                "is_supplemented": False,
                "is_partly_abolished": False,
                "legal_status_hint": "current_verified_vbpl_2026-09-29",
                "qa_flags": [
                    "official_vbpl_identity_status_verified",
                    "mirror_full_text_article_sequence_verified",
                    "forms_and_appendices_excluded",
                ],
                "canonical_record_id": record_id,
                "duplicate_group_size": 1,
                "is_duplicate_content": False,
                "removed_attachment_filenames": [],
                "document_type": "thong_tu",
                "source_priority": 100,
            }
        )
    return records, {
        "document_number": config["doc_number"],
        "official_url": config["official_url"],
        "mirror_url": config["mirror_url"],
        "source_revision": source_revision,
        "article_count": len(records),
        "expected_articles": config["expected_articles"],
        "continuous_article_numbers": numbers == expected,
        "no_empty_articles": no_empty,
        "passed": passed,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    args = parser.parse_args()

    records: list[dict] = []
    documents: list[dict] = []
    for config in DOCUMENTS:
        document_records, document_report = build_records(config)
        records.extend(document_records)
        documents.append(document_report)

    ids = [item["record_id"] for item in records]
    if len(ids) != len(set(ids)):
        raise RuntimeError("Duplicate priority-source record_id")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_suffix(".jsonl.tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    temporary.replace(args.output)

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "schema_version": "priority_labor.qa.v1",
        "record_count": len(records),
        "all_documents_qa_passed": all(item["passed"] for item in documents),
        "unique_record_ids": True,
        "documents": documents,
    }
    args.report.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
