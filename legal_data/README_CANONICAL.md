# Labor-law RAG data

The production corpus is stored in `rag_corpus/articles.jsonl` and
`rag_corpus/chunks.jsonl`. The active local vector index is selected by
`vectorstore_versions/current.json` (generated and intentionally not committed).

Canonical commands from the repository root:

```powershell
.venv\Scripts\python.exe -X utf8 legal_data\scripts\run_unified_labor_pipeline_v4.py
.venv\Scripts\python.exe -X utf8 legal_data\scripts\verify_index_v2.py
.venv\Scripts\python.exe -X utf8 legal_data\scripts\evaluate_retrieval_v2.py
.venv\Scripts\python.exe -X utf8 legal_data\scripts\pre_backend_gate.py
```

Runtime entry points are `retrieve_v2.py` and `generate_safe.py`. The three
remaining priority sources are tracked in
`external/official_labor_2024_2026/source_registry.current.jsonl`.
