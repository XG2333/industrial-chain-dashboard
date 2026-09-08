from __future__ import annotations

import hashlib
import json

from financial_variable_curation.rule_workflow.constants import (
    EXECUTION_PHASES,
    RULE_TYPE_TO_PHASE,
)
from financial_variable_curation.rule_workflow.models import (
    CompiledRule,
    CompiledRuleSetOutput,
    RuleConflictReport,
    RuleSetDocument,
    rule_document_hash,
)


class RuleCompilationError(ValueError):
    pass


class RuleCompiler:
    def compile(
        self,
        document: RuleSetDocument,
        *,
        source_hash: str,
        rule_set_name: str,
        version: str,
        conflicts: RuleConflictReport,
    ) -> CompiledRuleSetOutput:
        fatal = [conflict for conflict in conflicts.conflicts if conflict.severity == "FATAL"]
        if fatal:
            raise RuleCompilationError(
                "FATAL rule conflicts prevent compilation: "
                + "; ".join(conflict.description for conflict in fatal)
            )
        compiled_rules: list[CompiledRule] = []
        for rule in document.rules:
            phase = RULE_TYPE_TO_PHASE.get(rule.rule_type, "VALIDATION")
            dependencies = []
            if rule.rule_type == "EXCEPTION":
                dependencies = [
                    condition.target_rule_id
                    for condition in rule.conditions
                    if condition.target_rule_id
                ]
            compiled_rules.append(
                CompiledRule(rule=rule, execution_phase=phase, dependency_rule_ids=dependencies)
            )
        plan = [
            phase
            for phase in EXECUTION_PHASES
            if any(item.execution_phase == phase for item in compiled_rules)
        ]
        payload = {
            "source_hash": source_hash,
            "rule_set_name": rule_set_name,
            "version": version,
            "document_hash": rule_document_hash(document),
            "rules": [item.rule.model_dump(mode="json") for item in compiled_rules],
            "plan": plan,
        }
        compiled_hash = hashlib.sha256(
            json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
        ).hexdigest()
        compiled_rule_set_id = hashlib.sha256(
            f"{rule_set_name}|{version}|{source_hash}".encode("utf-8")
        ).hexdigest()[:16]
        warnings = [conflict.description for conflict in conflicts.conflicts if conflict.severity == "WARNING"]
        return CompiledRuleSetOutput(
            compiled_rule_set_id=compiled_rule_set_id,
            rule_set_name=rule_set_name,
            version=version,
            status="VALIDATED",
            production_ready=False,
            compiled_rules=compiled_rules,
            execution_plan=plan,
            source_hash=source_hash,
            compiled_hash=compiled_hash,
            warnings=warnings,
        )
