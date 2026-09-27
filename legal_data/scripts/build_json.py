"""
build_json.py - Quét thư mục chứa .docx (kể cả thư mục con), mỗi văn bản -> 1 file JSON
theo schema {metadata, articles}, rồi liên kết trạng thái hiệu lực giữa các văn bản.

Đặt cùng docx_reader.py, metadata_parser.py trong  dacs\\legal_data\\scripts\\
Chạy không tham số: quét legal_data\\raw\\nghi_dinh  ->  ghi vào legal_data\\json

    python build_json.py
    python build_json.py --input "C:\\...\\legal_data\\raw" --output "C:\\...\\legal_data\\json"
"""
import argparse
import json
from pathlib import Path

from metadata_parser import build_document, classify_by_filename

LEGAL_DATA = Path(__file__).resolve().parent.parent  # .../legal_data


def convert_folder(folder: Path, out_dir: Path) -> list[str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    report, used = [], set()
    files = sorted(p for p in folder.rglob("*") if p.is_file() and not p.name.startswith("~$"))
    for p in files:
        rel = p.relative_to(folder).as_posix()
        if p.suffix.lower() != ".docx":
            print(f"[BỎ QUA] {rel} (không phải .docx)")
            continue
        try:
            doc, warns = build_document(p)
        except Exception as e:  # 1 file lỗi không làm hỏng cả lượt quét
            print(f"[LỖI]    {rel}: {e}")
            report.append(f"{rel}: LỖI {e}")
            continue

        name = p.stem + ".json"
        if name in used:  # trùng tên ở thư mục khác
            name = f"{p.parent.name}__{name}"
        used.add(name)

        # Xếp theo TÊN FILE trước (mẫu số / phụ lục rời luôn vào thư mục con, kể cả khi bên
        # trong lỡ có vài dòng khớp "Điều N."). Chỉ văn bản không khớp mẫu nào mới xét có articles.
        kind = classify_by_filename(p.name)
        if kind is None:
            kind = None if "articles" in doc else doc["metadata"]["doc_type"]
        subdir = out_dir if kind is None else out_dir / kind
        subdir.mkdir(parents=True, exist_ok=True)
        out_path = subdir / name

        if out_path.exists():  # giữ lại topic_tags bạn đã gán tay
            try:
                old = json.loads(out_path.read_text(encoding="utf-8"))
                doc["metadata"]["topic_tags"] = old["metadata"].get("topic_tags", [])
            except Exception:
                pass
        out_path.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")

        m = doc["metadata"]
        flag = "OK " if not warns else "!! "
        if "articles" in doc:
            n_desc = f"{len(doc['articles'])} điều" + (f" + {len(doc['phu_luc'])} phụ lục" if doc.get("phu_luc") else "")
        elif "phu_luc" in doc:
            n_desc = f"{len(doc['phu_luc'])} phụ lục"
        else:
            n_desc = f"noi_dung ({m['doc_type']})"
        print(f"[{flag}] {m['doc_title']} | ban hành {m['issue_date'] or '?'} | {n_desc}")
        report.append(f"{rel} -> {name} | {n_desc}" + (f" | {'; '.join(warns)}" if warns else ""))
    return report


def relink_dir(out_dir: Path) -> None:
    """Đọc TẤT CẢ json trong out_dir: điền replaced_by và status từ trường replaces của các văn bản khác."""
    docs = {}
    for f in out_dir.glob("*.json"):
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
            if "metadata" in d:
                docs[f] = d
        except Exception:
            continue
    replaced_by: dict[str, list[str]] = {}
    for d in docs.values():
        for s in d["metadata"].get("replaces", []):
            replaced_by.setdefault(s, []).append(d["metadata"]["doc_number"])
    for f, d in docs.items():
        m = d["metadata"]
        rb = replaced_by.get(m["doc_number"], [])
        status = "het_hieu_luc" if rb else "con_hieu_luc"
        if m.get("replaced_by") != rb or m.get("status") != status:
            m["replaced_by"], m["status"] = rb, status
            f.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default=str(LEGAL_DATA / "raw" / "nghi_dinh"))
    ap.add_argument("--output", default=str(LEGAL_DATA / "json"))
    args = ap.parse_args()

    folder, out_dir = Path(args.input), Path(args.output)
    if not folder.exists():
        raise SystemExit(f"Không thấy thư mục: {folder}")

    report = convert_folder(folder, out_dir)
    relink_dir(out_dir)
    (out_dir / "scan_report.txt").write_text("\n".join(report), encoding="utf-8")

    n_warn = sum(1 for r in report if " | " in r and r.count(" | ") >= 2)
    print(f"\nXong: {len(report)} văn bản -> {out_dir}  (chi tiết cảnh báo: scan_report.txt)")


if __name__ == "__main__":
    main()