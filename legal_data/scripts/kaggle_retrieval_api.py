"""GPU retrieval HTTP service for ephemeral Kaggle development sessions."""

from __future__ import annotations

import argparse
import asyncio
import hmac
import os
import time
from contextlib import asynccontextmanager
from typing import Any

import torch
import uvicorn
from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from retrieve_v2 import MAX_QUERY_CHARS, SafeRetriever


API_KEY_ENV = "LEGAL_RAG_API_KEY"
REQUIRE_CUDA_ENV = "LEGAL_RAG_REQUIRE_CUDA"
MAX_TOP_K = 10
MAX_CONCURRENT_RETRIEVALS = 1


class RetrievalRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str = Field(min_length=1, max_length=MAX_QUERY_CHARS)
    top_k: int = Field(default=5, ge=1, le=MAX_TOP_K)
    filters: dict[str, Any] | None = None


def require_api_key(x_api_key: str | None = Header(default=None)) -> None:
    expected = os.getenv(API_KEY_ENV, "")
    if not expected:
        raise HTTPException(status_code=503, detail="API authentication is not configured")
    if x_api_key is None or not hmac.compare_digest(x_api_key, expected):
        raise HTTPException(status_code=401, detail="Invalid API key")


@asynccontextmanager
async def lifespan(app: FastAPI):
    require_cuda = os.getenv(REQUIRE_CUDA_ENV, "1") == "1"
    if require_cuda and not torch.cuda.is_available():
        raise RuntimeError("CUDA is required but unavailable")
    app.state.retriever = SafeRetriever()
    app.state.retrieval_slots = asyncio.Semaphore(MAX_CONCURRENT_RETRIEVALS)
    yield


app = FastAPI(
    title="Vietnamese Labor Law Retrieval API",
    version="1.0.0",
    lifespan=lifespan,
)


@app.get("/health")
async def health() -> dict:
    retriever: SafeRetriever = app.state.retriever
    verification = retriever.manifest.get("verification") or {}
    return {
        "status": "ok",
        "service": "labor-law-retrieval",
        "cuda": torch.cuda.is_available(),
        "gpu": torch.cuda.get_device_name(0) if torch.cuda.is_available() else None,
        "embedding_model": retriever.manifest.get("embedding_model"),
        "embedding_dimension": verification.get("embedding_dimension"),
        "distance_metric": verification.get("distance_metric"),
        "chunk_count": verification.get("chunk_count"),
        "index_dir": str(retriever.index_dir),
        "index_schema_version": retriever.manifest.get("schema_version"),
    }


@app.post("/retrieve", dependencies=[Depends(require_api_key)])
async def retrieve(payload: RetrievalRequest) -> dict:
    retriever: SafeRetriever = app.state.retriever
    started = time.perf_counter()
    try:
        async with app.state.retrieval_slots:
            result = await asyncio.to_thread(
                retriever.search,
                payload.query,
                top_k=payload.top_k,
                filters=payload.filters,
            )
    except (TypeError, ValueError) as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except Exception as error:
        raise HTTPException(status_code=500, detail="Retrieval failed") from error

    # Internal weak candidates must never cross the production API boundary.
    result.pop("diagnostic_candidates", None)
    result["latency_ms"] = round((time.perf_counter() - started) * 1000.0, 3)
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=9999)
    args = parser.parse_args()
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
