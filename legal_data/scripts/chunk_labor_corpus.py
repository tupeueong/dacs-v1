"""Chunk token-aware, structure-aware cho dữ liệu Pháp điển lao động đã làm sạch."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path

from transformers import AutoTokenizer


LEGAL_DATA = Path(__file__).resolve().parent.parent
MODEL_NAME = "truro7/vn-law-embedding"
CLAUSE_RE = re.compile(r"(?m)^\s*(\d+[a-zđ]?)\.\s+")
POINT_RE = re.compile(r"(?m)^\s*([a-zđ])\)\s+", re.IGNORECASE)
SENTENCE_RE = re.compile(r"(?<=[.;!?])\s+(?=[A-ZÀ-ỸĐ0-9])")


@dataclass
class Segment:
    body: str
    level: str
    labels: str = ""
    parent_context: str = ""


def compact_space(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def hash_text(text: str) -> str:
    return hashlib.sha256(compact_space(text).casefold().encode("utf-8")).hexdigest()


class LegalChunker:
    def __init__(self, model_name: str, target_tokens: int, hard_max_tokens: int):
        if target_tokens >= hard_max_tokens:
            raise ValueError("target_tokens phải nhỏ hơn hard_max_tokens")
        self.tokenizer = AutoTokenizer.from_pretrained(model_name)
        self.model_name = model_name
        self.target_tokens = target_tokens
        self.hard_max_tokens = hard_max_tokens

    @lru_cache(maxsize=50_000)
    def token_count(self, text: str) -> int:
        return len(self.tokenizer(text, add_special_tokens=True, truncation=False)["input_ids"])

    def truncate_exact(self, text: str, max_tokens: int) -> str:
        if self.token_count(text) <= max_tokens:
            return text
        encoded = self.tokenizer(
            text,
            add_special_tokens=False,
            truncation=False,
            return_offsets_mapping=True,
        )
        offsets = encoded["offset_mapping"]
        if len(offsets) <= max_tokens:
            return text
        end = offsets[max_tokens - 1][1]
        return text[:end].rstrip()

    def origin_reference(self, article: dict) -> str:
        note = article.get("source_note_text", "").strip(" ()")
        return compact_space(note.split(",", 1)[0])

    def base_context(self, article: dict) -> str:
        changes = []
        if article.get("is_amended"):
            changes.append("có sửa đổi")
        if article.get("is_supplemented"):
            changes.append("có bổ sung")
        if article.get("is_partly_abolished"):
            changes.append("có nội dung bị bãi bỏ")
        lines = [
            f"Pháp điển: {article['article_title']}",
            f"Nguồn gốc: {self.origin_reference(article)}",
            "Văn bản liên quan: " + ", ".join(article.get("origin_document_numbers", [])),
            f"Chủ đề/Đề mục: {article['topic_title']} / {article['subject_title']}",
        ]
        if changes:
            lines.append("Tình trạng ghi nhận tại nguồn: " + ", ".join(changes))
        if article.get("chapter_title"):
            lines.append("Chương/Mục: " + compact_space(article["chapter_title"]))
        # Context có thứ tự ưu tiên; cắt phần cuối (thường là hierarchy dài) nếu cần.
        return self.truncate_exact("\n".join(lines), 160)

    def embed_text(self, base_context: str, body: str, parent_context: str = "") -> str:
        pieces = [base_context]
        if parent_context:
            pieces.append(self.truncate_exact("Khoản cha: " + compact_space(parent_context), 80))
        pieces.extend(["Nội dung:", body.strip()])
        return "\n".join(pieces)

    def fits(self, base_context: str, body: str, parent_context: str, limit: int) -> bool:
        return self.token_count(self.embed_text(base_context, body, parent_context)) <= limit

    @staticmethod
    def split_by_pattern(text: str, pattern: re.Pattern) -> tuple[str, list[tuple[str, str]]]:
        matches = list(pattern.finditer(text))
        if not matches:
            return text.strip(), []
        prefix = text[: matches[0].start()].strip()
        units = []
        for index, match in enumerate(matches):
            end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
            units.append((match.group(1), text[match.start() : end].strip()))
        return prefix, units

    def hard_split(self, base_context: str, text: str, parent_context: str, level: str, labels: str) -> list[Segment]:
        prefix_tokens = self.token_count(self.embed_text(base_context, "", parent_context))
        budget = max(48, self.hard_max_tokens - prefix_tokens - 2)
        encoded = self.tokenizer(
            text,
            add_special_tokens=False,
            truncation=False,
            return_offsets_mapping=True,
        )
        offsets = encoded["offset_mapping"]
        if not offsets:
            return []
        result = []
        start_token = 0
        while start_token < len(offsets):
            end_token = min(start_token + budget, len(offsets))
            if end_token < len(offsets):
                # Lùi tối đa 24 token để ưu tiên biên khoảng trắng/dấu câu.
                for candidate in range(end_token, max(start_token + 1, end_token - 24), -1):
                    char_pos = offsets[candidate - 1][1]
                    if char_pos >= len(text) or text[char_pos : char_pos + 1].isspace() \
                            or text[max(0, char_pos - 1) : char_pos] in ".;:!?":
                        end_token = candidate
                        break
            start_char = offsets[start_token][0]
            end_char = offsets[end_token - 1][1]
            piece = text[start_char:end_char].strip()
            if piece:
                result.append(Segment(piece, level, labels, parent_context))
            start_token = end_token
        return result

    def split_sentences(self, base_context: str, text: str, parent_context: str, level: str, labels: str) -> list[Segment]:
        sentences = [part.strip() for part in SENTENCE_RE.split(text) if part.strip()]
        if len(sentences) <= 1:
            return self.hard_split(base_context, text, parent_context, level, labels)
        result = []
        current = ""
        for sentence in sentences:
            candidate = sentence if not current else current + " " + sentence
            if current and not self.fits(base_context, candidate, parent_context, self.target_tokens):
                result.append(Segment(current, level, labels, parent_context))
                current = ""
            if not self.fits(base_context, sentence, parent_context, self.hard_max_tokens):
                result.extend(self.hard_split(base_context, sentence, parent_context, level, labels))
            else:
                current = sentence if not current else current + " " + sentence
        if current:
            result.append(Segment(current, level, labels, parent_context))
        return result

    def split_clause(self, base_context: str, label: str, clause: str) -> list[Segment]:
        if self.fits(base_context, clause, "", self.target_tokens):
            return [Segment(clause, "clause", label)]
        intro, points = self.split_by_pattern(clause, POINT_RE)
        if not points:
            return self.split_sentences(base_context, clause, intro[:400], "clause_part", label)
        parent_context = intro
        result = []
        for point_label, point_text in points:
            combined_label = f"{label}.{point_label}"
            if self.fits(base_context, point_text, parent_context, self.target_tokens):
                result.append(Segment(point_text, "point", combined_label, parent_context))
            else:
                result.extend(
                    self.split_sentences(
                        base_context, point_text, parent_context, "point_part", combined_label
                    )
                )
        return result

    def pack_adjacent(self, base_context: str, segments: list[Segment]) -> list[Segment]:
        """Gom các đơn vị cấu trúc ngắn liền nhau nhưng không vượt target."""
        packed = []
        current: Segment | None = None
        for segment in segments:
            if current is None:
                current = segment
                continue
            same_parent = current.parent_context == segment.parent_context
            combined = current.body + "\n" + segment.body
            if same_parent and self.fits(base_context, combined, current.parent_context, self.target_tokens):
                current = Segment(
                    combined,
                    current.level if current.level == segment.level else "structural_group",
                    ",".join(filter(None, (current.labels, segment.labels))),
                    current.parent_context,
                )
            else:
                packed.append(current)
                current = segment
        if current is not None:
            packed.append(current)
        return packed

    def segment_article(self, article: dict) -> tuple[str, list[Segment]]:
        context = self.base_context(article)
        body = article["content_text"].strip()
        if self.fits(context, body, "", self.target_tokens):
            return context, [Segment(body, "article")]

        preamble, clauses = self.split_by_pattern(body, CLAUSE_RE)
        if not clauses:
            return context, self.split_sentences(context, body, "", "article_part", "")

        segments = []
        if preamble:
            if self.fits(context, preamble, "", self.target_tokens):
                segments.append(Segment(preamble, "preamble"))
            else:
                segments.extend(self.split_sentences(context, preamble, "", "preamble_part", ""))
        for label, clause in clauses:
            segments.extend(self.split_clause(context, label, clause))
        return context, self.pack_adjacent(context, segments)

    def chunk_article(self, article: dict) -> list[dict]:
        context, segments = self.segment_article(article)
        chunks = []
        origin_numbers = article.get("origin_document_numbers", [])
        effective_dates = article.get("effective_dates", [])
        for sequence, segment in enumerate(segments, 1):
            embed_text = self.embed_text(context, segment.body, segment.parent_context)
            token_count = self.token_count(embed_text)
            if token_count > self.hard_max_tokens:
                raise RuntimeError(
                    f"Chunk vượt {self.hard_max_tokens} token: {article['record_id']} #{sequence} = {token_count}"
                )
            display_parts = [article["article_title"]]
            if segment.parent_context:
                display_parts.append("Khoản cha: " + compact_space(segment.parent_context))
            display_parts.append(segment.body)
            text = "\n".join(display_parts)
            chunks.append({
                "chunk_id": f"phapdien__{article['record_id']}__{sequence}",
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
                "duplicate_group_size": article["duplicate_group_size"],
                "chunk_type": "codified_article",
                "source_type": "phapdien",
                "source_dataset": article["source_dataset"],
                "source_revision": article["source_revision"],
                "source_id": article["record_id"],
                "source_url": article["source_url"],
                "scraped_at": article["scraped_at"],
                "source_note_text": article["source_note_text"],
                "related_note_text": article["related_note_text"],
                "origin_reference": self.origin_reference(article),
                "origin_document_numbers": ",".join(origin_numbers),
                "effective_dates": ",".join(effective_dates),
                "is_amended": bool(article["is_amended"]),
                "is_supplemented": bool(article["is_supplemented"]),
                "is_partly_abolished": bool(article["is_partly_abolished"]),
                "doc_number": origin_numbers[0] if origin_numbers else article["article_id"],
                "doc_type": "phapdien",
                "doc_title": article["subject_title"],
                "status": article["legal_status_hint"],
                "article_number": article["article_id"],
                "article_title": article["article_title"],
                "hierarchy_path": " > ".join(
                    item for item in (
                        article["topic_title"], article["subject_title"], article["chapter_title"]
                    ) if item
                ),
                "topic_id": article["topic_id"],
                "topic_number": article["topic_number"],
                "topic_title": article["topic_title"],
                "subject_id": article["subject_id"],
                "subject_number": article["subject_number"],
                "subject_title": article["subject_title"],
                "embedding_model": self.model_name,
            })
        return chunks


def percentile(values: list[int], ratio: float) -> int:
    return sorted(values)[int((len(values) - 1) * ratio)] if values else 0

def safe_prefix(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.casefold()).strip("_") or "source"


class UnifiedLegalChunker(LegalChunker):
    def __init__(
        self,
        model_name: str,
        target_tokens: int,
        hard_max_tokens: int,
        corpus_as_of: str,
    ):
        super().__init__(model_name, target_tokens, hard_max_tokens)
        self.corpus_as_of = corpus_as_of

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
                    "corpus_as_of": self.corpus_as_of,
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
    policy_path = LEGAL_DATA / "rag_corpus" / "corpus_policy.json"
    policy = json.loads(policy_path.read_text(encoding="utf-8"))
    corpus_as_of = str(policy["as_of_date"])
    chunker = UnifiedLegalChunker(
        args.model, args.target_tokens, args.hard_max_tokens, corpus_as_of
    )
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
        "schema_version": "unified_labor.chunks.v2",
        "corpus_as_of": corpus_as_of,
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
