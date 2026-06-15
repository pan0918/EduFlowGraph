import unittest
from unittest.mock import patch
import tempfile
import json
import os
from pathlib import Path

from fastapi.testclient import TestClient

from eduflowgraph.config import load_settings_from_mapping
from eduflowgraph.web_app import app, get_pipeline
import eduflowgraph.web_app as web_app_module


class WebAppApiTest(unittest.TestCase):
    def tearDown(self):
        web_app_module._pipeline = None
        web_app_module._pipeline_key = None

    def test_chat_api_supports_cors_preflight_for_frontend(self):
        client = TestClient(app)
        response = client.options(
            "/api/chat",
            headers={
                "Origin": "http://127.0.0.1:3000",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type",
            },
        )

        self.assertEqual(200, response.status_code)
        self.assertEqual("http://127.0.0.1:3000", response.headers.get("access-control-allow-origin"))
        self.assertIn("POST", response.headers.get("access-control-allow-methods", ""))

    def test_stream_chat_api_returns_delta_and_final_events(self):
        with tempfile.TemporaryDirectory() as tmp:
            settings = load_settings_from_mapping({"data_dir": tmp, "provider": "mock"})
            with patch.object(web_app_module, "_settings", return_value=settings):
                client = TestClient(app)
                with client.stream(
                    "POST",
                    "/api/chat/stream",
                    json={"session_id": "session_stream", "message": "请解释条件概率。"},
                ) as response:
                    body = "".join(response.iter_text())

            self.assertEqual(200, response.status_code)
            events = [
                json.loads(chunk.removeprefix("data: ").strip())
                for chunk in body.split("\n\n")
                if chunk.startswith("data: ")
            ]
            context_event = next(event for event in events if event.get("type") == "context")
            self.assertIn("user_event", context_event)
            self.assertEqual("user_message", context_event["user_event"]["event_type"])
            self.assertTrue(any(event.get("type") == "delta" for event in events))
            self.assertTrue(any(event.get("type") == "final" for event in events))

    def test_pipeline_cache_separates_distinct_runtime_profiles(self):
        settings_a = load_settings_from_mapping(
            {
                "data_dir": "data",
                "runtime": {
                    "llm": {
                        "provider": "openai-compatible",
                        "name": "DeepSeek Pro",
                        "base_url": "https://api.deepseek.com",
                        "api_key": "key-a",
                        "model_id": "deepseek-v4-pro",
                    },
                    "embedding": {
                        "provider": "openai-compatible",
                        "name": "Qwen Embedding",
                        "endpoint_url": "https://api.siliconflow.cn/v1/embeddings",
                        "api_key": "embed-a",
                        "model_id": "Qwen/Qwen3-VL-Embedding-8B",
                    },
                },
            }
        )
        settings_b = load_settings_from_mapping(
            {
                "data_dir": "data",
                "runtime": {
                    "llm": {
                        "provider": "openai-compatible",
                        "name": "OpenAI Tutor",
                        "base_url": "https://api.openai.com/v1",
                        "api_key": "key-b",
                        "model_id": "gpt-4o-mini",
                    },
                    "embedding": {
                        "provider": "openai-compatible",
                        "name": "OpenAI Embedding",
                        "endpoint_url": "https://api.openai.com/v1/embeddings",
                        "api_key": "embed-b",
                        "model_id": "text-embedding-3-small",
                    },
                },
            }
        )

        first = get_pipeline(settings_a)
        second = get_pipeline(settings_b)

        self.assertIsNot(first, second)
        self.assertEqual("gpt-4o-mini", second.llm.chat_model)
        self.assertEqual("text-embedding-3-small", second.llm.embedding_model)

    def test_default_dashboard_is_empty_without_seed_content(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(
                web_app_module,
                "_settings",
                return_value=load_settings_from_mapping({"data_dir": tmp, "provider": "mock"}),
            ):
                client = TestClient(app)
                response = client.get("/api/dashboard")

            self.assertEqual(200, response.status_code)
            payload = response.json()
            self.assertEqual([], payload["events"])
            self.assertEqual([], payload["concepts"])
            self.assertEqual([], payload["episodes"])
            self.assertEqual([], payload["skills"])
            self.assertEqual([], payload["edges"])
            self.assertIn("retrieval_health", payload)

    def test_api_responses_disable_http_caching(self):
        with tempfile.TemporaryDirectory() as tmp:
            settings = load_settings_from_mapping({"data_dir": tmp, "provider": "mock"})
            with patch.object(web_app_module, "_settings", return_value=settings):
                client = TestClient(app)
                dashboard_response = client.get("/api/dashboard")
                with client.stream(
                    "POST",
                    "/api/chat/stream",
                    json={"session_id": "session_cache", "message": "请解释条件概率。"},
                ) as stream_response:
                    _ = "".join(stream_response.iter_text())

        self.assertEqual(200, dashboard_response.status_code)
        self.assertEqual("no-store", dashboard_response.headers.get("cache-control"))
        self.assertEqual(200, stream_response.status_code)
        self.assertEqual("no-store", stream_response.headers.get("cache-control"))

    def test_rebuild_retrieval_api_returns_stats(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(
                web_app_module,
                "_settings",
                return_value=load_settings_from_mapping({"data_dir": tmp, "provider": "mock"}),
            ):
                client = TestClient(app)
                response = client.post("/api/rebuild-retrieval", json={"data_dir": tmp})

            self.assertEqual(200, response.status_code)
            payload = response.json()
            self.assertIn("rebuilt_nodes", payload)
            self.assertIn("snapshot", payload)

    def test_delete_event_and_reset_memory_update_persisted_snapshot(self):
        with tempfile.TemporaryDirectory() as tmp:
            settings = load_settings_from_mapping({"data_dir": tmp, "provider": "mock"})
            with patch.object(web_app_module, "_settings", return_value=settings):
                client = TestClient(app)
                chat_response = client.post(
                    "/api/chat",
                    json={"session_id": "session_delete", "message": "请解释条件概率。"},
                )
                self.assertEqual(200, chat_response.status_code)
                user_event_id = chat_response.json()["user_event"]["event_id"]

                delete_response = client.delete(f"/api/events/{user_event_id}")
                self.assertEqual(200, delete_response.status_code)
                self.assertFalse(
                    any(
                        event["event_id"] == user_event_id
                        for event in delete_response.json()["snapshot"]["events"]
                    )
                )

                reset_response = client.post("/api/reset-memory", json={"data_dir": tmp})

            self.assertEqual(200, reset_response.status_code)
            snapshot = reset_response.json()["snapshot"]
            self.assertEqual([], snapshot["events"])
            self.assertEqual([], snapshot["concepts"])
            self.assertEqual([], snapshot["episodes"])
            self.assertEqual([], snapshot["skills"])
            self.assertEqual([], snapshot["edges"])

    def test_reset_memory_uses_request_data_dir_instead_of_default_data_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            default_cwd = root / "cwd"
            default_data = default_cwd / "data"
            target_data = root / "target-data"
            default_data.mkdir(parents=True)
            target_data.mkdir()
            sentinel_event = {
                "event_id": "event_sentinel",
                "stream_index": 1,
                "session_id": "session_sentinel",
                "turn_index": 1,
                "timestamp": "2026-06-11T00:00:00Z",
                "actor": "student",
                "event_type": "user_message",
                "content": "sentinel",
            }
            default_data.joinpath("dataflow.jsonl").write_text(
                json.dumps(sentinel_event, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            default_data.joinpath("graph_nodes.json").write_text('{"sentinel": true}', encoding="utf-8")
            default_data.joinpath("graph_edges.json").write_text('[{"sentinel": true}]', encoding="utf-8")
            target_event = {
                **sentinel_event,
                "event_id": "event_target",
                "session_id": "session_target",
                "content": "target",
            }
            target_data.joinpath("dataflow.jsonl").write_text(
                json.dumps(target_event, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            target_data.joinpath("graph_nodes.json").write_text('{"target": true}', encoding="utf-8")
            target_data.joinpath("graph_edges.json").write_text('[{"target": true}]', encoding="utf-8")

            previous_cwd = Path.cwd()
            os.chdir(default_cwd)
            try:
                client = TestClient(app)
                response = client.post("/api/reset-memory", json={"data_dir": str(target_data)})
            finally:
                os.chdir(previous_cwd)

            self.assertEqual(200, response.status_code)
            self.assertEqual(
                json.dumps(sentinel_event, ensure_ascii=False) + "\n",
                default_data.joinpath("dataflow.jsonl").read_text(encoding="utf-8"),
            )
            self.assertEqual('{"sentinel": true}', default_data.joinpath("graph_nodes.json").read_text(encoding="utf-8"))
            self.assertEqual('[{"sentinel": true}]', default_data.joinpath("graph_edges.json").read_text(encoding="utf-8"))
            self.assertEqual("", target_data.joinpath("dataflow.jsonl").read_text(encoding="utf-8"))
            self.assertEqual("{}", target_data.joinpath("graph_nodes.json").read_text(encoding="utf-8").strip())
            self.assertEqual("[]", target_data.joinpath("graph_edges.json").read_text(encoding="utf-8").strip())


if __name__ == "__main__":
    unittest.main()
