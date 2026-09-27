"""OCR scanned official labor-law PDFs with page-level provenance.

The signed PDFs remain the source of record. OCR output is an auditable
intermediate and must pass article-count/sample checks before RAG ingestion.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import easyocr


ROOT = Path(__file__).resolve().parents[2]
SOURCE_ROOT = ROOT / "legal_data" / "external" / "official_labor_2024_2026"
ARTICLE_RE = re.compile(r"(?mi)^\s*Điều\s+(\d+[a-zđ]?)\s*\.")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def order_lines(result: list) -> list[dict]:
    rows = []
    for box, text, confidence in result:
        if not text.strip():
            continue
        x = min(point[0] for point in box)
        y = min(point[1] for point in box)
        height = max(point[1] for point in box) - y
        rows.append({"x": x, "y": y, "height": height, "text": text.strip(),
                     "confidence": float(confidence)})
    rows.sort(key=lambda row: (round(row["y"] / max(row["height"], 1)), row["x"]))
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pdf-dir", type=Path, default=SOURCE_ROOT / "pdf")
    parser.add_argument("--output-dir", type=Path, default=SOURCE_ROOT / "ocr")
    parser.add_argument("--model-dir", type=Path,
                        default=ROOT / "legal_data" / "external" / "cache" / "easyocr")
    parser.add_argument("--include", action="append", default=[])
    parser.add_argument("--dpi", type=int, default=200)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)
    args.model_dir.mkdir(parents=True, exist_ok=True)
    selected = set(args.include)
    pdfs = [path for path in sorted(args.pdf_dir.glob("*.pdf"))
            if not selected or path.name in selected]
    if not pdfs:
        raise RuntimeError("No PDFs selected")

    reader = easyocr.Reader(
        ["vi", "en"],
        gpu=False,
        model_storage_directory=str(args.model_dir),
        download_enabled=True,
    )
    reports = []
    temp_root = ROOT / "tmp" / "pdfs"
    temp_root.mkdir(parents=True, exist_ok=True)

    for pdf in pdfs:
        text_path = args.output_dir / f"{pdf.stem}.txt"
        pages_path = args.output_dir / f"{pdf.stem}.pages.jsonl"
        report_path = args.output_dir / f"{pdf.stem}.report.json"
        if report_path.exists() and not args.force:
            reports.append(json.loads(report_path.read_text(encoding="utf-8")))
            print(f"SKIP {pdf.name}: report exists", flush=True)
            continue

        work = Path(tempfile.mkdtemp(prefix=f"ocr-{pdf.stem}-", dir=temp_root))
        try:
            prefix = work / "page"
            subprocess.run(
                ["pdftoppm", "-jpeg", "-r", str(args.dpi), str(pdf), str(prefix)],
                check=True,
            )
            images = sorted(work.glob("page-*.jpg"))
            page_records = []
            page_texts = []
            confidences = []
            for page_number, image in enumerate(images, 1):
                detected = reader.readtext(str(image), detail=1, paragraph=False)
                rows = order_lines(detected)
                page_text = "\n".join(row["text"] for row in rows)
                page_texts.append(page_text)
                confidences.extend(row["confidence"] for row in rows)
                page_records.append({
                    "document": pdf.stem,
                    "page": page_number,
                    "text": page_text,
                    "lines": rows,
                })
                print(f"{pdf.name}: page {page_number}/{len(images)}", flush=True)

            full_text = "\n\n\f\n\n".join(page_texts).strip() + "\n"
            text_path.write_text(full_text, encoding="utf-8")
            with pages_path.open("w", encoding="utf-8") as handle:
                for record in page_records:
                    handle.write(json.dumps(record, ensure_ascii=False) + "\n")
            articles = ARTICLE_RE.findall(full_text)
            report = {
                "schema_version": "official_labor.ocr.v1",
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "source_pdf": str(pdf.resolve()),
                "source_sha256": sha256(pdf),
                "dpi": args.dpi,
                "page_count": len(images),
                "character_count": len(full_text),
                "article_heading_count": len(articles),
                "first_article_headings": articles[:5],
                "last_article_headings": articles[-5:],
                "mean_line_confidence": (
                    sum(confidences) / len(confidences) if confidences else 0.0
                ),
                "text_output": str(text_path.resolve()),
                "pages_output": str(pages_path.resolve()),
                "qa_status": "pending_review",
            }
            report_path.write_text(
                json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            reports.append(report)
        finally:
            shutil.rmtree(work, ignore_errors=True)

    summary = {
        "schema_version": "official_labor.ocr_summary.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "documents": reports,
    }
    (args.output_dir / "ocr_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )


if __name__ == "__main__":
    main()
