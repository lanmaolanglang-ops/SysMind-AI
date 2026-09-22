from __future__ import annotations

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import NullPool

# SQLite in WAL mode still permits only a single writer at a time. Without a busy
# timeout a second writer fails immediately with "database is locked"; with it the
# connection waits up to the timeout for the lock to clear.
BUSY_TIMEOUT_MS = 5000


def create_database_engine(database_url: str) -> Engine:
    engine = create_engine(database_url, future=True, poolclass=NullPool)

    @event.listens_for(engine, "connect")
    def configure_sqlite(dbapi_connection: object, _connection_record: object) -> None:
        cursor = dbapi_connection.cursor()  # type: ignore[attr-defined]
        try:
            cursor.execute("PRAGMA foreign_keys=ON")
            # journal_mode is a persistent, database-level property, so setting it on
            # every connection is redundant rather than harmful; it is kept here to make
            # the connection contract self-describing.
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute(f"PRAGMA busy_timeout={BUSY_TIMEOUT_MS}")
        finally:
            cursor.close()

    return engine


def create_session_factory(database_url: str) -> sessionmaker[Session]:
    return sessionmaker(
        bind=create_database_engine(database_url),
        class_=Session,
        expire_on_commit=False,
    )
