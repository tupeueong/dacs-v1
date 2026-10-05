"""Run the canonical labor-law data, index, and evaluation pipeline."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from rag_config import SETTINGS


def run(script: str, *arguments: str) -> None:
    command = [sys.executable, "-X", "utf8", str(Path(__file__).with_name(script)), *arguments]
    print("RUN", " ".join(command), flush=True)
    subprocess.run(command, cwd=SETTINGS.root, check=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skip-index", action="store_true")
    parser.add_argument("--skip-eval", action="store_true")
    parser.add_argument("--refresh-priority-sources", action="store_true")
    parser.add_argument("--batch-size", type=int, default=32)
    args = parser.parse_args()

    if args.batch_size <= 0:
        parser.error("--batch-size must be positive")

    if args.refresh_priority_sources:
        run("ingest_priority_sources.py")
    run("build_labor_corpus.py")
    run("chunk_labor_corpus.py")
    if args.skip_index:
        return 0
    run("build_index_v4.py", "--batch-size", str(args.batch_size))
    run("verify_index_v2.py")
    if not args.skip_eval:
        run("evaluate_retrieval_v2.py")
    run("pre_backend_gate.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
