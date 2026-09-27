"""Chạy luồng sinh câu trả lời trên chỉ mục luật lao động hợp nhất."""

from generate import answer
from retrieve_unified import create_retriever


if __name__ == "__main__":
    retriever = create_retriever()
    while True:
        query = input("Câu hỏi: ").strip()
        if not query or query.lower() in {"thoat", "exit", "quit"}:
            break
        print("\n" + answer(query, retriever) + "\n")
