# Hệ thống hỏi đáp pháp luật lao động

Dự án xây dựng hệ thống hỏi đáp tiếng Việt sử dụng RAG trên tập văn bản pháp
luật lao động. Repository hiện gồm giao diện React, bộ dữ liệu canonical và
runtime truy hồi; backend API sẽ được xây dựng trong thư mục `be/`.

## Cấu trúc

- `fe/`: giao diện React 19, TypeScript và Vite.
- `be/`: vị trí triển khai backend API.
- `legal_data/`: corpus, bộ đánh giá và mã lõi RAG.
- `requirements.txt`: dependency Python đã dùng để xác minh hệ thống.
- `.env.example`: biến môi trường mẫu, không chứa khóa bí mật.

## Trạng thái RAG

- 1.710 điều luật đã chuẩn hóa thành 3.410 chunk canonical.
- Đã tích hợp và QA đủ `11/2025/TT-BNV`, `12/2025/TT-BNV` và
  `56/2025/TT-BYT`; các nguồn bị thay thế tương ứng không còn trong current corpus.
- Vector embedding 768 chiều, cosine; index được quản lý theo phiên bản và chỉ
  được promote khi Chroma/BM25 khớp toàn bộ ID cùng hash corpus.
- Bộ đánh giá retrieval có 66 case; cần chạy báo cáo GPU mới sau mỗi lần đổi
  corpus, index hoặc gold label.

## Thiết lập

```powershell
python -m venv .venv
.venv\Scripts\pip.exe install -r requirements.txt
Copy-Item .env.example .env
cd fe
npm install
```

Điền `OPENROUTER_API_KEY` trong `.env` khi sử dụng chức năng sinh câu trả lời (mặc định model Gemma 26B Free `google/gemma-4-26b-a4b-it:free`, fallback `qwen/qwen3.8-27b:free`).

## Chạy dự án (Frontend & Backend)

Hệ thống yêu cầu chạy song song cả API Backend và Web Frontend. Bạn nên mở 2 terminal (cửa sổ dòng lệnh) riêng biệt:

**Terminal 1: Chạy Backend (FastAPI)**
```powershell
# Từ thư mục gốc (dacs)
.venv\Scripts\activate
cd be
pip install -r requirements.txt
python -m uvicorn main:app --port 8000 --reload
# Backend sẽ chạy ở http://127.0.0.1:8000
```

**Terminal 2: Chạy Frontend (React/Vite)**
```powershell
# Từ thư mục gốc (dacs)
cd fe
npm install
npm run dev
# Frontend sẽ chạy ở http://localhost:5173
```

Chi tiết dữ liệu, index và các lệnh kiểm tra nằm trong
[`legal_data/README.md`](legal_data/README.md).
