"""
retrieve.py - Truy vấn hybrid: vector (Chroma) + BM25, gộp điểm bằng Reciprocal Rank Fusion,
rồi rerank top ứng viên bằng cross-encoder cho chính xác hơn.

Cài đặt thêm: pip install sentence-transformers (đã có nếu chạy build_index.py)

    from retrieve import Retriever
    r = Retriever("legal_data/vectorstore")
    ket_qua = r.retrieve("mức phạt khi không ký hợp đồng lao động bằng văn bản", top_k=5,
                          filters={"status": "con_hieu_luc"})
"""
import pickle
import re
from pathlib import Path

import chromadb
from sentence_transformers import CrossEncoder, SentenceTransformer

from build_index import EMBED_MODEL, simple_tokenize

RERANK_MODEL = "BAAI/bge-reranker-v2-m3"   # cross-encoder đa ngôn ngữ, có tiếng Việt


class Retriever:
    def __init__(self, index_dir: str, embed_model: str = EMBED_MODEL,
                 rerank_model: str = RERANK_MODEL, k_candidates: int = 30):
        index_dir = Path(index_dir)
        self.embed_model = SentenceTransformer(embed_model)
        self.reranker = CrossEncoder(rerank_model)
        self.k_candidates = k_candidates  # số ứng viên lấy từ mỗi nhánh trước khi rerank

        self.client = chromadb.PersistentClient(path=str(index_dir / "chroma"))
        self.coll = self.client.get_collection("legal_chunks")

        with open(index_dir / "bm25.pkl", "rb") as f:
            d = pickle.load(f)
        self.bm25, self.chunk_ids, self.by_id = d["bm25"], d["chunk_ids"], d["chunks_by_id"]

    # ---------------------------------------------------------------- nhánh vector
    def _vector_search(self, query: str, k: int, where: dict | None):
        emb = self.embed_model.encode([query], normalize_embeddings=True).tolist()
        res = self.coll.query(query_embeddings=emb, n_results=k, where=where or None)
        return list(res["ids"][0])  # đã sắp theo độ liên quan giảm dần

    def debug_similarity(self, query: str, k: int = 5):
        """In ra cosine similarity thật của từng chunk, để soi độ tương đồng thay vì chỉ thấy thứ hạng.
        Chroma trả về 'distances' (khoảng cách), với không gian cosine thì similarity = 1 - distance."""
        emb = self.embed_model.encode([query], normalize_embeddings=True).tolist()
        res = self.coll.query(query_embeddings=emb, n_results=k, include=["distances", "documents"])
        for cid, dist, doc in zip(res["ids"][0], res["distances"][0], res["documents"][0]):
            sim = 1 - dist
            print(f"  cosine similarity = {sim:.4f}   [{cid}]  {doc[:60]}...")

    # ---------------------------------------------------------------- nhánh BM25
    def _bm25_search(self, query: str, k: int, where: dict | None):
        scores = self.bm25.get_scores(simple_tokenize(query))
        ranked = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)
        out = []
        for i in ranked:
            cid = self.chunk_ids[i]
            if where and not all(self.by_id[cid].get(k) == v for k, v in where.items()):
                continue
            out.append(cid)
            if len(out) >= k:
                break
        return out

    # ---------------------------------------------------------------- gộp bằng Reciprocal Rank Fusion
    @staticmethod
    def _rrf_fuse(*ranked_lists, k: int = 60) -> list[str]:
        """RRF: mỗi id được cộng điểm 1/(k + hạng), cộng dồn qua các danh sách rồi sắp lại.
        Không cần chuẩn hoá điểm số giữa vector và BM25 (2 thang đo khác nhau)."""
        scores: dict[str, float] = {}
        for lst in ranked_lists:
            for rank, cid in enumerate(lst):
                scores[cid] = scores.get(cid, 0.0) + 1.0 / (k + rank + 1)
        return sorted(scores, key=scores.get, reverse=True)

    # ---------------------------------------------------------------- lấy trọn 1 Điều (cha), không chỉ phần đã trúng (con)
    def get_full_article(self, doc_number: str, article_number: str) -> str:
        """Điều bị chunk thành nhiều phần (part 1, 2, 3...) khi lưu index. Khi đã biết 1 phần của
        Điều nào trúng truy vấn, hàm này lấy lại TOÀN BỘ các phần của đúng Điều đó theo đúng thứ tự,
        để đưa cho LLM đọc đủ ngữ cảnh thay vì chỉ đọc phần lọt vào top-k."""
        matched = [c for c in self.by_id.values()
                   if c["doc_number"] == doc_number and c.get("article_number") == article_number]
        matched.sort(key=lambda c: c["part"])
        return "\n".join(c["text"] for c in matched)

    # ---------------------------------------------------------------- Điều nguyên tắc chung (cá nhân/tổ chức)
    def get_principle_article(self, doc_number: str) -> str | None:
        """Tìm Điều nói về nguyên tắc áp dụng mức phạt (thường có cụm 'mức phạt tiền' và
        'cá nhân' trong tiêu đề, ví dụ Điều 6 Nghị định 12/2022) - áp dụng cho MỌI Điều xử phạt
        khác trong cùng văn bản nên cần kèm theo dù câu hỏi không trực tiếp nhắc tới."""
        candidates = [c for c in self.by_id.values() if c["doc_number"] == doc_number]
        titles_seen = set()
        for c in candidates:
            t = (c.get("article_title") or "")
            if c.get("article_number") not in titles_seen and re.search(r"mức phạt tiền", t, re.I) \
                    and re.search(r"cá nhân|nguyên tắc", t, re.I):
                titles_seen.add(c["article_number"])
                return self.get_full_article(doc_number, c["article_number"])
        return None

    # ---------------------------------------------------------------- công khai
    def retrieve(self, query: str, top_k: int = 5, filters: dict | None = None) -> list[dict]:
        """filters: ví dụ {"status": "con_hieu_luc", "doc_type": "nghi_dinh"}"""
        vec_ids = self._vector_search(query, self.k_candidates, filters)
        bm25_ids = self._bm25_search(query, self.k_candidates, filters)
        fused = self._rrf_fuse(vec_ids, bm25_ids)[: self.k_candidates]

        if not fused:
            return []

        # rerank: cross-encoder chấm điểm (query, text) cho từng ứng viên, chính xác hơn
        # bước fusion ở trên nhưng chậm hơn -> chỉ chạy trên top self.k_candidates, không toàn bộ
        cands = [self.by_id[cid] for cid in fused]
        # pairs = [(query, c["text"]) for c in cands]
        pairs = [(query, c.get("embed_text", c["text"])) for c in cands]
        rerank_scores = self.reranker.predict(pairs)
        order = sorted(range(len(cands)), key=lambda i: rerank_scores[i], reverse=True)

        return [
            {**cands[i], "rerank_score": float(rerank_scores[i])}
            for i in order[:top_k]
        ]
if __name__ == "__main__":
    r = Retriever("legal_data/vectorstore")
    for hit in r.retrieve("mức phạt khi không ký hợp đồng lao động bằng văn bản", top_k=5):
        print(f"{hit['rerank_score']:.3f}  {hit['doc_title']} - {hit.get('article_title')} ({hit['chunk_id']})")
