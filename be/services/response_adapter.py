"""Map GroundedGenerator output to the frontend JSON contract.

Frontend contract (fe/src/api.js, POST /api/chat response):
{
    "answer": str,  # formatted legal answer (markdown)
    "sources": [     # list of cited legal provisions
        {
            "doc_title": str,   # e.g. "Bộ luật Lao động 2019 (Luật số 45/2019/QH14)"
            "article": str,     # e.g. "Điều 25"
            "clause": str,      # e.g. "Khoản 1, 2"
            "text": str,        # relevant excerpt text
        }
    ]
}

GroundedGenerator.answer() output keys (success):
    answerable, answer, claims, conflicts, sources, formatted_answer,
    citation_verified, citation_errors, retrieval, conflict_analysis

GroundedGenerator.answer() output keys (failure via _failure()):
    answerable=False, answer (error message), formatted_answer (same),
    error_code, sources=[], ...
"""

from __future__ import annotations

from typing import Any


def adapt_rag_response(raw: dict[str, Any]) -> dict[str, Any]:
    """Convert GroundedGenerator.answer() dict → frontend-compatible dict.

    Always returns ``{"answer": str, "sources": list[dict]}`` regardless of
    whether the RAG pipeline succeeded or failed.
    """
    # --- answer text ---
    # Prefer the human-readable formatted_answer (markdown with headings,
    # references, conflict analysis), falling back to the raw LLM answer field.
    answer_text: str = (
        raw.get("formatted_answer")
        or raw.get("answer")
        or "Không nhận được nội dung trả lời từ hệ thống."
    )

    # --- sources ---
    # GroundedGenerator sources are richer dicts with reference, doc_number,
    # doc_title, article_number, article_title, source_url, status, etc.
    # Frontend expects: { doc_title, article, clause, text }.
    raw_sources = raw.get("sources") or []
    fe_sources: list[dict[str, str]] = []

    for src in raw_sources:
        fe_sources.append(
            {
                "doc_title": _source_doc_title(src),
                "article": src.get("article_title") or src.get("article_number") or "",
                "clause": _extract_clause(src),
                "text": _source_excerpt(src),
            }
        )

    return {
        "answer": answer_text,
        "sources": fe_sources,
    }


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _source_doc_title(src: dict) -> str:
    """Build a human-friendly document title from RAG source metadata.

    Combines doc_title (full name) with doc_number (e.g. "45/2019/QH14") to
    produce strings like "Bộ luật Lao động 2019 (Luật số 45/2019/QH14)".
    """
    doc_title = (src.get("doc_title") or "").strip()
    doc_number = (src.get("doc_number") or "").strip()

    if doc_title and doc_number and doc_number not in doc_title:
        return f"{doc_title} ({doc_number})"
    return doc_title or doc_number or "Văn bản pháp luật"


def _extract_clause(src: dict) -> str:
    """Best-effort clause extraction from RAG source metadata.

    The RAG pipeline stores article_number / article_title but doesn't always
    have a dedicated clause field.  We attempt to parse clause info from the
    article_title string (e.g. "Điều 25, Khoản 1").
    """
    # If there is an explicit clause field, use it directly.
    clause = (src.get("clause") or "").strip()
    if clause:
        return clause

    article_title = (src.get("article_title") or "").strip()
    # Try to extract "Khoản ..." from article_title
    if "khoản" in article_title.lower():
        import re
        match = re.search(r"(khoản\s+[\d,\s]+)", article_title, re.IGNORECASE)
        if match:
            return match.group(1).strip()

    # Fall back to the article_number itself (e.g. "Điều 25")
    return src.get("article_number") or article_title


def _source_excerpt(src: dict) -> str:
    """Build a concise text excerpt for the frontend source card.

    The RAG sources don't carry the raw chunk text at the top level, so we
    synthesize a descriptive line from available metadata: article, document,
    authority tier, status, and effective dates.
    """
    parts: list[str] = []

    article = src.get("article_title") or src.get("article_number") or ""
    doc = src.get("doc_number") or src.get("doc_title") or ""
    if article and doc:
        parts.append(f"{article} — {doc}")
    elif article or doc:
        parts.append(article or doc)

    tier = src.get("authority_tier") or ""
    if tier:
        parts.append(f"Cấp văn bản: {tier}")

    status = src.get("status") or ""
    if status:
        parts.append(f"Trạng thái: {status}")

    effective = src.get("effective_dates") or ""
    if effective:
        parts.append(f"Hiệu lực: {effective}")

    url = src.get("source_url") or ""
    if url:
        parts.append(f"Nguồn: {url}")

    return ". ".join(parts) if parts else "Xem chi tiết trong văn bản gốc."
