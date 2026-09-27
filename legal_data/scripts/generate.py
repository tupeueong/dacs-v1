# """
# generate.py - Ghép retrieve() với 1 LLM để trả lời câu hỏi bằng văn tự nhiên,
# có trích dẫn nguồn, thay vì chỉ liệt kê danh sách chunk.

# Cài đặt:  pip install anthropic
# Cần biến môi trường ANTHROPIC_API_KEY (lấy tại https://console.anthropic.com/settings/keys)

#     from generate import answer
#     print(answer("mức phạt khi không ký hợp đồng lao động bằng văn bản"))
# """
# import os

# from dotenv import load_dotenv
# from google import genai

# from retrieve import Retriever

# load_dotenv()  # đọc file .env cùng thư mục chạy script, nạp vào biến môi trường

# client = genai.Client()  # đọc API key từ biến môi trường GEMINI_API_KEY
# MODEL_NAME = "gemini-3.5-flash-lite"  # gemini-2.5-flash-lite đã ngừng cấp cho tài khoản mới (10/2026)

# SYSTEM_PROMPT = """Bạn là trợ lý tra cứu pháp luật lao động Việt Nam.

# QUY TẮC BẮT BUỘC:
# 1. Chỉ được trả lời dựa trên các đoạn luật được cung cấp bên dưới. Không được dùng kiến thức ngoài.
# 2. Nếu các đoạn cung cấp không đủ để trả lời, phải nói rõ "Không tìm thấy thông tin liên quan trong dữ
#    liệu hiện có", không được đoán hoặc bịa.
# 3. Mỗi ý, mỗi con số, mỗi mức phạt PHẢI ghi rõ nguồn ngay sau nó: (Khoản X Điều Y, Văn bản Z).

# CÁCH TRÌNH BÀY (bắt buộc theo, để trả lời sâu và dễ đọc):
# - Dùng tiêu đề nhỏ (##) nếu câu hỏi có nhiều khía cạnh.
# - Dùng gạch đầu dòng để liệt kê từng trường hợp/mức vi phạm riêng biệt, KHÔNG dồn tất cả vào 1 đoạn văn.
# - Nếu luật phân biệt mức phạt cho CÁ NHÂN và TỔ CHỨC (thường tổ chức bị phạt gấp đôi cá nhân), phải
#   nêu rõ CẢ HAI mức, không chỉ nêu 1 mức rồi bỏ qua mức còn lại.
# - Nếu có nhiều Khoản/Điểm áp dụng cho các tình huống khác nhau trong cùng 1 Điều, liệt kê riêng từng
#   tình huống kèm mức phạt tương ứng, không gộp chung thành 1 câu mơ hồ.
# - Nếu có biện pháp khắc phục hậu quả hoặc hình thức xử phạt bổ sung (tước giấy phép, đình chỉ...) đi
#   kèm, nêu thêm ở cuối, tách riêng khỏi phần phạt tiền.
# - Kết thúc bằng câu tóm tắt ngắn nếu câu trả lời dài hơn 3 gạch đầu dòng."""


# def build_context(chunks: list[dict], retriever: Retriever) -> str:
#     """Với mỗi Điều đã trúng truy vấn, lấy lại TOÀN BỘ Điều đó (mọi phần, kể cả phần không lọt
#     top-k) qua retriever.get_full_article(), thay vì chỉ ghép các phần tình cờ có trong top-k."""
#     seen, blocks = set(), []
#     for c in chunks:
#         key = (c["doc_number"], c.get("article_number") or c["chunk_id"])
#         if key in seen:
#             continue
#         seen.add(key)
#         nhan = f"[Nguồn: {c['doc_title']}, {c.get('article_title') or c.get('hierarchy_path') or ''}]"
#         if c.get("article_number"):
#             full_text = retriever.get_full_article(c["doc_number"], c["article_number"])
#         else:
#             full_text = c["text"]  # phụ lục / mẫu biểu, không có khái niệm "Điều" để lấy trọn
#         blocks.append(f"{nhan}\n{full_text}")
#     return "\n\n---\n\n".join(blocks)


# def answer(question: str, retriever: Retriever, top_k: int = 5, filters: dict | None = None) -> str:
#     chunks = retriever.retrieve(question, top_k=top_k, filters=filters)
#     if not chunks:
#         return "Không tìm thấy thông tin liên quan trong dữ liệu hiện có."

#     context = build_context(chunks, retriever)
#     prompt = f"""Dưới đây là các đoạn luật liên quan (mỗi Điều đã lấy TRỌN VẸN, không bị cắt):

# {context}

# Câu hỏi: {question}

# Hãy trả lời chi tiết, đầy đủ các trường hợp/mức phạt có trong các Điều trên, theo đúng cách trình bày đã yêu cầu."""

#     resp = client.models.generate_content(
#         model=MODEL_NAME,
#         config={"system_instruction": SYSTEM_PROMPT, "max_output_tokens": 2000},
#         contents=prompt,
#     )
#     return resp.text


# if __name__ == "__main__":
#     r = Retriever("legal_data/vectorstore")
#     while True:
#         q = input("Câu hỏi: ").strip()
#         if not q or q.lower() in ("thoat", "exit", "quit"):
#             break
#         print("\n" + answer(q, r) + "\n")

"""
generate.py - Ghép retrieve() với 1 LLM để trả lời câu hỏi bằng văn tự nhiên,
có trích dẫn nguồn, thay vì chỉ liệt kê danh sách chunk.

Cài đặt:  pip install anthropic
Cần biến môi trường ANTHROPIC_API_KEY (lấy tại https://console.anthropic.com/settings/keys)

    from generate import answer
    print(answer("mức phạt khi không ký hợp đồng lao động bằng văn bản"))
"""
import os
import re

from dotenv import load_dotenv
from google import genai

from retrieve import Retriever

load_dotenv()  # đọc file .env cùng thư mục chạy script, nạp vào biến môi trường

client = genai.Client()  # đọc API key từ biến môi trường GEMINI_API_KEY
MODEL_NAME = "gemini-3.5-flash-lite"  # gemini-2.5-flash-lite đã ngừng cấp cho tài khoản mới (10/2026)

SYSTEM_PROMPT = """Bạn là trợ lý tra cứu pháp luật lao động Việt Nam.

QUY TẮC BẮT BUỘC:
1. Chỉ được trả lời dựa trên các đoạn luật được cung cấp bên dưới. Không được dùng kiến thức ngoài.
2. Nếu các đoạn cung cấp không đủ để trả lời, phải nói rõ "Không tìm thấy thông tin liên quan trong dữ
   liệu hiện có", không được đoán hoặc bịa.
3. Mỗi ý, mỗi con số, mỗi mức phạt PHẢI ghi rõ nguồn ngay sau nó: (Khoản X Điều Y, Văn bản Z).

CÁCH TRÌNH BÀY (bắt buộc theo, để trả lời sâu và dễ đọc):
- Dùng tiêu đề nhỏ (##) nếu câu hỏi có nhiều khía cạnh.
- Dùng gạch đầu dòng để liệt kê từng trường hợp/mức vi phạm riêng biệt, KHÔNG dồn tất cả vào 1 đoạn văn.
- Nếu luật phân biệt mức phạt cho CÁ NHÂN và TỔ CHỨC (thường tổ chức bị phạt gấp đôi cá nhân), phải
  nêu rõ CẢ HAI mức, không chỉ nêu 1 mức rồi bỏ qua mức còn lại.
- Nếu có nhiều Khoản/Điểm áp dụng cho các tình huống khác nhau trong cùng 1 Điều, liệt kê riêng từng
  tình huống kèm mức phạt tương ứng, không gộp chung thành 1 câu mơ hồ.
- Nếu có biện pháp khắc phục hậu quả hoặc hình thức xử phạt bổ sung (tước giấy phép, đình chỉ...) đi
  kèm, nêu thêm ở cuối, tách riêng khỏi phần phạt tiền.
- Kết thúc bằng câu tóm tắt ngắn nếu câu trả lời dài hơn 3 gạch đầu dòng."""


def build_context(chunks: list[dict], retriever: Retriever) -> str:
    """Với mỗi Điều đã trúng truy vấn, lấy lại TOÀN BỘ Điều đó (mọi phần, kể cả phần không lọt
    top-k) qua retriever.get_full_article(), thay vì chỉ ghép các phần tình cờ có trong top-k.

    Ngoài ra, LUÔN kèm thêm "Điều nguyên tắc chung" của mỗi văn bản xuất hiện trong kết quả
    (ví dụ Điều 6 Nghị định 12/2022 quy định mức phạt là cho cá nhân, tổ chức phạt gấp đôi) -
    vì Điều này áp dụng cho MỌI Điều xử phạt khác trong cùng văn bản nhưng hiếm khi tự được
    retrieve ra do không khớp ngữ nghĩa với câu hỏi cụ thể."""
    seen, blocks, principle_added = set(), [], set()
    for c in chunks:
        key = (c["doc_number"], c.get("article_number") or c["chunk_id"])
        if key in seen:
            continue
        seen.add(key)
        nhan = f"[Nguồn: {c['doc_title']}, {c.get('article_title') or c.get('hierarchy_path') or ''}]"
        if c.get("article_number"):
            full_text = retriever.get_full_article(c["doc_number"], c["article_number"])
        else:
            full_text = c["text"]  # phụ lục / mẫu biểu, không có khái niệm "Điều" để lấy trọn
        blocks.append(f"{nhan}\n{full_text}")

        # Thêm 1 lần duy nhất cho mỗi văn bản: Điều nói về nguyên tắc mức phạt (cá nhân/tổ chức)
        if c["doc_number"] not in principle_added:
            principle_added.add(c["doc_number"])
            principle = retriever.get_principle_article(c["doc_number"])
            if principle:
                blocks.append(f"[Nguyên tắc áp dụng mức phạt của {c['doc_title']}]\n{principle}")
    return "\n\n---\n\n".join(blocks)


def answer(question: str, retriever: Retriever, top_k: int = 5, filters: dict | None = None,
           show_retrieved: bool = True) -> str:
    doc_match = re.search(
        r"\b\d+/\d{4}(?:/[A-ZĐ-]+)?\b",
        question,
        flags=re.IGNORECASE,
    )
    doc_number = None

    if doc_match:
        requested_doc_number = doc_match.group(0)
        known_doc_numbers = {
            chunk["doc_number"]
            for chunk in retriever.by_id.values()
            if chunk.get("doc_number")
        }
        matching_doc_numbers = sorted(
            doc
            for doc in known_doc_numbers
            if doc.casefold() == requested_doc_number.casefold()
            or doc.casefold().startswith(requested_doc_number.casefold() + "/")
        )
        if len(matching_doc_numbers) == 1:
            doc_number = matching_doc_numbers[0]
        elif requested_doc_number in known_doc_numbers:
            doc_number = requested_doc_number

    effective_filters = dict(filters or {})
    if doc_number:
        effective_filters["doc_number"] = doc_number

    chunks = retriever.retrieve(
        question,
        top_k=top_k,
        filters=effective_filters or None,
    )
    if not chunks:
        return "Không tìm thấy thông tin liên quan trong dữ liệu hiện có."

    if show_retrieved:
        print(f"\n[Đã truy vấn vector DB, lấy được {len(chunks)} chunk:]")
        for c in chunks:
            print(f"  - {c['doc_title']} | {c.get('article_title')} | "
                  f"điểm rerank={c['rerank_score']:.3f} | id={c['chunk_id']}")
        print()

    context = build_context(chunks, retriever)
    prompt = f"""Dưới đây là các đoạn luật liên quan (mỗi Điều đã lấy TRỌN VẸN, không bị cắt):

{context}

Câu hỏi: {question}

Hãy trả lời chi tiết, đầy đủ các trường hợp/mức phạt có trong các Điều trên, theo đúng cách trình bày đã yêu cầu."""

    resp = client.models.generate_content(
        model=MODEL_NAME,
        config={"system_instruction": SYSTEM_PROMPT, "max_output_tokens": 2000},
        contents=prompt,
    )
    return resp.text


if __name__ == "__main__":
    r = Retriever("legal_data/vectorstore")
    while True:
        q = input("Câu hỏi: ").strip()
        if not q or q.lower() in ("thoat", "exit", "quit"):
            break
        print("\n" + answer(q, r) + "\n")
