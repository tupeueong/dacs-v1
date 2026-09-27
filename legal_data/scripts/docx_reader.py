"""
docx_reader.py - Đọc file .docx văn bản pháp luật thành danh sách dòng.

    from docx_reader import read_docx
    lines = read_docx("Nghị-định-12-2022-NĐ-CP.docx")
"""
import re
import unicodedata

from docx import Document
from docx.table import Table
from docx.text.paragraph import Paragraph

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
W = f"{{{W_NS}}}"


# =====================================================================
# HÀM 1: ĐỌC DOCX -> DANH SÁCH DÒNG
# =====================================================================
def _clean(s: str) -> str:
    s = unicodedata.normalize("NFC", s).replace("\u00a0", " ")
    return re.sub(r"[ \t]+", " ", s).strip()


def _unique_cells(row):
    """Các ô của 1 hàng, bỏ ô trùng do merge."""
    seen, out = [], []
    for cell in row.cells:
        if cell._tc in seen:
            continue
        seen.append(cell._tc)
        out.append(cell)
    return out


def _article_numbering(doc):
    """Read Word numbering definitions whose labels start with article markers."""
    try:
        root = doc.part.numbering_part.element
    except (KeyError, NotImplementedError):
        return {}
    abstract = {}
    for node in root.findall(f"{W}abstractNum"):
        levels = {}
        for level in node.findall(f"{W}lvl"):
            ilvl = int(level.get(f"{W}ilvl"))
            text_node = level.find(f"{W}lvlText")
            start_node = level.find(f"{W}start")
            if text_node is not None:
                start = int(start_node.get(f"{W}val", "1")) if start_node is not None else 1
                levels[ilvl] = (text_node.get(f"{W}val", ""), start)
        abstract[node.get(f"{W}abstractNumId")] = levels
    return _numbering_instances(root, abstract)


def _numbering_instances(root, abstract):
    result = {}
    for node in root.findall(f"{W}num"):
        num_id = node.get(f"{W}numId")
        abstract_node = node.find(f"{W}abstractNumId")
        if abstract_node is None:
            continue
        levels = dict(abstract.get(abstract_node.get(f"{W}val"), {}))
        for override in node.findall(f"{W}lvlOverride"):
            ilvl = int(override.get(f"{W}ilvl"))
            start_override = override.find(f"{W}startOverride")
            if start_override is not None and ilvl in levels:
                levels[ilvl] = (levels[ilvl][0], int(start_override.get(f"{W}val")))
        if any(re.match(r"^Điều\s+%\d+", text, re.I) for text, _ in levels.values()):
            result[num_id] = levels
    return result


def _numbered_text(paragraph: Paragraph, numbering, counters) -> str:
    text = paragraph.text
    p_pr = paragraph._p.pPr
    num_pr = p_pr.numPr if p_pr is not None else None
    if num_pr is None and paragraph.style is not None:
        style_pr = paragraph.style.element.pPr
        num_pr = style_pr.numPr if style_pr is not None else None
    if num_pr is None or num_pr.numId is None:
        return text
    num_id = str(num_pr.numId.val)
    ilvl = int(num_pr.ilvl.val) if num_pr.ilvl is not None else 0
    spec = numbering.get(num_id, {}).get(ilvl)
    if not spec or not re.match(r"^Điều\s+%\d+", spec[0], re.I):
        return text
    key = (num_id, ilvl)
    counters[key] = counters.get(key, spec[1] - 1) + 1
    prefix = re.sub(r"%\d+", str(counters[key]), spec[0]).strip()
    return f"{prefix} {text}".strip()


def read_docx(path) -> list[str]:
    """
    Trả về danh sách dòng (đã bỏ dòng rỗng) theo đúng thứ tự trong file.
    - Đoạn văn: mỗi dòng 1 phần tử.
    - Bảng 1 hàng (bảng bố cục: quốc hiệu, số hiệu, nơi nhận...): tách từng ô, từng dòng trong ô.
    - Bảng nhiều hàng (dữ liệu, phụ lục): mỗi hàng nối bằng ' | '.
    """
    doc = Document(str(path))
    numbering = _article_numbering(doc)
    counters = {}
    lines: list[str] = []
    for child in doc.element.body.iterchildren():
        if child.tag.endswith("}p"):
            paragraph = Paragraph(child, doc)
            for ln in _numbered_text(paragraph, numbering, counters).split("\n"):
                ln = _clean(ln)
                if ln:
                    lines.append(ln)
        elif child.tag.endswith("}tbl"):
            tbl = Table(child, doc)
            if len(tbl.rows) == 1:
                for cell in _unique_cells(tbl.rows[0]):
                    for ln in cell.text.split("\n"):
                        ln = _clean(ln)
                        if ln:
                            lines.append(ln)
            else:
                for row in tbl.rows:
                    cells = [_clean(c.text.replace("\n", " ")) for c in _unique_cells(row)]
                    cells = [c for c in cells if c]
                    if cells:
                        lines.append(" | ".join(cells))
    return lines
