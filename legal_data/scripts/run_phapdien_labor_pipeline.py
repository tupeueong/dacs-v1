"""Run the canonical Phap dien labor-law preprocessing and indexing pipeline.

This entry point intentionally bypasses the legacy character-based chunk output.
It starts from the imported article-level source and always chunks articles.final.jsonl.
"""

import argparse
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "legal_data" / "scripts"
DATA = ROOT / "legal_data" / "external" / "phapdien_labor"


def run(*arguments: str) -> None:
    command = [sys.executable, *arguments]
    print("RUN:", " ".join(command), flush=True)
    subprocess.run(command, cwd=ROOT, check=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--skip-embedding",
        action="store_true",
        help="Stop after producing and validating the token-aware chunks.",
    )
    parser.add_argument("--batch-size", type=int, default=32)
    args = parser.parse_args()

    source = DATA / "articles.jsonl"
    final_articles = DATA / "processed" / "articles.final.jsonl"
    chunks = DATA / "chunked" / "chunks.jsonl"
    index = ROOT / "legal_data" / "vectorstore_phapdien_labor"

    if not source.exists():
        raise FileNotFoundError(f"Missing imported article source: {source}")

    run(str(SCRIPTS / "preprocess_phapdien_labor.py"), "--input", str(source))
    run(str(SCRIPTS / "finalize_phapdien_labor.py"))
    run(
        str(SCRIPTS / "chunk_phapdien_labor.py"),
        "--input",
        str(final_articles),
    )

    if args.skip_embedding:
        return

    run(
        str(SCRIPTS / "build_index.py"),
        "--chunks",
        str(chunks),
        "--out",
        str(index),
        "--batch-size",
        str(args.batch_size),
    )
    run(str(SCRIPTS / "verify_phapdien_labor_index.py"))


if __name__ == "__main__":
    main()
