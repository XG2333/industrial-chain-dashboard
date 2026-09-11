from __future__ import annotations

from sqlalchemy.orm import Session


class UnitOfWork:
    """Small explicit transaction handle used by persistence services."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def commit(self) -> None:
        self.session.commit()

    def rollback(self) -> None:
        self.session.rollback()
