"""Build in a child process, verify, then safely promote the versioned RAG index."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from build_index_v2 import file_sha256, load_chunks, verify_index
from rag_config import SETTINGS


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch-size", type=int, default=32)
    args = parser.parse_args()

    command = [
        sys.executable,
        "-X",
        "utf8",
        str(Path(__file__).with_name("build_index_worker_v3.py")),
        "--batch-size",
        str(args.batch_size),
    ]
    subprocess.run(command, cwd=SETTINGS.root, check=True)

    chunks = load_chunks(SETTINGS.chunks_path)
    corpus_hash = file_sha256(SETTINGS.chunks_path)
    model_slug = "truro7-vn-law-embedding"
    version = f"labor-rag-index.v2-{corpus_hash[:12]}-{model_slug}"
    root = SETTINGS.index_root.resolve()
    staging = root / f"{version}.staging"
    final = root / version
    if not staging.exists():
        if final.exists():
            verification = verify_index(final, [item["chunk_id"] for item in chunks])
        else:
            raise RuntimeError(f"Worker produced neither staging nor final index: {version}")
    else:
        manifest_path = staging / "index_manifest.json"
        if not manifest_path.exists():
            raise RuntimeError(f"Incomplete staging index: {staging}")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest["corpus_sha256"] != corpus_hash:
            raise RuntimeError("Staging manifest does not match current corpus")
        verification = verify_index(staging, [item["chunk_id"] for item in chunks])
        if final.exists():
            raise RuntimeError(f"Refusing to overwrite existing index: {final}")
        staging.replace(final)

    pointer = {
        "schema_version": "labor-rag-current-pointer.v1",
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "version": version,
        "index_dir": str(final),
        "corpus_sha256": corpus_hash,
        "verification": verification,
    }
    SETTINGS.current_pointer.parent.mkdir(parents=True, exist_ok=True)
    temporary = SETTINGS.current_pointer.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(pointer, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(SETTINGS.current_pointer)
    print(json.dumps(pointer, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
