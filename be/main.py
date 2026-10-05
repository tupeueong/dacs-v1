"""FastAPI backend for the Vietnamese Labor Law RAG Assistant.

Endpoints (matching the contract in fe/src/api.js):
    GET  /api/health     → system health check
    GET  /api/index-info → RAG index metadata
    POST /api/chat       → ask a legal question and receive a grounded answer

Run:
    cd be && python -m uvicorn main:app --port 8000 --reload
"""

from __future__ import annotations

import asyncio
import logging
import sys
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Path bootstrap — ensure the RAG scripts package is importable.
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parents[1]  # dacs/
LEGAL_SCRIPTS = ROOT / "legal_data" / "scripts"
if str(LEGAL_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(LEGAL_SCRIPTS))

load_dotenv(ROOT / ".env")

from generate_safe import GroundedGenerator  # noqa: E402
from retrieve_v2 import SafeRetriever  # noqa: E402
from services.response_adapter import adapt_rag_response  # noqa: E402

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
)
logger = logging.getLogger("be.main")

# ---------------------------------------------------------------------------
# Concurrency guard — heavyweight models should not run in parallel.
# ---------------------------------------------------------------------------
MAX_CONCURRENT_RAG = 2
_rag_semaphore = asyncio.Semaphore(MAX_CONCURRENT_RAG)


# ---------------------------------------------------------------------------
# Lifespan — initialise the GroundedGenerator singleton at startup.
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup/shutdown lifecycle.

    Heavy one-time work (load embeddings, BM25 index, cross-encoder) happens
    here so that individual requests don't pay the cold-start penalty.
    """
    logger.info("🚀 Initialising RAG pipeline (this may take 20-30 s) …")
    start = time.perf_counter()

    # Build retriever + generator on a background thread to avoid blocking
    # the event loop during startup.
    retriever = await asyncio.to_thread(SafeRetriever)
    generator = GroundedGenerator(retriever=retriever)

    elapsed = time.perf_counter() - start
    logger.info("✅ RAG pipeline ready in %.1f s (available=%s)", elapsed, generator.available)

    app.state.generator = generator
    app.state.retriever = retriever
    yield
    logger.info("⏹  Backend shutting down.")


# ---------------------------------------------------------------------------
# Application
# ---------------------------------------------------------------------------
app = FastAPI(
    title="Trợ lý Luật Lao động Việt Nam – Backend API",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS — allow the Vite dev server (port 5173) and any localhost origin.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------
class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000)


class SourceItem(BaseModel):
    doc_title: str = ""
    article: str = ""
    clause: str = ""
    text: str = ""


class ChatResponse(BaseModel):
    answer: str
    sources: list[SourceItem] = []


# ---------------------------------------------------------------------------
# GET /api/health
# ---------------------------------------------------------------------------
@app.get("/api/health")
async def health_check() -> dict[str, Any]:
    """Return system health status.

    Frontend expects: { status, checks, message }
    """
    generator: GroundedGenerator = app.state.generator
    retriever: SafeRetriever = app.state.retriever

    checks = {
        "backend": True,
        "vector_index": retriever is not None,
        "openrouter_api": bool(generator.api_key),
        "retriever": generator.available,
    }
    all_ok = all(checks.values())

    return {
        "status": "ok" if all_ok else "degraded",
        "service": "labor-law-rag-agent",
        "checks": checks,
        "message": (
            "Hệ thống sẵn sàng phục vụ tra cứu"
            if all_ok
            else "Một số thành phần chưa sẵn sàng"
        ),
    }


# ---------------------------------------------------------------------------
# GET /api/index-info
# ---------------------------------------------------------------------------
@app.get("/api/index-info")
async def index_info() -> dict[str, Any]:
    """Return metadata about the vector index and RAG configuration."""
    retriever: SafeRetriever = app.state.retriever
    generator: GroundedGenerator = app.state.generator
    manifest = retriever.manifest
    verification = manifest.get("verification") or {}

    return {
        "status": "ready",
        "corpus_name": "Dữ liệu pháp điển & Luật Lao động Việt Nam",
        "article_count": verification.get("article_count"),
        "chunk_count": verification.get("chunk_count"),
        "embedding_dimension": verification.get("embedding_dimension"),
        "distance_metric": verification.get("distance_metric"),
        "embedding_model": manifest.get("embedding_model"),
        "rerank_model": manifest.get("rerank_model", "BAAI/bge-reranker-v2-m3"),
        "generator_model": generator.model_name,
        "active_pointer": str(retriever.index_dir),
        "index_version": (
            manifest.get("index_version") or manifest.get("version")
        ),
        "last_updated": manifest.get("created_at"),
    }


# ---------------------------------------------------------------------------
# POST /api/chat
# ---------------------------------------------------------------------------
@app.post("/api/chat", response_model=ChatResponse)
async def chat(payload: ChatRequest) -> dict[str, Any]:
    """Receive a legal question and return a grounded RAG answer.

    The heavy retrieval + generation call runs on a thread pool to keep the
    async event loop responsive.
    """
    question = payload.message.strip()
    if not question:
        raise HTTPException(status_code=400, detail={
            "message": "Câu hỏi không được để trống."
        })

    generator: GroundedGenerator = app.state.generator

    if not generator.available:
        raise HTTPException(status_code=503, detail={
            "message": "Pipeline RAG chưa được khởi tạo hoặc thiếu OPENROUTER_API_KEY."
        })

    logger.info("💬 Nhận câu hỏi: %s", question[:120])
    start = time.perf_counter()

    try:
        async with _rag_semaphore:
            raw_result = await asyncio.to_thread(generator.answer, question)
    except Exception as exc:
        logger.exception("RAG pipeline error")
        raise HTTPException(status_code=500, detail={
            "message": f"Lỗi xử lý nội bộ: {exc}"
        }) from exc

    elapsed = time.perf_counter() - start
    logger.info(
        "✅ Trả lời trong %.1f s | answerable=%s | error_code=%s",
        elapsed,
        raw_result.get("answerable"),
        raw_result.get("error_code", "none"),
    )

    # Adapt the rich RAG output to the simple frontend contract.
    adapted = adapt_rag_response(raw_result)
    return adapted


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host="127.0.0.1",
        port=8000,
        reload=True,
        log_level="info",
    )
