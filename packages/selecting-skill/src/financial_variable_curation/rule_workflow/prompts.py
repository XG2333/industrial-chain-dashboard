from __future__ import annotations

import os
from pathlib import Path


def _prompt_dir() -> Path:
    env_dir = os.getenv("FVC_PROMPT_DIR")
    if env_dir:
        return Path(env_dir)
    return Path(__file__).resolve().parents[3] / "prompts"


def load_rule_system_prompt() -> str:
    return (_prompt_dir() / "rule_parser_system_v1.txt").read_text(encoding="utf-8")


def load_rule_user_prompt(rule_text: str) -> str:
    template = (_prompt_dir() / "rule_parser_user_v1.txt").read_text(encoding="utf-8")
    return template.format(rule_text=rule_text)
