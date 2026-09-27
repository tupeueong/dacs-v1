"""Gazette ingestion entry point with TLS and multi-document issue handling."""

from __future__ import annotations

from urllib.parse import urlparse

import requests
import urllib3

import ingest_official_congbao_labor as ingest


_original_get = requests.Session.get
_original_parse_articles = ingest.parse_articles


def _get_with_official_cdn_fallback(self, url, **kwargs):
    try:
        return _original_get(self, url, **kwargs)
    except requests.exceptions.SSLError:
        if urlparse(str(url)).hostname != "g7.cdnchinhphu.vn":
            raise
        fallback_kwargs = dict(kwargs)
        fallback_kwargs["verify"] = False
        return _original_get(self, url, **fallback_kwargs)


def _truncate_at_next_document(text: str) -> str:
    """Stop when a Gazette issue starts a second document at Điều 1."""
    largest_numeric = 0
    for match in ingest.ARTICLE_RE.finditer(text):
        label = match.group(1).lower()
        if label.isdigit():
            number = int(label)
            if number == 1 and largest_numeric >= 5:
                return text[: match.start()]
            largest_numeric = max(largest_numeric, number)
    return text


def _parse_single_document(text, metadata, page_url, pdf_url, pdf_hash):
    return _original_parse_articles(
        _truncate_at_next_document(text), metadata, page_url, pdf_url, pdf_hash
    )


requests.Session.get = _get_with_official_cdn_fallback
ingest.parse_articles = _parse_single_document
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


if __name__ == "__main__":
    raise SystemExit(ingest.main())
