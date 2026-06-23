import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


def _coerce_headers(raw: Any) -> dict[str, str]:
    if isinstance(raw, dict):
        return {str(key): str(value) for key, value in raw.items() if value is not None}
    return {}


@dataclass
class LLMRuntimeConfig:
    provider: str = field(default_factory=lambda: os.getenv("EDUFLOW_PROVIDER", "mock"))
    name: str = ""
    api_key: str = field(default_factory=lambda: os.getenv("OPENAI_API_KEY", ""))
    base_url: str = field(default_factory=lambda: os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"))
    api_version: str = ""
    extra_headers: dict[str, str] = field(default_factory=dict)
    model_id: str = field(default_factory=lambda: os.getenv("EDUFLOW_CHAT_MODEL", "gpt-4o-mini"))
    model_label: str = ""
    context_window: int | None = None


@dataclass
class EmbeddingRuntimeConfig:
    provider: str = field(default_factory=lambda: os.getenv("EDUFLOW_PROVIDER", "mock"))
    name: str = ""
    api_key: str = field(default_factory=lambda: os.getenv("OPENAI_API_KEY", ""))
    endpoint_url: str = field(default_factory=lambda: os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/") + "/embeddings")
    api_version: str = ""
    extra_headers: dict[str, str] = field(default_factory=dict)
    model_id: str = field(default_factory=lambda: os.getenv("EDUFLOW_EMBEDDING_MODEL", "text-embedding-3-small"))
    model_label: str = ""
    dimensions: int | None = None
    send_dimensions: bool = False


@dataclass
class RerankerRuntimeConfig:
    provider: str = field(default_factory=lambda: os.getenv("EDUFLOW_PROVIDER", "mock"))
    name: str = ""
    api_key: str = field(default_factory=lambda: os.getenv("OPENAI_API_KEY", ""))
    endpoint_url: str = field(default_factory=lambda: os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/") + "/rerank")
    api_version: str = ""
    extra_headers: dict[str, str] = field(default_factory=dict)
    model_id: str = field(default_factory=lambda: os.getenv("EDUFLOW_RERANKER_MODEL", ""))
    model_label: str = ""


@dataclass
class Settings:
    data_dir: Path = field(default_factory=lambda: Path(os.getenv("EDUFLOW_DATA_DIR", "data")))
    storage_backend: str = field(default_factory=lambda: os.getenv("EDUFLOW_STORAGE_BACKEND", "sqlite"))
    database_path: Path | None = field(
        default_factory=lambda: Path(value)
        if (value := os.getenv("EDUFLOW_DATABASE_PATH", "")).strip()
        else None
    )
    extraction_turns: int = field(default_factory=lambda: int(os.getenv("EDUFLOW_EXTRACTION_TURNS", "4")))
    llm: LLMRuntimeConfig = field(default_factory=LLMRuntimeConfig)
    embedding: EmbeddingRuntimeConfig = field(default_factory=EmbeddingRuntimeConfig)
    reranker: RerankerRuntimeConfig = field(default_factory=RerankerRuntimeConfig)

    @property
    def conversations_dir(self) -> Path:
        return self.data_dir / "conversations"

    @property
    def memory_flow_path(self) -> Path:
        return self.data_dir / "memory_flow.jsonl"

    @property
    def nodes_path(self) -> Path:
        return self.data_dir / "graph_nodes.json"

    @property
    def edges_path(self) -> Path:
        return self.data_dir / "graph_edges.json"

    @property
    def profile_evidence_path(self) -> Path:
        return self.data_dir / "profile_evidence.jsonl"

    @property
    def profile_view_path(self) -> Path:
        return self.data_dir / "learner_profile.json"

    @property
    def resolved_database_path(self) -> Path:
        return self.database_path or self.data_dir / "eduflowgraph.db"


def load_settings_from_mapping(values: dict) -> Settings:
    runtime = values.get("runtime") or {}
    llm_values = runtime.get("llm") or {}
    embedding_values = runtime.get("embedding") or {}
    reranker_values = runtime.get("reranker") or {}

    provider = values.get("provider") or os.getenv("EDUFLOW_PROVIDER", "mock")
    api_key = values.get("api_key") or os.getenv("OPENAI_API_KEY", "")
    base_url = values.get("base_url") or os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
    chat_model = values.get("chat_model") or os.getenv("EDUFLOW_CHAT_MODEL", "gpt-4o-mini")
    embedding_model = values.get("embedding_model") or os.getenv("EDUFLOW_EMBEDDING_MODEL", "text-embedding-3-small")

    storage_backend = str(
        values.get("storage_backend")
        or os.getenv("EDUFLOW_STORAGE_BACKEND", "sqlite")
    ).strip().lower()
    if storage_backend not in {"json", "sqlite"}:
        raise ValueError(
            "storage_backend must be either 'json' or 'sqlite', "
            f"got {storage_backend!r}"
        )
    database_path_raw = str(
        values.get("database_path")
        or os.getenv("EDUFLOW_DATABASE_PATH", "")
    ).strip()

    return Settings(
        data_dir=Path(values.get("data_dir") or os.getenv("EDUFLOW_DATA_DIR", "data")),
        storage_backend=storage_backend,
        database_path=Path(database_path_raw) if database_path_raw else None,
        extraction_turns=int(values.get("extraction_turns") or os.getenv("EDUFLOW_EXTRACTION_TURNS", "4")),
        llm=LLMRuntimeConfig(
            provider=llm_values.get("provider") or provider,
            name=llm_values.get("name") or "",
            api_key=llm_values.get("api_key") or api_key,
            base_url=llm_values.get("base_url") or base_url,
            api_version=llm_values.get("api_version") or "",
            extra_headers=_coerce_headers(llm_values.get("extra_headers")),
            model_id=llm_values.get("model_id") or chat_model,
            model_label=llm_values.get("model_label") or "",
            context_window=llm_values.get("context_window"),
        ),
        embedding=EmbeddingRuntimeConfig(
            provider=embedding_values.get("provider") or provider,
            name=embedding_values.get("name") or "",
            api_key=embedding_values.get("api_key") or api_key,
            endpoint_url=embedding_values.get("endpoint_url") or base_url.rstrip("/") + "/embeddings",
            api_version=embedding_values.get("api_version") or "",
            extra_headers=_coerce_headers(embedding_values.get("extra_headers")),
            model_id=embedding_values.get("model_id") or embedding_model,
            model_label=embedding_values.get("model_label") or "",
            dimensions=embedding_values.get("dimensions"),
            send_dimensions=bool(embedding_values.get("send_dimensions", False)),
        ),
        reranker=RerankerRuntimeConfig(
            provider=reranker_values.get("provider") or "mock",
            name=reranker_values.get("name") or "",
            api_key=reranker_values.get("api_key") or api_key,
            endpoint_url=reranker_values.get("endpoint_url") or base_url.rstrip("/") + "/rerank",
            api_version=reranker_values.get("api_version") or "",
            extra_headers=_coerce_headers(reranker_values.get("extra_headers")),
            model_id=reranker_values.get("model_id") or "",
            model_label=reranker_values.get("model_label") or "",
        ),
    )
