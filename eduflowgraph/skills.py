from copy import deepcopy


TEACHING_ACTION_TAXONOMY = {
    "contrastive_explanation": {
        "label": "Contrastive explanation",
        "description": "通过对比两个容易混淆的对象来澄清概念差异。",
        "procedure_steps": [
            "先点名两个容易混淆的对象。",
            "用自然语言分别解释两个对象。",
            "放到同一个场景里对比它们。",
        ],
    },
    "step_by_step_guidance": {
        "label": "Step-by-step guidance",
        "description": "把复杂问题拆成连续小步骤，逐步降低理解门槛。",
        "procedure_steps": [
            "把目标拆成更小的步骤。",
            "一次只解释一个步骤。",
            "每一步后都检查理解。",
        ],
    },
    "worked_example": {
        "label": "Worked example",
        "description": "先给完整示范，再帮助学生迁移到相似问题。",
        "procedure_steps": [
            "先给一个小型完整例题。",
            "标出关键判断点。",
            "请学习者把模式迁移到相似题。",
        ],
    },
    "socratic_questioning": {
        "label": "Socratic questioning",
        "description": "通过连续追问让学生自己暴露和修正理解缺口。",
        "procedure_steps": [
            "先问一个低门槛诊断问题。",
            "根据学习者回答继续追问。",
            "请学习者总结规则。",
        ],
    },
    "concrete_example": {
        "label": "Concrete example",
        "description": "用具体例子、数字实例或类比让抽象概念落地。",
        "procedure_steps": [
            "设置一个具体的场景或数字实例。",
            "列出相关数量关系。",
            "把具体例子映射回抽象概念。",
        ],
    },
    "formula_decomposition": {
        "label": "Formula decomposition",
        "description": "把公式拆成局部项并解释每一项的含义与依赖关系。",
        "procedure_steps": [
            "把公式拆成更小的项。",
            "解释每一项的含义。",
            "再把各项连回完整表达式。",
        ],
    },
    "self_explanation_prompt": {
        "label": "Self explanation prompt",
        "description": "要求学生用自己的话复述关键关系与结论。",
        "procedure_steps": [
            "请学习者用自己的话复述。",
            "追问缺失的理解环节。",
            "用一个新例子确认能否迁移。",
        ],
    },
    "diagnostic_check": {
        "label": "Diagnostic check",
        "description": "通过短问题或小练习快速判断学生是否真正掌握。",
        "procedure_steps": [
            "问一个聚焦的小检查问题。",
            "检查学习者的回答。",
            "判断是否还需要继续支架。",
        ],
    },
    "guided_practice": {
        "label": "Guided practice",
        "description": "让学习者在导师支持下完成练习或相似任务。",
        "procedure_steps": [
            "给出一个相似任务。",
            "在学习者尝试时提供提示。",
            "逐步减少支架直到独立完成。",
        ],
    },
    "error_correction": {
        "label": "Error correction",
        "description": "指出并纠正学习者的具体错误推理、步骤或应用。",
        "procedure_steps": [
            "精确指出错误位置和内容。",
            "解释为什么是错的。",
            "引导学习者自己修正。",
        ],
    },
}

DIFFICULTY_PATTERN_TAXONOMY = {
    "direction_confusion": {
        "label": "Direction confusion",
        "description": "学生混淆两个方向相关但不对称的概念、条件或公式。",
        "trigger_phrase": "方向、条件、因果等不对称关系的混淆",
    },
    "abstraction_gap": {
        "label": "Abstraction gap",
        "description": "学生能跟着话走，但抽象定义或原则本身没有落地。",
        "trigger_phrase": "尚未落地的抽象概念",
    },
    "procedural_gap": {
        "label": "Procedural gap",
        "description": "学生知道目标是什么，但不会把过程拆成可执行步骤。",
        "trigger_phrase": "缺少可执行步骤的问题",
    },
    "symbol_grounding": {
        "label": "Symbol grounding",
        "description": "学生记住了符号或公式，却无法把它映射回自然语言或情境。",
        "trigger_phrase": "没有落到含义的符号或公式",
    },
    "transfer_failure": {
        "label": "Transfer failure",
        "description": "学生在原例子中能跟上，但换一个相似场景就不会迁移。",
        "trigger_phrase": "难以迁移到相似情境的问题",
    },
    "conceptual_confusion": {
        "label": "Conceptual confusion",
        "description": "学生对概念本身、定义、边界或核心含义存在一般性混淆。",
        "trigger_phrase": "概念本身的理解混淆",
    },
    "unknown": {
        "label": "Unknown",
        "description": "当前证据不足以稳定判断困难模式。",
        "trigger_phrase": "尚不明确的学习困难模式",
    },
}

ACTION_TO_SUCCESS_CRITERIA = {
    "contrastive_explanation": "学习者能清楚说出两个目标的差异。",
    "step_by_step_guidance": "学习者能按顺序解释关键步骤。",
    "worked_example": "学习者能把例题模式迁移到相似情境。",
    "socratic_questioning": "学习者能先于导师自己说出规则。",
    "concrete_example": "学习者能把具体例子映射回抽象概念。",
    "formula_decomposition": "学习者能解释每个公式项为什么出现。",
    "self_explanation_prompt": "学习者能用自己的话复述核心思想。",
    "diagnostic_check": "学习者能正确回答一个短检查题。",
    "guided_practice": "学习者能在减少支架后独立完成相似任务。",
    "error_correction": "学习者能指出并修正自己先前的错误。",
}


TEACHING_ACTIONS = tuple(TEACHING_ACTION_TAXONOMY.keys())
DIFFICULTY_PATTERNS = tuple(DIFFICULTY_PATTERN_TAXONOMY.keys())


def teaching_action_taxonomy() -> dict:
    return deepcopy(TEACHING_ACTION_TAXONOMY)


def difficulty_pattern_taxonomy() -> dict:
    return deepcopy(DIFFICULTY_PATTERN_TAXONOMY)
