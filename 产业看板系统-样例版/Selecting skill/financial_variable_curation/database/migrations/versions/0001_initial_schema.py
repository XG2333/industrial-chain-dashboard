from __future__ import annotations

from sqlalchemy import Connection

from financial_variable_curation.database.base import Base
import financial_variable_curation.database.models  # noqa: F401


def upgrade(connection: Connection) -> None:
    Base.metadata.create_all(bind=connection)


def downgrade(connection: Connection) -> None:
    Base.metadata.drop_all(bind=connection)
