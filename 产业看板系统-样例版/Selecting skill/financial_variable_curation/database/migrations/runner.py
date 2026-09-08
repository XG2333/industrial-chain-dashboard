from __future__ import annotations

import importlib
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import Connection, Engine, text

from financial_variable_curation.database.exceptions import MigrationError


@dataclass(frozen=True)
class Migration:
    version: str
    name: str
    module: object


def _load_migrations() -> list[Migration]:
    migrations = [
        Migration(
            version="0001",
            name="initial_schema",
            module=importlib.import_module(
                "financial_variable_curation.database.migrations.versions.0001_initial_schema"
            ),
        ),
        Migration(
            version="0002",
            name="classification_columns",
            module=importlib.import_module(
                "financial_variable_curation.database.migrations.versions.0002_classification_columns"
            ),
        ),
        Migration(
            version="0003",
            name="rule_workflow_tables",
            module=importlib.import_module(
                "financial_variable_curation.database.migrations.versions.0003_rule_workflow_tables"
            ),
        ),
        Migration(
            version="0004",
            name="selection_execution_fields",
            module=importlib.import_module(
                "financial_variable_curation.database.migrations.versions.0004_selection_execution_fields"
            ),
        ),
        Migration(
            version="0005",
            name="export_tables",
            module=importlib.import_module(
                "financial_variable_curation.database.migrations.versions.0005_export_tables"
            ),
        ),
        Migration(
            version="0006",
            name="source_sheet_metadata_rows",
            module=importlib.import_module(
                "financial_variable_curation.database.migrations.versions.0006_source_sheet_metadata_rows"
            ),
        ),
    ]
    return sorted(migrations, key=lambda item: item.version)


class MigrationRunner:
    MIGRATION_TABLE = "schema_migrations"

    def __init__(self, engine: Engine) -> None:
        self.engine = engine
        self.migrations = _load_migrations()

    def _ensure_migration_table(self, connection: Connection) -> None:
        connection.execute(
            text(
                "CREATE TABLE IF NOT EXISTS schema_migrations ("
                " version VARCHAR(40) PRIMARY KEY,"
                " name VARCHAR(120) NOT NULL,"
                " applied_at DATETIME NOT NULL"
                ")"
            )
        )

    def get_current_version(self) -> str | None:
        with self.engine.connect() as connection:
            self._ensure_migration_table(connection)
            result = connection.execute(
                text("SELECT version FROM schema_migrations ORDER BY version DESC LIMIT 1")
            ).scalar()
            return str(result) if result is not None else None

    def get_applied_versions(self) -> set[str]:
        with self.engine.connect() as connection:
            self._ensure_migration_table(connection)
            rows = connection.execute(text("SELECT version FROM schema_migrations")).scalars().all()
            return {str(row) for row in rows}

    def upgrade(self, target_version: str = "head") -> list[str]:
        with self.engine.begin() as connection:
            self._ensure_migration_table(connection)
            applied = self._read_applied(connection)
            pending = [migration for migration in self.migrations if migration.version not in applied]
            if target_version != "head":
                pending = [migration for migration in pending if migration.version <= target_version]
            applied_versions: list[str] = []
            for migration in pending:
                try:
                    migration.module.upgrade(connection)
                    connection.execute(
                        text(
                            "INSERT INTO schema_migrations (version, name, applied_at) "
                            "VALUES (:version, :name, :applied_at)"
                        ),
                        {
                            "version": migration.version,
                            "name": migration.name,
                            "applied_at": datetime.now(timezone.utc),
                        },
                    )
                except Exception as exc:
                    raise MigrationError(
                        f"Migration {migration.version} ({migration.name}) failed: {exc}"
                    ) from exc
                applied_versions.append(migration.version)
            return applied_versions

    def downgrade(self, target_version: str = "base") -> list[str]:
        with self.engine.begin() as connection:
            self._ensure_migration_table(connection)
            applied = self._read_applied(connection)
            to_downgrade = [
                migration
                for migration in reversed(self.migrations)
                if migration.version in applied
                and (target_version == "base" or migration.version > target_version)
            ]
            downgraded_versions: list[str] = []
            for migration in to_downgrade:
                try:
                    migration.module.downgrade(connection)
                    connection.execute(
                        text("DELETE FROM schema_migrations WHERE version = :version"),
                        {"version": migration.version},
                    )
                except Exception as exc:
                    raise MigrationError(
                        f"Migration downgrade {migration.version} ({migration.name}) failed: {exc}"
                    ) from exc
                downgraded_versions.append(migration.version)
            return downgraded_versions

    def _read_applied(self, connection: Connection) -> set[str]:
        rows = connection.execute(text("SELECT version FROM schema_migrations")).scalars().all()
        return {str(row) for row in rows}
