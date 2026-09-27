"""Entrypoint truy xuất bộ dữ liệu RAG luật lao động hợp nhất."""

from retrieve import Retriever


INDEX_DIR = "legal_data/vectorstore_labor_unified"


def create_retriever(**kwargs) -> Retriever:
    """Tạo retriever dùng chỉ mục hợp nhất; cho phép truyền tùy chọn của Retriever."""
    return Retriever(INDEX_DIR, **kwargs)


if __name__ == "__main__":
    retriever = create_retriever()
    while True:
        query = input("Câu hỏi: ").strip()
        if not query or query.lower() in {"thoat", "exit", "quit"}:
            break
        for hit in retriever.retrieve(query, top_k=5):
            print(
                f"{hit['rerank_score']:.3f}  {hit['doc_title']} - "
                f"{hit.get('article_title')} ({hit['chunk_id']})"
            )
