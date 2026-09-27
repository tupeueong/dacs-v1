# Kế hoạch tối ưu trước Backend/Frontend

Ngày bắt đầu: 2026-09-27

## Mục tiêu chấp nhận

Hệ thống dữ liệu và RAG chỉ được bàn giao cho backend khi đáp ứng đồng thời:

1. Corpus có nguồn, phiên bản, thời điểm hiệu lực và lịch sử thay thế kiểm tra được.
2. Build lại toàn bộ bằng một lệnh, không làm hỏng index đang dùng.
3. JSONL, Chroma và BM25 có cùng tập `chunk_id`.
4. Truy vấn ngoài luật lao động bị từ chối thay vì trả kết quả gần đúng.
5. Mọi trích dẫn trong câu trả lời ánh xạ được về chunk và URL nguồn.
6. Có evaluation cố định và báo cáo pass/fail trước mỗi lần phát hành corpus.
7. Secret, dependency và cấu hình runtime không nằm rải rác trong mã nguồn.

## Giai đoạn 1 — Dữ liệu pháp lý

- Bổ sung 18/VBHN-VPQH và 19/VBHN-VPQH năm 2026.
- Xử lý 9 văn bản hiện hành còn thiếu trong source registry.
- Đồng bộ `extraction_status` giữa registry và dữ liệu đã xử lý.
- Chuyển hiệu lực từ cấp văn bản/Điều xuống Khoản/Điểm khi có bãi bỏ một phần.
- Giữ đầy đủ alias trích dẫn khi nhiều văn bản có nội dung giống nhau.

Điều kiện hoàn thành: không còn nguồn ưu tiên cao ở trạng thái chưa xử lý; QA không có
ID trùng, nội dung rỗng, URL nguồn thiếu hoặc văn bản đã bị thay thế lọt vào current corpus.

## Giai đoạn 2 — Build và index

- Cấu hình tập trung cho đường dẫn, model và ngưỡng retrieval.
- Build index vào thư mục staging mới; verify xong mới đổi `current`.
- Xóa được ID cũ khi chunk biến mất; phát hiện nội dung đổi dù `chunk_id` không đổi.
- Dùng cosine distance nhất quán với embedding đã chuẩn hóa.
- Ghi `index_manifest.json` gồm hash corpus, model, dimension, số bản ghi và ngày build.
- Tạo entrypoint pipeline hợp nhất duy nhất.

Điều kiện hoàn thành: build sạch từ đầu và build lặp lại cho cùng manifest; index đang phục
vụ không bao giờ ở trạng thái dở dang.

## Giai đoạn 3 — Retrieval an toàn

- Hybrid vector + BM25 + reranker.
- Chuẩn hóa filter trạng thái pháp lý.
- Thêm domain gate, ngưỡng reranker và khoảng cách vector.
- Giới hạn context theo token; mở rộng Khoản/Điều có kiểm soát.
- Trả kết quả có evidence ID và URL nguồn.

Điều kiện hoàn thành: câu hỏi ngoài phạm vi trong evaluation bị từ chối; câu hỏi trong phạm
vi đạt Recall@5 và MRR theo ngưỡng đã định.

## Giai đoạn 4 — Generation và citation

- Khởi tạo LLM client lazy; lỗi cấu hình API key phải rõ ràng.
- Dùng structured output cho answer và citations.
- Kiểm tra citation sau sinh: chunk tồn tại, văn bản/Điều khớp và quote có trong nguồn.
- Không sinh câu trả lời khi retrieval không đủ bằng chứng.

Điều kiện hoàn thành: 100% citation máy kiểm tra được trên evaluation; không có câu trả lời
khẳng định khi domain gate/retrieval confidence không đạt.

## Giai đoạn 5 — Reproducibility và bàn giao

- `.gitignore`, dependency manifest/lock, tài liệu biến môi trường.
- Unit test cho parser, chunker, dedupe, index reconciliation, filters và citation verifier.
- Evaluation regression chạy bằng một lệnh và sinh báo cáo JSON.
- Tài liệu vận hành, cập nhật nguồn và rollback corpus/index.

Sau khi hoàn tất năm giai đoạn trên mới thiết kế API backend và giao diện frontend.
