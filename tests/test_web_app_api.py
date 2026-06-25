import unittest
from unittest.mock import patch
import tempfile
import json
import os
from pathlib import Path

from fastapi.testclient import TestClient

from EduFlowGraph.config import load_settings_from_mapping
from EduFlowGraph.web_app import app, get_pipeline
import EduFlowGraph.web_app as web_app_module


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
            self.assertIn("context", context_event)
            self.assertIn("profile", context_event["context"])
            self.assertTrue(any(event.get("type") == "delta" for event in events))
            self.assertTrue(any(event.get("type") == "answer" for event in events))
            self.assertTrue(any(event.get("type") == "final" for event in events))

    def test_pipeline_cache_separates_distinct_runtime_profiles(self):
        with tempfile.TemporaryDirectory() as tmp:
            settings_a = load_settings_from_mapping(
                {
                    "data_dir": tmp,
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
                    "data_dir": tmp,
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
            self.assertEqual([], payload["concepts"])
            self.assertEqual([], payload["episodes"])
            self.assertEqual([], payload["skills"])
            self.assertEqual([], payload["edges"])
            self.assertEqual([], payload["memory_events"])
            self.assertEqual(0, payload["memory_flow_count"])
            self.assertEqual(
                {"learner_model", "context_model"},
                set(payload["profile"]["models"]),
            )
            self.assertEqual("", payload["skill_adaptation"]["summary"])
            self.assertEqual(0, payload["profile"]["revision_count"])
            self.assertEqual("ok", payload["profile"]["health"]["status"])
            self.assertEqual("sqlite", payload["storage_health"]["backend"])

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

    def test_reset_memory_clears_turns_and_persisted_snapshot(self):
        with tempfile.TemporaryDirectory() as tmp:
            settings = load_settings_from_mapping({"data_dir": tmp, "provider": "mock"})
            with patch.object(web_app_module, "_settings", return_value=settings):
                client = TestClient(app)
                chat_response = client.post(
                    "/api/chat",
                    json={"session_id": "session_delete", "message": "请解释条件概率。"},
                )
                self.assertEqual(200, chat_response.status_code)
                before = client.get("/api/sessions/session_delete/turns")
                self.assertEqual(1, len(before.json()["turns"]))

                reset_response = client.post("/api/reset-memory", json={"data_dir": tmp})
                after = client.get("/api/sessions/session_delete/turns")

            self.assertEqual(200, reset_response.status_code)
            self.assertEqual([], after.json()["turns"])
            snapshot = reset_response.json()["snapshot"]
            self.assertEqual([], snapshot["concepts"])
            self.assertEqual([], snapshot["episodes"])
            self.assertEqual([], snapshot["skills"])
            self.assertEqual([], snapshot["edges"])
            self.assertEqual([], snapshot["memory_events"])
            self.assertEqual(0, snapshot["memory_flow_count"])
            self.assertEqual(0, snapshot["profile"]["revision_count"])

    def test_chat_api_returns_profile_trace_after_profile_is_learned(self):
        with tempfile.TemporaryDirectory() as tmp:
            settings = load_settings_from_mapping({"data_dir": tmp, "provider": "mock"})
            with patch.object(web_app_module, "_settings", return_value=settings):
                client = TestClient(app)
                first = client.post(
                    "/api/chat",
                    json={
                        "session_id": "session_profile_trace",
                        "message": "我学公式时喜欢先看具体例子，再看抽象定义。",
                        "memory_mode": "memory_augmented",
                    },
                )
                second = client.post(
                    "/api/chat",
                    json={
                        "session_id": "session_profile_trace",
                        "message": "讲条件概率时我还是喜欢先看具体例子，再看公式。",
                        "memory_mode": "memory_augmented",
                    },
                )
                extracted = client.post(
                    "/api/extract",
                    json={"session_id": "session_profile_trace"},
                )
                third = client.post(
                    "/api/chat",
                    json={
                        "session_id": "session_profile_trace",
                        "message": "请解释条件概率公式。",
                        "memory_mode": "memory_augmented",
                    },
                )

            self.assertEqual(200, first.status_code)
            self.assertEqual(200, second.status_code)
            self.assertEqual(200, extracted.status_code)
            self.assertEqual(200, third.status_code)
            context = third.json()["context"]
            self.assertTrue(
                any(
                    model["summary"]
                    for model in context["profile"]["models"].values()
                )
            )
            self.assertTrue(context["profile_context"])
            self.assertGreaterEqual(third.json()["snapshot"]["profile"]["revision_count"], 1)

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
            target_settings = load_settings_from_mapping({
                "data_dir": str(target_data),
                "provider": "mock",
                "storage_backend": "sqlite",
            })
            target_pipeline = get_pipeline(target_settings)
            target_pipeline.handle_user_message("session_target", "请解释条件概率。")
            self.assertEqual(1, len(target_pipeline.conv_log.list_turns("session_target")))

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
            reset_pipeline = get_pipeline(target_settings)
            self.assertEqual([], reset_pipeline.conv_log.list_turns("session_target"))
            self.assertEqual([], reset_pipeline.dashboard()["episodes"])


if __name__ == "__main__":
    unittest.main()
