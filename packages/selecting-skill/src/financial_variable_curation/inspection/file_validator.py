from __future__ import annotations

import hashlib
import zipfile
from pathlib import Path

from financial_variable_curation.models.artifacts import FileValidationResult


class FileValidator:
    def validate(self, path: str | Path) -> FileValidationResult:
        input_path = Path(path)
        errors: list[str] = []

        if not input_path.exists():
            errors.append(f"File does not exist: {input_path}")
            return FileValidationResult(
                valid=False,
                file_name=input_path.name,
                file_path=str(input_path.resolve()),
                errors=errors,
            )

        if not input_path.is_file():
            errors.append(f"Path is not a file: {input_path}")
        if input_path.suffix.lower() != ".xlsx":
            errors.append("Only .xlsx files are supported in this stage.")
        if input_path.stat().st_size == 0:
            errors.append("File is empty.")
        if not zipfile.is_zipfile(input_path):
            errors.append("File is not a valid xlsx zip container.")

        file_hash: str | None = None
        try:
            file_hash = self._sha256(input_path)
        except OSError as exc:
            errors.append(f"Cannot read file: {exc}")

        return FileValidationResult(
            valid=not errors,
            file_name=input_path.name,
            file_path=str(input_path.resolve()),
            file_size_bytes=input_path.stat().st_size,
            file_hash=file_hash,
            errors=errors,
        )

    @staticmethod
    def _sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()
