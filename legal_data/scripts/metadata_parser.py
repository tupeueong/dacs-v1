"""
metadata_parser.py - Chuyển danh sách dòng (từ docx_reader) thành 1 văn bản JSON:

    {
      "metadata": {doc_number, doc_type, doc_title, status, effective_date, issue_date,
                   signer, issuing_body, topic_tags, replaces, replaced_by},
      "articles": [{article_number, title, hierarchy_path, content}, ...]
    }

    from metadata_parser import build_document
    doc, warnings = build_document("Nghị-định-12-2022-NĐ-CP.docx")
"""
import re
import unicodedata
from pathlib import Path

from docx_reader import read_docx

# ---------------------------------------------------------------- regex
RE_LOAI = re.compile(
    r"^(NGHỊ ĐỊNH|NGHỊ QUYẾT|THÔNG TƯ LIÊN TỊCH|THÔNG TƯ|QUYẾT ĐỊNH|BỘ LUẬT|LUẬT|PHÁP LỆNH)\s*:?$"
)
RE_SEP = re.compile(r"^[\s_\-\*=\.]{3,}$")
RE_SO = re.compile(r"số\s*[:：]?\s*(\d+(?:/[\w\-]+)+)", re.I)
RE_NGAY = re.compile(r"ngày\s+(\d{1,2})\s+tháng\s+(\d{1,2})\s+năm\s+(\d{4})", re.I)
RE_DIADANH = re.compile(r"^(.+?),\s*ngày\s+\d{1,2}\s+tháng\s+\d{1,2}\s+năm\s+\d{4}", re.I)
RE_CHUONG = re.compile(r"^Chương\s+([IVXLCDM]+|\d+)\b[\.:]?\s*(.*)$", re.I)
RE_MUC = re.compile(r"^Mục\s+(\d+|[IVXLC]+)\b[\.:]?\s*(.*)$", re.I)
RE_DIEU = re.compile(r"^Điều\s+(\d+[a-zđ]?)(?:\s*[\.:]\s*|\s+|$)(.*)$", re.I)
RE_NOINHAN = re.compile(r"^Nơi nhận", re.I)
RE_KY = re.compile(
    r"^(?:TM\.|KT\.|TL\.|TUQ\.|Q\.)\s*\S"
    r"|^CHỦ TỊCH QUỐC HỘI\b|^CHỦ TỊCH NƯỚC\b|^THỦ TƯỚNG\b|^PHÓ THỦ TƯỚNG\b"
    r"|^BỘ TRƯỞNG\b|^THỨ TRƯỞNG\b|^TỔNG GIÁM ĐỐC\b|^CHỦ NHIỆM\b"
)
RE_KY_MANH = re.compile(r"^(?:TM\.|KT\.|TL\.|TUQ\.|Q\.)\s*\S", re.I)
RE_SOHIEU_ANY = re.compile(r"\d+/\d{4}/[\w\-]+")
RE_SOHIEU_FILE = re.compile(r"(\d+)[-_/](\d{4})[-_/]([A-Za-zĐđ0-9]+(?:[-_/][A-Za-zĐđ0-9]+)*)")
RE_HIEU_LUC = re.compile(
    r"(?:Nghị định|Thông tư|Luật|Bộ luật|Quyết định|Nghị quyết|Pháp lệnh)\s+này\s+có\s+hiệu\s+lực(.*)",
    re.I,
)
RE_HET_HL = re.compile(r"hết hiệu lực|bãi bỏ|thay thế", re.I)
RE_PARTIAL = re.compile(r"(?:Điều|khoản|điểm|Chương|Mục|Phụ lục)\s+\d")  # chỉ bãi bỏ 1 phần
STOP_TRICH_YEU = ("Căn cứ", "Theo đề nghị", "Chương", "Điều", "Quốc hội ban hành", "Chính phủ ban hành")
RE_IS_MAU = re.compile(r"m[aẫ]u\s*s[oôố]", re.I)               # "Mau so", "mẫu số"
RE_IS_PHULUC = re.compile(r"ph[uụ]\s*l[uụ]c", re.I)             # "Phu luc", "phụ lục"
RE_PL_HEADER = re.compile(r"^PHỤ LỤC\b|^Phụ lục\b", re.I)

LOAI_CHUAN = {
    "NGHỊ ĐỊNH": "Nghị định", "NGHỊ QUYẾT": "Nghị quyết", "THÔNG TƯ": "Thông tư",
    "THÔNG TƯ LIÊN TỊCH": "Thông tư liên tịch", "QUYẾT ĐỊNH": "Quyết định",
    "BỘ LUẬT": "Bộ luật", "LUẬT": "Luật", "PHÁP LỆNH": "Pháp lệnh",
}
DOC_TYPE_KEY = {
    "Nghị định": "nghi_dinh", "Nghị quyết": "nghi_quyet", "Thông tư": "thong_tu",
    "Thông tư liên tịch": "thong_tu_lien_tich", "Quyết định": "quyet_dinh",
    "Bộ luật": "bo_luat", "Luật": "luat", "Pháp lệnh": "phap_lenh",
}


def _iso(d, m, y) -> str:
    return f"{int(y):04d}-{int(m):02d}-{int(d):02d}"


def _sentence(s: str) -> str:
    return s.capitalize() if s.isupper() else s


# ---------------------------------------------------------------- 1. phần đầu văn bản
def parse_header(lines: list[str], file_name: str = "") -> dict:
    warnings: list[str] = []
    head = lines[:30]

    so_hieu, so_idx = None, None
    for i, ln in enumerate(head):
        m = RE_SO.search(ln)
        if m:
            so_hieu, so_idx = m.group(1), i
            break
    if not so_hieu:
        m = RE_SOHIEU_FILE.search(unicodedata.normalize("NFC", file_name))
        if m:
            so_hieu = f"{m.group(1)}/{m.group(2)}/{m.group(3).replace('_', '-')}"
            warnings.append("doc_number lấy từ tên file (không thấy 'Số:' trong văn bản)")
        else:
            warnings.append("không tìm thấy số hiệu")

    # cơ quan ban hành = các dòng trước dòng 'Số:' (bỏ quốc hiệu, gạch ngang)
    issuing_body = ""
    if so_idx is not None:
        parts = [
            ln for ln in head[:so_idx]
            if not RE_SEP.match(ln) and not re.search(r"CỘNG HÒA|Độc lập|ngày\s+\d", ln, re.I)
        ]
        issuing_body = _sentence(" ".join(parts)) if parts else ""
    if not issuing_body:
        warnings.append("không tìm thấy cơ quan ban hành")

    # ngày ban hành = ngày đi kèm địa danh ("Hà Nội, ngày 17 tháng 01 năm 2022")
    issue_date = ""
    for ln in head:
        if RE_DIADANH.match(ln):
            issue_date = _iso(*RE_NGAY.search(ln).groups())
            break
    if not issue_date:
        warnings.append("không thấy 'địa danh, ngày... tháng... năm...' nên issue_date để trống")

    # loại văn bản + trích yếu
    loai, loai_idx = None, None
    for i, ln in enumerate(lines[:40]):
        m = RE_LOAI.match(ln)
        if m:
            loai, loai_idx = LOAI_CHUAN[m.group(1)], i
            break
    if not loai and so_hieu:
        suffix = so_hieu.split("/")[-1].upper()
        loai = ("Nghị định" if suffix.startswith("NĐ") else "Thông tư" if suffix.startswith("TT")
                else "Luật" if suffix.startswith("QH") else "Quyết định" if suffix.startswith("QĐ") else None)
    if not loai:
        warnings.append("không xác định được loại văn bản")

    trich_yeu = ""
    if loai_idx is not None:
        buf = []
        for ln in lines[loai_idx + 1: loai_idx + 8]:
            if RE_SEP.match(ln) or ln.startswith(STOP_TRICH_YEU):
                break
            buf.append(ln)
        trich_yeu = _sentence(" ".join(buf)) if buf else ""

    return {"so_hieu": so_hieu, "loai": loai, "issuing_body": issuing_body,
            "issue_date": issue_date, "trich_yeu": trich_yeu, "warnings": warnings}


# ---------------------------------------------------------------- 2. các Điều
def _path(chuong, muc) -> str:
    parts = []
    if chuong:
        parts.append(f"Chương {chuong[0]}" + (f": {chuong[1]}" if chuong[1] else ""))
    if muc:
        parts.append(f"Mục {muc[0]}" + (f": {muc[1]}" if muc[1] else ""))
    return " > ".join(parts)


def parse_articles(lines: list[str]):
    """Trả về (articles, tail_lines, warnings). tail_lines = khối 'Nơi nhận + chữ ký'."""
    warnings: list[str] = []
    start = next(
        (i for i, ln in enumerate(lines)
         if (len(ln) <= 150 and (RE_CHUONG.match(ln))) or RE_DIEU.match(ln)), None)
    if start is None:
        return [], [], ["không thấy Chương/Điều nào"]

    first_dieu = next((i for i in range(start, len(lines)) if RE_DIEU.match(lines[i])), start)

    def signature_start(i: int) -> bool:
        if RE_NOINHAN.match(lines[i]) or RE_KY_MANH.match(lines[i]):
            return True
        if not RE_KY.match(lines[i]):
            return False
        # Standalone uppercase role near a signature note/person. This avoids
        # treating normative sentences beginning with a minister/title as a signature.
        nearby = lines[i + 1:i + 6]
        return lines[i].isupper() and any(
            ln.startswith("(") or (
                len(ln) <= 50 and len(ln.split()) >= 2 and not ln.isupper()
                and not re.search(r"\d|[:;.]", ln)
            )
            for ln in nearby
        )

    tail_start = next(
        (i for i in range(first_dieu + 1, len(lines)) if signature_start(i)),
        len(lines),
    )

    articles, chuong, muc, cur, expect = [], None, None, None, None

    def close():
        nonlocal cur
        if cur:
            articles.append({
                "article_number": cur["number"],
                "title": cur["title"].strip(" ."),
                "hierarchy_path": cur["path"],
                "content": "\n".join(cur["lines"]),
            })
        cur = None

    for ln in lines[start:tail_start]:
        short = len(ln) <= 150
        m_ch = RE_CHUONG.match(ln) if short else None
        m_mu = RE_MUC.match(ln) if short else None
        m_di = RE_DIEU.match(ln)
        if m_ch:
            close()
            chuong = [m_ch.group(1), m_ch.group(2).strip()]
            muc = None  # sang Chương mới thì bỏ Mục cũ
            expect = "chuong" if not chuong[1] else None
        elif m_mu:
            close()
            muc = [m_mu.group(1), m_mu.group(2).strip()]
            expect = "muc" if not muc[1] else None
        elif m_di:
            close()
            cur = {"number": m_di.group(1), "title": m_di.group(2).strip(),
                   "path": _path(chuong, muc), "lines": [ln]}
            expect = "dieu" if not cur["title"] else None
        elif expect and len(ln) < 200:
            if expect == "chuong":
                chuong[1] = ln
            elif expect == "muc":
                muc[1] = ln
            elif expect == "dieu" and cur:
                cur["title"] = ln
                cur["lines"].append(ln)
            expect = None
        else:
            expect = None
            if cur:
                cur["lines"].append(ln)
    close()
    return articles, lines[tail_start:], warnings


# ---------------------------------------------------------------- 3. người ký, hiệu lực, thay thế
def parse_signer(tail: list[str]) -> str:
    idx = next((i for i, ln in enumerate(tail) if RE_KY.match(ln)), None)
    if idx is None:
        return ""
    for ln in tail[idx: idx + 12]:
        if RE_KY.match(ln) or ln.isupper() or ln.startswith(("-", "(")):
            continue  # chức danh viết hoa, ghi chú
        if len(ln) <= 40 and len(ln.split()) >= 2 and not re.search(r"\d|[:;]", ln):
            return ln
    return ""


# ---------------------------------------------------------------- 3b. mẫu số / phụ lục rời (không có "Điều N.")
def classify_by_filename(file_name: str) -> str | None:
    """Đoán loại 'văn bản' không có cấu trúc Điều, dựa trên tên file."""
    name = unicodedata.normalize("NFC", file_name)
    if RE_IS_MAU.search(name):
        return "mau_bieu"
    if RE_IS_PHULUC.search(name):
        return "phu_luc"
    return None


# ---------------------------------------------------------------- 3c. phụ lục đính kèm sau chữ ký (cùng 1 file với Điều)
def split_signature_and_appendix(tail: list[str]):
    """Tách khối 'Nơi nhận + chữ ký' (đầu tail) ra khỏi phần phụ lục phía sau nó (nếu có)."""
    idx = next((i for i, ln in enumerate(tail) if RE_KY.match(ln)), None)
    if idx is None:
        return tail, []
    end = idx + 1
    while end < len(tail) and end < idx + 12:
        ln = tail[end]
        end += 1
        if not (RE_KY.match(ln) or ln.isupper() or ln.startswith(("-", "("))):
            break  # gặp dòng tên người ký -> hết khối chữ ký
    return tail[:end], tail[end:]


def parse_phu_luc(lines: list[str]) -> list[dict]:
    """Chia phần phụ lục thành từng khối theo dòng tiêu đề 'PHỤ LỤC ...'."""
    blocks, cur = [], None
    for ln in lines:
        if RE_PL_HEADER.match(ln):
            if cur:
                blocks.append(cur)
            cur = {"tieu_de": ln, "noi_dung": []}
        elif cur is not None:
            cur["noi_dung"].append(ln)
    if cur:
        blocks.append(cur)
    for b in blocks:
        b["noi_dung"] = "\n".join(b["noi_dung"])
    return blocks


def parse_effective_and_replaces(articles: list[dict], doc_number: str, issue_date: str):
    """Tìm ngày hiệu lực và văn bản bị thay thế trong các Điều 'Hiệu lực / Điều khoản thi hành'."""
    key = re.compile(r"hiệu lực|thi hành|chuyển tiếp|bãi bỏ|thay thế", re.I)
    cand = [a for a in articles if key.search(a["title"])] or articles[-2:]

    effective, replaces = "", []
    for a in cand:
        pending = False
        for ln in a["content"].split("\n"):
            m = RE_HIEU_LUC.search(ln)
            if m and not effective:
                d = RE_NGAY.search(m.group(1))
                if d:
                    effective = _iso(*d.groups())
                elif "ngày ký" in m.group(1):
                    effective = issue_date
            if re.match(r"^\d+\.\s", ln):
                pending = False
            scan = False
            if RE_HET_HL.search(ln):
                pending, scan = True, True
            elif pending and re.match(r"^([a-zđ]\)|-)\s", ln):
                scan = True
            if scan and not RE_PARTIAL.search(ln):
                for s in RE_SOHIEU_ANY.findall(ln):
                    if s != doc_number and s not in replaces:
                        replaces.append(s)
    if not effective:  # fallback: tìm trong toàn bộ các Điều
        for a in reversed(articles):
            for ln in a["content"].split("\n"):
                m = RE_HIEU_LUC.search(ln)
                if m and RE_NGAY.search(m.group(1)):
                    return _iso(*RE_NGAY.search(m.group(1)).groups()), replaces
    return effective, replaces


# ---------------------------------------------------------------- 4. ghép lại
def parse_document(lines: list[str], file_name: str = ""):
    h = parse_header(lines, file_name)
    articles, tail, w_art = parse_articles(lines)

    # ---- Không có Điều nào: đây là mẫu biểu hoặc phụ lục rời, không phải văn bản pháp luật ----
    if not articles:
        kind = classify_by_filename(file_name) or "khac"
        doc = {
            "metadata": {
                "doc_number": h["so_hieu"] or "",
                "doc_type": kind,
                "doc_title": Path(file_name).stem,
                "status": "con_hieu_luc",
                "effective_date": "",
                "issue_date": "",
                "signer": "",
                "issuing_body": "",
                "topic_tags": [],
                "replaces": [],
                "replaced_by": [],
            },
        }
        if kind == "phu_luc":
            blocks = parse_phu_luc(lines)
            doc["phu_luc"] = blocks if blocks else [{"tieu_de": Path(file_name).stem, "noi_dung": "\n".join(lines)}]
        else:
            doc["noi_dung"] = "\n".join(lines)   # mẫu biểu: không chia được gì, để nguyên
        warnings = [f"không có cấu trúc 'Điều N.' -> xếp loại {kind}"]
        return doc, warnings

    warnings = h["warnings"] + w_art
    sig_block, appendix_lines = split_signature_and_appendix(tail)

    effective, replaces = parse_effective_and_replaces(articles, h["so_hieu"], h["issue_date"])
    if not effective:
        warnings.append("không tìm thấy ngày hiệu lực")
    signer = parse_signer(sig_block) or parse_signer(tail) or parse_signer(lines[-40:])
    if not signer:
        warnings.append("không tìm thấy người ký")

    doc_number = h["so_hieu"] or ""
    loai = h["loai"]
    doc = {
        "metadata": {
            "doc_number": doc_number,
            "doc_type": DOC_TYPE_KEY.get(loai, "khac"),
            "doc_title": f"{loai} {doc_number}" if loai and doc_number else Path(file_name).stem,
            "status": "con_hieu_luc",       # build_json.py sẽ cập nhật sau khi liên kết các văn bản
            "effective_date": effective,
            "issue_date": h["issue_date"],
            "signer": signer,
            "issuing_body": h["issuing_body"],
            "topic_tags": [],
            "replaces": replaces,
            "replaced_by": [],
        },
        "articles": articles,
    }

    # ---- Phụ lục đính kèm ngay trong cùng file, sau khối chữ ký ----
    phu_luc = parse_phu_luc(appendix_lines)
    if phu_luc:
        doc["phu_luc"] = phu_luc
    elif len(appendix_lines) > 5:
        doc["phu_luc"] = [{"tieu_de": "Phụ lục (chưa nhận diện được tiêu đề)",
                            "noi_dung": "\n".join(appendix_lines)}]
        warnings.append("có nội dung sau chữ ký nhưng không thấy dòng 'PHỤ LỤC' -> gộp vào 1 khối")

    return doc, warnings


def build_document(path):
    """Đọc 1 file docx -> (doc, warnings)."""
    path = Path(path)
    return parse_document(read_docx(path), path.name)
