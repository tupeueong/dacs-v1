# Pipeline chuẩn cho dữ liệu Pháp điển lao động

Đầu vào chuẩn là `articles.jsonl`. Đầu ra dùng cho chunking là
`processed/articles.final.jsonl`; chỉ mục cuối cùng nằm tại
`legal_data/vectorstore_phapdien_labor`.

Chạy toàn bộ quy trình:

```powershell
.\.venv\Scripts\python.exe legal_data\scripts\run_phapdien_labor_pipeline.py
```

Chỉ tiền xử lý và chunk, chưa embedding:

```powershell
.\.venv\Scripts\python.exe legal_data\scripts\run_phapdien_labor_pipeline.py --skip-embedding
```

Không dùng hoặc tái tạo `external/phapdien_labor/chunks.jsonl`; đó là định dạng
thử nghiệm cũ theo số ký tự. Chunk chuẩn là `chunked/chunks.jsonl`, được đo bằng
tokenizer thật của `truro7/vn-law-embedding` và giữ cấu trúc Điều/Khoản/Điểm.
