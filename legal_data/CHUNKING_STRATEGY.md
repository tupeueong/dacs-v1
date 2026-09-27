# Chiến lược chunk cho corpus pháp luật lao động

## Trạng thái dữ liệu đầu vào

Nguồn dùng để chunk phải là:

`legal_data/external/phapdien_labor/processed/articles.clean.jsonl`

Không chunk trực tiếp `articles.jsonl`. Bản `processed` đã:

- chuẩn hóa Unicode NFC, khoảng trắng và ký tự điều khiển;
- giữ cả `content_text_raw` để truy nguyên;
- tách phụ lục bị ghép vào Điều thành `attachments.jsonl`;
- loại các dòng tên tệp như `Phuluc 01.doc` khỏi nội dung Điều;
- trích số hiệu văn bản gốc và ngày hiệu lực từ `source_note_text`;
- gắn cờ sửa đổi, bổ sung, bãi bỏ một phần;
- đánh dấu nhóm nội dung trùng nhưng không tự ý xóa bản ghi;
- giữ revision, URL và thời điểm thu thập.

Báo cáo máy đọc được nằm tại `processed/qa_report.json`.

## Các phương án đã xem xét

### 1. Cửa sổ cố định theo ký tự

Dễ triển khai nhưng có thể cắt giữa Khoản/Điểm, làm mất chủ thể, điều kiện hoặc
ngoại lệ. Không chọn làm phương án chính.

### 2. Cửa sổ cố định theo token có overlap

Kiểm soát được giới hạn model nhưng vẫn phá cấu trúc pháp lý và tạo nhiều kết quả
trùng. Chỉ dùng làm fallback cuối cùng cho một đơn vị cấu trúc quá dài.

### 3. Semantic chunking

Có thể tìm ranh giới chủ đề nhưng ranh giới ngữ nghĩa không nhất thiết trùng ranh
giới có hiệu lực pháp lý. Một Điểm hoặc Khoản không nên bị ghép sang Điều khác chỉ
vì gần nhau về embedding. Không chọn làm splitter chính.

### 4. LLM/contextual chunking, RAPTOR hoặc summary-generated chunks

Có thể bổ sung ngữ cảnh toàn văn bản nhưng tốn chi phí, khó tái lập và có nguy cơ
đưa diễn giải sinh bởi LLM vào corpus luật. Có thể thử nghiệm sau như một trường
`context_summary`, không thay thế văn bản gốc.

### 5. Late chunking

Cần embedding model hỗ trợ ngữ cảnh dài và truy cập token embeddings trước bước
pooling. Model hiện tại `truro7/vn-law-embedding` có giới hạn 512 token nên không
phù hợp với late chunking trên toàn Điều dài.

### 6. Chunk phân cấp theo cấu trúc pháp luật

Giữ Điều làm đơn vị cha; chỉ tách Điều dài theo Khoản, sau đó theo Điểm và cuối
cùng mới theo câu/token. Đây là phương án được chọn.

## Căn cứ lựa chọn

- *Chunking German Legal Code* (2026) so sánh nhiều chiến lược trên luật thành văn
  và cho thấy đơn vị bám cấu trúc điều/khoản đạt recall tốt hơn các phương pháp phức
  tạp phá vỡ cấu trúc: <https://arxiv.org/abs/2605.19806>.
- *LegalBench-RAG* ưu tiên đoạn tối thiểu nhưng đủ căn cứ thay vì trả cả tài liệu hoặc
  khối dài thiếu chính xác: <https://arxiv.org/abs/2408.10343>.
- *A Systematic Investigation of Document Chunking Strategies and Embedding
  Sensitivity* ghi nhận paragraph grouping mạnh ở miền pháp lý và fixed-character
  chunking hoạt động kém: <https://arxiv.org/abs/2603.06976>.
- Model card của `truro7/vn-law-embedding` cho thấy model được huấn luyện để truy hồi
  văn bản pháp luật Việt Nam; kiểm tra runtime xác nhận giới hạn 512 token:
  <https://huggingface.co/truro7/vn-law-embedding>.

## Thiết kế được chọn

### Đơn vị và thứ tự tách

1. Nếu toàn Điều vừa ngân sách: giữ nguyên Điều.
2. Nếu dài: gom các Khoản hoàn chỉnh (`1.`, `2.`, ...).
3. Khoản quá dài: tách theo Điểm (`a)`, `b)`, `đ)`, ...), luôn lặp lại nhãn Khoản cha.
4. Điểm quá dài: tách theo câu/dấu chấm phẩy.
5. Chỉ hard-split theo token khi một câu hoặc một dòng bảng vẫn vượt giới hạn.

Không ghép nội dung của hai Điều khác nhau vào cùng chunk.

### Ngân sách token

- hard maximum: **448 token**;
- target khi gom: **384 token**;
- dành phần còn lại trong giới hạn 512 token cho sai số tokenizer và metadata;
- đo bằng đúng tokenizer của `truro7/vn-law-embedding`, không ước lượng ký tự.

### Context gắn vào từng chunk

`embed_text` gồm context ngắn, có cấu trúc và phần nội dung nguyên văn:

```text
Chủ đề: Lao động
Đề mục: Lao động
Chương: ...
Nguồn gốc: Điều 112 Bộ luật số 45/2019/QH14, hiệu lực từ 01/01/2021
Pháp điển: Điều 20.2.LQ.112 — Nghỉ lễ, tết
Khoản cha: ...                 # chỉ khi chunk là Điểm/phần con

<nội dung nguyên văn>
```

Không dùng tóm tắt do LLM trong trường văn bản được embedding ở phiên bản đầu.

### ID và quan hệ cha-con

- khóa Điều: `record_id`;
- khóa chunk: `phapdien:{record_id}:{structural_path}:{part}`;
- `article_id` chỉ để hiển thị/trích dẫn vì có mã bị tái sử dụng;
- mỗi chunk có `parent_record_id`, `structural_level`, `clause_number`,
  `point_label`, `part`, `n_parts`, `content_hash`;
- phụ lục dùng `chunk_type=appendix` và index riêng hoặc giảm trọng số.

### Trùng lặp

Không xóa bản ghi chỉ vì trùng `content_hash`, do provenance có thể khác nhau.
Sau retrieval, collapse theo `content_hash`, giữ bản có điểm cao nhất và gộp danh
sách nguồn tương đương.

### Mở rộng context khi sinh câu trả lời

Không mặc định lấy toàn bộ Điều dài. Khi một chunk trúng:

1. lấy chunk đó;
2. lấy chunk liền trước/sau cùng `parent_record_id` nếu cần;
3. lấy toàn Điều chỉ khi tổng token nằm trong ngân sách context;
4. luôn kèm `source_note_text` và `source_url` để tạo trích dẫn.

## Tiêu chí chấp nhận trước embedding

- không chunk nào vượt 448 token theo tokenizer thật;
- không cắt giữa nhãn Khoản/Điểm và nội dung của nó;
- mọi chunk truy ngược được tới đúng một `record_id`;
- 100% chunk có nguồn gốc, revision và URL;
- không có chunk rỗng, ID trùng hoặc lỗi UTF-8;
- kiểm thử retrieval có ground truth cho tối thiểu 30 câu hỏi lao động;
- báo cáo Recall@5, Recall@10, MRR@10 và tỷ lệ trích đúng nguồn.

