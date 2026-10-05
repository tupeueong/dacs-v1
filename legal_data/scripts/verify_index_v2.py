"""Verify the active versioned RAG index against its source corpus and manifest."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from build_index import file_sha256, load_chunks, verify_index
from rag_config import SETTINGS


def resolve_index(pointer_path: Path) -> Path:
    pointer = json.loads(pointer_path.read_text(encoding="utf-8"))
    return Path(pointer["index_dir"])


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--chunks", type=Path, default=SETTINGS.chunks_path)
    parser.add_argument("--pointer", type=Path, default=SETTINGS.current_pointer)
    parser.add_argument("--index", type=Path)
    args = parser.parse_args()

    index_dir = args.index or resolve_index(args.pointer)
    chunks = load_chunks(args.chunks)
    result = verify_index(index_dir, [chunk["chunk_id"] for chunk in chunks])
    manifest = json.loads((index_dir / "index_manifest.json").read_text(encoding="utf-8"))
    actual_hash = file_sha256(args.chunks)
    if manifest["corpus_sha256"] != actual_hash:
        raise RuntimeError("Manifest corpus hash does not match chunks.jsonl")
    if result["distance_metric"] != "cosine":
        raise RuntimeError(f"Expected cosine index, got {result['distance_metric']}")
    print(json.dumps({"index_dir": str(index_dir), **result}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

