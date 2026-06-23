import json
import time
from typing import Any
from urllib import error, request

from .prompts import RERANK_FALLBACK_PROMPT

_RETRYABLE_HTTP_CODES = {408, 429, 500, 502, 503, 504}
_MAX_HTTP_ATTEMPTS = 3
_RETRY_BASE_DELAY_SEC = 1.0


def _safe_preview(value: str, limit: int = 240) -> str:
    value = value.strip()
    return value if len(value) <= limit else value[:limit] + "..."


class LLMClient:
    def __init__(
        self,
        provider: str,
        api_key: str,
        base_url: str,
        chat_model: str,
        embedding_model: str,
        *,
        llm_name: str = "",
        llm_api_version: str = "",
        llm_extra_headers: dict[str, str] | None = None,
        embedding_provider: str | None = None,
        embedding_api_key: str | None = None,
        embedding_endpoint_url: str | None = None,
        embedding_api_version: str = "",
        embedding_extra_headers: dict[str, str] | None = None,
        embedding_dimensions: int | None = None,
        embedding_send_dimensions: bool = False,
        embedding_name: str = "",
        reranker_provider: str | None = None,
        reranker_api_key: str | None = None,
        reranker_endpoint_url: str | None = None,
        reranker_api_version: str = "",
        reranker_extra_headers: dict[str, str] | None = None,
        reranker_model_id: str = "",
        reranker_name: str = "",
    ):
        self.provider = provider
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.chat_model = chat_model
        self.embedding_model = embedding_model
        self.llm_name = llm_name or chat_model
        self.llm_api_version = llm_api_version
        self.llm_extra_headers = llm_extra_headers or {}
        self.embedding_provider = embedding_provider or provider
        self.embedding_api_key = embedding_api_key if embedding_api_key is not None else api_key
        self.embedding_endpoint_url = (
            embedding_endpoint_url.rstrip("/") if embedding_endpoint_url else self.base_url.rstrip("/") + "/embeddings"
        )
        self.embedding_api_version = embedding_api_version
        self.embedding_extra_headers = embedding_extra_headers or {}
        self.embedding_dimensions = embedding_dimensions
        self.embedding_send_dimensions = embedding_send_dimensions
        self.embedding_name = embedding_name or embedding_model
        self.reranker_provider = reranker_provider or "mock"
        self.reranker_api_key = reranker_api_key if reranker_api_key is not None else api_key
        self.reranker_endpoint_url = (
            reranker_endpoint_url.rstrip("/")
            if reranker_endpoint_url
            else self.base_url.rstrip("/") + "/rerank"
        )
        self.reranker_api_version = reranker_api_version
        self.reranker_extra_headers = reranker_extra_headers or {}
        self.reranker_model_id = reranker_model_id
        self.reranker_name = reranker_name or reranker_model_id or "LLM fallback"

    @property
    def is_live(self) -> bool:
        return self.provider != "mock" and bool(self.api_key)

    @property
    def embedding_is_live(self) -> bool:
        return self.embedding_provider != "mock" and bool(self.embedding_api_key)

    @property
    def reranker_is_live(self) -> bool:
        return self.reranker_provider != "mock" and bool(self.reranker_api_key) and bool(
            self.reranker_model_id
        )

    def _build_headers(
        self,
        *,
        api_key: str,
        extra_headers: dict[str, str],
        api_version: str,
    ) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        if api_version:
            headers["api-version"] = api_version
        headers.update(extra_headers)
        return headers

    def _retry_delay(self, attempt: int) -> float:
        return _RETRY_BASE_DELAY_SEC * (2 ** attempt)

    def _should_retry_http(self, exc: error.HTTPError) -> bool:
        return exc.code in _RETRYABLE_HTTP_CODES

    def _should_retry_transport(self, exc: Exception) -> bool:
        if isinstance(exc, TimeoutError):
            return True
        if isinstance(exc, error.URLError):
            reason = getattr(exc, "reason", None)
            if isinstance(reason, TimeoutError):
                return True
            return True
        if isinstance(exc, OSError):
            return True
        return False

    def _post_json(
        self,
        url: str,
        payload: dict[str, Any],
        *,
        api_key: str,
        extra_headers: dict[str, str],
        api_version: str,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers = self._build_headers(
            api_key=api_key,
            extra_headers=extra_headers,
            api_version=api_version,
        )
        last_exc: Exception | None = None
        for attempt in range(_MAX_HTTP_ATTEMPTS):
            req = request.Request(
                url,
                data=body,
                headers=headers,
                method="POST",
            )
            started = time.perf_counter()
            try:
                with request.urlopen(req, timeout=60) as response:
                    data = json.loads(response.read().decode("utf-8"))
                latency_ms = round((time.perf_counter() - started) * 1000, 1)
                return data, {
                    "url": url,
                    "latency_ms": latency_ms,
                    "request_preview": {
                        "headers": {
                            key: ("<redacted>" if key.lower() == "authorization" else value)
                            for key, value in headers.items()
                        },
                        "payload": payload,
                    },
                }
            except error.HTTPError as exc:
                last_exc = exc
                if attempt >= _MAX_HTTP_ATTEMPTS - 1 or not self._should_retry_http(exc):
                    raise
                time.sleep(self._retry_delay(attempt))
            except Exception as exc:
                last_exc = exc
                if attempt >= _MAX_HTTP_ATTEMPTS - 1 or not self._should_retry_transport(exc):
                    raise
                time.sleep(self._retry_delay(attempt))
        if last_exc is not None:
            raise last_exc
        raise RuntimeError("HTTP request failed without an exception")

    def _should_send_rerank_instruction(self) -> bool:
        model = (self.reranker_model_id or "").lower()
        return "qwen" in model and "reranker" in model

    def _build_rerank_payload(
        self,
        query: str,
        documents: list[dict[str, Any]],
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self.reranker_model_id,
            "query": query,
            "documents": [str(item.get("text") or "") for item in documents],
            "top_n": len(documents),
        }
        if self._should_send_rerank_instruction():
            payload["instruction"] = (
                "Rank the documents by how useful they are for answering the learner query in a tutoring context."
            )
        return payload

    def _chat_endpoint(self) -> str:
        return f"{self.base_url}/chat/completions"

    def _extract_chat_content(self, data: dict[str, Any]) -> str:
        try:
            return str(data["choices"][0]["message"]["content"])
        except Exception as exc:
            raise ValueError("Chat response does not contain choices[0].message.content") from exc

    def _extract_embedding_vector(self, data: dict[str, Any]) -> list[float]:
        try:
            vector = data["data"][0]["embedding"]
        except Exception as exc:
            raise ValueError("Embedding response does not contain data[0].embedding") from exc
        if not isinstance(vector, list):
            raise ValueError("Embedding response field data[0].embedding is not a list")
        return [float(item) for item in vector]

    def _extract_rerank_order(
        self,
        data: dict[str, Any],
        documents: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        results = data.get("results", [])
        if not isinstance(results, list):
            raise ValueError("Rerank response does not contain a results list")
        ranked: list[dict[str, Any]] = []
        for item in results:
            if not isinstance(item, dict):
                continue
            index_value = item.get("index", item.get("document_index"))
            try:
                index = int(index_value)
            except (TypeError, ValueError):
                continue
            if 0 <= index < len(documents):
                ranked.append(documents[index])
        if not ranked:
            raise ValueError("Rerank response results did not include usable indexes")
        return ranked

    def _llm_contract_summary(self) -> dict[str, Any]:
        return {
            "mode": "openai_chat_completions",
            "request_path": "/chat/completions",
            "response_path": "choices[0].message.content",
        }

    def _embedding_contract_summary(self) -> dict[str, Any]:
        return {
            "mode": "embeddings",
            "request_path": self.embedding_endpoint_url,
            "response_path": "data[0].embedding",
            "dimensions_requested": self.embedding_dimensions if self.embedding_send_dimensions else None,
        }

    def _rerank_contract_summary(self) -> dict[str, Any]:
        return {
            "mode": "rerank",
            "request_path": self.reranker_endpoint_url,
            "documents_format": "string[]",
            "response_path": "results[].index",
            "instruction_enabled": self._should_send_rerank_instruction(),
        }

    def chat(self, messages: list[dict[str, str]], temperature: float = 0.2) -> str:
        if not self.is_live:
            return self.mock_chat(messages)
        payload = {
            "model": self.chat_model,
            "messages": messages,
            "temperature": temperature,
        }
        data, _ = self._post_json(
            self._chat_endpoint(),
            payload,
            api_key=self.api_key,
            extra_headers=self.llm_extra_headers,
            api_version=self.llm_api_version,
        )
        return self._extract_chat_content(data)

    def stream_chat(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.2,
    ) -> Any:
        if not self.is_live:
            content = self.mock_chat(messages)
            step = 12
            for index in range(0, len(content), step):
                yield {"type": "delta", "delta": content[index : index + step]}
            return

        payload = {
            "model": self.chat_model,
            "messages": messages,
            "temperature": temperature,
            "stream": True,
            "stream_options": {"include_usage": True},
        }
        try:
            yield from self._stream_chat_payload(payload)
        except error.HTTPError as exc:
            if exc.code not in {400, 422}:
                raise
            payload_without_usage = dict(payload)
            payload_without_usage.pop("stream_options", None)
            yield from self._stream_chat_payload(payload_without_usage)

    def _stream_chat_payload(self, payload: dict[str, Any]) -> Any:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers = self._build_headers(
            api_key=self.api_key,
            extra_headers=self.llm_extra_headers,
            api_version=self.llm_api_version,
        )
        headers["Accept"] = "text/event-stream"
        last_exc: Exception | None = None
        for attempt in range(_MAX_HTTP_ATTEMPTS):
            req = request.Request(
                self._chat_endpoint(),
                data=body,
                headers=headers,
                method="POST",
            )
            try:
                with request.urlopen(req, timeout=60) as response:
                    for raw_line in response:
                        line = raw_line.decode("utf-8", errors="ignore").strip()
                        if not line or not line.startswith("data:"):
                            continue
                        payload_text = line.removeprefix("data:").strip()
                        if payload_text == "[DONE]":
                            break
                        try:
                            chunk = json.loads(payload_text)
                        except json.JSONDecodeError:
                            continue
                        usage = chunk.get("usage")
                        if usage:
                            yield {"type": "usage", "usage": usage}
                            continue
                        for choice in chunk.get("choices", []):
                            delta_payload = choice.get("delta", {})
                            reasoning = (
                                delta_payload.get("reasoning_content")
                                or delta_payload.get("reasoning")
                                or delta_payload.get("reasoning_text")
                            )
                            if reasoning:
                                yield {"type": "reasoning", "delta": str(reasoning)}
                            delta = delta_payload.get("content")
                            if delta:
                                yield {"type": "delta", "delta": str(delta)}
                return
            except error.HTTPError as exc:
                last_exc = exc
                if attempt >= _MAX_HTTP_ATTEMPTS - 1 or not self._should_retry_http(exc):
                    raise
                time.sleep(self._retry_delay(attempt))
            except Exception as exc:
                last_exc = exc
                if attempt >= _MAX_HTTP_ATTEMPTS - 1 or not self._should_retry_transport(exc):
                    raise
                time.sleep(self._retry_delay(attempt))
        if last_exc is not None:
            raise last_exc
        raise RuntimeError("Streaming chat request failed without an exception")

    def embedding(self, text: str) -> list[float]:
        if not self.embedding_is_live:
            return self.mock_embedding(text)
        payload: dict[str, Any] = {"model": self.embedding_model, "input": text}
        if self.embedding_send_dimensions and self.embedding_dimensions:
            payload["dimensions"] = self.embedding_dimensions
        data, _ = self._post_json(
            self.embedding_endpoint_url,
            payload,
            api_key=self.embedding_api_key,
            extra_headers=self.embedding_extra_headers,
            api_version=self.embedding_api_version,
        )
        return self._extract_embedding_vector(data)

    def test_llm_connection(self) -> dict[str, Any]:
        if not self.is_live:
            return {
                "status": "ok",
                "kind": "llm",
                "provider": self.provider,
                "profile_name": self.llm_name,
                "model_id": self.chat_model,
                "latency_ms": 0,
                "request_preview": {
                    "url": "mock://chat/completions",
                    "headers": {"Authorization": "<redacted>"},
                    "payload": {
                        "model": self.chat_model,
                        "messages": [{"role": "user", "content": "请只回复 OK"}],
                        "temperature": 0,
                    },
                },
                "response_preview": "OK (mock)",
                "contract_summary": self._llm_contract_summary(),
                "live_enabled": False,
            }

        payload = {
            "model": self.chat_model,
            "messages": [{"role": "user", "content": "请只回复 OK"}],
            "temperature": 0,
            "max_tokens": 16,
        }
        try:
            data, meta = self._post_json(
                self._chat_endpoint(),
                payload,
                api_key=self.api_key,
                extra_headers=self.llm_extra_headers,
                api_version=self.llm_api_version,
            )
            content = self._extract_chat_content(data)
            return {
                "status": "ok",
                "kind": "llm",
                "provider": self.provider,
                "profile_name": self.llm_name,
                "model_id": self.chat_model,
                "latency_ms": meta["latency_ms"],
                "request_preview": {"url": meta["url"], **meta["request_preview"]},
                "response_preview": _safe_preview(content),
                "contract_summary": self._llm_contract_summary(),
                "live_enabled": True,
            }
        except Exception as exc:
            return {
                "status": "error",
                "kind": "llm",
                "provider": self.provider,
                "profile_name": self.llm_name,
                "model_id": self.chat_model,
                "request_preview": {
                    "url": self._chat_endpoint(),
                    "headers": {
                        key: ("<redacted>" if key.lower() == "authorization" else value)
                        for key, value in self._build_headers(
                            api_key=self.api_key,
                            extra_headers=self.llm_extra_headers,
                            api_version=self.llm_api_version,
                        ).items()
                    },
                    "payload": payload,
                },
                "contract_summary": self._llm_contract_summary(),
                "live_enabled": True,
                "error": str(exc),
            }

    def test_embedding_connection(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self.embedding_model,
            "input": "embedding health check",
        }
        if self.embedding_send_dimensions and self.embedding_dimensions:
            payload["dimensions"] = self.embedding_dimensions

        if not self.embedding_is_live:
            vector = self.mock_embedding("embedding health check")
            return {
                "status": "ok",
                "kind": "embedding",
                "provider": self.embedding_provider,
                "profile_name": self.embedding_name,
                "model_id": self.embedding_model,
                "latency_ms": 0,
                "request_preview": {
                    "url": "mock://embeddings",
                    "headers": {"Authorization": "<redacted>"},
                    "payload": payload,
                },
                "response_preview": f"Embedding length={len(vector)} (mock)",
                "contract_summary": self._embedding_contract_summary(),
                "live_enabled": False,
            }

        try:
            data, meta = self._post_json(
                self.embedding_endpoint_url,
                payload,
                api_key=self.embedding_api_key,
                extra_headers=self.embedding_extra_headers,
                api_version=self.embedding_api_version,
            )
            vector = self._extract_embedding_vector(data)
            return {
                "status": "ok",
                "kind": "embedding",
                "provider": self.embedding_provider,
                "profile_name": self.embedding_name,
                "model_id": self.embedding_model,
                "latency_ms": meta["latency_ms"],
                "request_preview": {"url": meta["url"], **meta["request_preview"]},
                "response_preview": f"Embedding length={len(vector)}",
                "contract_summary": self._embedding_contract_summary(),
                "live_enabled": True,
            }
        except Exception as exc:
            return {
                "status": "error",
                "kind": "embedding",
                "provider": self.embedding_provider,
                "profile_name": self.embedding_name,
                "model_id": self.embedding_model,
                "request_preview": {
                    "url": self.embedding_endpoint_url,
                    "headers": {
                        key: ("<redacted>" if key.lower() == "authorization" else value)
                        for key, value in self._build_headers(
                            api_key=self.embedding_api_key,
                            extra_headers=self.embedding_extra_headers,
                            api_version=self.embedding_api_version,
                        ).items()
                    },
                    "payload": payload,
                },
                "contract_summary": self._embedding_contract_summary(),
                "live_enabled": True,
                "error": str(exc),
            }

    def rerank(
        self,
        query: str,
        documents: list[dict[str, Any]],
        *,
        kind: str,
    ) -> list[dict[str, Any]]:
        if not documents:
            return []
        if self.reranker_is_live:
            try:
                payload = self._build_rerank_payload(query, documents)
                data, _ = self._post_json(
                    self.reranker_endpoint_url,
                    payload,
                    api_key=self.reranker_api_key,
                    extra_headers=self.reranker_extra_headers,
                    api_version=self.reranker_api_version,
                )
                return self._extract_rerank_order(data, documents)
            except Exception:
                pass
        return self.rerank_with_llm_fallback(query, documents, kind=kind)

    def rerank_with_llm_fallback(
        self,
        query: str,
        documents: list[dict[str, Any]],
        *,
        kind: str,
    ) -> list[dict[str, Any]]:
        if not documents:
            return []
        if not self.is_live:
            return self.mock_rerank(query, documents)
        prompt = RERANK_FALLBACK_PROMPT.format(
            kind=kind,
            query=query,
            candidates_json=json.dumps(
                [
                    {
                        "id": str(item.get("id") or item.get("node_id") or index),
                        "text": str(item.get("text") or ""),
                        "score": float(item.get("score", 0.0)),
                    }
                    for index, item in enumerate(documents)
                ],
                ensure_ascii=False,
                indent=2,
            ),
        )
        try:
            raw = self.chat(messages_for_prompt(prompt), temperature=0)
            parsed = json.loads(raw.strip().strip("`").removeprefix("json").strip())
            order = [str(item) for item in parsed.get("ordered_ids", [])]
            by_id = {
                str(item.get("id") or item.get("node_id") or index): item
                for index, item in enumerate(documents)
            }
            ranked = [by_id[item_id] for item_id in order if item_id in by_id]
            if ranked:
                seen = {str(item.get("id") or item.get("node_id")) for item in ranked}
                ranked.extend(
                    item
                    for item in documents
                    if str(item.get("id") or item.get("node_id")) not in seen
                )
                return ranked
        except Exception:
            return self.mock_rerank(query, documents)
        return self.mock_rerank(query, documents)

    def mock_rerank(self, query: str, documents: list[dict[str, Any]]) -> list[dict[str, Any]]:
        query_lower = query.lower()
        scored = []
        for index, item in enumerate(documents):
            text = str(item.get("text") or "").lower()
            keyword_bonus = sum(1.0 for token in query_lower.split() if token and token in text)
            if query_lower and query_lower in text:
                keyword_bonus += 2.0
            scored.append((item, float(item.get("score", 0.0)) + keyword_bonus, index))
        scored.sort(key=lambda entry: (entry[1], -entry[2]), reverse=True)
        return [item for item, _, _ in scored]

    def test_reranker_connection(self) -> dict[str, Any]:
        if not self.reranker_is_live:
            return {
                "status": "ok",
                "kind": "reranker",
                "provider": self.reranker_provider,
                "profile_name": self.reranker_name,
                "model_id": self.reranker_model_id or "llm-fallback",
                "latency_ms": 0,
                "request_preview": {
                    "url": self.reranker_endpoint_url or "mock://rerank",
                    "headers": {"Authorization": "<redacted>"},
                    "payload": self._build_rerank_payload(
                        "why is P(A|B) not equal to P(B|A)?",
                        [{"id": "episode_1", "text": "Conditional probability confusion"}],
                    ),
                },
                "response_preview": "Reranker unavailable, using LLM fallback or mock rule rerank.",
                "contract_summary": self._rerank_contract_summary(),
                "live_enabled": False,
            }
        payload = self._build_rerank_payload(
            "why is P(A|B) not equal to P(B|A)?",
            [{"id": "episode_1", "text": "Conditional probability confusion"}],
        )
        try:
            data, meta = self._post_json(
                self.reranker_endpoint_url,
                payload,
                api_key=self.reranker_api_key,
                extra_headers=self.reranker_extra_headers,
                api_version=self.reranker_api_version,
            )
            return {
                "status": "ok",
                "kind": "reranker",
                "provider": self.reranker_provider,
                "profile_name": self.reranker_name,
                "model_id": self.reranker_model_id,
                "latency_ms": meta["latency_ms"],
                "request_preview": {"url": meta["url"], **meta["request_preview"]},
                "response_preview": _safe_preview(json.dumps(data, ensure_ascii=False)),
                "contract_summary": self._rerank_contract_summary(),
                "live_enabled": True,
            }
        except Exception as exc:
            return {
                "status": "error",
                "kind": "reranker",
                "provider": self.reranker_provider,
                "profile_name": self.reranker_name,
                "model_id": self.reranker_model_id,
                "request_preview": {
                    "url": self.reranker_endpoint_url,
                    "headers": {
                        key: ("<redacted>" if key.lower() == "authorization" else value)
                        for key, value in self._build_headers(
                            api_key=self.reranker_api_key,
                            extra_headers=self.reranker_extra_headers,
                            api_version=self.reranker_api_version,
                        ).items()
                    },
                    "payload": payload,
                },
                "contract_summary": self._rerank_contract_summary(),
                "live_enabled": True,
                "error": str(exc),
            }

    def mock_chat(self, messages: list[dict[str, str]]) -> str:
        prompt = messages[-1]["content"] if messages else ""
        if "记忆抽取器" in prompt:
            return '{"should_extract": false}'
        if "贝叶斯" in prompt or "检测准确率" in prompt or "P(A|B)" in prompt:
            return (
                '你之前主要卡在\u201c检测准确率\u201d和\u201c患病概率\u201d的条件方向上。我们先把事件写清楚：'
                'P(阳性|患病) 是检测对病人的命中率，P(患病|阳性) 才是看到阳性后真正想问的后验概率。'
                '它们中间还隔着先验概率，也就是人群里本来有多少人患病。'
                '\n\n小检查：如果 1000 人里只有 10 人患病，检测灵敏度 90%，假阳性率 5%，阳性的人里大约有多少是真患病？'
            )
        return "我会先判断你卡在哪个概念，再用一个小例子解释。你能先说说你觉得最不确定的一步是什么吗？"

    def mock_embedding(self, text: str) -> list[float]:
        buckets = [0.0] * 32
        for index, char in enumerate(text):
            buckets[(ord(char) + index) % len(buckets)] += 1.0
        total = sum(value * value for value in buckets) ** 0.5 or 1.0
        return [round(value / total, 6) for value in buckets]


def messages_for_prompt(prompt: str, *, system_prompt: str | None = None) -> list[dict[str, str]]:
    messages: list[dict[str, str]] = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})
    return messages
