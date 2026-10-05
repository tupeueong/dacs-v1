# Index Builder Refactor Verification Report

Date: 2026-10-05
Old Index (Production): `C:\Users\dang khoa\Desktop\dacs\legal_data\vectorstore_versions\labor-rag-index.v2-fbc986cb0ee7-truro7-vn-law-embedding`
New Index (Staging): `C:\Users\dang khoa\Desktop\dacs\legal_data\vectorstore_versions\labor-rag-index.v2-fbc986cb0ee7-truro7-vn-law-embedding.staging`

## 1. ID & Count Verification
- Chroma ID Count Match: **PASS** (Old: 3410, New: 3410)
- Chroma ID Set Match: **PASS**
- BM25 ID Count Match: **PASS** (Old: 3410, New: 3410)
- BM25 ID Set Match: **PASS**

## 2. Embedding Verification
- Sampled 20 chunks for vector equality check.
- Vector Identity Check (`atol=1e-5`): **PASS**

## 3. Retrieval Verification
- Query: `Mức đóng bảo hiểm xã hội bắt buộc đối với người lao động là bao nhiêu?` -> **PASS** (Hits identical)
- Query: `Làm thêm giờ vào ngày nghỉ lễ, tết được trả lương thế nào?` -> **PASS** (Hits identical)
- Query: `Thời gian thử việc tối đa là bao lâu?` -> **PASS** (Hits identical)

## Overall Result: **PASS**
The refactored builder correctly preserves existing behavior mà không thay đổi nội dung vector hay thuật toán BM25.
