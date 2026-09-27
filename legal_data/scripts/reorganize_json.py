"""
reorganize_json.py - Chạy 1 LẦN để dọn các file .json đã tạo trước đây (khi build_json.py
còn để chung mọi thứ ở 1 thư mục): dời mẫu biểu / phụ lục rời vào thư mục con theo doc_type,
giữ nguyên văn bản pháp luật thật (có "articles") ở gốc.

    python reorganize_json.py --json-dir legal_data/json
"""
import argparse
import json
import shutil
from pathlib import Path

from metadata_parser import classify_by_filename


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json-dir", default="legal_data/json")
    args = ap.parse_args()

    root = Path(args.json_dir)
    moved = 0
    for jf in list(root.glob("*.json")):
        try:
            doc = json.loads(jf.read_text(encoding="utf-8"))
        except Exception:
            continue
        if "metadata" not in doc:
            continue

        # Tên file khớp "Mau so"/"Phụ lục" -> LUÔN chuyển đi, kể cả khi bên trong có vài "Điều N."
        kind = classify_by_filename(jf.name)
        if kind is None:
            if "articles" in doc:
                continue  # văn bản pháp luật thật, không khớp mẫu nào -> để yên ở gốc
            kind = doc["metadata"]["doc_type"]  # phụ lục/khac không đoán được từ tên file

        subdir = root / kind
        subdir.mkdir(exist_ok=True)
        shutil.move(str(jf), str(subdir / jf.name))
        print(f"[chuyển] {jf.name} -> {subdir.name}/")
        moved += 1

    print(f"\nXong: chuyển {moved} file.")


if __name__ == "__main__":
    main()