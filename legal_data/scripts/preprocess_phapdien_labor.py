"""Chuẩn hóa và kiểm định dữ liệu Bộ Pháp Điển chủ đề Lao động trước khi chunk.

Script này không tạo chunk. Nó giữ nguyên bản ghi nguồn, bổ sung provenance có cấu
trúc, tách phần phụ lục bị ghép vào Điều và xuất báo cáo QA có thể kiểm tra lại.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import unicodedata
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse


LEGAL_DATA = Path(__file__).resolve().parent.parent
DOC_NUMBER_RE = re.compile(r"\b\d+/\d{4}/[A-ZĐ0-9-]+\b", re.IGNORECASE)
DATE_RE = re.compile(r"\b(?:ngày\s+)?(\d{1,2})/(\d{1,2})/(\d{4})\b", re.IGNORECASE)
ATTACHMENT_RE = re.compile(r"(?:^|\n)(PHỤ LỤC(?:\s+[IVXLCDM\d]+)?)\s*(?:\n|$)")
FILE_ARTIFACT_RE = re.compile(r"(?im)^\s*phu\s*luc[^\n]*\.docx?\s*$")
CONTROL_RE = re.compile(r"[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f]")


def clean_text(value: object) -> str:
    if value is None:
        return ""
    text = unicodedata.normalize("NFC", str(value))
    text = CONTROL_RE.sub("", text)
    text = text.replace("\u00a0", " ").replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def content_hash(text: str) -> str:
    normalized = re.sub(r"\s+", " ", text).strip().casefold()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def extract_doc_numbers(text: str) -> list[str]:
    seen = set()
    result = []
    for match in DOC_NUMBER_RE.finditer(text):
        value = match.group(0).upper()
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result


def extract_dates(text: str) -> list[str]:
    result = []
    for day, month, year in DATE_RE.findall(text):
        try:
            value = datetime(int(year), int(month), int(day)).date().isoformat()
        except ValueError:
            continue
        if value not in result:
            result.append(value)
    return result


def normalize_links(value: object) -> list[dict[str, str]]:
    links = []
    if not isinstance(value, list):
        return links
    for item in value:
        if not isinstance(item, dict):
            continue
        text = clean_text(item.get("text"))
        href = clean_text(item.get("href"))
        if text or href:
            links.append({"text": text, "href": href})
    return links


def split_attachment(text: str) -> tuple[str, str, str]:
    """Tách phần bắt đầu bằng heading PHỤ LỤC; không suy đoán từ câu văn thường."""
    matches = list(ATTACHMENT_RE.finditer(text))
    if not matches:
        return clean_text(FILE_ARTIFACT_RE.sub("", text)), "", ""
    first = matches[0]
    body = clean_text(text[: first.start()])
    attachment = clean_text(text[first.start() :])
    return body, attachment, clean_text(first.group(1))


def preprocess(record: dict) -> tuple[dict, dict | None]:
    cleaned = dict(record)
    for key in (
        "record_id", "topic_id", "topic_title", "subject_id", "subject_title",
        "article_id", "article_title", "chapter_title", "source_note_text",
        "related_note_text", "source_url", "scraped_at",
    ):
        cleaned[key] = clean_text(cleaned.get(key))

    raw_content = clean_text(cleaned.get("content_text"))
    article_body, attachment_text, attachment_title = split_attachment(raw_content)
    links = normalize_links(cleaned.get("source_links"))
    source_note = cleaned["source_note_text"]
    note_folded = source_note.casefold()
    doc_numbers = extract_doc_numbers(source_note)
    effective_dates = extract_dates(source_note)

    flags = []
    if len(article_body) < 80:
        flags.append("short_content")
    if len(article_body) > 10_000:
        flags.append("long_content")
    if attachment_text:
        flags.append("embedded_attachment_split")
    if FILE_ARTIFACT_RE.search(raw_content):
        flags.append("file_name_artifact_removed")
    if not doc_numbers:
        flags.append("missing_origin_document_number")
    if not links:
        flags.append("missing_source_link")
    elif any(urlparse(link["href"]).scheme not in ("http", "https") for link in links if link["href"]):
        flags.append("non_http_source_link")

    is_amended = "sửa đổi" in note_folded
    is_supplemented = "bổ sung" in note_folded
    is_partly_abolished = "bãi bỏ" in note_folded
    if is_amended or is_supplemented or is_partly_abolished:
        flags.append("modified_provision")

    cleaned.update({
        "schema_version": "phapdien_labor.article.v1",
        "content_text_raw": raw_content,
        "content_text": article_body,
        "content_hash": content_hash(article_body),
        "source_links": links,
        "origin_document_numbers": doc_numbers,
        "effective_dates": effective_dates,
        "is_amended": is_amended,
        "is_supplemented": is_supplemented,
        "is_partly_abolished": is_partly_abolished,
        "legal_status_hint": "modified" if flags and "modified_provision" in flags else "source_declares_effective",
        "qa_flags": flags,
    })

    attachment = None
    if attachment_text:
        attachment = {
            "schema_version": "phapdien_labor.attachment.v1",
            "attachment_id": f"{cleaned['record_id']}::attachment",
            "parent_record_id": cleaned["record_id"],
            "parent_article_id": cleaned["article_id"],
            "title": attachment_title or "Phụ lục",
            "content_text": attachment_text,
            "content_hash": content_hash(attachment_text),
            "source_url": cleaned["source_url"],
            "source_note_text": source_note,
            "source_revision": cleaned.get("source_revision", ""),
            "scraped_at": cleaned["scraped_at"],
        }
    return cleaned, attachment


def percentile(values: list[int], ratio: float) -> int:
    if not values:
        return 0
    return sorted(values)[int((len(values) - 1) * ratio)]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input",
        type=Path,
        default=LEGAL_DATA / "external" / "phapdien_labor" / "articles.jsonl",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=LEGAL_DATA / "external" / "phapdien_labor" / "processed",
    )
    args = parser.parse_args()

    records = []
    parse_errors = []
    for line_number, line in enumerate(args.input.read_text(encoding="utf-8").splitlines(), 1):
        try:
            records.append(json.loads(line))
        except Exception as exc:
            parse_errors.append({"line": line_number, "error": str(exc)})
    if parse_errors:
        raise RuntimeError(f"JSONL không hợp lệ: {parse_errors[:5]}")

    processed = []
    attachments = []
    for record in records:
        article, attachment = preprocess(record)
        processed.append(article)
        if attachment:
            attachments.append(attachment)

    hash_groups: dict[str, list[dict]] = defaultdict(list)
    for article in processed:
        hash_groups[article["content_hash"]].append(article)
    for group in hash_groups.values():
        canonical = min(item["record_id"] for item in group)
        for article in group:
            article["canonical_record_id"] = canonical
            article["duplicate_group_size"] = len(group)
            article["is_duplicate_content"] = len(group) > 1

    ids = Counter(article["record_id"] for article in processed)
    article_ids = Counter(article["article_id"] for article in processed)
    lengths = [len(article["content_text"]) for article in processed]
    qa_counts = Counter(flag for article in processed for flag in article["qa_flags"])
    origin_docs = Counter(
        number for article in processed for number in article["origin_document_numbers"]
    )

    report = {
        "schema_version": "phapdien_labor.qa.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "input": str(args.input),
        "records": len(processed),
        "attachments_split": len(attachments),
        "duplicate_record_ids": [key for key, count in ids.items() if count > 1],
        "reused_article_ids": {
            key: count for key, count in article_ids.items() if count > 1
        },
        "duplicate_content_groups": sum(len(group) > 1 for group in hash_groups.values()),
        "duplicate_content_records": sum(len(group) for group in hash_groups.values() if len(group) > 1),
        "qa_flags": dict(qa_counts),
        "content_length": {
            "min": min(lengths, default=0),
            "median": percentile(lengths, 0.5),
            "p90": percentile(lengths, 0.9),
            "p95": percentile(lengths, 0.95),
            "p99": percentile(lengths, 0.99),
            "max": max(lengths, default=0),
        },
        "origin_document_count": len(origin_docs),
        "top_origin_documents": origin_docs.most_common(30),
        "source_url_coverage": sum(bool(article["source_url"]) for article in processed),
        "source_note_coverage": sum(bool(article["source_note_text"]) for article in processed),
    }

    args.output_dir.mkdir(parents=True, exist_ok=True)
    outputs = {
        args.output_dir / "articles.clean.jsonl": processed,
        args.output_dir / "attachments.jsonl": attachments,
    }
    for path, rows in outputs.items():
        temporary = path.with_suffix(path.suffix + ".tmp")
        with temporary.open("w", encoding="utf-8") as handle:
            for row in rows:
                handle.write(json.dumps(row, ensure_ascii=False) + "\n")
        temporary.replace(path)
    (args.output_dir / "qa_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=True, indent=2))


if __name__ == "__main__":
    main()
