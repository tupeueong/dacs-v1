# Bộ RAG luật lao động hợp nhất

Ngày chốt dữ liệu: **2026-09-27**.

## Thành phần

- `articles.jsonl`: 1.662 điều luật chuẩn hóa, đã loại bản bị thay thế và trùng nội dung.
- `chunks.jsonl`: 3.324 chunk theo cấu trúc điều luật; không chunk nào vượt 448 token.
- `articles_qa_report.json`: báo cáo hợp nhất, loại trừ và khử trùng lặp.
- `chunks_qa_report.json`: thống kê và kiểm tra chất lượng chunk.
- Vector/BM25 index: `../vectorstore_labor_unified/`.

Nguồn trong bộ hiện tại gồm Pháp điển, Công báo điện tử (văn bản chính thức 2025-2026),
và ba văn bản cũ đã kiểm tra còn hiệu lực dùng để giữ độ phủ nghiệp vụ.

## Truy xuất

Chạy tương tác:

```powershell
.venv\Scripts\python.exe -X utf8 legal_data\scripts\retrieve_unified.py
```

Trong Python:

```python
from retrieve_unified import create_retriever

retriever = create_retriever()
hits = retriever.retrieve("điều kiện hưởng trợ cấp thất nghiệp năm 2026", top_k=5)
```

Luồng sinh câu trả lời dùng Gemini:

```powershell
.venv\Scripts\python.exe -X utf8 legal_data\scripts\generate_unified.py
```

## Kiểm tra chỉ mục

```powershell
.venv\Scripts\python.exe -X utf8 legal_data\scripts\verify_phapdien_labor_index.py `
  --chunks legal_data\rag_corpus\chunks.jsonl `
  --index legal_data\vectorstore_labor_unified
```

Kết quả đã xác nhận: JSONL = Chroma = BM25 = 3.324 ID; embedding 768 chiều.

Các vectorstore cũ được giữ nguyên để đối chiếu nhưng không phải bộ hợp nhất hiện hành.
