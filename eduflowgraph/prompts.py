from pathlib import Path


PROMPT_DIR = Path(__file__).resolve().parent / "Prompt"
EPISODE_EXTRACTION_PROMPT = (PROMPT_DIR / "Episode_Extraction_Prompt.md").read_text(
    encoding="utf-8"
)
CONCEPT_EXTRACTION_PROMPT = (PROMPT_DIR / "Concept_Extraction_Prompt.md").read_text(
    encoding="utf-8"
)
TEACHING_ACTIONS_EXTRACTION_PROMPT = (
    PROMPT_DIR / "Teaching_Actions_Extraction_Prompt.md"
).read_text(encoding="utf-8")
SKILL_DISTILLATION_PROMPT = (
    PROMPT_DIR / "Skill_Distillation_Prompt.md"
).read_text(encoding="utf-8")
TUTOR_SYSTEM_PROMPT = (PROMPT_DIR / "Tutor_System_Prompt.md").read_text(encoding="utf-8")
TUTOR_USER_PROMPT = (PROMPT_DIR / "Tutor_User_Prompt.md").read_text(encoding="utf-8")
TUTOR_MEMORY_AUGMENTED_USER_PROMPT = (
    PROMPT_DIR / "Tutor_Memory_Augmented_User_Prompt.md"
).read_text(encoding="utf-8")
RERANK_FALLBACK_PROMPT = (PROMPT_DIR / "Rerank_Fallback_Prompt.md").read_text(
    encoding="utf-8"
)
