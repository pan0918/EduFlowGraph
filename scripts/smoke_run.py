from pathlib import Path
import sys
import tempfile


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from EduFlowGraph.config import load_settings_from_mapping
from EduFlowGraph.pipeline import TutorPipeline


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        pipeline = TutorPipeline(
            load_settings_from_mapping({"provider": "mock", "data_dir": tmp})
        )
        session_id = "session_smoke"
        first = pipeline.handle_user_message(session_id, "为什么不能直接用检测准确率当作患病概率？")
        pipeline.handle_user_message(session_id, "我还是不懂 P(A|B) 和 P(B|A) 的区别。")
        second = pipeline.handle_user_message(session_id, "你能再对比一下 P(A|B) 和 P(B|A) 吗？")
        third = pipeline.handle_user_message(session_id, "懂了，我现在能说出这两个条件概率的方向差异。")
        fourth = pipeline.handle_user_message(session_id, "请再对比一次 P(A|B) 和 P(B|A)，我想检查自己。")
        fifth = pipeline.handle_user_message(session_id, "懂了，这次我可以自己解释这两个方向了。")
        snapshot = pipeline.dashboard()
        print("FIRST_ANSWER=", first["answer"][:120].replace("\n", " "))
        print("SECOND_ANSWER=", second["answer"][:120].replace("\n", " "))
        print("THIRD_EPISODE=", third["episode"]["node_id"] if third.get("episode") else "none")
        print("FOURTH_EPISODE=", fourth["episode"]["node_id"] if fourth.get("episode") else "none")
        print("FIFTH_EPISODE=", fifth["episode"]["node_id"] if fifth.get("episode") else "none")
        print(
            "COUNTS=",
            {
                key: len(snapshot[key])
                for key in ["memory_events", "concepts", "episodes", "skills", "edges"]
            },
        )


if __name__ == "__main__":
    main()
