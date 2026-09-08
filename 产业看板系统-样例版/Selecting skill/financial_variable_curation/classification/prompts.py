from __future__ import annotations

import os
from pathlib import Path


def _prompt_dir() -> Path:
    env_dir = os.getenv("FVC_PROMPT_DIR")
    if env_dir:
        return Path(env_dir)
    return Path(__file__).resolve().parents[3] / "prompts"


def load_system_prompt() -> str:
    return (_prompt_dir() / "variable_classifier_system_v1.txt").read_text(encoding="utf-8")


def load_user_prompt(variable_batch_json: str) -> str:
    template = (_prompt_dir() / "variable_classifier_user_v1.txt").read_text(encoding="utf-8")
    return template.format(variable_batch_json=variable_batch_json)
