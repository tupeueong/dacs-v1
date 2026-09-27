"""
build_index.py - Đọc chunks.jsonl, tạo 2 index:
  1. Vector index (Chroma) từ embed_text, dùng model đa ngôn ngữ / luật Việt Nam.
  2. BM25 index (từ khóa) từ text, lưu ra pickle để retrieve.py dùng chung.

Cài đặt:
    pip install chromadb sentence-transformers rank_bm25

Chạy:
    python build_index.py --chunks legal_data/chunks/chunks.jsonl --out legal_data/vectorstore
"""
import argparse
import json
import pickle
from pathlib import Path

import chromadb
from rank_bm25 import BM25Okapi
from sentence_transformers import SentenceTransformer

# Có thể đổi sang "truro7/vn-law-embedding" (chuyên luật VN) hoặc "BAAI/bge-m3" (đa ngôn ngữ)
EMBED_MODEL = "truro7/vn-law-embedding"


def simple_tokenize(text: str) -> list[str]:
    """Tách từ đơn giản cho BM25 (tách theo khoảng trắng + hạ chữ thường).
    Có thể thay bằng underthesea/pyvi để tách từ tiếng Việt chuẩn hơn."""
    return text.lower().split()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--chunks", default="legal_data/chunks/chunks.jsonl")
    ap.add_argument("--out", default="legal_data/vectorstore")
    ap.add_argument("--model", default=EMBED_MODEL)
    ap.add_argument("--batch-size", type=int, default=32)
    ap.add_argument("--incremental", action="store_true",
                    help="Chỉ embed các chunk_id chưa có trong Chroma; BM25 vẫn được tạo lại toàn bộ.")
    args = ap.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    chunks = [json.loads(l) for l in open(args.chunks, encoding="utf-8")]
    print(f"Đọc {len(chunks)} chunk từ {args.chunks}")

    # ---- 1. Vector index ----
    print(f"Tải model embedding: {args.model} ...")
    model = SentenceTransformer(args.model)

    client = chromadb.PersistentClient(path=str(out_dir / "chroma"))
    coll = client.get_or_create_collection("legal_chunks")

    indexed_chunks = chunks
    if args.incremental:
        existing_ids = set(coll.get(include=[])["ids"])
        indexed_chunks = [c for c in chunks if c["chunk_id"] not in existing_ids]
        print(f"Incremental: {len(indexed_chunks)} chunk mới, {len(existing_ids)} chunk đã có")

    texts = [c["embed_text"] for c in indexed_chunks]
    ids = [c["chunk_id"] for c in indexed_chunks]
    # metadata: Chroma không nhận list/dict lồng nhau -> chuyển replaces/replaced_by thành chuỗi
    metas = []
    for c in indexed_chunks:
        m = {k: v for k, v in c.items() if k not in ("embed_text",)}
        for k in ("replaces", "replaced_by"):
            if isinstance(m.get(k), list):
                m[k] = ",".join(m[k])
        metas.append({k: ("" if v is None else v) for k, v in m.items()})

    for i in range(0, len(indexed_chunks), args.batch_size):
        batch = texts[i:i + args.batch_size]
        emb = model.encode(batch, normalize_embeddings=True).tolist()
        coll.upsert(ids=ids[i:i + args.batch_size], embeddings=emb,
                    documents=[c["text"] for c in indexed_chunks[i:i + args.batch_size]],
                    metadatas=metas[i:i + args.batch_size])
        print(f"  embedded {min(i + args.batch_size, len(indexed_chunks))}/{len(indexed_chunks)}")

    # ---- 2. BM25 index ----
    all_ids = [c["chunk_id"] for c in chunks]
    tokenized = [simple_tokenize(c["embed_text"]) for c in chunks]
    bm25 = BM25Okapi(tokenized)
    with open(out_dir / "bm25.pkl", "wb") as f:
        pickle.dump({"bm25": bm25, "chunk_ids": all_ids,
                     "chunks_by_id": {c["chunk_id"]: c for c in chunks}}, f)

    print(f"\nXong: vector index -> {out_dir/'chroma'} | BM25 index -> {out_dir/'bm25.pkl'}")


if __name__ == "__main__":
    main()
