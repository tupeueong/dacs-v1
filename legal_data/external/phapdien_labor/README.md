# Pháp điển lao động

## Dữ liệu nguồn

- `articles.jsonl`: bản chuẩn hóa ban đầu từ Parquet; giữ để đối chiếu.
- `chunks.jsonl`: bản chunk thử nghiệm cũ theo giới hạn ký tự. **Không dùng để
  embedding**, vì một số `embed_text` vượt giới hạn 512 token của model.

## Dữ liệu đã tiền xử lý

- `processed/articles.clean.jsonl`: đầu vào chuẩn cho chunker mới.
- `processed/attachments.jsonl`: phụ lục được tách khỏi nội dung Điều.
- `processed/qa_report.json`: báo cáo chất lượng và provenance.

Chạy lại tiền xử lý:

```powershell
.\.venv\Scripts\python.exe legal_data\scripts\preprocess_phapdien_labor.py
```

Quy tắc chunk được mô tả tại `legal_data/CHUNKING_STRATEGY.md`. Chỉ tạo embedding
sau khi chunker token-aware đạt toàn bộ tiêu chí trong tài liệu đó.

