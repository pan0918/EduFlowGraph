import unittest

from fastapi.testclient import TestClient

from EduFlowGraph.web_app import app


class DiagnosticsApiTest(unittest.TestCase):
    def test_mock_diagnostics_reports_live_fields(self):
        client = TestClient(app)
        response = client.post(
            "/api/diagnostics/model-test",
            json={
                "kind": "llm",
                "runtime": {
                    "llm": {
                        "provider": "mock",
                        "name": "Mock Tutor",
                        "base_url": "https://api.example.com",
                        "api_key": "",
                        "model_id": "mock-chat-model"
                    },
                    "embedding": {
                        "provider": "mock",
                        "name": "Mock Embedding",
                        "endpoint_url": "https://api.example.com/embeddings",
                        "api_key": "",
                        "model_id": "mock-embedding-model"
                    },
                }
            },
        )

        self.assertEqual(200, response.status_code)
        payload = response.json()
        self.assertEqual("ok", payload["status"])
        self.assertEqual("llm", payload["kind"])
        self.assertEqual("mock-chat-model", payload["model_id"])
        self.assertIn("request_preview", payload)

    def test_diagnostics_preserves_non_mock_provider_identity(self):
        client = TestClient(app)
        response = client.post(
            "/api/diagnostics/model-test",
            json={
                "kind": "embedding",
                "runtime": {
                    "llm": {
                        "provider": "deepseek",
                        "name": "DeepSeek Tutor",
                        "base_url": "https://api.deepseek.com",
                        "api_key": "",
                        "model_id": "deepseek-chat",
                    },
                    "embedding": {
                        "provider": "siliconflow",
                        "name": "SiliconFlow Embedding",
                        "endpoint_url": "https://api.siliconflow.cn/v1/embeddings",
                        "api_key": "",
                        "model_id": "Qwen/Qwen3-Embedding-8B",
                    },
                },
            },
        )

        self.assertEqual(200, response.status_code)
        payload = response.json()
        self.assertEqual("embedding", payload["kind"])
        self.assertEqual("siliconflow", payload["provider"])
        self.assertEqual("SiliconFlow Embedding", payload["profile_name"])

    def test_reranker_diagnostics_uses_fallback_preview_in_mock_mode(self):
        client = TestClient(app)
        response = client.post(
            "/api/diagnostics/model-test",
            json={
                "kind": "reranker",
                "runtime": {
                    "llm": {
                        "provider": "mock",
                        "name": "Mock Tutor",
                        "base_url": "https://api.example.com",
                        "api_key": "",
                        "model_id": "mock-chat-model",
                    },
                    "embedding": {
                        "provider": "mock",
                        "name": "Mock Embedding",
                        "endpoint_url": "https://api.example.com/embeddings",
                        "api_key": "",
                        "model_id": "mock-embedding-model",
                    },
                    "reranker": {
                        "provider": "mock",
                        "name": "Mock Reranker",
                        "endpoint_url": "https://api.example.com/rerank",
                        "api_key": "",
                        "model_id": "mock-reranker-model",
                    },
                },
            },
        )

        self.assertEqual(200, response.status_code)
        payload = response.json()
        self.assertEqual("reranker", payload["kind"])
        self.assertEqual("mock-reranker-model", payload["model_id"])
        self.assertIn("fallback", payload["response_preview"].lower())
        self.assertIn("contract_summary", payload)
        self.assertEqual("string[]", payload["contract_summary"]["documents_format"])
        self.assertFalse(payload["live_enabled"])

    def test_embedding_diagnostics_exposes_contract_summary(self):
        client = TestClient(app)
        response = client.post(
            "/api/diagnostics/model-test",
            json={
                "kind": "embedding",
                "runtime": {
                    "llm": {
                        "provider": "mock",
                        "name": "Mock Tutor",
                        "base_url": "https://api.example.com",
                        "api_key": "",
                        "model_id": "mock-chat-model",
                    },
                    "embedding": {
                        "provider": "mock",
                        "name": "Mock Embedding",
                        "endpoint_url": "https://api.example.com/embeddings",
                        "api_key": "",
                        "model_id": "mock-embedding-model",
                        "dimensions": 1024,
                        "send_dimensions": True,
                    },
                    "reranker": {
                        "provider": "mock",
                        "name": "Mock Reranker",
                        "endpoint_url": "https://api.example.com/rerank",
                        "api_key": "",
                        "model_id": "mock-reranker-model",
                    },
                },
            },
        )

        self.assertEqual(200, response.status_code)
        payload = response.json()
        self.assertEqual("embedding", payload["kind"])
        self.assertIn("contract_summary", payload)
        self.assertEqual("data[0].embedding", payload["contract_summary"]["response_path"])


if __name__ == "__main__":
    unittest.main()
