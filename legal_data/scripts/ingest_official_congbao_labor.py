"""Download and parse current labor-law documents from the official Gazette.

Only native-text Gazette PDFs are accepted. Scanned PDFs and OCR output are
rejected so that legal citations are not silently corrupted.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup


LEGAL_DATA = Path(__file__).resolve().parents[1]
BASE_DIR = LEGAL_DATA / "external" / "official_labor_2024_2026"
REGISTRY_PATH = BASE_DIR / "source_registry.merged.jsonl"
PDF_DIR = BASE_DIR / "congbao_pdf"
TEXT_DIR = BASE_DIR / "congbao_text"
OUTPUT_DIR = BASE_DIR / "processed"

SOURCE_PAGES = {
    "58/VBHN-VPQH": "https://congbao.chinhphu.vn/van-ban/van-ban-hop-nhat-so-58-vbhn-vpqh-45848.htm",
    "74/2025/QH15": "https://congbao.chinhphu.vn/van-ban/luat-so-74-2025-qh15-45562.htm",
    "157/2025/NĐ-CP": "https://congbao.chinhphu.vn/van-ban/nghi-dinh-so-157-2025-nd-cp-45230.htm",
    "158/2025/NĐ-CP": "https://congbao.chinhphu.vn/van-ban/nghi-dinh-so-158-2025-nd-cp-45240.htm",
    "159/2025/NĐ-CP": "https://congbao.chinhphu.vn/van-ban/nghi-dinh-so-159-2025-nd-cp-45253.htm",
    "176/2025/NĐ-CP": "https://congbao.chinhphu.vn/van-ban/nghi-dinh-so-176-2025-nd-cp-45409.htm",
    "274/2025/NĐ-CP": "https://congbao.chinhphu.vn/van-ban/nghi-dinh-so-274-2025-nd-cp-46418.htm",
    "318/2025/NĐ-CP": "https://congbao.chinhphu.vn/van-ban/nghi-dinh-so-318-2025-nd-cp-46804/60300.htm",
    "338/2025/NĐ-CP": "https://congbao.chinhphu.vn/van-ban/nghi-dinh-so-338-2025-nd-cp-467951.htm",
    "352/2025/NĐ-CP": "https://congbao.chinhphu.vn/van-ban/nghi-dinh-so-352-2025-nd-cp-468351.htm",
    "374/2025/NĐ-CP": "https://congbao.chinhphu.vn/van-ban/nghi-dinh-so-374-2025-nd-cp-468724.htm",
}

ARTICLE_RE = re.compile(r"(?m)^\s*Điều\s+(\d+[a-zđ]?)\.\s*([^\n]*)", re.IGNORECASE)
HIERARCHY_RE = re.compile(r"^\s*(Chương|Mục|Phần)\s+([IVXLCDM\d]+)\b(?:\s*[-–.]\s*)?(.*)$", re.IGNORECASE)
STRUCTURAL_RE = re.compile(
    r"^(?:\d+[a-zđ]?\.\s+|[a-zđ]\)\s+|[IVXLCDM]+\.\s+|Chương\s+|Mục\s+|Phần\s+)",
    re.IGNORECASE,
)
PAGE_NO_RE = re.compile(r"^\s*\d{1,4}\s*$")
GAZETTE_HEADER_RE = re.compile(r"CÔNG BÁO/Số|Ngày\s+\d{1,2}-\d{1,2}-\d{4}", re.IGNORECASE)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_text(text: str) -> str:
    normalized = re.sub(r"\s+", " ", text).strip().casefold()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def safe_stem(document_number: str) -> str:
    return re.sub(r"[^0-9A-Za-z]+", "-", document_number).strip("-")


def load_registry() -> dict[str, dict]:
    records = {}
    for line in REGISTRY_PATH.read_text(encoding="utf-8").splitlines():
        if line.strip():
            record = json.loads(line)
            records[record["document_number"]] = record
    return records


def find_pdf_url(session: requests.Session, page_url: str) -> str:
    response = session.get(page_url, timeout=60)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    candidates = []
    for anchor in soup.find_all("a", href=True):
        label = anchor.get_text(" ", strip=True).lower()
        href = urljoin(page_url, anchor["href"])
        if label.endswith(".pdf") or "file_name=" in href.lower() and ".pdf" in href.lower():
            candidates.append(href)
    if not candidates:
        raise RuntimeError(f"No Gazette PDF link found: {page_url}")
    return candidates[0]


def download_pdf(session: requests.Session, document_number: str, page_url: str) -> tuple[Path, str, str]:
    pdf_url = find_pdf_url(session, page_url)
    response = session.get(pdf_url, timeout=120)
    response.raise_for_status()
    data = response.content
    if not data.startswith(b"%PDF"):
        raise RuntimeError(f"Downloaded content is not PDF: {document_number} ({pdf_url})")
    PDF_DIR.mkdir(parents=True, exist_ok=True)
    path = PDF_DIR / f"{safe_stem(document_number)}.pdf"
    path.write_bytes(data)
    return path, pdf_url, sha256_bytes(data)


def pdf_to_text(pdf_path: Path) -> tuple[Path, str]:
    executable = shutil.which("pdftotext")
    if not executable:
        raise RuntimeError("pdftotext is required")
    TEXT_DIR.mkdir(parents=True, exist_ok=True)
    text_path = TEXT_DIR / f"{pdf_path.stem}.txt"
    subprocess.run(
        [executable, "-layout", "-enc", "UTF-8", str(pdf_path), str(text_path)],
        check=True,
        capture_output=True,
    )
    text = text_path.read_text(encoding="utf-8", errors="strict")
    if len(text.strip()) < 1_000 or not ARTICLE_RE.search(text):
        raise RuntimeError(f"Native text QA failed (OCR is not allowed): {pdf_path.name}")
    return text_path, text


def remove_page_noise(text: str) -> str:
    cleaned = []
    for raw_line in text.replace("\r", "").replace("\f", "\n").splitlines():
        line = raw_line.rstrip()
        stripped = line.strip()
        if not stripped:
            cleaned.append("")
            continue
        if PAGE_NO_RE.fullmatch(stripped) or GAZETTE_HEADER_RE.search(stripped):
            continue
        if stripped in {"VĂN BẢN QUY PHẠM PHÁP LUẬT", "CHÍNH PHỦ", "QUỐC HỘI"}:
            continue
        cleaned.append(line)
    return "\n".join(cleaned)


def normalize_body(text: str) -> str:
    lines = [re.sub(r"\s+", " ", line).strip() for line in text.splitlines()]
    output: list[str] = []
    for line in lines:
        if not line:
            continue
        if STRUCTURAL_RE.match(line):
            output.append(line)
        elif output:
            output[-1] = output[-1].rstrip() + " " + line
        else:
            output.append(line)
    return "\n".join(output).strip()


def hierarchy_before(text: str, position: int) -> str:
    current = ""
    for line in text[:position].splitlines():
        match = HIERARCHY_RE.match(line)
        if match:
            current = re.sub(r"\s+", " ", line).strip()
    return current


def parse_articles(text: str, metadata: dict, page_url: str, pdf_url: str, pdf_hash: str) -> list[dict]:
    cleaned = remove_page_noise(text)
    matches = list(ARTICLE_RE.finditer(cleaned))
    records = []
    scraped_at = datetime.now(timezone.utc).isoformat()
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(cleaned)
        number = match.group(1)
        heading = re.sub(r"\s+", " ", match.group(2)).strip()
        body = normalize_body(cleaned[match.end() : end])
        if not body:
            continue
        article_id = f"Điều {number}"
        article_title = f"{article_id}. {heading}".strip()
        key = f"{metadata['document_number']}::{article_id}"
        record_id = hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]
        records.append(
            {
                "source_type": "official_gazette",
                "source_dataset": "congbao.chinhphu.vn",
                "source_revision": pdf_hash,
                "record_id": record_id,
                "topic_id": "official-labor-current",
                "topic_number": 20,
                "topic_title": "Lao động",
                "subject_id": metadata.get("scope", "labor"),
                "subject_number": 0,
                "subject_title": metadata["title"],
                "article_id": article_id,
                "article_title": article_title,
                "chapter_title": hierarchy_before(cleaned, match.start()),
                "source_note_text": f"({article_id} văn bản số {metadata['document_number']})",
                "source_links": [{"text": metadata["document_number"], "href": page_url}],
                "related_note_text": "",
                "content_text": body,
                "content_hash": sha256_text(body),
                "source_url": page_url,
                "source_pdf_url": pdf_url,
                "scraped_at": scraped_at,
                "schema_version": "official_labor.article.v1",
                "content_text_raw": body,
                "origin_document_numbers": [metadata["document_number"]],
                "effective_dates": [
                    value
                    for value in (metadata.get("issued_date"), metadata.get("effective_from"))
                    if value
                ],
                "is_amended": metadata["document_type"] == "van_ban_hop_nhat",
                "is_supplemented": metadata["document_type"] == "van_ban_hop_nhat",
                "is_partly_abolished": False,
                "legal_status_hint": metadata["status"],
                "qa_flags": [],
                "canonical_record_id": record_id,
                "duplicate_group_size": 1,
                "is_duplicate_content": False,
                "removed_attachment_filenames": [],
                "document_type": metadata["document_type"],
                "source_priority": metadata["source_priority"],
            }
        )
    return records


def article_qa(document_number: str, records: list[dict]) -> dict:
    numbers = [record["article_id"].removeprefix("Điều ") for record in records]
    numeric = [int(value) for value in numbers if value.isdigit()]
    duplicates = [number for number, count in Counter(numbers).items() if count > 1]
    missing = []
    if numeric:
        present = set(numeric)
        missing = [number for number in range(min(numeric), max(numeric) + 1) if number not in present]
    return {
        "document_number": document_number,
        "article_count": len(records),
        "first_article": numbers[0] if numbers else None,
        "last_article": numbers[-1] if numbers else None,
        "duplicate_article_numbers": duplicates,
        "missing_numeric_articles": missing,
        "empty_articles": sum(not record["content_text"].strip() for record in records),
        "qa_passed": bool(records) and not duplicates and not missing,
    }


def main() -> int:
    registry = load_registry()
    session = requests.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0 (compatible; LaborLawRAG/1.0)"})
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    all_records: list[dict] = []
    documents_report = []
    for document_number, page_url in SOURCE_PAGES.items():
        metadata = registry.get(document_number)
        if not metadata:
            raise RuntimeError(f"Missing registry record: {document_number}")
        pdf_path, pdf_url, pdf_hash = download_pdf(session, document_number, page_url)
        text_path, text = pdf_to_text(pdf_path)
        records = parse_articles(text, metadata, page_url, pdf_url, pdf_hash)
        qa = article_qa(document_number, records)
        qa.update(
            {
                "page_url": page_url,
                "pdf_url": pdf_url,
                "pdf_path": str(pdf_path),
                "text_path": str(text_path),
                "pdf_sha256": pdf_hash,
                "text_chars": len(text),
            }
        )
        documents_report.append(qa)
        all_records.extend(records)
        print(f"{document_number}: {len(records)} articles; QA={qa['qa_passed']}")

    output_path = OUTPUT_DIR / "articles.official.jsonl"
    temp_path = output_path.with_suffix(".jsonl.tmp")
    with temp_path.open("w", encoding="utf-8", newline="\n") as handle:
        for record in all_records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    temp_path.replace(output_path)

    record_ids = [record["record_id"] for record in all_records]
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": "Công báo điện tử nước CHXHCN Việt Nam",
        "document_count": len(documents_report),
        "article_count": len(all_records),
        "unique_record_ids": len(record_ids) == len(set(record_ids)),
        "all_documents_qa_passed": all(item["qa_passed"] for item in documents_report),
        "documents": documents_report,
        "production_rule": "OCR output is excluded",
    }
    (OUTPUT_DIR / "official_qa_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=True, indent=2))
    return 0 if report["all_documents_qa_passed"] and report["unique_record_ids"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
