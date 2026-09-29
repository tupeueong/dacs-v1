# Dữ liệu RAG luật lao động

## Dữ liệu canonical

- `rag_corpus/articles.jsonl`: 1.662 bản ghi cấp điều.
- `rag_corpus/chunks.jsonl`: 3.301 chunks dùng để embedding và retrieval.
- `rag_corpus/corpus_policy.json`: chính sách lựa chọn nguồn và phạm vi corpus.
- `eval/retrieval_cases.jsonl`: 60 ca kiểm thử với năm nhãn độc lập:
  `retrievable`, `answerable`, `out_of_domain`, `ambiguous`,
  `adversarial`.
- `eval/retrieval_report.json`: kết quả đánh giá gần nhất.
## Index cục bộ

Index được tạo trong `vectorstore_versions/` và không commit vào Git. File
`vectorstore_versions/current.json` chọn phiên bản đang hoạt động. Index hiện
có 3.301 vector, 768 chiều, khoảng cách cosine và chỉ số BM25 tương ứng.

## Mã lõi

- `retrieve_v2.py`: hybrid retrieval, domain/ambiguity gate, chuẩn hóa lỗi
  tiếng Việt, fuzzy lexical retrieval, phân rã câu nhiều ý, reranking và đa
  dạng hóa theo văn bản/điều.
- `generate_safe.py`: sinh câu trả lời claim-level có kiểm chứng trích dẫn,
  phân tích mâu thuẫn nguồn và tự dựng Markdown gồm Kết luận, Phân tích,
  Căn cứ pháp lý và Nguồn. Bộ phân xử bảo thủ kiểm tra trạng thái hiệu lực,
  điều khoản thay thế/bãi bỏ và thứ bậc văn bản; nếu metadata không đủ thì
  đánh dấu `unresolved` và chặn kết luận dứt khoát. Lỗi Gemini tạm thời được
  retry có giới hạn, còn lỗi request/schema không bị che giấu bằng retry.
- `build_index_v4.py`: build/promote index an toàn trên Windows.
- `verify_index_v2.py`: kiểm tra hash, ID, BM25 và vector index.
- `evaluate_retrieval_v2.py`: chạy bộ đánh giá retrieval.
- `kaggle_retrieval_api.py` và `notebooks/kaggle_retrieval_api.ipynb`:
  benchmark GPU và API thử nghiệm theo phiên Kaggle; không dùng làm backend
  thường trực.
- `pre_backend_gate.py`: cổng kiểm tra trước khi tích hợp backend.

## Lệnh vận hành

Chạy từ thư mục gốc repository:

```powershell
.venv\Scripts\python.exe -X utf8 legal_data\scripts\build_index_v4.py
.venv\Scripts\python.exe -X utf8 legal_data\scripts\verify_index_v2.py
.venv\Scripts\python.exe -X utf8 legal_data\scripts\evaluate_retrieval_v2.py
.venv\Scripts\python.exe -X utf8 legal_data\scripts\pre_backend_gate.py
```

Backend sử dụng `SafeRetriever` từ `retrieve_v2.py` và `GroundedGenerator` từ
`generate_safe.py`.
