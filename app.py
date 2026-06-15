import json
from pathlib import Path

import streamlit as st

from eduflowgraph.config import load_settings_from_mapping
from eduflowgraph.pipeline import TutorPipeline


st.set_page_config(page_title="EduFlowGraph Tutor", page_icon="EFG", layout="wide")


CSS = """
<style>
:root {
  --ink: #17202a;
  --muted: #637083;
  --line: #d9e2ec;
  --panel: #f7f9fc;
  --accent: #1f8a70;
  --accent-2: #d95d39;
}
.main .block-container { padding-top: 1.1rem; max-width: 1500px; }
.efg-title { font-size: 1.45rem; font-weight: 760; color: var(--ink); margin-bottom: .15rem; }
.efg-subtitle { color: var(--muted); font-size: .92rem; margin-bottom: .8rem; }
.metric-row { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: .65rem; margin: .45rem 0 1rem; }
.metric-card { border: 1px solid var(--line); border-radius: 8px; padding: .65rem .75rem; background: #fff; }
.metric-card b { display: block; font-size: 1.2rem; color: var(--ink); }
.metric-card span { color: var(--muted); font-size: .78rem; }
.node-pill { border: 1px solid var(--line); border-left: 4px solid var(--accent); border-radius: 8px; padding: .6rem .7rem; margin-bottom: .5rem; background: #fff; }
.node-pill.episode { border-left-color: var(--accent-2); }
.node-pill.skill { border-left-color: #3f63b5; }
.small-muted { color: var(--muted); font-size: .82rem; }
</style>
"""
st.markdown(CSS, unsafe_allow_html=True)


def get_pipeline() -> TutorPipeline:
    settings = load_settings_from_mapping(
        {
            "provider": st.session_state.get("provider", "mock"),
            "api_key": st.session_state.get("api_key", ""),
            "base_url": st.session_state.get("base_url", "https://api.openai.com/v1"),
            "chat_model": st.session_state.get("chat_model", "gpt-4o-mini"),
            "embedding_model": st.session_state.get("embedding_model", "text-embedding-3-small"),
            "extraction_turns": st.session_state.get("extraction_turns", 4),
            "data_dir": st.session_state.get("data_dir", "data"),
        }
    )
    key = (
        settings.provider,
        settings.api_key,
        settings.base_url,
        settings.chat_model,
        settings.embedding_model,
        settings.extraction_turns,
        str(settings.data_dir),
    )
    if st.session_state.get("pipeline_key") != key:
        st.session_state.pipeline = TutorPipeline(settings)
        st.session_state.pipeline_key = key
    return st.session_state.pipeline


def render_metrics(snapshot: dict) -> None:
    st.markdown(
        f"""
        <div class="metric-row">
          <div class="metric-card"><b>{len(snapshot['events'])}</b><span>DataFlow events</span></div>
          <div class="metric-card"><b>{len(snapshot['concepts'])}</b><span>Concept nodes</span></div>
          <div class="metric-card"><b>{len(snapshot['episodes'])}</b><span>Episode nodes</span></div>
          <div class="metric-card"><b>{len(snapshot['skills'])}</b><span>Skill nodes</span></div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_chat(pipeline: TutorPipeline) -> None:
    if "messages" not in st.session_state:
        st.session_state.messages = []
    session_id = st.session_state.get("session_id", "session_demo")
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])
    user_message = st.chat_input("Ask the tutor about a concept, exercise, or misconception...")
    if user_message:
        st.session_state.messages.append({"role": "user", "content": user_message})
        with st.chat_message("user"):
            st.markdown(user_message)
        result = pipeline.handle_user_message(session_id, user_message)
        st.session_state.last_context = result["context"]
        st.session_state.last_episode = result["episode"]
        st.session_state.messages.append({"role": "assistant", "content": result["answer"]})
        with st.chat_message("assistant"):
            st.markdown(result["answer"])
        st.rerun()


def render_context_panel(context: dict | None) -> None:
    st.subheader("Personalized Context")
    if not context:
        st.info("Ask a question after memory has been extracted to see retrieved Concept, Episode, and Skill context.")
        return
    tabs = st.tabs(["Concepts", "Episodes", "Skills", "Raw"])
    with tabs[0]:
        for concept in context.get("concepts", []):
            state = concept.get("learner_state", {})
            st.markdown(
                f"""
                <div class="node-pill">
                  <b>{concept.get('name')}</b>
                  <div class="small-muted">mastery={state.get('mastery')} | status={state.get('status')} | trend={state.get('trend')}</div>
                  <div>{concept.get('summary', '')}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
    with tabs[1]:
        for episode in context.get("episodes", []):
            st.markdown(
                f"""
                <div class="node-pill episode">
                  <b>{episode.get('topic')}</b>
                  <div class="small-muted">{episode.get('node_id')}</div>
                  <div>{episode.get('summary')}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
    with tabs[2]:
        for skill in context.get("skills", []):
            quality = skill.get("quality", {})
            st.markdown(
                f"""
                <div class="node-pill skill">
                  <b>{skill.get('name')}</b>
                  <div class="small-muted">confidence={quality.get('confidence')} | success={quality.get('success_count')} | fail={quality.get('fail_count')}</div>
                  <div>{skill.get('summary')}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
    with tabs[3]:
        st.json(context)


def graphviz_source(snapshot: dict) -> str:
    lines = ["digraph EduFlowGraph {", "rankdir=LR;", 'node [shape=box style="rounded,filled" fontname="Helvetica"];']
    for concept in snapshot["concepts"]:
        label = f"{concept['name']}\\nmastery={concept.get('learner_state', {}).get('mastery')}"
        lines.append(f'"{concept["node_id"]}" [label="{label}" fillcolor="#e9f7f3"];')
    for episode in snapshot["episodes"]:
        label = f"{episode.get('topic', 'Episode')}\\n{episode['node_id'][-6:]}"
        lines.append(f'"{episode["node_id"]}" [label="{label}" fillcolor="#fff0e8"];')
    for skill in snapshot["skills"]:
        if skill.get("quality", {}).get("last_used"):
            label = f"{skill['name']}\\nconf={skill.get('quality', {}).get('confidence')}"
            lines.append(f'"{skill["node_id"]}" [label="{label}" fillcolor="#eef2ff"];')
    for edge in snapshot["edges"]:
        if edge["source"] in {n["node_id"] for n in snapshot["episodes"]}:
            lines.append(f'"{edge["source"]}" -> "{edge["target"]}" [label="{edge["edge_type"].replace("episode_", "")}"];')
    lines.append("}")
    return "\n".join(lines)


def render_memory_workbench(snapshot: dict) -> None:
    render_metrics(snapshot)
    tab_graph, tab_dataflow, tab_nodes, tab_edges = st.tabs(["Memory Graph", "DataFlow", "Nodes", "Edges"])
    with tab_graph:
        if snapshot["episodes"]:
            st.graphviz_chart(graphviz_source(snapshot), use_container_width=True)
        else:
            st.info("No extracted episodes yet. Chat for a few turns or press Force extraction.")
    with tab_dataflow:
        for event in reversed(snapshot["events"][-80:]):
            st.caption(f"{event['timestamp']} | {event['session_id']} | turn {event['turn_index']} | {event['actor']} | {event['event_type']}")
            st.write(event["content"])
    with tab_nodes:
        st.json({"concepts": snapshot["concepts"], "episodes": snapshot["episodes"], "skills": snapshot["skills"]})
    with tab_edges:
        st.json(snapshot["edges"])


def render_knowledge(snapshot: dict) -> None:
    st.subheader("Knowledge Space")
    concepts = snapshot["concepts"]
    if not concepts:
        st.info("Concept nodes will appear after episode extraction.")
    for concept in concepts:
        state = concept.get("learner_state", {})
        st.markdown(f"#### {concept.get('name')}")
        st.progress(float(state.get("mastery", 0.0)))
        st.write(concept.get("summary", ""))
        if concept.get("misconceptions"):
            st.warning("Misconceptions: " + "；".join(concept["misconceptions"]))
        if concept.get("recommended_actions"):
            st.info("Recommended actions: " + ", ".join(concept["recommended_actions"]))


def render_skills(snapshot: dict) -> None:
    st.subheader("Skill Workbench")
    for skill in snapshot["skills"]:
        quality = skill.get("quality", {})
        with st.expander(f"{skill.get('name')} | confidence {quality.get('confidence')}"):
            st.write(skill.get("description"))
            st.write("Procedure")
            st.write(skill.get("procedure", []))
            st.json(quality)


with st.sidebar:
    st.markdown('<div class="efg-title">EduFlowGraph Tutor</div>', unsafe_allow_html=True)
    st.markdown('<div class="efg-subtitle">DataFlow + Memory Graph + Skill-aware tutoring</div>', unsafe_allow_html=True)
    workspace = st.radio("Workspace", ["Chat", "Memory", "Knowledge", "Skills", "Settings"], label_visibility="collapsed")
    st.divider()
    st.text_input("Session ID", key="session_id", value=st.session_state.get("session_id", "session_demo"))
    st.selectbox("Provider", ["mock", "openai-compatible"], key="provider", index=0 if st.session_state.get("provider", "mock") == "mock" else 1)
    st.text_input("API Key", type="password", key="api_key", value=st.session_state.get("api_key", ""))
    st.text_input("Base URL", key="base_url", value=st.session_state.get("base_url", "https://api.openai.com/v1"))
    st.text_input("Chat model", key="chat_model", value=st.session_state.get("chat_model", "gpt-4o-mini"))
    st.text_input("Embedding model", key="embedding_model", value=st.session_state.get("embedding_model", "text-embedding-3-small"))
    st.number_input("Extraction events", min_value=2, max_value=12, value=st.session_state.get("extraction_turns", 4), key="extraction_turns")
    st.text_input("Data dir", key="data_dir", value=st.session_state.get("data_dir", "data"))


pipeline = get_pipeline()
snapshot = pipeline.dashboard()

header_left, header_right = st.columns([0.72, 0.28])
with header_left:
    st.markdown('<div class="efg-title">AI Tutor Workspace</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="efg-subtitle">DeepTutor-style learning workspace with an episode-centric memory graph: Concept ← Episode → Skill.</div>',
        unsafe_allow_html=True,
    )
with header_right:
    if st.button("Force extraction", use_container_width=True):
        episode = pipeline.force_extract(st.session_state.get("session_id", "session_demo"))
        st.session_state.last_episode = episode
        st.rerun()


if workspace == "Chat":
    left, right = st.columns([0.62, 0.38], gap="large")
    with left:
        render_chat(pipeline)
    with right:
        render_context_panel(st.session_state.get("last_context"))
elif workspace == "Memory":
    render_memory_workbench(snapshot)
elif workspace == "Knowledge":
    render_knowledge(snapshot)
elif workspace == "Skills":
    render_skills(snapshot)
else:
    st.subheader("Project Settings")
    st.write("Set an OpenAI-compatible API endpoint in the sidebar, then switch Provider from mock to openai-compatible.")
    st.code(
        "OPENAI_API_KEY=...\nOPENAI_BASE_URL=https://api.openai.com/v1\nEDUFLOW_CHAT_MODEL=gpt-4o-mini\nEDUFLOW_EMBEDDING_MODEL=text-embedding-3-small",
        language="bash",
    )
    st.write("Current graph files")
    st.json(
        {
            "dataflow": str(Path(st.session_state.get("data_dir", "data")) / "dataflow.jsonl"),
            "nodes": str(Path(st.session_state.get("data_dir", "data")) / "graph_nodes.json"),
            "edges": str(Path(st.session_state.get("data_dir", "data")) / "graph_edges.json"),
        }
    )
