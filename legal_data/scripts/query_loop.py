"""
query_loop.py - Nhập câu hỏi liên tục, mỗi lần in ra top-k chunk liên quan nhất.
Model chỉ load 1 lần khi khởi động, không load lại mỗi câu hỏi.

    python query_loop.py
"""
from retrieve import Retriever

print("Đang tải model + index (chỉ 1 lần, hơi lâu)...")
r = Retriever("legal_data/vectorstore")
print("Xong. Gõ câu hỏi rồi Enter. Gõ 'thoat' hoặc để trống để dừng.\n")

while True:
    query = input("Câu hỏi: ").strip()
    if not query or query.lower() in ("thoat", "exit", "quit"):
        break

    ket_qua = r.retrieve(query, top_k=5)
    if not ket_qua:
        print("  (không tìm thấy kết quả nào)\n")
        continue

    for hit in ket_qua:
        print(f"  {hit['rerank_score']:.3f}  {hit['doc_title']} - {hit.get('article_title')} "
              f"[{hit['chunk_id']}]")
    print()  # dòng trống ngăn cách giữa các câu hỏi