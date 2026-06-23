from pathlib import Path


PROMPT_DIR = Path(__file__).resolve().parent / "Prompt"


def _load(name: str) -> str:
    return (PROMPT_DIR / name).read_text(encoding="utf-8")


EPISODE_DETECTION_PROMPT = _load("Episode_Detection_Prompt.md")
EPISODE_EXTRACTION_PROMPT = _load("Episode_Extraction_Prompt.md")
CONCEPT_EXTRACTION_PROMPT = _load("Concept_Extraction_Prompt.md")
SKILL_EVIDENCE_EXTRACTION_PROMPT = _load("Skill_Evidence_Extraction_Prompt.md")
SKILL_DISTILLATION_PROMPT = _load("Skill_Distillation_Prompt.md")
RERANK_FALLBACK_PROMPT = _load("Rerank_Fallback_Prompt.md")
TUTOR_SYSTEM_PROMPT = _load("Tutor_System_Prompt.md")
TUTOR_USER_PROMPT = _load("Tutor_User_Prompt.md")
TUTOR_MEMORY_AUGMENTED_USER_PROMPT = _load("Tutor_Memory_Augmented_User_Prompt.md")
PROFILE_UPDATE_PROMPT = _load("Profile_Update_Prompt.md")
CONTEXT_UPDATE_PROMPT = _load("Context_Update_Prompt.md")
PROFILE_CONDENSE_PROMPT = _load("Profile_Condense_Prompt.md")
