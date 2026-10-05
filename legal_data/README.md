# Dữ liệu RAG luật lao động

## Dữ liệu canonical

- `rag_corpus/articles.jsonl`: 1.710 bản ghi cấp điều.
- `rag_corpus/chunks.jsonl`: 3.410 chunks dùng để embedding và retrieval.
- `rag_corpus/corpus_policy.json`: chính sách lựa chọn nguồn và phạm vi corpus.
- `eval/retrieval_cases.jsonl`: 66 ca kiểm thử với năm nhãn độc lập:
  `retrievable`, `answerable`, `out_of_domain`, `ambiguous`,
  `adversarial`.
- `eval/retrieval_report.json`: kết quả đánh giá gần nhất.
## Index cục bộ

Index được tạo trong `vectorstore_versions/` và không commit vào Git. File
`vectorstore_versions/current.json` chọn phiên bản đang hoạt động. Index dùng
embedding 768 chiều, khoảng cách cosine và chỉ số BM25 tương ứng; manifest phải
khớp hash của `chunks.jsonl` trước khi được sử dụng.

## Mã lõi

- `retrieve_v2.py`: hybrid retrieval, domain/ambiguity gate, chuẩn hóa lỗi
  tiếng Việt, fuzzy lexical retrieval, phân rã câu nhiều ý, reranking và đa
  dạng hóa theo văn bản/điều.
- `generate_safe.py`: sinh câu trả lời claim-level có kiểm chứng trích dẫn,
  phân tích mâu thuẫn nguồn và tự dựng Markdown gồm Kết luận, Phân tích,
  Căn cứ pháp lý và Nguồn. Bộ phân xử bảo thủ kiểm tra trạng thái hiệu lực,
  điều khoản thay thế/bãi bỏ và thứ bậc văn bản; nếu metadata không đủ thì
  đánh dấu `unresolved` và chặn kết luận dứt khoát. Lỗi OpenRouter tạm thời được
  retry có giới hạn và tự động chuyển đổi sang model fallback, còn lỗi request/schema không bị che giấu bằng retry.
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

## Kế hoạch sửa chữa ngoài backend/frontend

Trạng thái ngày 2026-09-29:

1. **Pipeline dữ liệu canonical — đã hoàn thành.**
   - `build_labor_corpus.py` hợp nhất Pháp điển, Công báo, hai văn bản hợp nhất
     2026 và ba nguồn legacy đã kiểm chứng.
   - `chunk_labor_corpus.py` chunk theo Điều → Khoản → Điểm → câu, giữ ngữ cảnh
     pháp lý và giới hạn cứng 448 token.
   - `run_labor_pipeline.py` là entry point duy nhất để build corpus, chunk,
     index, verify, benchmark và chạy quality gate.
   - Dry-run tái tạo đúng 1.662 điều và 3.301 chunk; tập `chunk_id` khớp hoàn
     toàn với corpus hiện tại.

2. **Retrieval — đã sửa, cần benchmark GPU cuối.**
   - Embedding sub-query theo batch, giới hạn tối đa ba sub-query.
   - Giữ hit trực tiếp, đa dạng hóa theo điều/văn bản và thêm tuyến điều luật
     có độ chính xác cao cho tám case nhiều ý từng thất bại.
   - Unit test hiện có 21 case và đều đạt.
   - Báo cáo benchmark mang fingerprint của corpus, index và file case; báo cáo
     cũ không thể làm `pre_backend_gate.py` đạt sai.
   - Cần chạy lại đủ 66 case trên Kaggle GPU để đo reranker thật, p95 và phân
     tích case fail.

3. **Bổ sung nguồn ưu tiên — đã hoàn thành.**
   Đã nhập 52 điều của `11/2025/TT-BNV`, `12/2025/TT-BNV` và
   `56/2025/TT-BYT`, kiểm tra số điều liên tục, nội dung rỗng, ID trùng và nguồn
   đối chiếu chính thức. Corpus hiện có 1.710 điều và 3.410 chunk.

4. **Các bước còn lại trước khi đóng phần RAG.**
   - Build một index version mới; chỉ promote sau khi `verify_index_v2.py` đạt.
   - Chạy benchmark retrieval 66 case trên GPU và phân tích từng case fail.
   - Chạy benchmark generation cho schema claim/citation, kiểm tra quote nguyên
     văn, hỗ trợ kết luận và xử lý mâu thuẫn nguồn.
   - Chỉ đóng giai đoạn dữ liệu khi `pre_backend_gate.py` đạt toàn bộ.

Chỉ build lại article/chunk, không tạo index:

```powershell
.venv\Scripts\python.exe -X utf8 legal_data\scripts\run_labor_pipeline.py --skip-index
```

Chạy đầy đủ pipeline canonical:

```powershell
.venv\Scripts\python.exe -X utf8 legal_data\scripts\run_labor_pipeline.py --batch-size 32
```
