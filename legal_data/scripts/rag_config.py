"""Cấu hình tập trung cho pipeline và runtime RAG luật lao động."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
LEGAL_DATA = ROOT / "legal_data"


def _env_path(name: str, default: Path) -> Path:
    value = os.getenv(name)
    path = Path(value) if value else default
    return path if path.is_absolute() else ROOT / path


@dataclass(frozen=True)
class RagSettings:
    root: Path = ROOT
    legal_data: Path = LEGAL_DATA
    articles_path: Path = LEGAL_DATA / "rag_corpus" / "articles.jsonl"
    chunks_path: Path = LEGAL_DATA / "rag_corpus" / "chunks.jsonl"
    index_root: Path = _env_path(
        "LEGAL_RAG_INDEX_ROOT", LEGAL_DATA / "vectorstore_versions"
    )
    current_pointer: Path = _env_path(
        "LEGAL_RAG_CURRENT_POINTER", LEGAL_DATA / "vectorstore_versions" / "current.json"
    )
    legacy_unified_index: Path = LEGAL_DATA / "vectorstore_labor_unified"
    embed_model: str = os.getenv("LEGAL_RAG_EMBED_MODEL", "truro7/vn-law-embedding")
    rerank_model: str = os.getenv("LEGAL_RAG_RERANK_MODEL", "BAAI/bge-reranker-v2-m3")
    min_rerank_score: float = float(os.getenv("LEGAL_RAG_MIN_RERANK_SCORE", "0.05"))
    max_context_tokens: int = int(os.getenv("LEGAL_RAG_MAX_CONTEXT_TOKENS", "12000"))
    collection_name: str = "legal_chunks"


SETTINGS = RagSettings()

