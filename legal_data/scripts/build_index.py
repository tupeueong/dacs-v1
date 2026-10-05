"""Build a versioned, verified cosine Chroma + BM25 index into a staging directory."""

from __future__ import annotations
import argparse
import hashlib
import json
import pickle
import re
import time
import subprocess
import sys
import inspect
from datetime import datetime, timezone
from pathlib import Path
try:
    from importlib.metadata import version as get_pkg_version
except ImportError:
    import pkg_resources
    def get_pkg_version(name): return pkg_resources.get_distribution(name).version

from rag_config import SETTINGS

INDEX_SCHEMA_VERSION = "labor-rag-index.v2"
from vi_tokenizer import vi_legal_tokenize
import hashlib

def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()

def load_chunks(path: Path) -> list[dict]:
    chunks = [json.loads(line) for line in path.open(encoding="utf-8") if line.strip()]
    ids = [chunk["chunk_id"] for chunk in chunks]
    if not chunks:
        raise RuntimeError("Chunk corpus is empty")
    if len(ids) != len(set(ids)):
        raise RuntimeError("Duplicate chunk_id in input corpus")
    return chunks

def scalar_metadata(chunk: dict) -> dict:
    metadata = {}
    for key, value in chunk.items():
        if key in {"embed_text", "text", "content_text"}:
            continue
        if value is None:
            value = ""
        elif isinstance(value, (list, dict)):
            value = json.dumps(value, ensure_ascii=False, sort_keys=True)
        metadata[key] = value
    return metadata

def verify_index(index_dir: Path, expected_ids: list[str]) -> dict:
    import chromadb
    collection = chromadb.PersistentClient(path=str(index_dir / "chroma")).get_collection(
        SETTINGS.collection_name
    )
    stored_ids = collection.get(include=[])["ids"]
    if set(stored_ids) != set(expected_ids):
        raise RuntimeError(
            f"Chroma ID mismatch: missing={len(set(expected_ids)-set(stored_ids))}, "
            f"extra={len(set(stored_ids)-set(expected_ids))}"
        )
    sample = collection.get(ids=[expected_ids[0]], include=["embeddings"])
    dimension = len(sample["embeddings"][0])
    with (index_dir / "bm25.pkl").open("rb") as handle:
        bm25_data = pickle.load(handle)
    if bm25_data["chunk_ids"] != expected_ids:
        raise RuntimeError("BM25 IDs/order do not match the chunk corpus")
    return {
        "chunk_count": len(expected_ids),
        "chroma_count": collection.count(),
        "bm25_count": len(bm25_data["chunk_ids"]),
        "embedding_dimension": dimension,
        "distance_metric": collection.configuration["hnsw"]["space"],
        "id_sets_match": True,
        "bm25_order_matches": True,
    }

def worker_main(args: argparse.Namespace) -> int:
    import chromadb
    from rank_bm25 import BM25Okapi
    from sentence_transformers import SentenceTransformer
    
    chunks_path = args.chunks.resolve()
    index_root = args.index_root.resolve()
    chunks = load_chunks(chunks_path)
    corpus_hash = file_sha256(chunks_path)
    model_slug = re.sub(r"[^a-z0-9]+", "-", args.model.casefold()).strip("-")
    version_name = f"{INDEX_SCHEMA_VERSION}-{corpus_hash[:12]}-{model_slug}"
    staging_dir = index_root / f"{version_name}.staging"
    index_root.mkdir(parents=True, exist_ok=True)
    
    chunk_ids = [chunk["chunk_id"] for chunk in chunks]
    expected_ids = set(chunk_ids)
    
    if staging_dir.exists():
        client = chromadb.PersistentClient(path=str(staging_dir / "chroma"))
        collection = client.get_collection(SETTINGS.collection_name)
        stored_ids = set(collection.get(include=[])["ids"])
    else:
        staging_dir.mkdir(parents=True)
        client = chromadb.PersistentClient(path=str(staging_dir / "chroma"))
        collection = client.create_collection(
            SETTINGS.collection_name,
            configuration={"hnsw": {"space": "cosine"}},
        )
        stored_ids = set()

    pending_chunks = [chunk for chunk in chunks if chunk["chunk_id"] not in stored_ids]
    if pending_chunks:
        model = SentenceTransformer(args.model)
        for offset in range(0, len(pending_chunks), args.batch_size):
            batch = pending_chunks[offset : offset + args.batch_size]
            embeddings = model.encode(
                [chunk["embed_text"] for chunk in batch],
                normalize_embeddings=True,
            ).tolist()
            collection.add(
                ids=[chunk["chunk_id"] for chunk in batch],
                embeddings=embeddings,
                documents=[chunk["text"] for chunk in batch],
                metadatas=[scalar_metadata(chunk) for chunk in batch],
            )
            completed = len(stored_ids) + min(offset + len(batch), len(pending_chunks))
            print(f"embedded={completed}/{len(chunks)}", flush=True)
            
        dim = len(embeddings[0])
    else:
        dim = len(collection.get(ids=[chunk_ids[0]], include=["embeddings"])["embeddings"][0])

    bm25 = BM25Okapi([vi_legal_tokenize(chunk["embed_text"]) for chunk in chunks])
    tokenizer_source = inspect.getsource(vi_legal_tokenize)
    tokenizer_version = hashlib.sha256(tokenizer_source.encode("utf-8")).hexdigest()[:12]
    
    with (staging_dir / "bm25.pkl").open("wb") as handle:
        pickle.dump(
            {
                "bm25": bm25,
                "chunk_ids": chunk_ids,
                "chunks_by_id": {chunk["chunk_id"]: chunk for chunk in chunks},
                "tokenizer": f"vi_legal_words_and_bigrams.v{tokenizer_version}",
            },
            handle,
        )

    libs = {}
    for lib in ["chromadb", "sentence-transformers", "rank-bm25", "torch"]:
        try:
            libs[lib] = get_pkg_version(lib)
        except Exception:
            libs[lib] = "unknown"
            
    verification = verify_index(staging_dir, chunk_ids)
    manifest = {
        "schema_version": INDEX_SCHEMA_VERSION,
        "version": version_name,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "corpus_path": str(chunks_path),
        "corpus_sha256": corpus_hash,
        "embedding_model": args.model,
        "normalized_embeddings": True,
        "bm25_tokenizer": f"vi_legal_words_and_bigrams.v{tokenizer_version}",
        
        "corpus_schema_version": INDEX_SCHEMA_VERSION,
        "corpus_hash": f"sha256:{corpus_hash}",
        "embedding_model_revision": "unknown",
        "embedding_dimension": dim,
        "distance_metric": collection.configuration["hnsw"]["space"],
        "chunk_count": len(chunks),
        "built_at": datetime.now(timezone.utc).astimezone().isoformat(),
        "bm25_tokenizer_version": tokenizer_version,
        "library_versions": libs,
        "verification": verification
    }
    
    (staging_dir / "index_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    
    print(f"STAGING_DIR={staging_dir}")
    return 0

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--chunks", type=Path, default=SETTINGS.chunks_path)
    parser.add_argument("--index-root", type=Path, default=SETTINGS.index_root)
    parser.add_argument("--model", default=SETTINGS.embed_model)
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--worker", action="store_true")
    args = parser.parse_args()

    if args.worker:
        return worker_main(args)
    else:
        cmd = [sys.executable, "-X", "utf8", str(Path(__file__).resolve())]
        for arg in sys.argv[1:]:
            cmd.append(arg)
        cmd.append("--worker")
        print("Spawning worker to avoid Chroma locks...", flush=True)
        res = subprocess.run(cmd, check=True)
        return res.returncode

if __name__ == "__main__":
    raise SystemExit(main())
