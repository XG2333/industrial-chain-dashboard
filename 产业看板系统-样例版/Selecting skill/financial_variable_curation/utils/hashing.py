import hashlib
import json

from pydantic import BaseModel


def canonical_json(data: object) -> str:
    return json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def hash_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def hash_model(model: BaseModel) -> str:
    payload = model.model_dump(mode="json", exclude={"rules_hash"})
    return hash_text(canonical_json(payload))
