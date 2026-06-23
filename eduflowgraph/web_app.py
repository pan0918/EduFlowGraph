from __future__ import annotations

import json
from typing import Any

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, StreamingResponse
from pydantic import BaseModel

from .config import Settings, load_settings_from_mapping
from .llm import LLMClient
from .pipeline import TutorPipeline


class ChatRequest(BaseModel):
    session_id: str = "session_demo"
    message: str
    memory_mode: str = "ordinary"
    runtime: dict[str, Any] | None = None
    provider: str = "mock"
    api_key: str = ""
    base_url: str = "https://api.openai.com/v1"
    chat_model: str = "gpt-4o-mini"
    embedding_model: str = "text-embedding-3-small"
    extraction_turns: int = 4


class ExtractRequest(BaseModel):
    session_id: str = "session_demo"
    runtime: dict[str, Any] | None = None
    provider: str = "mock"
    api_key: str = ""
    base_url: str = "https://api.openai.com/v1"
    chat_model: str = "gpt-4o-mini"
    embedding_model: str = "text-embedding-3-small"
    extraction_turns: int = 4


class DiagnosticsRequest(BaseModel):
    kind: str
    runtime: dict[str, Any] | None = None
    provider: str = "mock"
    api_key: str = ""
    base_url: str = "https://api.openai.com/v1"
    chat_model: str = "gpt-4o-mini"
    embedding_model: str = "text-embedding-3-small"


class RebuildRetrievalRequest(BaseModel):
    data_dir: str = "data"
    runtime: dict[str, Any] | None = None
    provider: str = "mock"
    api_key: str = ""
    base_url: str = "https://api.openai.com/v1"
    chat_model: str = "gpt-4o-mini"
    embedding_model: str = "text-embedding-3-small"


def _settings(payload: ChatRequest | ExtractRequest | None = None) -> Settings:
    if payload is None:
        return load_settings_from_mapping({"data_dir": "data", "provider": "mock"})
    values = payload.model_dump()
    if payload.runtime is not None:
        values["runtime"] = payload.runtime
    return _settings_from_values(values)


def _settings_from_values(values: dict[str, Any]) -> Settings:
    values = {**values, "data_dir": values.get("data_dir") or "data"}
    return load_settings_from_mapping(values)


def _client_from_settings(settings: Settings) -> LLMClient:
    return LLMClient(
        settings.llm.provider,
        settings.llm.api_key,
        settings.llm.base_url,
        settings.llm.model_id,
        settings.embedding.model_id,
        llm_name=settings.llm.name,
        llm_api_version=settings.llm.api_version,
        llm_extra_headers=settings.llm.extra_headers,
        embedding_provider=settings.embedding.provider,
        embedding_api_key=settings.embedding.api_key,
        embedding_endpoint_url=settings.embedding.endpoint_url,
        embedding_api_version=settings.embedding.api_version,
        embedding_extra_headers=settings.embedding.extra_headers,
        embedding_dimensions=settings.embedding.dimensions,
        embedding_send_dimensions=settings.embedding.send_dimensions,
        embedding_name=settings.embedding.name,
        reranker_provider=settings.reranker.provider,
        reranker_api_key=settings.reranker.api_key,
        reranker_endpoint_url=settings.reranker.endpoint_url,
        reranker_api_version=settings.reranker.api_version,
        reranker_extra_headers=settings.reranker.extra_headers,
        reranker_model_id=settings.reranker.model_id,
        reranker_name=settings.reranker.name,
    )


_pipeline_key: tuple[Any, ...] | None = None
_pipeline: TutorPipeline | None = None


def get_pipeline(settings: Settings) -> TutorPipeline:
    global _pipeline_key, _pipeline
    key = (
        settings.llm.provider,
        settings.llm.api_key,
        settings.llm.base_url,
        settings.llm.api_version,
        tuple(sorted(settings.llm.extra_headers.items())),
        settings.llm.model_id,
        settings.embedding.provider,
        settings.embedding.api_key,
        settings.embedding.endpoint_url,
        settings.embedding.api_version,
        tuple(sorted(settings.embedding.extra_headers.items())),
        settings.embedding.model_id,
        settings.embedding.dimensions,
        settings.embedding.send_dimensions,
        settings.reranker.provider,
        settings.reranker.api_key,
        settings.reranker.endpoint_url,
        settings.reranker.api_version,
        tuple(sorted(settings.reranker.extra_headers.items())),
        settings.reranker.model_id,
        settings.extraction_turns,
        str(settings.data_dir),
        settings.storage_backend,
        str(settings.resolved_database_path.resolve()),
    )
    if _pipeline is None or _pipeline_key != key:
        _pipeline = TutorPipeline(settings)
        _pipeline_key = key
    return _pipeline


app = FastAPI(title="EduFlowGraph Tutor")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:3000",
        "http://localhost:3000",
        "http://127.0.0.1:3001",
        "http://localhost:3001",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def add_api_cache_headers(request: Request, call_next):
    response = await call_next(request)
    if request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
    return response


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/dashboard")
def dashboard() -> dict[str, Any]:
    return get_pipeline(_settings()).dashboard()


@app.post("/api/chat")
def chat(payload: ChatRequest) -> dict[str, Any]:
    pipeline = get_pipeline(_settings(payload))
    result = pipeline.handle_user_message(
        payload.session_id,
        payload.message,
        memory_mode=payload.memory_mode,
    )
    snapshot = pipeline.dashboard()
    return {
        "answer": result["answer"],
        "context": result["context"],
        "turn": result["turn"],
        "episode": result["episode"],
        "boundary": result["boundary"],
        "usage": result.get("usage", {}),
        "snapshot": snapshot,
    }


@app.post("/api/chat/stream")
def chat_stream(payload: ChatRequest) -> StreamingResponse:
    pipeline = get_pipeline(_settings(payload))

    def event_stream():
        for event in pipeline.stream_user_message(
            payload.session_id,
            payload.message,
            memory_mode=payload.memory_mode,
        ):
            if event.get("type") in {"final", "memory"}:
                event = {**event, "snapshot": pipeline.dashboard()}
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@app.post("/api/extract")
def extract(payload: ExtractRequest) -> dict[str, Any]:
    pipeline = get_pipeline(_settings(payload))
    episode = pipeline.force_extract(payload.session_id)
    return {"episode": episode, "snapshot": pipeline.dashboard()}


@app.post("/api/diagnostics/model-test")
def diagnostics(payload: DiagnosticsRequest) -> dict[str, Any]:
    settings = _settings_from_values(payload.model_dump())
    client = _client_from_settings(settings)
    if payload.kind == "embedding":
        return client.test_embedding_connection()
    if payload.kind == "reranker":
        return client.test_reranker_connection()
    return client.test_llm_connection()


@app.post("/api/rebuild-retrieval")
def rebuild_retrieval(payload: RebuildRetrievalRequest) -> dict[str, Any]:
    pipeline = get_pipeline(_settings_from_values(payload.model_dump()))
    stats = pipeline.rebuild_retrieval_embeddings()
    return {**stats, "snapshot": pipeline.dashboard()}


@app.post("/api/reset-memory")
def reset_memory(payload: RebuildRetrievalRequest) -> dict[str, Any]:
    pipeline = get_pipeline(_settings_from_values(payload.model_dump()))
    result = pipeline.reset_memory()
    return {**result, "snapshot": pipeline.dashboard()}


@app.get("/api/sessions")
def list_sessions() -> dict[str, Any]:
    pipeline = get_pipeline(_settings())
    sessions = pipeline.conv_log.list_sessions()
    result = []
    for sid in sessions:
        turns = pipeline.conv_log.list_turns(sid)
        first_user = next(
            (t["user_message"] for t in turns if t.get("user_message", "").strip()),
            "",
        )
        result.append({
            "id": sid,
            "title": first_user[:36] if first_user else "未命名对话",
            "message_count": len(turns) * 2,
            "last_updated": turns[-1]["timestamp"] if turns else "",
        })
    return {"sessions": result}


@app.get("/api/sessions/{session_id}/turns")
def get_session_turns(session_id: str) -> dict[str, Any]:
    pipeline = get_pipeline(_settings())
    turns = pipeline.conv_log.list_turns(session_id)
    return {"turns": turns}
