"""Run the structural chunker and stamp the v2 corpus date/schema."""

from __future__ import annotations

import json
from datetime import datetime, timezone

import chunk_unified_labor
from rag_config import SETTINGS


def main() -> int:
    result = chunk_unified_labor.main()
    chunks = [
        json.loads(line) for line in SETTINGS.chunks_path.open(encoding="utf-8") if line.strip()
    ]
    for chunk in chunks:
        chunk["corpus_as_of"] = "2026-09-28"
    temp = SETTINGS.chunks_path.with_suffix(".jsonl.tmp")
    with temp.open("w", encoding="utf-8", newline="\n") as handle:
        for chunk in chunks:
            handle.write(json.dumps(chunk, ensure_ascii=False) + "\n")
    temp.replace(SETTINGS.chunks_path)
    report_path = SETTINGS.chunks_path.parent / "chunks_qa_report.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    report["generated_at"] = datetime.now(timezone.utc).isoformat()
    report["schema_version"] = "unified_labor.chunks.v2"
    report["corpus_as_of"] = "2026-09-28"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


if __name__ == "__main__":
    raise SystemExit(main())

