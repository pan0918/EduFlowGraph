from __future__ import annotations

import json
from pathlib import Path
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


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    return INDEX_HTML


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
        "user_event": result["user_event"],
        "assistant_event": result["assistant_event"],
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
            if event.get("type") == "final":
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


@app.delete("/api/events/{event_id}")
def delete_event(event_id: str) -> dict[str, Any]:
    pipeline = get_pipeline(_settings())
    result = pipeline.delete_event(event_id)
    return {**result, "snapshot": pipeline.dashboard()}


@app.post("/api/reset-memory")
def reset_memory(payload: RebuildRetrievalRequest) -> dict[str, Any]:
    pipeline = get_pipeline(_settings_from_values(payload.model_dump()))
    result = pipeline.reset_memory()
    return {**result, "snapshot": pipeline.dashboard()}


INDEX_HTML = r"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>EduFlowGraph Tutor</title>
  <style>
    :root {
      --bg: #f5f7fa;
      --panel: #ffffff;
      --panel-soft: #f9fbfd;
      --ink: #18202b;
      --muted: #657284;
      --line: #dbe3ec;
      --green: #1f8a70;
      --orange: #d95d39;
      --blue: #3f63b5;
      --shadow: 0 10px 28px rgba(21, 35, 52, .08);
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      color: var(--ink);
      background: var(--bg);
      letter-spacing: 0;
    }
    button, input, select, textarea { font: inherit; }
    .app {
      display: grid;
      grid-template-columns: 248px minmax(0, 1fr) 380px;
      min-height: 100vh;
    }
    aside {
      background: #111820;
      color: #edf2f7;
      padding: 18px 14px;
      display: flex;
      flex-direction: column;
      gap: 14px;
    }
    .brand { padding: 6px 8px 12px; border-bottom: 1px solid rgba(255,255,255,.11); }
    .brand h1 { margin: 0 0 4px; font-size: 19px; }
    .brand p { margin: 0; color: #aab7c7; font-size: 12px; line-height: 1.4; }
    nav { display: grid; gap: 6px; }
    nav button {
      border: 0;
      background: transparent;
      color: #c8d3df;
      padding: 10px 10px;
      border-radius: 8px;
      text-align: left;
      cursor: pointer;
    }
    nav button.active { background: #243140; color: #fff; }
    .settings { margin-top: auto; display: grid; gap: 8px; }
    label { color: #aab7c7; font-size: 12px; display: grid; gap: 4px; }
    input, select {
      width: 100%;
      border: 1px solid var(--line);
      background: #fff;
      color: var(--ink);
      border-radius: 8px;
      min-height: 36px;
      padding: 7px 9px;
    }
    aside input, aside select { border-color: #364657; background: #182332; color: #edf2f7; }
    main { padding: 20px; min-width: 0; }
    .topbar {
      display: flex;
      justify-content: space-between;
      gap: 16px;
      align-items: flex-start;
      margin-bottom: 14px;
    }
    .title h2 { margin: 0 0 4px; font-size: 24px; }
    .title p { margin: 0; color: var(--muted); }
    .primary {
      border: 0;
      background: var(--green);
      color: white;
      border-radius: 8px;
      min-height: 38px;
      padding: 0 14px;
      cursor: pointer;
    }
    .secondary {
      border: 1px solid var(--line);
      background: #fff;
      color: var(--ink);
      border-radius: 8px;
      min-height: 36px;
      padding: 0 12px;
      cursor: pointer;
    }
    .metrics { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 10px; margin-bottom: 14px; }
    .metric { background: var(--panel); border: 1px solid var(--line); border-radius: 8px; padding: 11px; }
    .metric b { display: block; font-size: 22px; }
    .metric span { color: var(--muted); font-size: 12px; }
    .workspace { display: none; }
    .workspace.active { display: block; }
    .chat-shell {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      min-height: calc(100vh - 184px);
      display: grid;
      grid-template-rows: 1fr auto;
      overflow: hidden;
      box-shadow: var(--shadow);
    }
    .messages { padding: 16px; overflow: auto; max-height: calc(100vh - 260px); }
    .message { max-width: 820px; margin-bottom: 12px; display: flex; }
    .bubble { border-radius: 8px; padding: 11px 13px; line-height: 1.58; white-space: pre-wrap; }
    .student { justify-content: flex-end; margin-left: auto; }
    .student .bubble { background: #e7f3ef; }
    .assistant .bubble { background: #f0f3f7; }
    .composer { display: grid; grid-template-columns: 1fr auto; gap: 10px; border-top: 1px solid var(--line); padding: 12px; }
    textarea { resize: none; border: 1px solid var(--line); border-radius: 8px; padding: 10px; min-height: 48px; }
    .right {
      border-left: 1px solid var(--line);
      background: #fbfcfe;
      padding: 20px 14px;
      overflow: auto;
      max-height: 100vh;
    }
    .right h3 { margin: 0 0 10px; font-size: 16px; }
    .panel {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 13px;
      margin-bottom: 12px;
    }
    .node {
      border: 1px solid var(--line);
      border-left: 4px solid var(--green);
      background: #fff;
      border-radius: 8px;
      padding: 10px;
      margin-bottom: 9px;
    }
    .node.episode { border-left-color: var(--orange); }
    .node.skill { border-left-color: var(--blue); }
    .node b { display: block; margin-bottom: 4px; }
    .muted { color: var(--muted); font-size: 12px; }
    .grid2 { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); gap: 12px; }
    pre {
      background: #111820;
      color: #dbeafe;
      border-radius: 8px;
      padding: 12px;
      overflow: auto;
      max-height: 520px;
      font-size: 12px;
    }
    .graph {
      min-height: 430px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #fff;
      overflow: hidden;
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 10px;
      padding: 12px;
    }
    .graph-node {
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--panel-soft);
      padding: 10px;
      box-shadow: var(--shadow);
      text-align: center;
      margin-bottom: 10px;
      min-height: 70px;
      display: grid;
      align-content: center;
    }
    .graph-node.concept { background: #e9f7f3; }
    .graph-node.episode { background: #fff0e8; }
    .graph-node.skill { background: #eef2ff; }
    .graph-column h4 { margin: 0 0 10px; font-size: 13px; color: var(--muted); text-align: center; }
    .event { border-bottom: 1px solid var(--line); padding: 9px 0; }
    .event:last-child { border-bottom: 0; }
    @media (max-width: 1120px) {
      .app { grid-template-columns: 220px minmax(0, 1fr); }
      .right { grid-column: 1 / -1; border-left: 0; border-top: 1px solid var(--line); max-height: none; }
    }
    @media (max-width: 760px) {
      .app { display: block; }
      aside { position: static; }
      .metrics, .grid2 { grid-template-columns: 1fr; }
      .topbar { display: block; }
    }
  </style>
</head>
<body>
  <div class="app">
    <aside>
      <div class="brand">
        <h1>EduFlowGraph Tutor</h1>
        <p>DataFlow + Memory Graph + Skill-aware tutoring</p>
      </div>
      <nav>
        <button class="active" data-tab="chat">Chat</button>
        <button data-tab="memory">Memory Workbench</button>
        <button data-tab="knowledge">Knowledge</button>
        <button data-tab="skills">Skills</button>
        <button data-tab="settings">Settings</button>
      </nav>
      <div class="settings">
        <label>Session ID <input id="sessionId" value="session_demo"></label>
        <label>Provider
          <select id="provider">
            <option value="mock">mock</option>
            <option value="openai-compatible">openai-compatible</option>
          </select>
        </label>
        <label>API Key <input id="apiKey" type="password" placeholder="sk-..."></label>
        <label>Base URL <input id="baseUrl" value="https://api.openai.com/v1"></label>
        <label>Chat Model <input id="chatModel" value="gpt-4o-mini"></label>
        <label>Embedding Model <input id="embeddingModel" value="text-embedding-3-small"></label>
      </div>
    </aside>
    <main>
      <div class="topbar">
        <div class="title">
          <h2>AI Tutor Workspace</h2>
          <p>DeepTutor-style workspace with Concept ← Episode → Skill memory.</p>
        </div>
        <button class="primary" id="forceExtract">Force extraction</button>
      </div>
      <div class="metrics" id="metrics"></div>

      <section id="chat" class="workspace active">
        <div class="chat-shell">
          <div class="messages" id="messages">
            <div class="message assistant"><div class="bubble">你好，我是 EduFlowGraph Tutor。你可以先问：“为什么不能直接用检测准确率当作患病概率？”然后到 Memory Workbench 看 DataFlow 和图记忆如何更新。</div></div>
          </div>
          <div class="composer">
            <textarea id="input" placeholder="Ask the tutor..."></textarea>
            <button class="primary" id="send">Send</button>
          </div>
        </div>
      </section>

      <section id="memory" class="workspace">
        <div class="grid2">
          <div class="panel"><h3>Memory Graph</h3><div class="graph" id="graph"></div></div>
          <div class="panel"><h3>DataFlow</h3><div id="events"></div></div>
        </div>
        <div class="grid2">
          <div class="panel"><h3>Nodes</h3><pre id="nodesJson"></pre></div>
          <div class="panel"><h3>Edges</h3><pre id="edgesJson"></pre></div>
        </div>
      </section>

      <section id="knowledge" class="workspace"><div class="panel"><h3>Knowledge Space</h3><div id="conceptList"></div></div></section>
      <section id="skills" class="workspace"><div class="panel"><h3>Skill Workbench</h3><div id="skillList"></div></div></section>
      <section id="settings" class="workspace">
        <div class="panel">
          <h3>Model API Configuration</h3>
          <p>Use mock mode for local testing, or switch to openai-compatible and fill API Key / Base URL / model names in the sidebar.</p>
          <pre>OPENAI_API_KEY=...
OPENAI_BASE_URL=https://api.openai.com/v1
EDUFLOW_PROVIDER=openai-compatible
EDUFLOW_CHAT_MODEL=gpt-4o-mini
EDUFLOW_EMBEDDING_MODEL=text-embedding-3-small</pre>
        </div>
      </section>
    </main>
    <section class="right">
      <h3>Personalized Context</h3>
      <div id="contextPanel" class="panel"><p class="muted">No retrieval yet.</p></div>
    </section>
  </div>

  <script>
    let snapshot = { events: [], concepts: [], episodes: [], skills: [], edges: [] };
    let lastContext = null;
    const $ = (id) => document.getElementById(id);

    function payload(extra = {}) {
      return {
        session_id: $("sessionId").value || "session_demo",
        provider: $("provider").value,
        api_key: $("apiKey").value,
        base_url: $("baseUrl").value,
        chat_model: $("chatModel").value,
        embedding_model: $("embeddingModel").value,
        extraction_turns: 4,
        ...extra
      };
    }

    async function api(path, body) {
      const res = await fetch(path, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body)
      });
      if (!res.ok) throw new Error(await res.text());
      return res.json();
    }

    function escapeHtml(text) {
      return String(text ?? "").replace(/[&<>"']/g, (m) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;" }[m]));
    }

    function renderMetrics() {
      $("metrics").innerHTML = [
        ["DataFlow events", snapshot.events.length],
        ["Concept nodes", snapshot.concepts.length],
        ["Episode nodes", snapshot.episodes.length],
        ["Skill nodes", snapshot.skills.length]
      ].map(([label, value]) => `<div class="metric"><b>${value}</b><span>${label}</span></div>`).join("");
    }

    function renderContext(context) {
      if (!context) {
        $("contextPanel").innerHTML = '<p class="muted">No retrieval yet.</p>';
        return;
      }
      const concepts = context.concepts.map(c => {
        const aliases = (c.aliases || []).slice(0, 3).join(" · ");
        return `<div class="node"><b>${escapeHtml(c.name)}</b><div class="muted">${escapeHtml(aliases)}</div><p>${escapeHtml(c.description || "")}</p></div>`;
      }).join("") || '<p class="muted">No concept retrieved.</p>';
      const episodes = context.episodes.map(e => `<div class="node episode"><b>${escapeHtml(e.summary?.title || "Untitled")}</b><div class="muted">${escapeHtml(e.node_id)}</div><p>${escapeHtml(e.summary?.short_summary || "")}</p></div>`).join("");
      const skills = context.skills.map(s => `<div class="node skill"><b>${escapeHtml(s.name)}</b><div class="muted">${escapeHtml(s.status || "candidate")} | ${escapeHtml(s.difficulty_pattern || "unknown")} | confidence=${escapeHtml((s.quality?.confidence ?? 0).toFixed?.(2) || s.quality?.confidence)}</div><p>${escapeHtml(s.trigger || "")}</p></div>`).join("");
      $("contextPanel").innerHTML = `<h4>Concepts</h4>${concepts}<h4>Episodes</h4>${episodes || '<p class="muted">No episode.</p>'}<h4>Skills</h4>${skills || '<p class="muted">No skill.</p>'}`;
    }

    function addMessage(role, text) {
      const div = document.createElement("div");
      div.className = `message ${role}`;
      div.innerHTML = `<div class="bubble">${escapeHtml(text)}</div>`;
      $("messages").appendChild(div);
      $("messages").scrollTop = $("messages").scrollHeight;
    }

    function renderGraph() {
      const graph = $("graph");
      if (!snapshot.episodes.length) {
        graph.innerHTML = '<p class="muted" style="padding:14px">No extracted episodes yet.</p>';
        return;
      }
      const concepts = snapshot.concepts.slice(0, 5);
      const episodes = snapshot.episodes.slice(-5);
      const usedSkillIds = new Set(snapshot.edges.filter(e => e.edge_type === "episode_skill").map(e => e.target));
      const skills = snapshot.skills.filter(s => usedSkillIds.has(s.node_id)).slice(0, 5);
      const conceptHtml = concepts.map(c => `<div class="graph-node concept"><b>${escapeHtml(c.name)}</b><div class="muted">${escapeHtml((c.aliases || []).slice(0, 2).join(" · "))}</div></div>`).join("");
      const episodeHtml = episodes.map(e => `<div class="graph-node episode"><b>${escapeHtml(e.summary?.title || "Untitled")}</b><div class="muted">${escapeHtml(e.node_id.slice(-6))}</div></div>`).join("");
      const skillHtml = skills.map(s => `<div class="graph-node skill"><b>${escapeHtml(s.name)}</b><div class="muted">${escapeHtml(s.status || "candidate")} | conf=${escapeHtml((s.quality?.confidence ?? 0).toFixed?.(2) || s.quality?.confidence)}</div></div>`).join("");
      graph.innerHTML = `
        <div class="graph-column"><h4>Concept</h4>${conceptHtml || '<p class="muted">No concept</p>'}</div>
        <div class="graph-column"><h4>Episode</h4>${episodeHtml || '<p class="muted">No episode</p>'}</div>
        <div class="graph-column"><h4>Skill</h4>${skillHtml || '<p class="muted">No skill</p>'}</div>
      `;
    }

    function renderDashboard() {
      renderMetrics();
      renderGraph();
      $("events").innerHTML = snapshot.events.slice(-40).reverse().map(e => `<div class="event"><div class="muted">${escapeHtml(e.timestamp)} | ${escapeHtml(e.actor)} | ${escapeHtml(e.event_type)}</div><div>${escapeHtml(e.content)}</div></div>`).join("") || '<p class="muted">No events.</p>';
      $("nodesJson").textContent = JSON.stringify({ concepts: snapshot.concepts, episodes: snapshot.episodes, skills: snapshot.skills }, null, 2);
      $("edgesJson").textContent = JSON.stringify(snapshot.edges, null, 2);
      $("conceptList").innerHTML = snapshot.concepts.map(c => `<div class="node"><b>${escapeHtml(c.name)}</b><div class="muted">${escapeHtml((c.aliases || []).join("；"))}</div><p>${escapeHtml(c.description || "")}</p></div>`).join("") || '<p class="muted">Concept nodes will appear after extraction.</p>';
      $("skillList").innerHTML = snapshot.skills.map(s => `<div class="node skill"><b>${escapeHtml(s.name)}</b><div class="muted">${escapeHtml(s.status || "candidate")} | difficulty=${escapeHtml(s.difficulty_pattern || "unknown")} | confidence=${escapeHtml((s.quality?.confidence ?? 0).toFixed?.(2) || s.quality?.confidence)} | support=${escapeHtml(s.quality?.support_episode_count)} | validation+=${escapeHtml(s.quality?.validation_success_count)} | validation-=${escapeHtml(s.quality?.validation_fail_count)}</div><p>${escapeHtml(s.trigger || "")}</p></div>`).join("");
    }

    async function refresh() {
      const res = await fetch("/api/dashboard");
      snapshot = await res.json();
      renderDashboard();
      renderContext(lastContext);
    }

    async function sendMessage() {
      const text = $("input").value.trim();
      if (!text) return;
      $("input").value = "";
      addMessage("student", text);
      addMessage("assistant", "Thinking with memory...");
      try {
        const data = await api("/api/chat", payload({ message: text }));
        $("messages").lastChild.remove();
        addMessage("assistant", data.answer);
        lastContext = data.context;
        snapshot = data.snapshot;
        renderDashboard();
        renderContext(lastContext);
      } catch (err) {
        $("messages").lastChild.remove();
        addMessage("assistant", `Error: ${err.message}`);
      }
    }

    document.querySelectorAll("nav button").forEach(btn => {
      btn.addEventListener("click", () => {
        document.querySelectorAll("nav button").forEach(b => b.classList.remove("active"));
        document.querySelectorAll(".workspace").forEach(w => w.classList.remove("active"));
        btn.classList.add("active");
        $(btn.dataset.tab).classList.add("active");
      });
    });
    $("send").addEventListener("click", sendMessage);
    $("input").addEventListener("keydown", (e) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        sendMessage();
      }
    });
    $("forceExtract").addEventListener("click", async () => {
      const data = await api("/api/extract", payload());
      snapshot = data.snapshot;
      renderDashboard();
    });
    refresh();
  </script>
</body>
</html>"""
