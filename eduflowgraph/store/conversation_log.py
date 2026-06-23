import json
from pathlib import Path
from typing import Any, Iterator

from ..schemas import Turn, make_id, utc_now


class ConversationLog:
    """Per-session JSONL turn storage.

    Each session is stored in its own file at ``conversations/{session_id}.jsonl``.
    Each line is a complete turn (user message + assistant reply).
    """

    def __init__(self, conversations_dir: Path):
        self.dir = conversations_dir
        self.dir.mkdir(parents=True, exist_ok=True)

    def _session_path(self, session_id: str) -> Path:
        safe = session_id.replace("/", "_").replace("\\", "_")
        return self.dir / f"{safe}.jsonl"

    def append_turn(
        self,
        *,
        session_id: str,
        turn_index: int,
        user_message: str,
        assistant_message: str,
        metadata: dict[str, Any] | None = None,
    ) -> Turn:
        turn = Turn(
            turn_index=turn_index,
            timestamp=utc_now(),
            session_id=session_id,
            user_message=user_message,
            assistant_message=assistant_message,
            metadata=metadata or {},
        )
        path = self._session_path(session_id)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(turn.to_dict(), ensure_ascii=False) + "\n")
        return turn

    def iter_turns(self, session_id: str) -> Iterator[dict[str, Any]]:
        path = self._session_path(session_id)
        if not path.exists():
            return
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue

    def list_turns(self, session_id: str) -> list[dict[str, Any]]:
        return list(self.iter_turns(session_id))

    def next_turn_index(self, session_id: str) -> int:
        turns = self.list_turns(session_id)
        if not turns:
            return 1
        return max(int(t.get("turn_index", 0)) for t in turns) + 1

    def list_sessions(self) -> list[str]:
        if not self.dir.exists():
            return []
        return sorted(
            p.stem for p in self.dir.glob("*.jsonl") if p.stat().st_size > 0
        )

    def session_messages(
        self, session_id: str, *, limit: int = 16
    ) -> list[dict[str, str]]:
        """Build an OpenAI-style message list from recent turns."""
        messages: list[dict[str, str]] = []
        for turn in self.list_turns(session_id):
            user = str(turn.get("user_message", "")).strip()
            assistant = str(turn.get("assistant_message", "")).strip()
            if user:
                messages.append({"role": "user", "content": user})
            if assistant:
                messages.append({"role": "assistant", "content": assistant})
        return messages[-limit:]

    def render_for_extraction(self, session_id: str) -> str:
        """Render turns as text for episode boundary detection / extraction."""
        lines = []
        for turn in self.list_turns(session_id):
            ts = turn.get("timestamp", "")
            user = str(turn.get("user_message", "")).strip()
            assistant = str(turn.get("assistant_message", "")).strip()
            if user:
                lines.append(f"[{ts}] student: {user}")
            if assistant:
                lines.append(f"[{ts}] assistant: {assistant}")
        return "\n".join(lines)

    def clear_session(self, session_id: str) -> None:
        path = self._session_path(session_id)
        if path.exists():
            path.write_text("", encoding="utf-8")

    def clear_all(self) -> None:
        for path in self.dir.glob("*.jsonl"):
            path.unlink()
