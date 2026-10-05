"""Build a versioned, verified cosine Chroma + BM25 index.

The active pointer changes only after the complete staging index passes integrity checks.
"""

from __future__ import annotations

import argparse
import gc
import hashlib
import json
import pickle
import re
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path

import chromadb
from rank_bm25 import BM25Okapi
from sentence_transformers import SentenceTransformer

from rag_config import SETTINGS


INDEX_SCHEMA_VERSION = "labor-rag-index.v2"
WORD_RE = re.compile(r"[0-9A-Za-zÀ-ỹĐđ]+", re.UNICODE)


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def vi_legal_tokenize(text: str) -> list[str]:
    """Tokens plus adjacent syllable bigrams for Vietnamese exact-term retrieval."""
    words = [token.casefold() for token in WORD_RE.findall(text)]
    bigrams = [f"{left}_{right}" for left, right in zip(words, words[1:])]
    return words + bigrams


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


def safely_remove_staging(path: Path, root: Path) -> None:
    resolved_path = path.resolve()
    resolved_root = root.resolve()
    if resolved_path.parent != resolved_root or not resolved_path.name.endswith(".staging"):
        raise RuntimeError(f"Refusing to remove unsafe staging path: {resolved_path}")
    if resolved_path.exists():
        shutil.rmtree(resolved_path)


def verify_index(index_dir: Path, expected_ids: list[str]) -> dict:
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


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--chunks", type=Path, default=SETTINGS.chunks_path)
    parser.add_argument("--index-root", type=Path, default=SETTINGS.index_root)
    parser.add_argument("--pointer", type=Path, default=SETTINGS.current_pointer)
    parser.add_argument("--model", default=SETTINGS.embed_model)
    parser.add_argument("--batch-size", type=int, default=32)
    args = parser.parse_args()

    chunks_path = args.chunks.resolve()
    index_root = args.index_root.resolve()
    pointer_path = args.pointer.resolve()
    chunks = load_chunks(chunks_path)
    corpus_hash = file_sha256(chunks_path)
    model_slug = re.sub(r"[^a-z0-9]+", "-", args.model.casefold()).strip("-")
    version = f"{INDEX_SCHEMA_VERSION}-{corpus_hash[:12]}-{model_slug}"
    final_dir = index_root / version
    staging_dir = index_root / f"{version}.staging"
    index_root.mkdir(parents=True, exist_ok=True)

    if final_dir.exists():
        verification = verify_index(final_dir, [chunk["chunk_id"] for chunk in chunks])
        print(f"Reuse verified index: {final_dir}")
    else:
        chunk_ids = [chunk["chunk_id"] for chunk in chunks]
        manifest_path = staging_dir / "index_manifest.json"
        if manifest_path.exists():
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            if (
                manifest.get("corpus_sha256") != corpus_hash
                or manifest.get("embedding_model") != args.model
            ):
                raise RuntimeError("Completed staging manifest does not match corpus/model")
            verification = verify_index(staging_dir, chunk_ids)
            print(f"Reuse completed staging index: {staging_dir}", flush=True)
        else:
            expected_ids = set(chunk_ids)
            if staging_dir.exists():
                client = chromadb.PersistentClient(path=str(staging_dir / "chroma"))
                try:
                    collection = client.get_collection(SETTINGS.collection_name)
                except Exception as exc:
                    raise RuntimeError(
                        f"Staging exists but its Chroma collection is unusable: {staging_dir}"
                    ) from exc
                stored_ids = set(collection.get(include=[])["ids"])
                extra_ids = stored_ids - expected_ids
                if extra_ids:
                    raise RuntimeError(
                        f"Refusing to resume staging with {len(extra_ids)} unexpected IDs"
                    )
                if collection.configuration["hnsw"]["space"] != "cosine":
                    raise RuntimeError("Refusing to resume a non-cosine staging collection")
                print(
                    f"Resume staging: embedded={len(stored_ids)}/{len(chunks)}",
                    flush=True,
                )
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

            bm25 = BM25Okapi([vi_legal_tokenize(chunk["embed_text"]) for chunk in chunks])
            with (staging_dir / "bm25.pkl").open("wb") as handle:
                pickle.dump(
                    {
                        "bm25": bm25,
                        "chunk_ids": chunk_ids,
                        "chunks_by_id": {chunk["chunk_id"]: chunk for chunk in chunks},
                        "tokenizer": "vi_legal_words_and_bigrams.v1",
                    },
                    handle,
                )

            verification = verify_index(staging_dir, chunk_ids)
            manifest = {
                "schema_version": INDEX_SCHEMA_VERSION,
                "version": version,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "corpus_path": str(chunks_path),
                "corpus_sha256": corpus_hash,
                "embedding_model": args.model,
                "normalized_embeddings": True,
                "bm25_tokenizer": "vi_legal_words_and_bigrams.v1",
                "verification": verification,
            }
            manifest_path.write_text(
                json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )

        # Chroma keeps underlying files open on Windows until the client object is released.
        # Explicitly release references and retry a few times to avoid PermissionError during rename.
        if "collection" in locals():
            del collection
        client = None
        gc.collect()
        for attempt in range(10):
            try:
                staging_dir.replace(final_dir)
                break
            except PermissionError:
                if attempt == 9:
                    raise
                time.sleep(0.5)
                gc.collect()

    pointer = {
        "schema_version": "labor-rag-current-pointer.v1",
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "version": version,
        "index_dir": str(final_dir),
        "corpus_sha256": corpus_hash,
        "verification": verification,
    }
    pointer_path.parent.mkdir(parents=True, exist_ok=True)
    pointer_tmp = pointer_path.with_suffix(pointer_path.suffix + ".tmp")
    pointer_tmp.write_text(json.dumps(pointer, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    pointer_tmp.replace(pointer_path)
    print(json.dumps(pointer, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

