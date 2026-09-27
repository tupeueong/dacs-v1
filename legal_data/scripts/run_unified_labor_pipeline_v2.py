"""One-command rebuild and QA pipeline for the unified labor-law RAG corpus."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from rag_config import SETTINGS


SCRIPTS = SETTINGS.legal_data / "scripts"


def run(script: str, *args: str) -> None:
    command = [sys.executable, "-X", "utf8", str(SCRIPTS / script), *args]
    print("RUN", " ".join(command), flush=True)
    subprocess.run(command, cwd=SETTINGS.root, check=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--refresh-official",
        action="store_true",
        help="Download and parse the official Gazette sources before rebuilding.",
    )
    parser.add_argument("--skip-embedding", action="store_true")
    parser.add_argument("--skip-eval", action="store_true")
    parser.add_argument("--batch-size", type=int, default=32)
    args = parser.parse_args()

    run("merge_labor_source_registries.py")
    if args.refresh_official:
        run("ingest_official_congbao_labor_v4.py")
    run("build_unified_labor_articles.py")
    run("chunk_unified_labor.py")
    if args.skip_embedding:
        return 0
    run("build_index_v2.py", "--batch-size", str(args.batch_size))
    run("verify_index_v2.py")
    if not args.skip_eval:
        run("evaluate_retrieval_v2.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

