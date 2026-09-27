"""Verify the finalized Phap dien labor-law Chroma and BM25 indexes."""

import argparse
import json
import pickle
from pathlib import Path

import chromadb
from sentence_transformers import SentenceTransformer


def load_chunks(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--chunks",
        type=Path,
        default=Path("legal_data/external/phapdien_labor/chunked/chunks.jsonl"),
    )
    parser.add_argument(
        "--index",
        type=Path,
        default=Path("legal_data/vectorstore_phapdien_labor"),
    )
    parser.add_argument("--model", default="truro7/vn-law-embedding")
    parser.add_argument(
        "--query",
        action="append",
        default=[],
        help="Optional semantic query; may be supplied more than once.",
    )
    args = parser.parse_args()

    chunks = load_chunks(args.chunks)
    expected_ids = [chunk["chunk_id"] for chunk in chunks]
    if len(expected_ids) != len(set(expected_ids)):
        raise RuntimeError("Duplicate chunk IDs in JSONL")

    collection = chromadb.PersistentClient(path=str(args.index / "chroma")).get_collection(
        "legal_chunks"
    )
    stored = collection.get(include=[])
    stored_ids = stored["ids"]
    if set(stored_ids) != set(expected_ids):
        missing = set(expected_ids) - set(stored_ids)
        extra = set(stored_ids) - set(expected_ids)
        raise RuntimeError(f"Chroma ID mismatch: missing={len(missing)}, extra={len(extra)}")

    sample = collection.get(ids=[expected_ids[0]], include=["embeddings"])
    dimension = len(sample["embeddings"][0])

    with (args.index / "bm25.pkl").open("rb") as handle:
        bm25_data = pickle.load(handle)
    bm25_ids = bm25_data["chunk_ids"]
    if bm25_ids != expected_ids:
        raise RuntimeError("BM25 IDs/order do not match chunks JSONL")

    print(f"chunks={len(chunks)}")
    print(f"chroma={collection.count()}")
    print(f"bm25={len(bm25_ids)}")
    print(f"embedding_dimension={dimension}")
    print("id_sets_match=true")
    print("bm25_order_matches=true")

    if args.query:
        model = SentenceTransformer(args.model)
        embeddings = model.encode(args.query, normalize_embeddings=True).tolist()
        for query, embedding in zip(args.query, embeddings):
            result = collection.query(
                query_embeddings=[embedding],
                n_results=3,
                include=["documents", "metadatas", "distances"],
            )
            print(f"\nQUERY: {query}")
            for rank, (chunk_id, metadata, distance) in enumerate(
                zip(result["ids"][0], result["metadatas"][0], result["distances"][0]),
                start=1,
            ):
                label = metadata.get("article_title") or metadata.get("article_id") or ""
                print(f"{rank}. {chunk_id} | {label} | distance={distance:.6f}")


if __name__ == "__main__":
    main()
