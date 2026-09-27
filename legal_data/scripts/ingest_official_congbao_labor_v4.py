"""Production Gazette ingestion: TLS fallback, issue boundary, clean legal tail."""

from __future__ import annotations

import re

import ingest_official_congbao_labor_v3 as v3


ingest = v3.ingest
_parse_single_document = ingest.parse_articles
TAIL_RE = re.compile(
    r"\s+(?:TM\.\s+CHÍNH PHỦ|KT\.\s+THỦ TƯỚNG|Phụ\s+lục\b|Nơi\s+nhận:).*$",
    re.IGNORECASE | re.DOTALL,
)


def _parse_and_clean_tail(text, metadata, page_url, pdf_url, pdf_hash):
    records = _parse_single_document(text, metadata, page_url, pdf_url, pdf_hash)
    for record in records:
        cleaned = TAIL_RE.sub("", record["content_text"]).rstrip()
        if cleaned != record["content_text"]:
            record["content_text"] = cleaned
            record["content_text_raw"] = cleaned
            record["content_hash"] = ingest.sha256_text(cleaned)
            record["qa_flags"].append("publication_tail_removed")
    return records


ingest.parse_articles = _parse_and_clean_tail


if __name__ == "__main__":
    raise SystemExit(ingest.main())
