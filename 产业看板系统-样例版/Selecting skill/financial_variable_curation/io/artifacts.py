from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel


class ArtifactManager:
    def __init__(self, run_id: str, base_dir: str | Path = "artifacts") -> None:
        self.run_id = run_id
        self.directory = Path(base_dir) / run_id
        self.directory.mkdir(parents=True, exist_ok=True)

    def write_json(self, name: str, payload: Any) -> Path:
        path = self.directory / name
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        return path

    def write_model(self, name: str, model: BaseModel) -> Path:
        return self.write_json(name, model.model_dump(mode="json"))

    def write_text(self, name: str, text: str) -> Path:
        path = self.directory / name
        path.write_text(text, encoding="utf-8")
        return path
