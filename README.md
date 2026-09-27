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

- 1.662 điều luật đã chuẩn hóa.
- 3.301 chunks trong corpus canonical.
- Vector embedding 768 chiều, cosine; BM25 và vector ID khớp hoàn toàn.
- Đánh giá retrieval: 8/8 câu trong miền đúng, 4/4 câu ngoài miền bị từ chối.
- Còn ba nguồn ưu tiên cần bổ sung: `11/2025/TT-BNV`, `12/2025/TT-BNV` và
  `56/2025/TT-BYT`.

## Thiết lập

```powershell
python -m venv .venv
.venv\Scripts\pip.exe install -r requirements.txt
Copy-Item .env.example .env
cd fe
npm install
```

Điền `GEMINI_API_KEY` trong `.env` khi sử dụng chức năng sinh câu trả lời.

## Chạy frontend

```powershell
cd fe
npm run dev
```

Chi tiết dữ liệu, index và các lệnh kiểm tra nằm trong
[`legal_data/README.md`](legal_data/README.md).
