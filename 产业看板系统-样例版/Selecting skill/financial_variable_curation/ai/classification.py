from typing import Protocol

from financial_variable_curation.models.variable import VariableClassification, VariableProfile


class VariableClassifier(Protocol):
    name: str

    def classify(self, profile: VariableProfile) -> VariableClassification:
        """Return a semantic classification for one variable profile."""
