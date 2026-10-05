"""Promote a staging index to a final index by verifying and updating current pointer."""

from __future__ import annotations
import argparse
import json
import time
import os
from pathlib import Path
from datetime import datetime, timezone
from rag_config import SETTINGS
from build_index import file_sha256, load_chunks
from verify_index_v2 import main as verify_main

def replace_with_retry(src: Path, dst: Path, attempts: int = 5, delay: float = 0.5) -> None:
    """Rename src to dst, retrying briefly on Windows file-lock errors (PermissionError/OSError)."""
    for attempt in range(attempts):
        try:
            os.replace(src, dst)
            return
        except (PermissionError, OSError):
            if attempt == attempts - 1:
                raise
            time.sleep(delay)

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--staging-dir", type=Path, required=True)
    parser.add_argument("--chunks", type=Path, default=SETTINGS.chunks_path)
    parser.add_argument("--pointer", type=Path, default=SETTINGS.current_pointer)
    parser.add_argument("--dry-run", action="store_true", help="Only verify, don't promote")
    args = parser.parse_args()

    staging_dir = args.staging_dir.resolve()
    if not staging_dir.exists():
        raise FileNotFoundError(f"Staging directory not found: {staging_dir}")
        
    manifest_path = staging_dir / "index_manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(f"Staging manifest not found: {manifest_path}")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    
    # Verification
    print("Verifying staging index...")
    import sys
    sys.argv = ["verify_index_v2.py", "--index", str(staging_dir), "--chunks", str(args.chunks)]
    try:
        verify_main()
    except Exception as e:
        print(f"Verification FAIL: {e}")
        return 1

    actual_hash = file_sha256(args.chunks)
    if manifest["corpus_sha256"] != actual_hash and manifest.get("corpus_hash") != f"sha256:{actual_hash}":
        print("Verification FAIL: Manifest corpus hash does not match chunks.jsonl")
        return 1

    print("Verification PASS!")
    
    final_dir = staging_dir.parent / manifest["version"]
    if args.dry_run:
        print(f"[DRY-RUN] Would rename {staging_dir} to {final_dir}")
        print(f"[DRY-RUN] Would write pointer to {args.pointer}")
        return 0

    if final_dir.exists():
        print(f"Final directory already exists: {final_dir}. Skipping rename.")
    else:
        replace_with_retry(staging_dir, final_dir)
        print(f"Promoted to {final_dir}")

    # Read verification results from verify_main output (or recalculate)
    # verify_main prints json to stdout, but we can just import verify_index directly since verify_main exited cleanly
    from build_index import verify_index
    chunks = load_chunks(args.chunks)
    verification = verify_index(final_dir, [c["chunk_id"] for c in chunks])
    
    # Write pointer atomic
    pointer = {
        "schema_version": "labor-rag-current-pointer.v1",
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "version": manifest["version"],
        "index_dir": str(final_dir),
        "corpus_sha256": actual_hash,
        "verification": verification,
    }
    
    pointer_tmp = args.pointer.with_suffix(args.pointer.suffix + ".tmp")
    args.pointer.parent.mkdir(parents=True, exist_ok=True)
    pointer_tmp.write_text(json.dumps(pointer, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    replace_with_retry(pointer_tmp, args.pointer)
    
    print(f"Updated pointer at {args.pointer}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
