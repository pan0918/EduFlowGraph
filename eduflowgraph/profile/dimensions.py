"""Lightweight three-model profile metadata.

The learner profile is intentionally small: each of the three models is a single
short paragraph (a "memory note") that gets rewritten over time rather than a
growing list of evidence items.

1. learner_model  — Student's cognitive state (diagnosis)
2. teaching_adaptation_model — Which teaching Skills fit this learner
3. context_model  — Current learning situation (scene adaptation)
"""
from __future__ import annotations

PROFILE_MODELS = {
    "learner_model": {
        "label": "学习者模型",
        "subtitle": "长期认知画像 — 稳定特征与待验证假设",
        "description": "沉淀跨多轮对话的稳定认知特征：反复出现的缺口、误区、推理习惯；口头“懂了”仅作待验证信号，不作已掌握结论。",
        "icon": "brain",
        "budget": 300,
    },
    "teaching_adaptation_model": {
        "label": "教学适配模型",
        "subtitle": "Skill 选择 — 个性化重排与过滤依据",
        "description": "描述更适合或应避免的 Skill 类型、认知负荷、教学节奏与验证偏好，不保存具体教学程序。",
        "icon": "compass",
        "budget": 300,
    },
    "context_model": {
        "label": "情境模型",
        "subtitle": "当前场景 — 任务、阶段与情绪",
        "description": "仅描述此刻的学习任务、所处阶段（探索/练习/复习等）和情绪状态；不含认知诊断或掌握判断。",
        "icon": "clock",
        "budget": 200,
    },
}

MODEL_NAMES = tuple(PROFILE_MODELS.keys())

# Models consolidated at episode boundaries (deep, stable signals).
EPISODE_MODELS = ("learner_model", "teaching_adaptation_model")
# Model refreshed lightly on every turn (time-sensitive situation).
TURN_MODEL = "context_model"

# Maximum number of bounded change-log entries kept for the UI.
MAX_RECENT_CHANGES = 8


def model_budget(model_name: str) -> int:
    return int(PROFILE_MODELS.get(model_name, {}).get("budget", 300))
