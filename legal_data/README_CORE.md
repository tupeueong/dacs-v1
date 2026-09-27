# Core labor-law RAG

Canonical data:

- `rag_corpus/articles.jsonl`
- `rag_corpus/chunks.jsonl`
- local active index selected by `vectorstore_versions/current.json`

Core commands:

```powershell
# Rebuild the vector/BM25 index from canonical chunks
.venv\Scripts\python.exe -X utf8 legal_data\scripts\build_index_v4.py

# Verify index integrity
.venv\Scripts\python.exe -X utf8 legal_data\scripts\verify_index_v2.py

# Evaluate retrieval and run the backend-readiness gate
.venv\Scripts\python.exe -X utf8 legal_data\scripts\evaluate_retrieval_v2.py
.venv\Scripts\python.exe -X utf8 legal_data\scripts\pre_backend_gate.py
```

Backend runtime should import `SafeRetriever` from `retrieve_v2.py` and
`GroundedGenerator` from `generate_safe.py`.
