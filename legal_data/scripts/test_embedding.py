from sentence_transformers import SentenceTransformer

model = SentenceTransformer("truro7/vn-law-embedding")   # lần đầu sẽ tải khoảng 1.1 GB

cau = [
    "Mức phạt khi không giao kết hợp đồng lao động bằng văn bản",
    "Doanh nghiệp không ký hợp đồng lao động thì bị xử phạt bao nhiêu",
    "Thủ tục đăng ký kết hôn",
]
vec = model.encode(cau, normalize_embeddings=True)
print(vec.shape)   # (3, 768) hoặc tương tự

# 2 câu đầu cùng chủ đề luật lao động phải giống nhau hơn câu thứ 3 (không liên quan)
print(model.similarity(vec, vec))