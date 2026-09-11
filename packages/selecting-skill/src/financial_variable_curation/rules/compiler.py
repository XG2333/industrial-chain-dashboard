from __future__ import annotations

from financial_variable_curation.models.rules import CompiledRuleSet, RuleSet
from financial_variable_curation.rules.validator import RuleValidator
from financial_variable_curation.utils.hashing import hash_model


class RuleValidationError(ValueError):
    pass


class RuleCompiler:
    def __init__(self, validator: RuleValidator | None = None) -> None:
        self.validator = validator or RuleValidator()

    def compile(self, rule_set: RuleSet) -> CompiledRuleSet:
        validation = self.validator.validate(rule_set)
        if not validation.valid:
            raise RuleValidationError("; ".join(validation.errors))

        payload = rule_set.model_dump(mode="json")
        compiled = CompiledRuleSet.model_validate(
            {
                **payload,
                "effective_category_order": self._effective_order(rule_set.category_priorities),
                "effective_subcategory_order": self._effective_order(rule_set.subcategory_priorities),
                "effective_frequency_order": self._effective_order(rule_set.frequency_priorities),
                "effective_source_order": self._effective_order(rule_set.source_priorities),
                "compile_warnings": validation.warnings,
                "rules_hash": rule_set.rules_hash or hash_model(rule_set),
            }
        )
        return compiled

    @staticmethod
    def _effective_order(items: list) -> list[str]:
        indexed = list(enumerate(items))
        indexed.sort(key=lambda item: (item[1].priority, item[0]))
        return [item[1].value for item in indexed]
