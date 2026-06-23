"""Lightweight three-model profile metadata.

The learner profile is intentionally small: each of the three models is a single
short paragraph (a "memory note") that gets rewritten over time rather than a
growing list of evidence items.

1. learner_model  — Student's cognitive state (diagnosis)
2. strategy_model — What teaching approaches work for this learner (prescription)
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
    "strategy_model": {
        "label": "教学策略模型",
        "subtitle": "下一步教学 — 条件规则驱动具体动作",
        "description": "可执行的“当…→优先…→然后…”规则，指导下一轮该怎么教、如何验证，而非仅记录某方法有效。",
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
EPISODE_MODELS = ("learner_model", "strategy_model")
# Model refreshed lightly on every turn (time-sensitive situation).
TURN_MODEL = "context_model"

# Maximum number of bounded change-log entries kept for the UI.
MAX_RECENT_CHANGES = 8


def model_budget(model_name: str) -> int:
    return int(PROFILE_MODELS.get(model_name, {}).get("budget", 300))
