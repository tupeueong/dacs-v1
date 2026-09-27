"""Audit JSON pháp luật bằng cách đối chiếu với toàn bộ DOCX nguồn.

Ví dụ:
    python legal_data/scripts/audit_json.py --input legal_data/raw --output legal_data/json
    python legal_data/scripts/audit_json.py --report-json legal_data/json/audit_before.json
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path

from docx_reader import read_docx


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


LEGAL_DATA = Path(__file__).resolve().parent.parent
CATEGORIES = {"bhxh", "bo_luat", "luat", "nghi_dinh", "quyet_dinh", "thong_tu"}
TEMPLATE_RE = re.compile(r"m[aẫ]u\s*s[oôố]|ph[uụ]\s*l[uụ]c|mau_so|phu_luc", re.I)
ARTICLE_HINT_RE = re.compile(r"^Điều\s+(\d+[a-zđ]?)\s*(?:[.:]|$)", re.I)
SIGNATURE_RE = re.compile(
    r"^(?:TM\.|KT\.|TL\.|TUQ\.|Q\.)\s*\S|^CHỦ TỊCH QUỐC HỘI\b|^CHỦ TỊCH NƯỚC\b"
    r"|^THỦ TƯỚNG\b|^PHÓ THỦ TƯỚNG\b|^BỘ TRƯỞNG\b|^THỨ TRƯỞNG\b"
    r"|^TỔNG GIÁM ĐỐC\b|^CHỦ NHIỆM\b",
    re.I,
)
BAD_SIGNER_RE = re.compile(r"độc\s+lập|tự\s+do|hạnh\s+phúc|cộng\s+hòa", re.I)
CHAPTER_RE = re.compile(r"Chương\s+([IVXLCDM]+|\d+)\b", re.I)
SECTION_RE = re.compile(r"(?:^|>\s*)Mục\s+([IVXLCDM]+|\d+)\b", re.I)
CATEGORY_ORDER = (
    "signer", "articles_empty", "article_sequence", "hierarchy",
    "metadata", "duplicate_overwrite", "relations",
)


@dataclass(frozen=True)
class Finding:
    category: str
    json_file: str
    source_file: str
    detail: str


def norm_text(value: object) -> str:
    return unicodedata.normalize("NFC", str(value or "")).strip()


def rel(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def source_files(raw_dir: Path) -> list[Path]:
    return sorted(
        p for p in raw_dir.rglob("*")
        if p.is_file() and p.suffix.lower() == ".docx" and not p.name.startswith("~$")
    )


def legacy_output_mapping(files: list[Path]) -> tuple[dict[Path, str], dict[str, list[Path]]]:
    """Mô phỏng đúng quy tắc đặt tên hiện hành trong build_json.py."""
    used: set[str] = set()
    mapping: dict[Path, str] = {}
    destinations: dict[str, list[Path]] = defaultdict(list)
    for path in files:
        name = path.stem + ".json"
        if name in used:
            name = f"{path.parent.name}__{name}"
        mapping[path] = name
        destinations[name].append(path)
        used.add(name)
    return mapping, destinations


def is_official(path: Path, raw_dir: Path) -> bool:
    parts = path.relative_to(raw_dir).parts
    return bool(parts and parts[0].casefold() in CATEGORIES and not TEMPLATE_RE.search("/".join(parts[1:])))


def signature_contexts(lines: list[str]) -> list[list[str]]:
    indexes = [i for i, line in enumerate(lines) if SIGNATURE_RE.search(line)]
    return [lines[max(0, i - 1): min(len(lines), i + 8)] for i in indexes]


def signature_has_person(context: list[str]) -> bool:
    """True only when the signature block contains a plausible real name."""
    for line in context:
        if SIGNATURE_RE.search(line) or line.isupper() or line.startswith(("-", "(")):
            continue
        if len(line) <= 50 and len(line.split()) >= 2 and not re.search(r"\d|[:;]", line):
            return True
    return False


def roman_to_int(value: str) -> int | None:
    if value.isdigit():
        return int(value)
    vals = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100, "D": 500, "M": 1000}
    total = prev = 0
    try:
        for char in reversed(value.upper()):
            cur = vals[char]
            total += -cur if cur < prev else cur
            prev = max(prev, cur)
        return total
    except KeyError:
        return None


def article_num(value: object) -> tuple[int, str] | None:
    match = re.fullmatch(r"(\d+)([a-zđ]?)", norm_text(value), re.I)
    return (int(match.group(1)), match.group(2).casefold()) if match else None


def add(findings: list[Finding], category: str, json_name: str, source: Path | None,
        raw_dir: Path, detail: str) -> None:
    findings.append(Finding(category, json_name, rel(source, raw_dir) if source else "?", detail))


def audit(raw_dir: Path, json_dir: Path) -> dict:
    files = source_files(raw_dir)
    mapping, destinations = legacy_output_mapping(files)
    reverse = {name: path for path, name in mapping.items()}
    findings: list[Finding] = []

    for name, paths in sorted(destinations.items()):
        if len(paths) > 1:
            detail = "nhiều DOCX cùng ánh xạ tới một JSON: " + "; ".join(rel(p, raw_dir) for p in paths)
            add(findings, "duplicate_overwrite", name, paths[0], raw_dir, detail)

    loaded: dict[str, dict] = {}
    source_lines: dict[Path, list[str]] = {}
    for json_path in sorted(json_dir.glob("*.json")):
        if json_path.name.startswith("audit_"):
            continue
        try:
            data = json.loads(json_path.read_text(encoding="utf-8"))
        except Exception as exc:
            add(findings, "invalid_json", json_path.name, reverse.get(json_path.name), raw_dir, str(exc))
            continue
        if not isinstance(data, dict) or "metadata" not in data:
            continue
        loaded[json_path.name] = data
        source = reverse.get(json_path.name)
        if source is None:
            add(findings, "orphan_json", json_path.name, None, raw_dir, "không ánh xạ được về DOCX theo quy tắc build")
            continue
        try:
            lines = read_docx(source)
        except Exception as exc:
            add(findings, "docx_read_error", json_path.name, source, raw_dir, str(exc))
            continue
        source_lines[source] = lines
        metadata = data.get("metadata") or {}
        articles = data.get("articles") or []

        signer = norm_text(metadata.get("signer"))
        sig_blocks = signature_contexts(lines)
        sig_context = next((block for block in sig_blocks if signature_has_person(block)),
                           sig_blocks[-1] if sig_blocks else [])
        signer_reasons = []
        if signer and BAD_SIGNER_RE.search(signer):
            signer_reasons.append("chứa quốc hiệu/tiêu ngữ")
        if signer and re.search(r"\d", signer):
            signer_reasons.append("chứa chữ số")
        if signer and signer.isupper():
            signer_reasons.append("toàn chữ hoa")
        if not signer and any(signature_has_person(block) for block in sig_blocks):
            signer_reasons.append("rỗng dù DOCX có khối chữ ký và tên người ký")
        if signer_reasons:
            context = " | ".join(sig_context) if sig_context else "không thấy khối chữ ký"
            add(findings, "signer", json_path.name, source, raw_dir,
                f"signer={signer!r}: {', '.join(signer_reasons)}; ngữ cảnh DOCX: {context}")

        raw_text = "\n".join(lines)
        no_payload = not articles and not norm_text(data.get("noi_dung")) and not data.get("phu_luc")
        structured_hint = sum(bool(ARTICLE_HINT_RE.match(line)) for line in lines)
        long_official_without_articles = not articles and is_official(source, raw_dir) and len(raw_text) > 1000 and structured_hint
        if (no_payload and len(raw_text) > 1000 and is_official(source, raw_dir)) or long_official_without_articles:
            payload = "không có payload" if no_payload else "đang bị dồn vào noi_dung/phu_luc"
            examples = [line for line in lines if ARTICLE_HINT_RE.match(line)][:5]
            add(findings, "articles_empty", json_path.name, source, raw_dir,
                f"DOCX dài {len(raw_text)} ký tự, {payload}, có {structured_hint} dòng giống Điều; ví dụ: {examples}")

        parsed = [(idx, article_num(a.get("article_number")), norm_text(a.get("article_number")))
                  for idx, a in enumerate(articles)]
        seen: dict[tuple[int, str], int] = {}
        for idx, number, raw_number in parsed:
            if number is None:
                add(findings, "article_sequence", json_path.name, source, raw_dir,
                    f"article[{idx}] có article_number không hiểu được: {raw_number!r}")
                continue
            if number in seen:
                add(findings, "article_sequence", json_path.name, source, raw_dir,
                    f"trùng Điều {raw_number} tại vị trí {seen[number] + 1} và {idx + 1}")
            else:
                seen[number] = idx
        for (idx1, n1, raw1), (idx2, n2, raw2) in zip(parsed, parsed[1:]):
            if not n1 or not n2:
                continue
            if n2[0] < n1[0] or (n2[0] == n1[0] and n2[1] < n1[1]):
                add(findings, "article_sequence", json_path.name, source, raw_dir,
                    f"thứ tự đảo tại vị trí {idx1 + 1}->{idx2 + 1}: Điều {raw1} -> Điều {raw2}")
            elif n2[0] - n1[0] > 1:
                add(findings, "article_sequence", json_path.name, source, raw_dir,
                    f"nhảy cóc tại vị trí {idx1 + 1}->{idx2 + 1}: Điều {raw1} -> Điều {raw2}")

        chapter_history: list[tuple[int, str, int]] = []
        for idx, article in enumerate(articles):
            path = norm_text(article.get("hierarchy_path"))
            if SECTION_RE.search(path) and not CHAPTER_RE.search(path):
                add(findings, "hierarchy", json_path.name, source, raw_dir,
                    f"Điều {article.get('article_number')} có Mục nhưng thiếu Chương: {path!r}")
            match = CHAPTER_RE.search(path)
            if match:
                chapter_history.append((idx, match.group(1), roman_to_int(match.group(1)) or -1))
        compact: list[tuple[int, str, int]] = []
        for item in chapter_history:
            if not compact or item[2] != compact[-1][2]:
                compact.append(item)
        for previous, current in zip(compact, compact[1:]):
            if current[2] <= previous[2]:
                add(findings, "hierarchy", json_path.name, source, raw_dir,
                    f"Chương quay lùi/lặp sau khi đã chuyển: Điều {articles[previous[0]].get('article_number')} "
                    f"Chương {previous[1]} -> Điều {articles[current[0]].get('article_number')} Chương {current[1]}")

        if is_official(source, raw_dir):
            missing = []
            if not norm_text(metadata.get("doc_number")):
                missing.append("doc_number rỗng")
            if norm_text(metadata.get("doc_type")) == "khac":
                missing.append("doc_type=khac")
            if not norm_text(metadata.get("issuing_body")):
                missing.append("issuing_body rỗng")
            if missing:
                add(findings, "metadata", json_path.name, source, raw_dir,
                    ", ".join(missing) + "; đầu DOCX: " + " | ".join(lines[:12]))

    by_number: dict[str, list[tuple[str, dict]]] = defaultdict(list)
    for name, data in loaded.items():
        number = norm_text((data.get("metadata") or {}).get("doc_number"))
        if number:
            by_number[number.casefold()].append((name, data))
    incoming: dict[str, list[str]] = defaultdict(list)
    for name, data in loaded.items():
        metadata = data.get("metadata") or {}
        own = norm_text(metadata.get("doc_number"))
        for target in metadata.get("replaces") or []:
            target_text = norm_text(target)
            if own and target_text.casefold() == own.casefold():
                add(findings, "relations", name, reverse.get(name), raw_dir,
                    f"replaces tự trỏ vào chính doc_number {own}")
            incoming[target_text.casefold()].append(own)
    for number_key, docs in by_number.items():
        expected_status = "het_hieu_luc" if incoming.get(number_key) else "con_hieu_luc"
        expected_replacers = {x.casefold() for x in incoming.get(number_key, []) if x}
        for name, data in docs:
            metadata = data.get("metadata") or {}
            actual_status = norm_text(metadata.get("status"))
            actual_replacers = {norm_text(x).casefold() for x in metadata.get("replaced_by") or []}
            if actual_status != expected_status:
                add(findings, "relations", name, reverse.get(name), raw_dir,
                    f"status={actual_status!r}, nhưng đồ thị replaces yêu cầu {expected_status!r}")
            if actual_replacers != expected_replacers:
                add(findings, "relations", name, reverse.get(name), raw_dir,
                    f"replaced_by={metadata.get('replaced_by')!r}, kỳ vọng {incoming.get(number_key, [])!r}")

    expected_names = set(mapping.values())
    for path in files:
        name = mapping[path]
        if name not in loaded:
            add(findings, "missing_json", name, path, raw_dir, "DOCX chưa có JSON đầu ra tương ứng")

    raw_counts = Counter(item.category for item in findings)
    counts = {category: raw_counts.get(category, 0) for category in CATEGORY_ORDER}
    counts.update({key: value for key, value in sorted(raw_counts.items()) if key not in counts})
    files_with_findings = {item.json_file for item in findings if item.json_file in loaded or item.json_file in expected_names}
    return {
        "summary": {
            "total_docx": len(files),
            "total_json_documents": len(loaded),
            "ok_files": len(expected_names - files_with_findings),
            "warning_files": len(files_with_findings),
            "counts": counts,
        },
        "findings": [asdict(item) for item in findings],
    }


def print_report(report: dict) -> None:
    findings = report["findings"]
    grouped: dict[str, list[dict]] = defaultdict(list)
    for item in findings:
        grouped[item["category"]].append(item)
    print("=== KIỂM TRA JSON ĐỐI CHIẾU DOCX ===")
    for category in sorted(grouped):
        print(f"\n[{category}] {len(grouped[category])} lỗi/cảnh báo")
        for item in grouped[category]:
            print(f"- {item['json_file']} <- {item['source_file']}: {item['detail']}")
    summary = report["summary"]
    print("\n=== TỔNG KẾT ===")
    print(f"DOCX: {summary['total_docx']} | JSON văn bản: {summary['total_json_documents']} | "
          f"OK hoàn toàn: {summary['ok_files']} | còn cảnh báo: {summary['warning_files']}")
    if summary["counts"]:
        print("Theo loại: " + ", ".join(f"{key}={value}" for key, value in summary["counts"].items()))
    else:
        print("Theo loại: không có cảnh báo")


def print_comparison(before: dict, after: dict) -> None:
    before_findings = before.get("findings", [])
    after_findings = after.get("findings", [])
    before_counts = Counter(item["category"] for item in before_findings)
    after_counts = Counter(item["category"] for item in after_findings)
    categories = list(CATEGORY_ORDER)
    categories.extend(sorted((set(before_counts) | set(after_counts)) - set(categories)))
    print("\n=== SO SÁNH TRƯỚC / SAU ===")
    for category in categories:
        before_files = {x["json_file"] for x in before_findings if x["category"] == category}
        after_files = {x["json_file"] for x in after_findings if x["category"] == category}
        print(f"{category}: {before_counts[category]} -> {after_counts[category]} lỗi/cảnh báo; "
              f"{len(before_files)} -> {len(after_files)} file")
    before_files = {x["json_file"] for x in before_findings}
    after_files = {x["json_file"] for x in after_findings}
    resolved = sorted(before_files - after_files)
    new = sorted(after_files - before_files)
    print("File hết lỗi: " + (", ".join(resolved) if resolved else "không có"))
    print("File phát sinh lỗi mới: " + (", ".join(new) if new else "không có"))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", default=str(LEGAL_DATA / "raw"), help="Thư mục DOCX nguồn")
    parser.add_argument("--output", default=str(LEGAL_DATA / "json"), help="Thư mục JSON đầu ra")
    parser.add_argument("--report-json", help="Ghi báo cáo máy đọc được để so sánh trước/sau")
    parser.add_argument("--compare-report", help="Report JSON cũ dùng để in so sánh trước/sau")
    args = parser.parse_args()
    report = audit(Path(args.input), Path(args.output))
    print_report(report)
    if args.compare_report:
        before = json.loads(Path(args.compare_report).read_text(encoding="utf-8"))
        print_comparison(before, report)
    if args.report_json:
        report_path = Path(args.report_json)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\nĐã ghi báo cáo: {report_path}")
    return 1 if report["findings"] else 0


if __name__ == "__main__":
    sys.exit(main())
