from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from financial_variable_curation import __version__
from financial_variable_curation.ai.openai import OpenAIVariableClassifier
from financial_variable_curation.ai.mock import MockVariableClassifier
from financial_variable_curation.ai.rule_parser import get_rule_parser
from financial_variable_curation.classification.exceptions import LLMError
from financial_variable_curation.classification.service import BatchClassificationService
from financial_variable_curation.classification.settings import LLMSettings
from financial_variable_curation.database.exceptions import DatabaseError, EntityNotFoundError, PersistenceError
from financial_variable_curation.database.manager import DatabaseManager
from financial_variable_curation.database.migrations.runner import MigrationRunner
from financial_variable_curation.database.services import InspectionPersistenceService, RunQueryService
from financial_variable_curation.database.settings import DatabaseSettings
from financial_variable_curation.export.service import SelectionExportError, SelectionExportService
from financial_variable_curation.export.directory_writer import update_directory_sheet
from financial_variable_curation.export.orchestrator import (
    FullPipelineOrchestrator,
    PipelineWorkflowError,
)
from financial_variable_curation.inspection.artifact_writer import InspectionArtifactWriter
from financial_variable_curation.inspection.exceptions import InspectionError
from financial_variable_curation.io.artifacts import ArtifactManager
from financial_variable_curation.io.excel_writer import write_selection_workbook
from financial_variable_curation.models.artifacts import (
    DataQualityReport,
    InspectionSummary,
    RequestRecord,
)
from financial_variable_curation.models.enums import RuleSetStatus
from financial_variable_curation.models.inspection import InspectionResult
from financial_variable_curation.models.rules import RuleSet
from financial_variable_curation.models.variable import VariableProfile
from financial_variable_curation.models.workbook import WorkbookProfile
from financial_variable_curation.pipeline.execute import (
    DeterministicRuleEngine,
    build_selection_result,
)
from financial_variable_curation.pipeline.inspect import run_inspection
from financial_variable_curation.rule_workflow.exceptions import RuleWorkflowError
from financial_variable_curation.rule_workflow.service import RuleParserService
from financial_variable_curation.rule_workflow.source_loader import load_rule_source
from financial_variable_curation.selection.service import SelectionWorkflowError, VariableSelectionService
from financial_variable_curation.rules.compiler import RuleCompiler, RuleValidationError
from financial_variable_curation.rules.default_rules import build_default_rules
from financial_variable_curation.rules.store import RuleStore
from financial_variable_curation.rules.validator import RuleValidator
from financial_variable_curation.utils.hashing import hash_model


def _new_run_id() -> str:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{timestamp}_{uuid4().hex[:8]}"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="financial_variable_curation",
        description="Rule-pluggable financial variable selection workflow.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    inspect_parser = subparsers.add_parser("inspect", help="Inspect an Excel workbook without selection.")
    inspect_parser.add_argument("--input", required=True, help="Input Excel file.")
    inspect_parser.add_argument("--artifacts-dir", default="artifacts", help="Artifact output directory.")
    inspect_parser.add_argument("--header-row", type=int, default=None, help="1-based header row.")
    inspect_parser.add_argument("--date-column", default=None, help="Explicit date column header or 1-based position.")
    inspect_parser.add_argument("--sheet", default=None, help="Only inspect this sheet by name.")
    inspect_parser.add_argument("--database", default=None, help="Optional SQLite database URL or path.")
    inspect_parser.add_argument(
        "--persist",
        action="store_true",
        help="Persist inspection artifacts to the database (requires --database).",
    )
    inspect_parser.set_defaults(handler=_handle_inspect)

    run_parser = subparsers.add_parser("run", help="Run variable selection.")
    run_parser.add_argument("--input", required=True, help="Input Excel file.")
    run_parser.add_argument("--output", default="output/selection.xlsx", help="Output Excel file.")
    run_parser.add_argument("--artifacts-dir", default="artifacts", help="Artifact output directory.")
    run_parser.add_argument("--rules", help="Natural language or JSON rule text file.")
    run_parser.add_argument("--rule-set-id", default=None)
    run_parser.add_argument("--provider", choices=["mock", "openai", "deepseek"], default="mock")
    run_parser.add_argument("--database", default=None)
    run_parser.add_argument("--overwrite", action="store_true")
    run_parser.add_argument("--limit", type=int, default=None)
    run_parser.add_argument("--batch-size", type=int, default=None)
    run_parser.add_argument("--dry-run", action="store_true")
    run_parser.add_argument("--use-default-rules", action="store_true", help="Use conservative placeholder rules.")
    run_parser.add_argument("--rule-set", help="Use a saved rule set name.")
    run_parser.add_argument("--rule-name", default="user_rules", help="Name for parsed user rules.")
    run_parser.add_argument("--save-rule-set", action="store_true", help="Save validated user rules as ACTIVE.")
    run_parser.add_argument(
        "--mark-production",
        action="store_true",
        help="Mark a saved user rule set as production_ready=true.",
    )
    run_parser.add_argument(
        "--classifier",
        choices=["mock", "openai", "deepseek"],
        default="mock",
        help="Semantic classifier backend.",
    )
    run_parser.set_defaults(handler=_handle_run)

    persist_parser = subparsers.add_parser(
        "persist-inspection",
        help="Persist an existing inspect artifact directory without rerunning Excel inspection.",
    )
    persist_parser.add_argument("--artifacts", required=True, help="Path to an inspect run artifact directory.")
    persist_parser.add_argument("--database", default=None, help="SQLite database URL or path.")
    persist_parser.set_defaults(handler=_handle_persist_inspection)

    show_parser = subparsers.add_parser("show-run", help="Show a persisted pipeline run summary.")
    show_parser.add_argument("--run-id", required=True, help="Pipeline run ID.")
    show_parser.add_argument("--database", default=None, help="SQLite database URL or path.")
    show_parser.set_defaults(handler=_handle_show_run)

    db_upgrade_parser = subparsers.add_parser("db-upgrade", help="Apply pending database migrations.")
    db_upgrade_parser.add_argument("--database", default=None, help="SQLite database URL or path.")
    db_upgrade_parser.add_argument("--revision", default="head", help="Target migration version (default: head).")
    db_upgrade_parser.set_defaults(handler=_handle_db_upgrade)

    db_current_parser = subparsers.add_parser("db-current", help="Show current database schema version.")
    db_current_parser.add_argument("--database", default=None, help="SQLite database URL or path.")
    db_current_parser.set_defaults(handler=_handle_db_current)

    db_downgrade_parser = subparsers.add_parser("db-downgrade", help="Downgrade the database schema.")
    db_downgrade_parser.add_argument("--database", default=None, help="SQLite database URL or path.")
    db_downgrade_parser.add_argument("--revision", required=True, help="Target version or 'base'.")
    db_downgrade_parser.set_defaults(handler=_handle_db_downgrade)

    classify_parser = subparsers.add_parser("classify", help="Classify persisted variables through an LLM client.")
    classify_parser.add_argument("--run-id", required=True, help="Pipeline run ID.")
    classify_parser.add_argument("--database", default=None, help="SQLite database URL or path.")
    classify_parser.add_argument(
        "--provider",
        choices=["mock", "openai", "deepseek"],
        default=None,
        help="LLM provider (default: LLM_PROVIDER env).",
    )
    classify_parser.add_argument("--model", default=None, help="Override the provider model.")
    classify_parser.add_argument("--limit", type=int, default=None, help="Limit selected variables.")
    classify_parser.add_argument("--batch-size", type=int, default=None, help="Variables per batch.")
    classify_parser.add_argument("--force-refresh", action="store_true", help="Ignore cache.")
    classify_parser.add_argument("--variable-id", action="append", default=None, help="Explicit variable IDs.")
    classify_parser.add_argument("--dry-run", action="store_true", help="Build inputs without network calls.")
    classify_parser.add_argument("--artifacts-dir", default="artifacts", help="Artifact output directory.")
    classify_parser.set_defaults(handler=_handle_classify)

    inspect_rules_parser = subparsers.add_parser("inspect-rules", help="Extract and inspect a rule source file without parsing or LLM calls.")
    inspect_rules_parser.add_argument("--rules", required=True)
    inspect_rules_parser.add_argument("--artifacts-dir", default="artifacts")
    inspect_rules_parser.set_defaults(handler=_handle_inspect_rules)

    validate_rules_parser = subparsers.add_parser(
        "validate-rules",
        help="Parse and validate a natural-language rule file.",
    )
    validate_rules_parser.add_argument("--rules", required=True, help="Path to a .txt or .md rule file.")
    validate_rules_parser.add_argument("--provider", choices=["mock", "openai", "deepseek"], default=None)
    validate_rules_parser.add_argument("--model", default=None)
    validate_rules_parser.add_argument("--database", default=None)
    validate_rules_parser.add_argument("--artifacts-dir", default="artifacts")
    validate_rules_parser.add_argument("--force-refresh", action="store_true")
    validate_rules_parser.add_argument("--dry-run", action="store_true")
    validate_rules_parser.add_argument("--name", default=None)
    validate_rules_parser.add_argument("--version", default="1")
    validate_rules_parser.set_defaults(handler=_handle_validate_rules)

    compile_rules_parser = subparsers.add_parser(
        "compile-rules",
        help="Parse, validate, compile, and persist a versioned rule set.",
    )
    compile_rules_parser.add_argument("--rules", required=True)
    compile_rules_parser.add_argument("--name", required=True)
    compile_rules_parser.add_argument("--version", required=True)
    compile_rules_parser.add_argument("--provider", choices=["mock", "openai", "deepseek"], default=None)
    compile_rules_parser.add_argument("--model", default=None)
    compile_rules_parser.add_argument("--database", default=None)
    compile_rules_parser.add_argument("--artifacts-dir", default="artifacts")
    compile_rules_parser.add_argument("--force-refresh", action="store_true")
    compile_rules_parser.add_argument("--dry-run", action="store_true")
    compile_rules_parser.add_argument("--activate", action="store_true")
    compile_rules_parser.set_defaults(handler=_handle_compile_rules)

    select_parser = subparsers.add_parser(
        "select",
        help="Execute a compiled rule set against classified variables.",
    )
    select_parser.add_argument("--run-id", required=True, help="Classification/inspection pipeline run ID.")
    select_parser.add_argument("--rule-set-id", default=None)
    select_parser.add_argument("--rule-set", default=None)
    select_parser.add_argument("--rule-version", default=None)
    select_parser.add_argument("--database", default=None)
    select_parser.add_argument("--artifacts-dir", default="artifacts")
    select_parser.add_argument("--dry-run", action="store_true")
    select_parser.add_argument("--resume", action="store_true")
    select_parser.add_argument("--allow-validated-rules", action="store_true")
    select_parser.add_argument("--include-review-candidates", action="store_true")
    select_parser.set_defaults(handler=_handle_select)

    show_selection_parser = subparsers.add_parser(
        "show-selection",
        help="Show a persisted selection run summary.",
    )
    show_selection_parser.add_argument("--selection-run-id", required=True)
    show_selection_parser.add_argument("--database", default=None)
    show_selection_parser.set_defaults(handler=_handle_show_selection)

    export_parser = subparsers.add_parser(
        "export",
        help="Export a selection run to a final Excel workbook.",
    )
    export_parser.add_argument("--selection-run-id", required=True)
    export_parser.add_argument("--output", default=None)
    export_parser.add_argument("--overwrite", action="store_true")
    export_parser.add_argument("--include-not-selected", action="store_true")
    export_parser.add_argument("--dry-run", action="store_true")
    export_parser.add_argument("--include-review-sheet", action="store_true")
    export_parser.add_argument("--include-rejected-sheet", action="store_true")
    export_parser.add_argument("--include-not-selected-sheet", action="store_true")
    export_parser.add_argument("--include-rule-summary", action="store_true")
    export_parser.add_argument("--database", default=None)
    export_parser.add_argument("--artifacts-dir", default="artifacts")
    export_parser.set_defaults(handler=_handle_export)

    export_selection_parser = subparsers.add_parser("export-selection", help="Export a selection run to Excel.")
    export_selection_parser.add_argument("--selection-run-id", required=True)
    export_selection_parser.add_argument("--output", default=None)
    export_selection_parser.add_argument("--overwrite", action="store_true")
    export_selection_parser.add_argument("--dry-run", action="store_true")
    export_selection_parser.add_argument("--include-review-sheet", action="store_true")
    export_selection_parser.add_argument("--include-rejected-sheet", action="store_true")
    export_selection_parser.add_argument("--include-not-selected", action="store_true")
    export_selection_parser.add_argument("--include-not-selected-sheet", action="store_true")
    export_selection_parser.add_argument("--include-rule-summary", action="store_true")
    export_selection_parser.add_argument("--database", default=None)
    export_selection_parser.add_argument("--artifacts-dir", default="artifacts")
    export_selection_parser.set_defaults(handler=_handle_export)

    pipeline_parser = subparsers.add_parser(
        "pipeline",
        help="Run the full inspection-classification-rules-selection-export workflow.",
    )
    pipeline_parser.add_argument("--input", required=True)
    pipeline_parser.add_argument("--rules", default=None)
    pipeline_parser.add_argument("--rule-set-id", default=None)
    pipeline_parser.add_argument("--use-default-rules", action="store_true")
    pipeline_parser.add_argument("--provider", choices=["mock", "openai", "deepseek"], default="mock")
    pipeline_parser.add_argument("--model", default=None)
    pipeline_parser.add_argument("--output", default=None)
    pipeline_parser.add_argument("--batch-size", type=int, default=None)
    pipeline_parser.add_argument("--limit", type=int, default=None)
    pipeline_parser.add_argument("--dry-run", action="store_true")
    pipeline_parser.add_argument("--force-refresh", action="store_true")
    pipeline_parser.add_argument("--overwrite", action="store_true")
    pipeline_parser.add_argument("--database", default=None)
    pipeline_parser.add_argument("--artifacts-dir", default="artifacts")
    pipeline_parser.set_defaults(handler=_handle_pipeline)

    dir_mark_parser = subparsers.add_parser(
        "directory-mark",
        help="Write selection results into the first (directory) sheet of the source Excel with a ' 是否选中' column.",
    )
    dir_mark_parser.add_argument("--input", required=True, help="Input Excel file.")
    dir_mark_parser.add_argument("--rules", default=None, help="Natural-language rule file (.txt, .docx).")
    dir_mark_parser.add_argument("--rule-set", default=None, help="Use a previously saved rule set name.")
    dir_mark_parser.add_argument("--rule-version", default="1")
    dir_mark_parser.add_argument("--provider", choices=["mock", "openai", "deepseek"], default="mock")
    dir_mark_parser.add_argument("--model", default=None)
    dir_mark_parser.add_argument("--output", default=None, help="Output path. Defaults to input stem + '_directory.xlsx'.")
    dir_mark_parser.add_argument("--batch-size", type=int, default=None)
    dir_mark_parser.add_argument("--limit", type=int, default=None)
    dir_mark_parser.add_argument("--database", default=None)
    dir_mark_parser.add_argument("--artifacts-dir", default="artifacts")
    dir_mark_parser.add_argument("--overwrite", action="store_true")
    dir_mark_parser.add_argument("--force-refresh", action="store_true")
    dir_mark_parser.set_defaults(handler=_handle_directory_mark)

    return parser


def _database_manager(database_url: str | None = None, migrate: bool = False) -> DatabaseManager:
    manager = DatabaseManager(DatabaseSettings.from_env(database_url=database_url))
    if migrate:
        MigrationRunner(manager.engine).upgrade()
    return manager


def _load_inspection_artifacts(artifacts_dir: Path) -> tuple[InspectionResult, RequestRecord]:
    def read_json(name: str) -> dict:
        path = artifacts_dir / name
        if not path.exists():
            raise FileNotFoundError(f"Missing artifact: {path}")
        return json.loads(path.read_text(encoding="utf-8"))

    request_record = RequestRecord.model_validate(read_json("request.json"))
    workbook_profile = WorkbookProfile.model_validate(read_json("workbook_profile.json"))
    variable_profiles = [
        VariableProfile.model_validate(item) for item in read_json("variable_profiles.json")
    ]
    data_quality_report = DataQualityReport.model_validate(read_json("data_quality_report.json"))
    needs_review = [
        VariableProfile.model_validate(item) for item in read_json("needs_review_variables.json")
    ]
    inspection_summary = InspectionSummary.model_validate(read_json("inspection_summary.json"))
    result = InspectionResult(
        workbook_profile=workbook_profile,
        variable_profiles=variable_profiles,
        data_quality_report=data_quality_report,
        needs_review_variables=needs_review,
        inspection_summary=inspection_summary,
    )
    return result, request_record


def _classifier(kind: str):
    if kind == "openai":
        return OpenAIVariableClassifier()
    if kind == "mock":
        return MockVariableClassifier()
    return None


def _handle_inspect(args: argparse.Namespace) -> int:
    run_id = _new_run_id()
    try:
        result = run_inspection(
            args.input,
            header_row=args.header_row,
            date_column=args.date_column,
            sheet=args.sheet,
            run_id=run_id,
        )
    except InspectionError as exc:
        print(f"Inspection failed: {exc}", file=sys.stderr)
        return 1
    manager = ArtifactManager(run_id, args.artifacts_dir)
    run_log = (
        f"Run ID: {run_id}\n"
        f"Input: {args.input}\n"
        f"Sheets: {len(result.workbook_profile.sheets)}\n"
        f"Variables: {len(result.variable_profiles)}\n"
        f"Status: COMPLETED\n"
    )
    request_record = RequestRecord(
        run_id=run_id,
        input_path=str(Path(args.input).resolve()),
        file_hash=result.workbook_profile.file_hash,
        cli_args={key: value for key, value in vars(args).items() if key != "handler"},
        started_at=result.workbook_profile.inspection_started_at,
        completed_at=result.workbook_profile.inspection_completed_at,
        software_version=__version__,
    )
    InspectionArtifactWriter().write(manager, result, run_log, request_record)

    print(f"Run ID: {run_id}")
    print(f"Sheets: {len(result.workbook_profile.sheets)}")
    print(f"Variables analyzed: {len(result.variable_profiles)}")
    print(f"Needs review: {len(result.needs_review_variables)}")
    print(f"Artifacts: {manager.directory}")

    if args.persist and not args.database:
        print("--persist requires --database.", file=sys.stderr)
        return 2
    if args.database:
        db_manager = None
        try:
            db_manager = _database_manager(args.database, migrate=True)
            summary = InspectionPersistenceService(db_manager).persist(
                result,
                request_record=request_record,
                artifacts_dir=manager.directory,
                run_id=run_id,
            )
            print(
                "Database: "
                f"run={run_id} status={summary.status} files={summary.file_count} "
                f"sheets={summary.sheet_count} variables={summary.variable_count} "
                f"quality={summary.quality_count} audit={summary.audit_event_count}"
            )
        except DatabaseError as exc:
            print(f"Persistence failed: {exc}", file=sys.stderr)
            return 1
        finally:
            if db_manager is not None:
                db_manager.close()
    return 0


def _handle_persist_inspection(args: argparse.Namespace) -> int:
    artifacts_dir = Path(args.artifacts)
    db_manager = None
    try:
        result, request_record = _load_inspection_artifacts(artifacts_dir)
        run_id = result.workbook_profile.run_id or request_record.run_id or artifacts_dir.name
        db_manager = _database_manager(args.database, migrate=True)
        summary = InspectionPersistenceService(db_manager).persist(
            result,
            request_record=request_record,
            artifacts_dir=artifacts_dir,
            run_id=run_id,
        )
    except (DatabaseError, FileNotFoundError, json.JSONDecodeError) as exc:
        print(f"Persistence failed: {exc}", file=sys.stderr)
        return 1
    finally:
        if db_manager is not None:
            db_manager.close()
    print(f"Run ID: {summary.run_id}")
    print(f"Status: {summary.status}")
    print(f"Files: {summary.file_count}")
    print(f"Sheets: {summary.sheet_count}")
    print(f"Variables: {summary.variable_count}")
    print(f"Quality records: {summary.quality_count}")
    print(f"Audit events: {summary.audit_event_count}")
    print(f"Artifacts: {artifacts_dir}")
    return 0


def _handle_show_run(args: argparse.Namespace) -> int:
    db_manager = None
    try:
        db_manager = _database_manager(args.database)
        summary = RunQueryService(db_manager).get_run_summary(args.run_id)
    except EntityNotFoundError as exc:
        print(f"Run not found: {exc}", file=sys.stderr)
        return 1
    finally:
        if db_manager is not None:
            db_manager.close()
    print(f"Run ID: {summary.run.run_id}")
    print(f"Status: {summary.run.status}")
    print(f"Files: {summary.file_count}")
    print(f"Sheets: {summary.sheet_count}")
    print(f"Variables: {summary.variable_count}")
    print(f"Quality records: {summary.quality_count}")
    print(f"Needs review: {summary.review_count}")
    print(f"Audit events: {summary.audit_event_count}")
    print(f"Artifacts: {summary.run.artifacts_path or '-'}")
    print(
        "DB records: "
        f"run=1 file={summary.file_count} source_file={summary.source_file_count} "
        f"sheet={summary.sheet_count} variable={summary.variable_count} "
        f"quality={summary.quality_count} audit={summary.audit_event_count}"
    )
    return 0


def _handle_db_upgrade(args: argparse.Namespace) -> int:
    db_manager = None
    try:
        db_manager = _database_manager(args.database)
        applied = MigrationRunner(db_manager.engine).upgrade(args.revision)
        print(f"Applied migrations: {', '.join(applied) if applied else 'none'}")
        print(f"Current version: {MigrationRunner(db_manager.engine).get_current_version() or 'base'}")
        return 0
    except DatabaseError as exc:
        print(f"Migration failed: {exc}", file=sys.stderr)
        return 1
    finally:
        if db_manager is not None:
            db_manager.close()


def _handle_db_current(args: argparse.Namespace) -> int:
    db_manager = _database_manager(args.database)
    try:
        version = MigrationRunner(db_manager.engine).get_current_version()
        print(f"Current version: {version or 'base'}")
    finally:
        db_manager.close()
    return 0


def _handle_db_downgrade(args: argparse.Namespace) -> int:
    db_manager = None
    try:
        db_manager = _database_manager(args.database)
        downgraded = MigrationRunner(db_manager.engine).downgrade(args.revision)
    except DatabaseError as exc:
        print(f"Migration failed: {exc}", file=sys.stderr)
        return 1
    finally:
        if db_manager is not None:
            db_manager.close()
    print(f"Downgraded migrations: {', '.join(downgraded) if downgraded else 'none'}")
    return 0


def _handle_classify(args: argparse.Namespace) -> int:
    settings = LLMSettings.from_env(
        provider=args.provider,
        model=args.model,
        batch_size=args.batch_size,
    )
    db_manager = None
    try:
        db_manager = _database_manager(args.database, migrate=True)
        service = BatchClassificationService(db_manager, settings=settings)
        result = service.classify_run(
            args.run_id,
            provider=args.provider,
            model=args.model,
            limit=args.limit,
            variable_ids=args.variable_id,
            batch_size=args.batch_size,
            force_refresh=args.force_refresh,
            dry_run=args.dry_run,
            artifacts_dir=args.artifacts_dir,
        )
    except (LLMError, DatabaseError) as exc:
        print(f"Classification failed: {exc}", file=sys.stderr)
        return 1
    finally:
        if db_manager is not None:
            db_manager.close()
    print(f"Run ID: {result.run_id}")
    print(f"Provider: {result.provider}")
    print(f"Model: {result.model}")
    print(f"Variables selected: {result.selected_variable_count}")
    print(f"Batch size: {args.batch_size or (settings.deepseek_batch_size if (args.provider or settings.llm_provider) == 'deepseek' else settings.openai_batch_size)}")
    print(f"Real API enabled: {str(settings.real_llm_enabled).lower()}")
    print(f"Dry run: {str(result.dry_run).lower()}")
    print(f"Successful: {result.successful_count}")
    print(f"Needs review: {result.needs_review_count}")
    print(f"Failed: {result.failed_count}")
    print(f"Cache hits: {result.cache_hit_count}")
    print(f"Input tokens: {result.input_tokens}")
    print(f"Output tokens: {result.output_tokens}")
    print(f"Total tokens: {result.total_tokens}")
    print(f"LLM calls: {result.total_llm_calls}")
    print(f"Artifacts: {result.artifacts_path}")
    return 0


def _handle_inspect_rules(args: argparse.Namespace) -> int:
    from pathlib import Path as _Path
    import json as _json
    try:
        loaded = load_rule_source(args.rules)
    except Exception as exc:
        print(f"Rule inspection failed: {exc}", file=sys.stderr)
        return 1
    run_id = f"rules_inspect_{uuid4().hex[:8]}"
    out_dir = _Path(args.artifacts_dir) / run_id / "rules"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "source_text.txt").write_text(loaded.text, encoding="utf-8")
    (out_dir / "source_structure.json").write_text(_json.dumps(loaded.structure, ensure_ascii=False, indent=2), encoding="utf-8")
    (out_dir / "source_metadata.json").write_text(_json.dumps(loaded.metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Paragraphs: {loaded.metadata['paragraph_count']}")
    print(f"Tables: {loaded.metadata['table_count']}")
    print(f"Extracted text length: {loaded.metadata['extracted_text_length']}")
    lines = [line for line in loaded.text.splitlines() if line.strip()][:10]
    print("First lines:")
    for line in lines:
        print(f"  {line}")
    print(f"Unsupported content: {loaded.metadata.get('unsupported_content', [])}")
    print(f"Artifacts: {out_dir}")
    return 0

def _handle_validate_rules(args: argparse.Namespace) -> int:
    settings = LLMSettings.from_env(provider=args.provider, model=args.model)
    db_manager = None
    try:
        db_manager = _database_manager(args.database, migrate=True)
        result = RuleParserService(db_manager, settings=settings).validate_rules(
            args.rules,
            provider=args.provider,
            model=args.model,
            force_refresh=args.force_refresh,
            dry_run=args.dry_run,
            rule_set_name=args.name,
            version=args.version,
            artifacts_dir=args.artifacts_dir,
        )
    except (RuleWorkflowError, LLMError, DatabaseError) as exc:
        print(f"Rule validation failed: {exc}", file=sys.stderr)
        return 1
    finally:
        if db_manager is not None:
            db_manager.close()
    print(f"Source hash: {result.summary.source_hash}")
    print(f"Rules parsed: {result.summary.rule_count}")
    print(f"Unresolved: {result.summary.unresolved_count}")
    print(f"Warnings: {result.summary.warning_count}")
    print(f"Conflicts: {result.summary.conflict_count}")
    print(f"Can compile: {str(result.summary.compile_successful).lower()}")
    print(f"Artifacts: {result.artifacts_path}")
    return 0


def _handle_compile_rules(args: argparse.Namespace) -> int:
    settings = LLMSettings.from_env(provider=args.provider, model=args.model)
    db_manager = None
    try:
        db_manager = _database_manager(args.database, migrate=True)
        result = RuleParserService(db_manager, settings=settings).compile_rules(
            args.rules,
            provider=args.provider,
            model=args.model,
            name=args.name,
            version=args.version,
            force_refresh=args.force_refresh,
            dry_run=args.dry_run,
            activate=args.activate,
            artifacts_dir=args.artifacts_dir,
        )
    except (RuleWorkflowError, LLMError, DatabaseError) as exc:
        print(f"Rule compilation failed: {exc}", file=sys.stderr)
        return 1
    finally:
        if db_manager is not None:
            db_manager.close()
    compiled = result.compiled
    print(f"Rule set: {args.name} v{args.version}")
    print(f"Source hash: {result.summary.source_hash}")
    print(f"Rules compiled: {result.summary.rule_count}")
    print(f"Compiled hash: {compiled.compiled_hash if compiled else '-'}")
    print(f"Status: {compiled.status if compiled else 'INVALID'}")
    print(f"Conflicts: {result.summary.conflict_count}")
    print(f"Dry run: {str(result.dry_run).lower()}")
    print(f"Artifacts: {result.artifacts_path}")
    return 0


def _handle_select(args: argparse.Namespace) -> int:
    db_manager = None
    try:
        db_manager = _database_manager(args.database, migrate=True)
        summary = VariableSelectionService(db_manager).select(
            args.run_id,
            rule_set_id=args.rule_set_id,
            rule_set_name=args.rule_set,
            rule_version=args.rule_version,
            dry_run=args.dry_run,
            resume=args.resume,
            allow_validated_rules=args.allow_validated_rules,
            include_review_candidates=args.include_review_candidates,
            artifacts_dir=args.artifacts_dir,
        )
    except (SelectionWorkflowError, DatabaseError) as exc:
        print(f"Selection failed: {exc}", file=sys.stderr)
        return 1
    finally:
        if db_manager is not None:
            db_manager.close()
    print(f"Selection run: {summary.selection_run_id}")
    print(f"Rule set: {summary.rule_set_name} v{summary.rule_set_version}")
    print(f"Total variables: {summary.total_variables}")
    print(f"SELECTED: {summary.selected_count}")
    print(f"REJECTED: {summary.rejected_count}")
    print(f"DUPLICATE: {summary.duplicate_count}")
    print(f"NEEDS_REVIEW: {summary.needs_review_count}")
    print(f"NOT_SELECTED: {summary.not_selected_count}")
    print(f"FAILED: {summary.failed_count}")
    print(f"Status: {summary.status}")
    print(f"Artifacts: {summary.artifacts_path}")
    return 0


def _handle_show_selection(args: argparse.Namespace) -> int:
    db_manager = None
    try:
        db_manager = _database_manager(args.database)
        summary = VariableSelectionService(db_manager).show_selection(args.selection_run_id)
    except (SelectionWorkflowError, DatabaseError) as exc:
        print(f"Show selection failed: {exc}", file=sys.stderr)
        return 1
    finally:
        if db_manager is not None:
            db_manager.close()
    print(f"Selection run: {summary.selection_run_id}")
    print(f"Rule set: {summary.rule_set_name} v{summary.rule_set_version}")
    print(f"Total variables: {summary.total_variables}")
    print(f"SELECTED: {summary.selected_count}")
    print(f"REJECTED: {summary.rejected_count}")
    print(f"DUPLICATE: {summary.duplicate_count}")
    print(f"NEEDS_REVIEW: {summary.needs_review_count}")
    print(f"NOT_SELECTED: {summary.not_selected_count}")
    print(f"Artifacts: {summary.artifacts_path}")
    return 0


def _handle_export(args: argparse.Namespace) -> int:
    db_manager = None
    try:
        db_manager = _database_manager(args.database, migrate=True)
        summary = SelectionExportService(db_manager).export(
            args.selection_run_id,
            output_path=args.output,
            overwrite=args.overwrite,
            dry_run=args.dry_run,
            include_not_selected=args.include_not_selected,
            include_rule_summary=args.include_rule_summary,
            artifacts_dir=args.artifacts_dir,
        )
    except (SelectionExportError, DatabaseError) as exc:
        print(f"Export failed: {exc}", file=sys.stderr)
        return 1
    finally:
        if db_manager is not None:
            db_manager.close()
    print(f"Export run: {summary.export_run_id}")
    print(f"Selection run: {summary.selection_run_id}")
    print(f"Status: {summary.status}")
    print(f"Output: {summary.output_path}")
    print(f"File hash: {summary.output_file_hash}")
    print(f"Selected variables: {summary.selected_variable_count}")
    print(f"Sheets: {', '.join(summary.sheet_names)}")
    print(f"Artifacts: {summary.artifacts_path}")
    return 0


def _handle_pipeline(args: argparse.Namespace) -> int:
    if not args.output:
        print("--output is required for pipeline runs.", file=sys.stderr)
        return 2
    db_manager = None
    try:
        db_manager = _database_manager(args.database, migrate=True)
        summary = FullPipelineOrchestrator(db_manager).run(
            args.input,
            rules_path=args.rules,
            rule_set_id=args.rule_set_id,
            use_default_rules=args.use_default_rules,
            provider=args.provider,
            model=args.model,
            output_path=args.output,
            batch_size=args.batch_size,
            limit=args.limit,
            dry_run=args.dry_run,
            force_refresh=args.force_refresh,
            overwrite=args.overwrite,
            artifacts_dir=args.artifacts_dir,
        )
    except (PipelineWorkflowError, DatabaseError) as exc:
        print(f"Pipeline failed: {exc}", file=sys.stderr)
        return 1
    finally:
        if db_manager is not None:
            db_manager.close()
    print(f"Pipeline run: {summary.pipeline_run_id}")
    print(f"Status: {summary.status}")
    print(f"Selection run: {summary.selection_run_id or '-'}")
    print(f"Export run: {summary.export_run_id or '-'}")
    print(f"Output: {summary.output_path or '-'}")
    print(f"File hash: {summary.output_file_hash or '-'}")
    print(f"Stages: {', '.join(f'{k}={v}' for k, v in summary.stages.items())}")
    return 0


def _resolve_rule_set(args: argparse.Namespace) -> RuleSet:
    mode_count = sum([bool(args.use_default_rules), bool(args.rules), bool(args.rule_set)])
    if mode_count != 1:
        raise ValueError("Exactly one of --use-default-rules, --rules, or --rule-set is required.")
    if args.use_default_rules:
        return build_default_rules()
    if args.rule_set:
        rule_set, _ = RuleStore().load_rule_set(args.rule_set)
        return rule_set
    parser = get_rule_parser()
    text = Path(args.rules).read_text(encoding="utf-8")
    parsed = parser.parse_rules(text, rule_set_name=args.rule_name)
    parsed.rule_set.status = RuleSetStatus.PARSED
    parsed.rule_set.metadata["parser"] = parser.name
    if parsed.warnings:
        parsed.rule_set.metadata["parser_warnings"] = parsed.warnings
    parsed.rule_set.rules_hash = hash_model(parsed.rule_set)
    return parsed.rule_set


def _handle_run(args: argparse.Namespace) -> int:
    use_pipeline = bool(getattr(args, "rule_set_id", None)) or bool(args.rules and Path(args.rules).suffix.lower() == ".docx")
    if use_pipeline:
        db_manager = _database_manager(args.database, migrate=True)
        try:
            summary = FullPipelineOrchestrator(db_manager).run(
                args.input,
                rule_set_id=args.rule_set_id,
                rules_path=args.rules if getattr(args, "rules", None) else None,
                provider=args.provider,
                model=None,
                output_path=args.output,
                limit=getattr(args, "limit", None),
                batch_size=getattr(args, "batch_size", None),
                dry_run=getattr(args, "dry_run", False),
                overwrite=args.overwrite,
                artifacts_dir=args.artifacts_dir,
            )
        finally:
            db_manager.close()
        print(f"Pipeline run: {summary.pipeline_run_id}")
        print(f"Selection run: {summary.selection_run_id}")
        print(f"Export run: {summary.export_run_id}")
        print(f"Output: {summary.output_path}")
        return 0
    run_id = _new_run_id()
    manager = ArtifactManager(run_id, args.artifacts_dir)
    inspection = run_inspection(args.input, classifier=_classifier(args.classifier), run_id=run_id)

    try:
        rule_set = _resolve_rule_set(args)
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2

    validator = RuleValidator()
    validation = validator.validate(rule_set)
    if not validation.valid:
        rule_set.status = RuleSetStatus.INVALID
        RuleStore().save_parsed(run_id, rule_set, args.artifacts_dir)
        manager.write_json("rule_validation_errors.json", validation.errors)
        print("Rule validation failed:", file=sys.stderr)
        for error in validation.errors:
            print(f"  - {error}", file=sys.stderr)
        return 1

    if rule_set.is_empty() and (args.rules or args.rule_set):
        print(
            "Empty rule set cannot be executed as a formal user rule set; "
            "use --use-default-rules for placeholder end-to-end validation.",
            file=sys.stderr,
        )
        return 2

    if args.rules:
        rule_set.status = RuleSetStatus.VALIDATED
        rule_set.rules_hash = hash_model(rule_set)

    saved_rule_set_path = None
    if args.save_rule_set:
        if not args.rules:
            print("--save-rule-set can only be used with --rules.", file=sys.stderr)
            return 2
        saved_rule_set_path, rule_set = RuleStore().save_versioned(
            rule_set, production_ready=args.mark_production
        )

    compiler = RuleCompiler(validator)
    try:
        compiled = compiler.compile(rule_set)
    except RuleValidationError as exc:
        rule_set.status = RuleSetStatus.INVALID
        manager.write_json("rule_validation_errors.json", [str(exc)])
        print(f"Rule compilation failed: {exc}", file=sys.stderr)
        return 1

    RuleStore().save_parsed(run_id, rule_set, args.artifacts_dir)
    RuleStore().save_compiled(run_id, compiled, args.artifacts_dir)

    engine = DeterministicRuleEngine()
    decisions = engine.execute(inspection.variable_profiles, compiled)
    result = build_selection_result(run_id, decisions, compiled, output_path=args.output)
    output_path = write_selection_workbook(args.input, inspection.workbook_profile, result, args.output)

    manager.write_model("workbook_profile.json", inspection.workbook_profile)
    manager.write_json("variable_profiles.json", [profile.model_dump(mode="json") for profile in decisions])
    manager.write_json(
        "variable_classification.json",
        [
            {
                "sheet_name": profile.sheet_name,
                "column_name": profile.column_name,
                "classification": profile.classification.model_dump(mode="json"),
            }
            for profile in decisions
        ],
    )
    manager.write_model("data_quality_report.json", inspection.data_quality_report)
    manager.write_json(
        "needs_review_variables.json",
        [profile.model_dump(mode="json") for profile in result.review_variables],
    )
    manager.write_model("selection_report.json", result.audit)

    print(f"Run ID: {run_id}")
    print(f"Variables analyzed: {len(decisions)}")
    print(f"Selected: {len(result.selected_variables)}")
    print(f"Rejected: {len(result.rejected_variables)}")
    print(f"Needs review: {len(result.review_variables)}")
    print(f"Rule source: {compiled.source.value}")
    print(f"Production ready: {compiled.production_ready}")
    print(f"Output: {output_path}")
    if saved_rule_set_path:
        print(f"Saved rule set: {saved_rule_set_path}")
    print(f"Artifacts: {manager.directory}")
    return 0


def _handle_directory_mark(args: argparse.Namespace) -> int:
    from financial_variable_curation.database.repositories import (
        VariableClassificationRepository,
        VariableQualityRepository,
        VariableRepository,
        SourceSheetRepository,
    )
    rules_path = args.rules
    rule_set_name = args.rule_set
    if not rules_path and not rule_set_name:
        print("Either --rules or --rule-set is required.", file=sys.stderr)
        return 2
    output = Path(args.output or f"{Path(args.input).stem}_directory.xlsx")

    db_manager = None
    try:
        db_manager = _database_manager(args.database, migrate=True)
        inspection = run_inspection(args.input, run_id=_new_run_id())
        # Exclude the first sheet (the directory itself) from selection.
        _first_sheet = (inspection.workbook_profile.sheet_names or [None])[0]
        if _first_sheet and inspection.workbook_profile.sheet_count > 1:
            inspection.variable_profiles = [
                p for p in inspection.variable_profiles
                if p.sheet_name != _first_sheet
            ]
            inspection.needs_review_variables = [
                p for p in inspection.needs_review_variables
                if p.sheet_name != _first_sheet
            ]
        InspectionPersistenceService(db_manager).persist(
            inspection, artifacts_dir=Path(args.artifacts_dir), run_id=inspection.workbook_profile.run_id,
        )
        run_id = inspection.workbook_profile.run_id

        settings = LLMSettings.from_env(provider=args.provider, model=args.model, batch_size=args.batch_size)

        print(f"Classifying {len(inspection.variable_profiles)} variables with provider={args.provider}...")
        concurrency = (
            settings.deepseek_max_concurrency if args.provider == "deepseek"
            else settings.openai_max_concurrency
        )
        if args.provider == "mock" or concurrency <= 1:
            classification = BatchClassificationService(db_manager, settings=settings).classify_run(
                run_id, provider=args.provider, model=args.model, limit=args.limit,
                batch_size=args.batch_size, force_refresh=args.force_refresh,
                artifacts_dir=args.artifacts_dir,
            )
        else:
            # Partition variables across concurrent classify_run calls
            all_var_ids = [v.variable_id for v in inspection.variable_profiles]
            chunk_size = max(1, len(all_var_ids) // concurrency)
            chunks: list[list[str]] = [
                all_var_ids[i : i + chunk_size]
                for i in range(0, len(all_var_ids), chunk_size)
            ]
            import time, json as _json
            _results = []
            _lock = threading.Lock()
            def _classify_chunk(var_ids, idx):
                svc = BatchClassificationService(db_manager, settings=settings)
                try:
                    return svc.classify_run(
                        run_id, provider=args.provider, model=args.model,
                        variable_ids=var_ids,
                        batch_size=args.batch_size, force_refresh=args.force_refresh,
                        artifacts_dir=args.artifacts_dir,
                    )
                except Exception as exc:
                    with _lock:
                        print(f"  Chunk {idx} failed: {exc}", file=sys.stderr)
                    return None
            with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as executor:
                futures = {executor.submit(_classify_chunk, chunk, i): i for i, chunk in enumerate(chunks)}
                for future in concurrent.futures.as_completed(futures):
                    result = future.result()
                    if result is not None:
                        _results.append(result)
            # Merge results
            classification = ClassificationRunResult(
                run_id=run_id, provider=args.provider, model="merged",
                prompt_version="merged", taxonomy_version="merged",
                schema_version="merged",
                selected_variable_count=sum(r.selected_variable_count for r in _results),
                batch_count=sum(r.batch_count for r in _results),
                successful_count=sum(r.successful_count for r in _results),
                needs_review_count=sum(r.needs_review_count for r in _results),
                failed_count=sum(r.failed_count for r in _results),
                cache_hit_count=sum(r.cache_hit_count for r in _results),
                input_tokens=sum(r.input_tokens for r in _results),
                output_tokens=sum(r.output_tokens for r in _results),
                total_tokens=sum(r.total_tokens for r in _results),
                total_llm_calls=sum(r.total_llm_calls for r in _results),
                errors=[e for r in _results for e in r.errors],
            )
        print(f"  Successful: {classification.successful_count}, Needs review: {classification.needs_review_count}, Failed: {classification.failed_count}")

        if rules_path:
            print(f"Compiling rules from {rules_path}...")
            loaded = load_rule_source(rules_path)
            source_hash = loaded.metadata.get("source_file_hash") or loaded.metadata.get("source_hash")
            name = f"{Path(rules_path).stem}_{str(source_hash or '')[:8]}"
            existing_rule_set = None
            if source_hash:
                from financial_variable_curation.database.repositories import RuleSetRepository
                with db_manager.session_scope() as session:
                    existing_rule_set = RuleSetRepository(session).get_by_name_version(
                        name, args.rule_version
                    )
                    if existing_rule_set and existing_rule_set.source_hash != source_hash:
                        existing_rule_set = None
            if existing_rule_set is not None:
                rule_set_id = existing_rule_set.rule_set_id
                print(f"  Reusing existing rule set {name} v{args.rule_version}")
            else:
                rule_result = RuleParserService(db_manager, settings=settings).compile_rules(
                    rules_path, provider=args.provider, model=args.model,
                    name=name, version=args.rule_version,
                    force_refresh=args.force_refresh, artifacts_dir=args.artifacts_dir,
                )
                rule_set_id = rule_result.compiled.compiled_rule_set_id if rule_result.compiled else None
                if not rule_set_id:
                    print("Rule compilation did not produce a rule set.", file=sys.stderr)
                    return 1
        else:
            rule_set_id = None

        print("Running selection...")
        selection = VariableSelectionService(db_manager).select(
            run_id, rule_set_id=rule_set_id, rule_set_name=rule_set_name if not rules_path else None,
            rule_version=args.rule_version, allow_validated_rules=True,
            include_review_candidates=True, artifacts_dir=args.artifacts_dir,
        )
        print(f"  Selected: {selection.selected_count}, Rejected: {selection.rejected_count}, Review: {selection.needs_review_count}, Failed: {selection.failed_count}")

        print("Writing directory sheet...")
        with db_manager.session_scope() as session:
            var_rows = VariableRepository(session).list_by_run_id(run_id)
            classifications = {item.variable_id: item for item in VariableClassificationRepository(session).list_for_run(run_id)}
            qualities_by_id = {item.variable_id: item for item in VariableQualityRepository(session).list_by_run_id(run_id)}
            from financial_variable_curation.database.repositories import SelectionResultRepository, SourceSheetRepository
            sel_results = {item.variable_id: item for item in SelectionResultRepository(session).list_for_run(selection.selection_run_id)}
            # Get all distinct sheet_ids from variables, then load sheets
            sheet_ids = list({v.sheet_id for v in var_rows})
            from sqlalchemy import select
            from financial_variable_curation.database.models import SourceSheet as SourceSheetModel
            all_sheets = session.scalars(select(SourceSheetModel).where(SourceSheetModel.sheet_id.in_(sheet_ids))).all()
            sheet_names = {s.sheet_id: s.sheet_name for s in all_sheets}

        directory_rows = []
        for var in var_rows:
            cls = classifications.get(var.variable_id)
            sel = sel_results.get(var.variable_id)
            quality = qualities_by_id.get(var.variable_id)
            directory_rows.append({
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
            })
        directory_rows.sort(key=lambda r: (r.get("sheet_name", ""), r.get("original_name", "")))

        output = update_directory_sheet(args.input, output, directory_rows)
        requested = Path(args.output or f"{Path(args.input).stem}_directory.xlsx")
        if output.resolve() != requested.resolve():
            print(
                f"Target file is locked, wrote to fallback path instead: {output}",
                file=sys.stderr,
            )
        print(f"Directory sheet written: {output.resolve()}")

    except (LLMError, DatabaseError, RuleWorkflowError, SelectionWorkflowError, InspectionError) as exc:
        print(f"Directory mark failed: {exc}", file=sys.stderr)
        return 1
    finally:
        if db_manager is not None:
            db_manager.close()
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    return args.handler(args)


app = main


if __name__ == "__main__":
    raise SystemExit(app())
import concurrent.futures
