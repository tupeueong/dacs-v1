"""Windows-safe index build: child builds/verifies, parent promotes after child exit."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from rag_config import SETTINGS


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch-size", type=int, default=32)
    args = parser.parse_args()
    corpus_hash = sha256(SETTINGS.chunks_path)
    model_slug = re.sub(r"[^a-z0-9]+", "-", SETTINGS.embed_model.casefold()).strip("-")
    version = f"labor-rag-index.v2-{corpus_hash[:12]}-{model_slug}"
    root = SETTINGS.index_root.resolve()
    staging = root / f"{version}.staging"
    final = root / version

    subprocess.run(
        [sys.executable, "-X", "utf8", str(Path(__file__).with_name("build_index_worker_v3.py")),
         "--batch-size", str(args.batch_size)],
        cwd=SETTINGS.root,
        check=True,
    )
    if staging.exists():
        manifest_path = staging / "index_manifest.json"
        if not manifest_path.exists():
            raise RuntimeError(f"Incomplete staging index: {staging}")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest.get("corpus_sha256") != corpus_hash:
            raise RuntimeError("Staging manifest does not match current corpus")
        if final.exists():
            raise RuntimeError(f"Refusing to overwrite existing index: {final}")
        staging.replace(final)
    if not final.exists():
        raise RuntimeError(f"Missing final index: {final}")

    # Verify in a disposable process so Chroma handles never interfere with promotion.
    subprocess.run(
        [sys.executable, "-X", "utf8", str(Path(__file__).with_name("verify_index_v2.py")),
         "--index", str(final)],
        cwd=SETTINGS.root,
        check=True,
    )
    manifest = json.loads((final / "index_manifest.json").read_text(encoding="utf-8"))
    pointer = {
        "schema_version": "labor-rag-current-pointer.v1",
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "version": version,
        "index_dir": str(final),
        "corpus_sha256": corpus_hash,
        "verification": manifest["verification"],
    }
    temporary = SETTINGS.current_pointer.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(pointer, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(SETTINGS.current_pointer)
    print(json.dumps(pointer, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
