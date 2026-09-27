"""
build_chunks.py - Đọc mọi file .json trong legal_data\\json (schema metadata+articles/phu_luc/noi_dung),
cắt thành các chunk vừa cỡ, ghi ra legal_data\\chunks\\chunks.jsonl.

    python build_chunks.py --input legal_data\\json --output legal_data\\chunks\\chunks.jsonl --max-chars 1500
"""
import argparse
import json
import re
from pathlib import Path

RE_KHOAN = re.compile(r"^\d+\.\s")     # "1. ", "2. "...
RE_DIEM = re.compile(r"^[a-zđ]\)\s")   # "a) ", "b) "...

META_KEYS = ("doc_number", "doc_type", "status", "issuing_body", "issue_date",
             "effective_date", "replaces", "replaced_by")


def _split_lines(lines: list[str], max_chars: int, header: str, breadcrumb: str, id_prefix: str):
    """Cắt danh sách dòng thành chunk, ưu tiên cắt ở ranh giới Khoản, rồi Điểm, rồi đoạn thường."""
    parts, cur, cur_len = [], [], 0
    last_khoan = None
    for ln in lines:
        if RE_KHOAN.match(ln):
            last_khoan = ln
        boundary = bool(RE_KHOAN.match(ln) or RE_DIEM.match(ln)) if lines else True
        if cur and cur_len + len(ln) > max_chars and (boundary or cur_len > max_chars * 1.3):
            parts.append(cur)
            cur, cur_len = [], 0
            if boundary and RE_DIEM.match(ln) and last_khoan and last_khoan not in cur:
                cur.append(last_khoan + " (tiếp)")
                cur_len += len(last_khoan) + 1
        cur.append(ln)
        cur_len += len(ln) + 1
    if cur:
        parts.append(cur)

    chunks = []
    for i, part in enumerate(parts, 1):
        text = (header + "\n" if header else "") + "\n".join(part)
        bc = breadcrumb + (f" (phần {i}/{len(parts)})" if len(parts) > 1 else "")
        chunks.append({
            "chunk_id": f"{id_prefix}__{i}",
            "part": i, "n_parts": len(parts),
            "text": text.strip(),
            "embed_text": f"{bc}\n{text}".strip(),
            "n_chars": len(text),
        })
    return chunks


def chunk_document(doc: dict, file_stem: str, max_chars: int) -> list[dict]:
    meta = doc["metadata"]
    doc_id = re.sub(r"[^0-9A-Za-z]+", "_", (meta.get("doc_number") or file_stem)).strip("_")
    base_meta = {k: meta.get(k) for k in META_KEYS}
    base_meta["doc_title"] = meta.get("doc_title")
    chunks = []
    articles = doc.get("articles", [])

    if articles:
        article_numbers = {
            str(article["article_number"])
            for article in articles
            if article.get("article_number")
        }
        article_list = "\n".join(
            f"- Điều {article['article_number']}: {article['title']}"
            for article in articles
        )
        overview_text = (
            f"Tổng quan {meta.get('doc_title')}\n"
            f"Số văn bản: {meta.get('doc_number')}\n"
            f"Văn bản gồm {len(article_numbers)} điều.\n"
            f"Danh mục các điều:\n{article_list}"
        )
        overview = {
            "chunk_id": f"{doc_id}__overview",
            "part": 1,
            "n_parts": 1,
            "text": overview_text,
            "embed_text": overview_text,
            "n_chars": len(overview_text),
            "article_number": None,
            "article_title": "Tổng quan văn bản",
            "hierarchy_path": "Tổng quan",
            "chunk_type": "document_overview",
        }
        overview.update(base_meta)
        chunks.append(overview)

    for a in articles:
        header = f"Điều {a['article_number']}. {a['title']}"
        bc = f"{meta.get('doc_title')} > {a['hierarchy_path']} > {header}"
        lines = a["content"].split("\n")[1:]  # bỏ dòng header, đã có riêng
        for c in _split_lines(lines, max_chars, header, bc, f"{doc_id}__d{a['article_number']}"):
            c.update(base_meta)
            c["article_number"] = a["article_number"]
            c["article_title"] = a["title"]
            c["hierarchy_path"] = a["hierarchy_path"]
            chunks.append(c)

    for i, p in enumerate(doc.get("phu_luc", []), 1):
        header = p["tieu_de"]
        bc = f"{meta.get('doc_title')} > {header}"
        lines = p["noi_dung"].split("\n")
        for c in _split_lines(lines, max_chars, header, bc, f"{doc_id}__pl{i}"):
            c.update(base_meta)
            c["article_number"], c["article_title"], c["hierarchy_path"] = None, header, "Phụ lục"
            chunks.append(c)

    if "noi_dung" in doc:
        bc = meta.get("doc_title") or file_stem
        lines = doc["noi_dung"].split("\n")
        for c in _split_lines(lines, max_chars, "", bc, doc_id):
            c.update(base_meta)
            c["article_number"], c["article_title"], c["hierarchy_path"] = None, None, None
            chunks.append(c)

    return chunks


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default="legal_data/json")
    ap.add_argument("--output", default="legal_data/chunks/chunks.jsonl")
    ap.add_argument("--max-chars", type=int, default=1500)
    ap.add_argument("--types", default="nghi_dinh,thong_tu",
                    help="Danh sách doc_type cần chunk, cách nhau bởi dấu phẩy. "
                         "Để trống (--types \"\") thì chunk hết mọi loại tìm thấy.")
    args = ap.parse_args()

    in_dir, out_path = Path(args.input), Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    wanted = {t.strip() for t in args.types.split(",") if t.strip()} or None

    total, skipped = 0, 0
    with open(out_path, "w", encoding="utf-8") as f:
        # Chỉ quét file .json Ở CẤP GỐC (không đụng vào mau_bieu\, phu_luc\ nếu chúng nằm
        # trong thư mục con, và không chunk mẫu biểu/phụ lục ngay cả khi chúng lỡ nằm ở gốc).
        for jf in sorted(in_dir.glob("*.json")):
            if jf.name == "scan_report.txt":
                continue
            doc = json.loads(jf.read_text(encoding="utf-8"))
            if "metadata" not in doc:
                continue
            doc_type = doc["metadata"].get("doc_type")
            if "articles" not in doc:              # mẫu biểu / phụ lục rời -> luôn bỏ qua
                skipped += 1
                continue
            if wanted is not None and doc_type not in wanted:  # không thuộc loại muốn chunk
                skipped += 1
                continue

            chunks = chunk_document(doc, jf.stem, args.max_chars)
            for c in chunks:
                f.write(json.dumps(c, ensure_ascii=False) + "\n")
            total += len(chunks)
            print(f"[OK] {jf.name} ({doc_type}): {len(chunks)} chunk")

    print(f"\nXong: {total} chunk từ {'/'.join(wanted) if wanted else 'mọi loại'} -> {out_path}")
    print(f"Bỏ qua {skipped} file (mẫu biểu / phụ lục / không thuộc loại chọn).")


if __name__ == "__main__":
    main()
