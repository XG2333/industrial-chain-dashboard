from __future__ import annotations

from financial_variable_curation.ai.classification import VariableClassifier
from financial_variable_curation.models.enums import ClassificationMethod
from financial_variable_curation.models.variable import VariableClassification, VariableProfile


class OpenAIVariableClassifier:
    """Optional LLM classifier; requires the optional 'ai' dependency and API key."""

    name = "openai"

    def classify(self, profile: VariableProfile) -> VariableClassification:
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise RuntimeError(
                "OpenAI variable classifier requires the optional 'ai' dependency: pip install -e '.[ai]'"
            ) from exc

        client = OpenAI()
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            response_format={"type": "json_object"},
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Classify one financial variable into category, subcategory, semantic_description, "
                        "confidence, and needs_review. Return JSON only."
                    ),
                },
                {
                    "role": "user",
                    "content": f"Variable header: {profile.original_header}\nSheet: {profile.sheet_name}",
                },
            ],
        )
        import json

        payload = json.loads(response.choices[0].message.content or "{}")
        return VariableClassification(
            category=str(payload.get("category") or "UNCLASSIFIED"),
            subcategory=str(payload.get("subcategory") or "UNCLASSIFIED"),
            semantic_description=str(payload.get("semantic_description") or ""),
            confidence=float(payload.get("confidence") or 0.0),
            method=ClassificationMethod.LLM,
            needs_review=bool(payload.get("needs_review", True)),
        )
