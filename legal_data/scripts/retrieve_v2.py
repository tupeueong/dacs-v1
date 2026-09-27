"""Production-oriented hybrid retrieval with confidence rejection and evidence."""

from __future__ import annotations

import json
import pickle
from collections import defaultdict
from pathlib import Path

import chromadb
from sentence_transformers import CrossEncoder, SentenceTransformer

from build_index_v2 import vi_legal_tokenize
from rag_config import SETTINGS


CURRENT_STATUSES = {
    "current",
    "current_consolidated",
    "current_verified_2026-09-27",
    "modified",
    "source_declares_effective",
}


def resolve_current_index(pointer_path: Path = SETTINGS.current_pointer) -> Path:
    if pointer_path.exists():
        pointer = json.loads(pointer_path.read_text(encoding="utf-8"))
        index_dir = Path(pointer["index_dir"])
        if not index_dir.is_absolute():
            index_dir = SETTINGS.root / index_dir
        return index_dir
    if SETTINGS.legacy_unified_index.exists():
        return SETTINGS.legacy_unified_index
    raise FileNotFoundError(f"Missing active index pointer: {pointer_path}")


class SafeRetriever:
    def __init__(
        self,
        index_dir: Path | str | None = None,
        *,
        embed_model: str = SETTINGS.embed_model,
        rerank_model: str = SETTINGS.rerank_model,
        k_candidates: int = 20,
        min_rerank_score: float = SETTINGS.min_rerank_score,
    ) -> None:
        self.index_dir = Path(index_dir) if index_dir else resolve_current_index()
        self.embed_model = SentenceTransformer(embed_model)
        self.reranker = CrossEncoder(rerank_model)
        self.k_candidates = k_candidates
        self.min_rerank_score = min_rerank_score
        self.client = chromadb.PersistentClient(path=str(self.index_dir / "chroma"))
        self.collection = self.client.get_collection(SETTINGS.collection_name)
        with (self.index_dir / "bm25.pkl").open("rb") as handle:
            data = pickle.load(handle)
        self.bm25 = data["bm25"]
        self.chunk_ids = data["chunk_ids"]
        self.by_id = data["chunks_by_id"]
        self.by_article: dict[tuple[str, str], list[dict]] = defaultdict(list)
        for chunk in self.by_id.values():
            self.by_article[(chunk["doc_number"], chunk.get("article_number", ""))].append(chunk)
        for chunks in self.by_article.values():
            chunks.sort(key=lambda item: int(item.get("part", 0)))

    @staticmethod
    def _matches(chunk: dict, filters: dict | None) -> bool:
        if not filters:
            return True
        for key, expected in filters.items():
            actual = chunk.get(key)
            if isinstance(expected, (set, list, tuple)):
                if actual not in expected:
                    return False
            elif actual != expected:
                return False
        return True

    @staticmethod
    def _rrf(*ranked: list[str], constant: int = 60) -> list[str]:
        scores: dict[str, float] = {}
        for ids in ranked:
            for rank, chunk_id in enumerate(ids, 1):
                scores[chunk_id] = scores.get(chunk_id, 0.0) + 1.0 / (constant + rank)
        return sorted(scores, key=scores.get, reverse=True)

    def _vector_search(self, query: str, filters: dict | None) -> tuple[list[str], dict[str, float]]:
        embedding = self.embed_model.encode([query], normalize_embeddings=True).tolist()
        result = self.collection.query(
            query_embeddings=embedding,
            n_results=min(self.k_candidates * 2, self.collection.count()),
            include=["distances"],
        )
        ids, distances = [], {}
        for chunk_id, distance in zip(result["ids"][0], result["distances"][0]):
            if self._matches(self.by_id[chunk_id], filters):
                ids.append(chunk_id)
                distances[chunk_id] = float(distance)
            if len(ids) >= self.k_candidates:
                break
        return ids, distances

    def _bm25_search(self, query: str, filters: dict | None) -> tuple[list[str], dict[str, float]]:
        raw_scores = self.bm25.get_scores(vi_legal_tokenize(query))
        ranked = sorted(range(len(raw_scores)), key=lambda index: raw_scores[index], reverse=True)
        ids, scores = [], {}
        for index in ranked:
            chunk_id = self.chunk_ids[index]
            if not self._matches(self.by_id[chunk_id], filters):
                continue
            ids.append(chunk_id)
            scores[chunk_id] = float(raw_scores[index])
            if len(ids) >= self.k_candidates:
                break
        return ids, scores

    def search(
        self,
        query: str,
        *,
        top_k: int = 5,
        filters: dict | None = None,
        current_only: bool = True,
    ) -> dict:
        query = query.strip()
        if not query:
            return {"accepted": False, "reason": "empty_query", "hits": []}
        effective_filters = dict(filters or {})
        if current_only and "status" not in effective_filters:
            effective_filters["status"] = CURRENT_STATUSES

        vector_ids, distances = self._vector_search(query, effective_filters)
        bm25_ids, bm25_scores = self._bm25_search(query, effective_filters)
        fused = self._rrf(vector_ids, bm25_ids)[: self.k_candidates]
        if not fused:
            return {"accepted": False, "reason": "no_candidates", "hits": []}

        candidates = [self.by_id[chunk_id] for chunk_id in fused]
        rerank_scores = self.reranker.predict(
            [(query, chunk.get("embed_text", chunk["text"])) for chunk in candidates]
        )
        order = sorted(range(len(candidates)), key=lambda index: float(rerank_scores[index]), reverse=True)
        hits = []
        for index in order[:top_k]:
            chunk = candidates[index]
            chunk_id = chunk["chunk_id"]
            hits.append(
                {
                    **chunk,
                    "rerank_score": float(rerank_scores[index]),
                    "vector_distance": distances.get(chunk_id),
                    "bm25_score": bm25_scores.get(chunk_id, 0.0),
                }
            )

        top_score = hits[0]["rerank_score"] if hits else float("-inf")
        if top_score < self.min_rerank_score:
            return {
                "accepted": False,
                "reason": "low_retrieval_confidence",
                "threshold": self.min_rerank_score,
                "top_score": top_score,
                "hits": [],
                "diagnostic_candidates": hits,
            }
        return {
            "accepted": True,
            "reason": "accepted",
            "threshold": self.min_rerank_score,
            "top_score": top_score,
            "hits": hits,
        }

    def retrieve(self, query: str, top_k: int = 5, filters: dict | None = None) -> list[dict]:
        """Compatibility method: rejected queries return an empty list."""
        return self.search(query, top_k=top_k, filters=filters)["hits"]

    def context_chunks(self, hits: list[dict], max_tokens: int = SETTINGS.max_context_tokens) -> list[dict]:
        """Expand hit articles while enforcing a deterministic context token budget."""
        selected, seen, used = [], set(), 0
        for hit in hits:
            key = (hit["doc_number"], hit.get("article_number", ""))
            article_chunks = self.by_article.get(key, [hit])
            article_tokens = sum(int(chunk.get("embed_token_count", 0)) for chunk in article_chunks)
            candidates = article_chunks if used + article_tokens <= max_tokens else [hit]
            for chunk in candidates:
                if chunk["chunk_id"] in seen:
                    continue
                token_count = int(chunk.get("embed_token_count", 0))
                if selected and used + token_count > max_tokens:
                    continue
                selected.append(chunk)
                seen.add(chunk["chunk_id"])
                used += token_count
        return selected


if __name__ == "__main__":
    retriever = SafeRetriever()
    while True:
        question = input("Câu hỏi: ").strip()
        if not question or question.casefold() in {"thoat", "exit", "quit"}:
            break
        result = retriever.search(question)
        if not result["accepted"]:
            print(f"Từ chối: {result['reason']} (top_score={result.get('top_score')})")
            continue
        for hit in result["hits"]:
            print(
                f"{hit['rerank_score']:.4f} | {hit['doc_number']} | "
                f"{hit.get('article_title')} | {hit['chunk_id']}"
            )

