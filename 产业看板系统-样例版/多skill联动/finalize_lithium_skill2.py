# -*- coding: utf-8 -*-
"""Finalize Skill2 using the completed DeepSeek classification run.

The directory-mark CLI re-classifies all variables on every invocation, and the
installed skill has a concurrency merge bug. This helper reuses the completed
classification run already stored in curation.db, then runs rule compilation,
selection, and directory writing without another 3,500-variable LLM pass.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from sqlalchemy import select

from financial_variable_curation.classification.settings import LLMSettings
from financial_variable_curation.database.manager import DatabaseManager
from financial_variable_curation.database.migrations.runner import MigrationRunner
from financial_variable_curation.database.models import SourceSheet as SourceSheetModel
from financial_variable_curation.database.repositories import (
    RuleSetRepository,
    SelectionResultRepository,
    SourceSheetRepository,
    VariableClassificationRepository,
    VariableQualityRepository,
    VariableRepository,
)
from financial_variable_curation.database.settings import DatabaseSettings
from financial_variable_curation.export.directory_writer import update_directory_sheet
from financial_variable_curation.rule_workflow.service import RuleParserService
from financial_variable_curation.rule_workflow.source_loader import load_rule_source
from financial_variable_curation.selection.service import VariableSelectionService


RUN_DIR = Path(r"C:\Users\11\Documents\多skill联动\workflow_runs\20260811T084756Z_ff8cb7541bcc")
DB_PATH = RUN_DIR / "curation.db"
INPUT_PATH = RUN_DIR / "01_excel_catalog_curator" / "cataloged.xlsx"
RULES_PATH = Path(r"C:\Users\11\Documents\Selecting skill\input\selection_rules.docx")
ARTIFACTS_DIR = RUN_DIR / "skill2_artifacts"
OUTPUT_PATH = RUN_DIR / "02_financial_variable_curation" / "directory_marked.xlsx"
RUN_ID = "20260811T092236Z_df2768cb"


def main() -> int:
    manager = DatabaseManager(DatabaseSettings.from_env(database_url=str(DB_PATH)))
    MigrationRunner(manager.engine).upgrade()
    settings = LLMSettings.from_env(provider="deepseek")

    try:
        # Reuse an existing compiled rule set when present, otherwise compile once.
        loaded = load_rule_source(RULES_PATH)
        source_hash = loaded.metadata.get("source_file_hash") or loaded.metadata.get("source_hash")
        name = f"{RULES_PATH.stem}_{str(source_hash or '')[:8]}"
        rule_set_id = None
        if source_hash:
            with manager.session_scope() as session:
                existing = RuleSetRepository(session).get_by_name_version(name, "1")
                if existing and existing.source_hash == source_hash:
                    rule_set_id = existing.rule_set_id
        if rule_set_id is None:
            print("Compiling rules once with DeepSeek...")
            rule_result = RuleParserService(manager, settings=settings).compile_rules(
                RULES_PATH,
                provider="deepseek",
                model=None,
                name=name,
                version="1",
                force_refresh=False,
                artifacts_dir=ARTIFACTS_DIR,
            )
            rule_set_id = rule_result.compiled.compiled_rule_set_id if rule_result.compiled else None
            if not rule_set_id:
                print("Rule compilation did not produce a rule set.", file=sys.stderr)
                return 1

        print("Running selection on completed classification run...")
        selection = VariableSelectionService(manager).select(
            RUN_ID,
            rule_set_id=rule_set_id,
            rule_version="1",
            allow_validated_rules=True,
            include_review_candidates=True,
            artifacts_dir=ARTIFACTS_DIR,
        )
        print(
            f"Selected: {selection.selected_count}, Rejected: {selection.rejected_count}, "
            f"Review: {selection.needs_review_count}, Failed: {selection.failed_count}"
        )

        print("Writing directory sheet...")
        with manager.session_scope() as session:
            var_rows = VariableRepository(session).list_by_run_id(RUN_ID)
            classifications = {
                item.variable_id: item
                for item in VariableClassificationRepository(session).list_for_run(RUN_ID)
            }
            qualities_by_id = {
                item.variable_id: item
                for item in VariableQualityRepository(session).list_by_run_id(RUN_ID)
            }
            sel_results = {
                item.variable_id: item
                for item in SelectionResultRepository(session).list_for_run(selection.selection_run_id)
            }
            sheet_ids = list({v.sheet_id for v in var_rows})
            all_sheets = session.scalars(
                select(SourceSheetModel).where(SourceSheetModel.sheet_id.in_(sheet_ids))
            ).all()
            sheet_names = {s.sheet_id: s.sheet_name for s in all_sheets}

        directory_rows = []
        for var in var_rows:
            cls = classifications.get(var.variable_id)
            sel = sel_results.get(var.variable_id)
            quality = qualities_by_id.get(var.variable_id)
            directory_rows.append(
                {
                    "original_name": var.original_name,
                    "sheet_name": sheet_names.get(var.sheet_id, ""),
                    "unit_hint": var.unit_hint,
                    "detected_frequency": quality.detected_frequency if quality else "",
                    "category_level_1": cls.category_level_1 if cls else "",
                    "category_level_2": cls.category_level_2 if cls else "",
                    "data_nature": cls.data_nature if cls else "",
                    "confidence": cls.confidence if cls else None,
                    "final_status": sel.final_status if sel else "UNCLASSIFIED",
                    "reason_text": sel.primary_reason_text if sel else "Not classified yet.",
                }
            )
        directory_rows.sort(key=lambda r: (r.get("sheet_name", ""), r.get("original_name", "")))
        output = update_directory_sheet(INPUT_PATH, OUTPUT_PATH, directory_rows)
        print(f"Directory sheet written: {output.resolve()}")
    finally:
        manager.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
