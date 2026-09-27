# Vận hành RAG luật lao động trước backend

## Build chuẩn

```powershell
.venv\Scripts\python.exe -X utf8 legal_data\scripts\run_unified_labor_pipeline_v3.py
```

Thêm `--refresh-official` khi cần tải lại nguồn Công báo. Có thể dùng
`--skip-embedding` khi chỉ kiểm tra dữ liệu/chunk.

Pipeline chuẩn thực hiện: registry → parse nguồn chính thức → đồng bộ trạng thái → hợp nhất
văn bản 2026 → chunk → index staging cosine → verify → evaluation. Con trỏ
`legal_data/vectorstore_versions/current.json` chỉ được đổi sau khi index vượt qua kiểm tra.

## Runtime

Retrieval an toàn:

```powershell
.venv\Scripts\python.exe -X utf8 legal_data\scripts\retrieve_v2.py
```

Generation có kiểm chứng citation:

```powershell
.venv\Scripts\python.exe -X utf8 legal_data\scripts\generate_safe.py
```

`generate_safe.py` yêu cầu `GEMINI_API_KEY` trong `.env`. Không commit `.env`.

## Cổng QA

```powershell
.venv\Scripts\python.exe -X utf8 legal_data\scripts\verify_index_v2.py
.venv\Scripts\python.exe -X utf8 legal_data\scripts\evaluate_retrieval_v2.py
.venv\Scripts\python.exe -X utf8 -m unittest discover -s legal_data\tests -p "test_*.py" -v
```

Không triển khai backend trên một index nếu bất kỳ lệnh nào ở trên thất bại.

## Cập nhật nguồn

- Nguồn chính thức ưu tiên: Công báo điện tử và CSDL quốc gia về VBPL.
- Mỗi văn bản mới phải có SHA-256, URL nguồn, ngày ban hành/hiệu lực và QA số Điều.
- Với bãi bỏ một phần, phải đánh dấu ở cấp Khoản/Điểm; không chỉ gắn trạng thái toàn Điều.
- Danh sách còn chờ xử lý nằm tại
  `external/official_labor_2024_2026/source_registry.current.report.json`.

