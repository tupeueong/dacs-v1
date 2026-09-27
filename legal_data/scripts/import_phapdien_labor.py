"""Tải và chuẩn hóa riêng Chủ đề 20 (Lao động) từ Bộ Pháp Điển.

Đầu ra mặc định:
  legal_data/external/phapdien_labor/articles.jsonl
  legal_data/external/phapdien_labor/chunks.jsonl
  legal_data/external/phapdien_labor/manifest.json

Chỉ tải config ``documents``. Embedding 4096-D của dataset nguồn không được tải
vì index hiện tại dùng một embedding model khác.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import unicodedata
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import pyarrow.compute as pc
import pyarrow.parquet as pq
import requests


LEGAL_DATA = Path(__file__).resolve().parent.parent
DATASET = "tmquan/phapdien-moj-gov-vn"
DEFAULT_REVISION = "a1b6860c821b7142ffe2385178af4e4bb6f86aff"
TOPIC_NUMBER = 20


def normalize_text(value: object) -> str:
    if value is None:
        return ""
    text = unicodedata.normalize("NFC", str(value))
    text = text.replace("\u00a0", " ").replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def dataset_document_files(revision: str) -> list[dict]:
    url = f"https://huggingface.co/api/datasets/{DATASET}/tree/{revision}"
    response = requests.get(url, params={"recursive": "false", "expand": "false"}, timeout=60)
    response.raise_for_status()
    files = [
        item for item in response.json()
        if item.get("type") == "file"
        and re.fullmatch(r"documents-\d+-of-\d+\.parquet", item.get("path", ""))
    ]
    if not files:
        raise RuntimeError("Không tìm thấy shard documents-*.parquet")
    return sorted(files, key=lambda item: item["path"])


def download_file(name: str, expected_size: int, revision: str, cache_dir: Path) -> Path:
    cache_dir.mkdir(parents=True, exist_ok=True)
    target = cache_dir / name
    if target.exists() and target.stat().st_size == expected_size:
        return target

    url = f"https://huggingface.co/datasets/{DATASET}/resolve/{revision}/{name}"
    temporary = target.with_suffix(target.suffix + ".part")
    with requests.get(url, stream=True, timeout=(30, 300)) as response:
        response.raise_for_status()
        with temporary.open("wb") as handle:
            for block in response.iter_content(chunk_size=1024 * 1024):
                if block:
                    handle.write(block)
    if temporary.stat().st_size != expected_size:
        raise RuntimeError(
            f"Sai kích thước {name}: {temporary.stat().st_size} != {expected_size}"
        )
    temporary.replace(target)
    return target


def split_body(text: str, max_chars: int) -> list[str]:
    """Cắt theo đoạn/câu và luôn hard-split nếu một đơn vị vẫn quá dài."""
    if len(text) <= max_chars:
        return [text]

    units: list[str] = []
    for paragraph in re.split(r"\n+", text):
        paragraph = paragraph.strip()
        if not paragraph:
            continue
        if len(paragraph) <= max_chars:
            units.append(paragraph)
            continue
        sentences = re.split(r"(?<=[.;!?])\s+(?=[A-ZÀ-ỸĐ0-9])", paragraph)
        for sentence in sentences:
            sentence = sentence.strip()
            while len(sentence) > max_chars:
                cut = sentence.rfind(" ", 0, max_chars + 1)
                if cut < max_chars // 2:
                    cut = max_chars
                units.append(sentence[:cut].strip())
                sentence = sentence[cut:].strip()
            if sentence:
                units.append(sentence)

    parts: list[str] = []
    current: list[str] = []
    current_len = 0
    for unit in units:
        added = len(unit) + (1 if current else 0)
        if current and current_len + added > max_chars:
            parts.append("\n".join(current))
            current, current_len = [], 0
        current.append(unit)
        current_len += len(unit) + (1 if current_len else 0)
    if current:
        parts.append("\n".join(current))
    return parts


def normalize_row(row: dict, revision: str) -> dict:
    content = normalize_text(row.get("content_text"))
    return {
        "source_type": "phapdien",
        "source_dataset": DATASET,
        "source_revision": revision,
        "record_id": normalize_text(row.get("record_id")),
        "topic_id": normalize_text(row.get("topic_id")),
        "topic_number": row.get("topic_number"),
        "topic_title": normalize_text(row.get("topic_title_vi") or row.get("topic_title")),
        "subject_id": normalize_text(row.get("subject_id")),
        "subject_number": row.get("subject_number"),
        "subject_title": normalize_text(row.get("subject_title_vi") or row.get("subject_title")),
        "article_id": normalize_text(row.get("article_id")),
        "article_title": normalize_text(row.get("article_title")),
        "chapter_title": normalize_text(row.get("chapter_title")),
        "source_note_text": normalize_text(row.get("source_note_text")),
        "source_links": row.get("source_links") or [],
        "related_note_text": normalize_text(row.get("related_note_text")),
        "content_text": content,
        "content_hash": sha256_text(content),
        "source_url": normalize_text(row.get("source_url")),
        "scraped_at": normalize_text(row.get("scraped_at")),
    }


def make_chunks(article: dict, max_chars: int) -> list[dict]:
    title = article["article_title"] or article["article_id"]
    body_limit = max(200, max_chars - len(title) - 1)
    bodies = split_body(article["content_text"], body_limit)
    breadcrumb = " > ".join(
        item for item in (
            article["topic_title"], article["subject_title"],
            article["chapter_title"], title,
        ) if item
    )
    chunks = []
    for part, body in enumerate(bodies, 1):
        text = f"{title}\n{body}".strip()
        suffix = f" (phần {part}/{len(bodies)})" if len(bodies) > 1 else ""
        chunks.append({
            "chunk_id": f"phapdien__{article['record_id']}__{part}",
            "part": part,
            "n_parts": len(bodies),
            "text": text,
            "embed_text": f"{breadcrumb}{suffix}\n{text}".strip(),
            "n_chars": len(text),
            "chunk_type": "codified_article",
            "source_type": article["source_type"],
            "source_dataset": article["source_dataset"],
            "source_revision": article["source_revision"],
            "source_id": article["record_id"],
            "source_url": article["source_url"],
            "source_note_text": article["source_note_text"],
            "content_hash": article["content_hash"],
            "doc_number": article["article_id"],
            "doc_type": "phapdien",
            "doc_title": article["subject_title"],
            "status": "chua_xac_minh",
            "article_number": article["article_id"],
            "article_title": title,
            "hierarchy_path": " > ".join(
                item for item in (article["topic_title"], article["subject_title"], article["chapter_title"])
                if item
            ),
            "topic_id": article["topic_id"],
            "topic_number": article["topic_number"],
            "topic_title": article["topic_title"],
            "subject_id": article["subject_id"],
            "subject_number": article["subject_number"],
            "subject_title": article["subject_title"],
        })
    return chunks


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--revision", default=DEFAULT_REVISION)
    parser.add_argument("--topic-number", type=int, default=TOPIC_NUMBER)
    parser.add_argument("--max-chars", type=int, default=1500)
    parser.add_argument("--cache-dir", type=Path, default=LEGAL_DATA / "external" / "cache" / "phapdien")
    parser.add_argument("--output-dir", type=Path, default=LEGAL_DATA / "external" / "phapdien_labor")
    args = parser.parse_args()

    source_files = dataset_document_files(args.revision)
    local_files = []
    for index, info in enumerate(source_files, 1):
        print(f"[{index}/{len(source_files)}] {info['path']}")
        local_files.append(download_file(info["path"], info["size"], args.revision, args.cache_dir))

    articles: dict[str, dict] = {}
    empty_rows = 0
    for parquet_path in local_files:
        parquet = pq.ParquetFile(parquet_path)
        for batch in parquet.iter_batches(batch_size=2048):
            selected = batch.filter(pc.equal(batch.column("topic_number"), args.topic_number))
            for raw in selected.to_pylist():
                article = normalize_row(raw, args.revision)
                if not article["record_id"]:
                    raise RuntimeError(f"Thiếu record_id trong {parquet_path.name}")
                if not article["content_text"]:
                    empty_rows += 1
                    continue
                articles[article["record_id"]] = article

    ordered_articles = sorted(
        articles.values(),
        key=lambda item: (str(item["subject_number"]), item["article_id"], item["record_id"]),
    )
    chunks = [
        chunk
        for article in ordered_articles
        for chunk in make_chunks(article, args.max_chars)
    ]

    args.output_dir.mkdir(parents=True, exist_ok=True)
    articles_path = args.output_dir / "articles.jsonl"
    chunks_path = args.output_dir / "chunks.jsonl"
    manifest_path = args.output_dir / "manifest.json"

    articles_tmp = articles_path.with_suffix(".jsonl.tmp")
    chunks_tmp = chunks_path.with_suffix(".jsonl.tmp")
    with articles_tmp.open("w", encoding="utf-8") as handle:
        for article in ordered_articles:
            handle.write(json.dumps(article, ensure_ascii=False) + "\n")
    with chunks_tmp.open("w", encoding="utf-8") as handle:
        for chunk in chunks:
            handle.write(json.dumps(chunk, ensure_ascii=False) + "\n")
    articles_tmp.replace(articles_path)
    chunks_tmp.replace(chunks_path)

    manifest = {
        "dataset": DATASET,
        "revision": args.revision,
        "imported_at": datetime.now(timezone.utc).isoformat(),
        "filter": {"topic_number": args.topic_number},
        "article_count": len(ordered_articles),
        "chunk_count": len(chunks),
        "empty_rows_skipped": empty_rows,
        "max_chars": args.max_chars,
        "subjects": dict(Counter(article["subject_title"] for article in ordered_articles)),
        "source_files": [
            {"name": info["path"], "size": info["size"]}
            for info in source_files
        ],
        "outputs": {
            "articles": articles_path.name,
            "chunks": chunks_path.name,
        },
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Hoàn tất: {len(ordered_articles)} điều -> {len(chunks)} chunk")
    print(f"Theo đề mục: {manifest['subjects']}")
    print(f"Đầu ra: {args.output_dir}")


if __name__ == "__main__":
    main()
