"""Structure-aware, token-aware chunking for the unified labor-law corpus."""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from chunk_phapdien_labor import LegalChunker, hash_text, percentile


LEGAL_DATA = Path(__file__).resolve().parents[1]
MODEL_NAME = "truro7/vn-law-embedding"


def safe_prefix(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.casefold()).strip("_") or "source"


class UnifiedLegalChunker(LegalChunker):
    def base_context(self, article: dict) -> str:
        origins = article.get("origin_document_numbers", [])
        document_number = origins[0] if origins else article["article_id"]
        source_label = {
            "official_gazette": "Công báo chính thức",
            "phapdien": "Pháp điển Bộ Tư pháp",
            "legacy_verified_current": "Bản địa phương đã đối chiếu CSDL VBPL",
        }.get(article.get("source_type"), article.get("source_dataset", "Nguồn pháp luật"))
        lines = [
            f"Văn bản: {document_number} - {article['subject_title']}",
            f"Điều: {article['article_title']}",
            f"Nguồn: {source_label}",
            "Mốc pháp lý: " + ", ".join(article.get("effective_dates", [])),
            f"Trạng thái: {article.get('legal_status_hint', 'current')}",
            f"Chủ đề: {article['topic_title']} / {article['subject_title']}",
        ]
        if article.get("chapter_title"):
            lines.append("Chương/Mục: " + self.truncate_exact(article["chapter_title"], 60))
        return self.truncate_exact("\n".join(lines), 160)

    def chunk_article(self, article: dict) -> list[dict]:
        context, segments = self.segment_article(article)
        origins = article.get("origin_document_numbers", [])
        effective_dates = article.get("effective_dates", [])
        source_type = article.get("source_type", "unknown")
        chunks = []
        for sequence, segment in enumerate(segments, 1):
            embed_text = self.embed_text(context, segment.body, segment.parent_context)
            token_count = self.token_count(embed_text)
            if token_count > self.hard_max_tokens:
                raise RuntimeError(
                    f"Chunk exceeds {self.hard_max_tokens}: {article['record_id']} #{sequence}={token_count}"
                )
            display_parts = [article["article_title"]]
            if segment.parent_context:
                display_parts.append("Khoản cha: " + segment.parent_context.strip())
            display_parts.append(segment.body)
            text = "\n".join(display_parts)
            chunks.append(
                {
                    "chunk_id": f"{safe_prefix(source_type)}__{article['record_id']}__{sequence}",
                    "parent_record_id": article["record_id"],
                    "part": sequence,
                    "n_parts": len(segments),
                    "structural_level": segment.level,
                    "structural_labels": segment.labels,
                    "content_text": segment.body,
                    "text": text,
                    "embed_text": embed_text,
                    "n_chars": len(text),
                    "embed_token_count": token_count,
                    "chunk_content_hash": hash_text(segment.body),
                    "article_content_hash": article["content_hash"],
                    "canonical_record_id": article["canonical_record_id"],
                    "duplicate_group_size": int(article.get("duplicate_group_size", 1)),
                    "chunk_type": "current_legal_article",
                    "source_type": source_type,
                    "source_dataset": article["source_dataset"],
                    "source_revision": article["source_revision"],
                    "source_id": article["record_id"],
                    "source_url": article["source_url"],
                    "scraped_at": article["scraped_at"],
                    "source_note_text": article.get("source_note_text", ""),
                    "related_note_text": article.get("related_note_text", ""),
                    "origin_reference": article.get("source_note_text", "").strip(" ()"),
                    "origin_document_numbers": ",".join(origins),
                    "effective_dates": ",".join(effective_dates),
                    "is_amended": bool(article.get("is_amended")),
                    "is_supplemented": bool(article.get("is_supplemented")),
                    "is_partly_abolished": bool(article.get("is_partly_abolished")),
                    "doc_number": origins[0] if origins else article["article_id"],
                    "doc_type": article.get("document_type", "phapdien"),
                    "doc_title": article["subject_title"],
                    "status": article.get("legal_status_hint", "current"),
                    "article_number": article["article_id"],
                    "article_title": article["article_title"],
                    "hierarchy_path": " > ".join(
                        item
                        for item in (
                            article["topic_title"],
                            article["subject_title"],
                            article.get("chapter_title", ""),
                        )
                        if item
                    ),
                    "topic_id": article["topic_id"],
                    "topic_number": int(article["topic_number"]),
                    "topic_title": article["topic_title"],
                    "subject_id": article["subject_id"],
                    "subject_number": int(article.get("subject_number", 0)),
                    "subject_title": article["subject_title"],
                    "source_priority": int(article.get("source_priority", 80)),
                    "corpus_as_of": "2026-09-27",
                    "embedding_model": self.model_name,
                }
            )
        return chunks


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=LEGAL_DATA / "rag_corpus" / "articles.jsonl")
    parser.add_argument("--output", type=Path, default=LEGAL_DATA / "rag_corpus" / "chunks.jsonl")
    parser.add_argument("--model", default=MODEL_NAME)
    parser.add_argument("--target-tokens", type=int, default=384)
    parser.add_argument("--hard-max-tokens", type=int, default=448)
    args = parser.parse_args()

    articles = [json.loads(line) for line in args.input.open(encoding="utf-8") if line.strip()]
    chunker = UnifiedLegalChunker(args.model, args.target_tokens, args.hard_max_tokens)
    chunks = [chunk for article in articles for chunk in chunker.chunk_article(article)]

    ids = [chunk["chunk_id"] for chunk in chunks]
    parents = Counter(chunk["parent_record_id"] for chunk in chunks)
    if len(ids) != len(set(ids)):
        raise RuntimeError("Duplicate chunk_id")
    if set(parents) != {article["record_id"] for article in articles}:
        raise RuntimeError("Not all articles are represented")
    if any(not chunk["content_text"].strip() for chunk in chunks):
        raise RuntimeError("Empty chunk")
    if any(chunk["embed_token_count"] > args.hard_max_tokens for chunk in chunks):
        raise RuntimeError("Hard token limit exceeded")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    temp_path = args.output.with_suffix(".jsonl.tmp")
    with temp_path.open("w", encoding="utf-8", newline="\n") as handle:
        for chunk in chunks:
            handle.write(json.dumps(chunk, ensure_ascii=False) + "\n")
    temp_path.replace(args.output)

    lengths = [chunk["embed_token_count"] for chunk in chunks]
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "schema_version": "unified_labor.chunks.v1",
        "article_count": len(articles),
        "chunk_count": len(chunks),
        "source_type_counts": dict(Counter(chunk["source_type"] for chunk in chunks)),
        "articles_split": sum(count > 1 for count in parents.values()),
        "max_parts_per_article": max(parents.values()),
        "structural_levels": dict(Counter(chunk["structural_level"] for chunk in chunks)),
        "token_length": {
            "min": min(lengths),
            "median": percentile(lengths, 0.5),
            "p90": percentile(lengths, 0.9),
            "p95": percentile(lengths, 0.95),
            "p99": percentile(lengths, 0.99),
            "max": max(lengths),
            "over_target": sum(value > args.target_tokens for value in lengths),
            "over_hard_max": sum(value > args.hard_max_tokens for value in lengths),
        },
        "validation": {
            "unique_chunk_ids": True,
            "all_articles_covered": True,
            "no_empty_chunks": True,
            "all_chunks_have_source_url": all(bool(chunk["source_url"]) for chunk in chunks),
            "ocr_chunks": sum(chunk["source_type"] == "ocr" for chunk in chunks),
        },
        "forms_and_attachments_indexed": False,
    }
    (args.output.parent / "chunks_qa_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
