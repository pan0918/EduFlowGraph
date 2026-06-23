import json
import unittest
from unittest.mock import patch

from EduFlowGraph.llm import LLMClient
from EduFlowGraph.prompts import (
    TUTOR_MEMORY_AUGMENTED_USER_PROMPT,
    TUTOR_SYSTEM_PROMPT,
    TUTOR_USER_PROMPT,
)


class FakeResponse:
    def __init__(self, payload: dict):
        self.payload = payload

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return None

    def __iter__(self):
        return iter([])


class FakeStreamingResponse:
    def __iter__(self):
        return iter(
            [
                'data: {"choices":[{"delta":{"reasoning_content":"先分析"}}]}\n\n'.encode("utf-8"),
                'data: {"choices":[{"delta":{"content":"你"}}]}\n\n'.encode("utf-8"),
                'data: {"choices":[{"delta":{"content":"好"}}]}\n\n'.encode("utf-8"),
                b'data: {"usage":{"prompt_tokens_details":{"cached_tokens":128}}}\n\n',
                b"data: [DONE]\n\n",
            ]
        )

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return None


class ModelRuntimeTest(unittest.TestCase):
    def test_chat_uses_chat_completions_endpoint(self):
        captured = {}

        def fake_urlopen(req, timeout=60):
            captured["url"] = req.full_url
            captured["body"] = json.loads(req.data.decode("utf-8"))
            return FakeResponse(
                {
                    "choices": [
                        {
                            "message": {
                                "content": "OK",
                            }
                        }
                    ]
                }
            )

        client = LLMClient(
            provider="openai-compatible",
            api_key="test-key",
            base_url="https://api.siliconflow.cn/v1",
            chat_model="Qwen/Qwen3-32B",
            embedding_model="embed-test",
        )

        with patch("EduFlowGraph.llm.request.urlopen", side_effect=fake_urlopen):
            result = client.chat([{"role": "user", "content": "请只回复 OK"}], temperature=0)

        self.assertEqual("https://api.siliconflow.cn/v1/chat/completions", captured["url"])
        self.assertEqual("Qwen/Qwen3-32B", captured["body"]["model"])
        self.assertEqual("请只回复 OK", captured["body"]["messages"][0]["content"])
        self.assertEqual("OK", result)

    def test_stream_chat_uses_streaming_payload_and_yields_usage(self):
        captured = {}

        def fake_urlopen(req, timeout=60):
            captured["url"] = req.full_url
            captured["body"] = json.loads(req.data.decode("utf-8"))
            return FakeStreamingResponse()

        client = LLMClient(
            provider="openai-compatible",
            api_key="test-key",
            base_url="https://api.deepseek.com",
            chat_model="deepseek-v4-flash",
            embedding_model="embed-test",
        )

        with patch("EduFlowGraph.llm.request.urlopen", side_effect=fake_urlopen):
            chunks = list(client.stream_chat([{"role": "user", "content": "你好"}], temperature=0.3))

        self.assertEqual("https://api.deepseek.com/chat/completions", captured["url"])
        self.assertTrue(captured["body"]["stream"])
        self.assertEqual({"include_usage": True}, captured["body"]["stream_options"])
        self.assertEqual(
            [
                {"type": "reasoning", "delta": "先分析"},
                {"type": "delta", "delta": "你"},
                {"type": "delta", "delta": "好"},
                {
                    "type": "usage",
                    "usage": {"prompt_tokens_details": {"cached_tokens": 128}},
                },
            ],
            chunks,
        )

    def test_embedding_uses_exact_endpoint_url(self):
        captured = {}

        def fake_urlopen(req, timeout=60):
            captured["url"] = req.full_url
            captured["body"] = json.loads(req.data.decode("utf-8"))
            return FakeResponse({"data": [{"embedding": [0.1, 0.2, 0.3]}]})

        client = LLMClient(
            provider="openai-compatible",
            api_key="test-key",
            base_url="https://api.deepseek.com",
            chat_model="deepseek-v4-pro",
            embedding_model="Qwen/Qwen3-VL-Embedding-8B",
            embedding_endpoint_url="https://api.siliconflow.cn/v1/embeddings",
            embedding_dimensions=4096,
            embedding_send_dimensions=True,
        )

        with patch("EduFlowGraph.llm.request.urlopen", side_effect=fake_urlopen):
            vector = client.embedding("hello")

        self.assertEqual("https://api.siliconflow.cn/v1/embeddings", captured["url"])
        self.assertEqual("Qwen/Qwen3-VL-Embedding-8B", captured["body"]["model"])
        self.assertEqual(4096, captured["body"]["dimensions"])
        self.assertEqual([0.1, 0.2, 0.3], vector)

    def test_rerank_with_llm_fallback_uses_prompt_template(self):
        client = LLMClient(
            provider="openai-compatible",
            api_key="test-key",
            base_url="https://api.example.com/v1",
            chat_model="gpt-test",
            embedding_model="embed-test",
        )
        captured = {}

        def fake_chat(messages, temperature=0.2):
            captured["prompt"] = messages[-1]["content"]
            return '{"ordered_ids": ["candidate_2", "candidate_1"]}'

        client.chat = fake_chat  # type: ignore[method-assign]
        ranked = client.rerank_with_llm_fallback(
            "帮我比较一下 P(A|B) 和 P(B|A)",
            [
                {"id": "candidate_1", "text": "first candidate", "score": 0.7},
                {"id": "candidate_2", "text": "second candidate", "score": 0.8},
            ],
            kind="skill",
        )

        self.assertEqual("candidate_2", ranked[0]["id"])
        self.assertIn("Candidate kind: skill", captured["prompt"])
        self.assertIn("Return JSON only.", captured["prompt"])
        self.assertIn('"ordered_ids": [string]', captured["prompt"])

    def test_messages_for_prompt_supports_system_and_user_split(self):
        from EduFlowGraph.llm import messages_for_prompt

        messages = messages_for_prompt("dynamic user content", system_prompt="static system prompt")

        self.assertEqual(
            [
                {"role": "system", "content": "static system prompt"},
                {"role": "user", "content": "dynamic user content"},
            ],
            messages,
        )

    def test_tutor_prompts_are_split_for_cache_friendliness(self):
        self.assertIn("专业的 AI 学习导师", TUTOR_SYSTEM_PROMPT)
        self.assertIn("个性化教学支持", TUTOR_SYSTEM_PROMPT)
        self.assertNotIn("Teaching instruction", TUTOR_SYSTEM_PROMPT)
        self.assertNotIn("小检查", TUTOR_SYSTEM_PROMPT)
        self.assertIn("{user_query}", TUTOR_USER_PROMPT)
        self.assertNotIn("{memory_context}", TUTOR_USER_PROMPT)
        self.assertIn("{user_query}", TUTOR_MEMORY_AUGMENTED_USER_PROMPT)
        self.assertIn("{memory_context}", TUTOR_MEMORY_AUGMENTED_USER_PROMPT)

    def test_rerank_uses_string_documents_payload_for_siliconflow_style_api(self):
        captured = {}

        def fake_urlopen(req, timeout=60):
            captured["url"] = req.full_url
            captured["body"] = json.loads(req.data.decode("utf-8"))
            return FakeResponse({"results": [{"index": 1}, {"index": 0}]})

        client = LLMClient(
            provider="openai-compatible",
            api_key="chat-key",
            base_url="https://api.example.com/v1",
            chat_model="chat-model",
            embedding_model="embed-model",
            reranker_provider="siliconflow",
            reranker_api_key="rerank-key",
            reranker_endpoint_url="https://api.siliconflow.cn/v1/rerank",
            reranker_model_id="Qwen/Qwen3-Reranker-8B",
        )

        with patch("EduFlowGraph.llm.request.urlopen", side_effect=fake_urlopen):
            ranked = client.rerank(
                "why is P(A|B) not equal to P(B|A)?",
                [
                    {"id": "candidate_1", "text": "first candidate"},
                    {"id": "candidate_2", "text": "second candidate"},
                ],
                kind="episode",
            )

        self.assertEqual("https://api.siliconflow.cn/v1/rerank", captured["url"])
        self.assertEqual("Qwen/Qwen3-Reranker-8B", captured["body"]["model"])
        self.assertEqual(
            ["first candidate", "second candidate"],
            captured["body"]["documents"],
        )
        self.assertEqual(2, captured["body"]["top_n"])
        self.assertIn("instruction", captured["body"])
        self.assertEqual("candidate_2", ranked[0]["id"])


if __name__ == "__main__":
    unittest.main()
