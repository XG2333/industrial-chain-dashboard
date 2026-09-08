from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from financial_variable_curation.classification.models import (
    ClassificationBatchResponse,
    ClassificationRequest,
    ClassificationResponse,
    ClassificationRunResult,
)


class ClassificationArtifactWriter:
    def __init__(self, artifacts_dir: str | Path, run_id: str) -> None:
        self.run_dir = Path(artifacts_dir) / run_id
        self.classification_dir = self.run_dir / "classification"
        self.classification_dir.mkdir(parents=True, exist_ok=True)

    def write_request(self, request: ClassificationRequest) -> Path:
        path = self.classification_dir / f"request_{request.batch_id}.json"
        path.write_text(
            json.dumps(request.model_dump(mode="json"), ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
        return path

    def write_response(self, response: ClassificationBatchResponse) -> Path:
        path = self.classification_dir / f"response_{response.batch_id}.json"
        path.write_text(
            json.dumps(response.model_dump(mode="json"), ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
        return path

    def write_audit(self, result: ClassificationRunResult) -> Path:
        path = self.classification_dir / "classification_audit.json"
        path.write_text(
            json.dumps(result.model_dump(mode="json"), ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
        return path

    def write_comparison(
        self,
        *,
        original_names: dict[str, str],
        mock_responses: list[ClassificationResponse],
        openai_responses: list[ClassificationResponse],
    ) -> Path:
        mock_by_id = {item.variable_id: item for item in mock_responses}
        openai_by_id = {item.variable_id: item for item in openai_responses}
        rows: list[dict[str, Any]] = []
        for variable_id in sorted(original_names):
            mock = mock_by_id.get(variable_id)
            real = openai_by_id.get(variable_id)
            rows.append(
                {
                    "variable_id": variable_id,
                    "original_name": original_names[variable_id],
                    "mock_category_level_1": mock.category_level_1.value if mock else None,
                    "openai_category_level_1": real.category_level_1.value if real else None,
                    "mock_commodity": mock.commodity if mock else None,
                    "openai_commodity": real.commodity if real else None,
                    "mock_confidence": mock.confidence if mock else None,
                    "openai_confidence": real.confidence if real else None,
                    "comparison_group_key_equal": bool(
                        mock and real and mock.comparison_group_components == real.comparison_group_components
                    ),
                    "enum_error": not bool(real),
                    "needs_review": bool(real and (real.review_reasons or real.confidence < 0.6)),
                    "difference_notes": _difference_note(mock, real),
                }
            )
        path = self.classification_dir / "provider_comparison.json"
        path.write_text(
            json.dumps(rows, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
        return path


def _difference_note(
    mock: ClassificationResponse | None,
    real: ClassificationResponse | None,
) -> str:
    if mock is None or real is None:
        return "Missing comparison result."
    differences = []
    if mock.category_level_1 != real.category_level_1:
        differences.append("category differs")
    if mock.commodity != real.commodity:
        differences.append("commodity differs")
    if mock.data_nature != real.data_nature:
        differences.append("data nature differs")
    return "; ".join(differences) if differences else "consistent"
