from __future__ import annotations

from sqlalchemy import Engine, create_engine, event, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker


class Base(DeclarativeBase):
    pass


def make_engine(db_url: str) -> Engine:
    """Create a SQLAlchemy engine configured for SQLite WAL mode and FK enforcement."""
    engine = create_engine(db_url, connect_args={"check_same_thread": False})

    if db_url.startswith("sqlite"):

        @event.listens_for(engine, "connect")
        def _set_sqlite_pragmas(dbapi_conn, _record):
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA journal_mode=WAL")
            cur.execute("PRAGMA foreign_keys=ON")
            cur.close()

    return engine


def migrate(engine: Engine) -> None:
    """Apply additive schema migrations, safe to call on every startup."""
    with engine.connect() as conn:
        existing = {
            row[1]
            for row in conn.execute(text("PRAGMA table_info(quizzes)"))
        }
        if "engine" not in existing:
            conn.execute(
                text("ALTER TABLE quizzes ADD COLUMN engine TEXT NOT NULL DEFAULT 'new'")
            )
        if "resource_id" not in existing:
            conn.execute(
                text("ALTER TABLE quizzes ADD COLUMN resource_id INTEGER NOT NULL DEFAULT 0")
            )
            # Backfill: for New Quizzes resource_id == assignment_id
            conn.execute(
                text(
                    "UPDATE quizzes SET resource_id = assignment_id"
                    " WHERE resource_id = 0 AND engine = 'new'"
                )
            )

        sched_cols = {
            row[1]
            for row in conn.execute(text("PRAGMA table_info(schedules)"))
        }
        if "group_id" not in sched_cols:
            conn.execute(text("ALTER TABLE schedules ADD COLUMN group_id TEXT"))
            # Each pre-existing schedule becomes its own solo group
            conn.execute(
                text("UPDATE schedules SET group_id = CAST(id AS TEXT) || '-solo'")
            )
            # Clear old per-quiz APScheduler jobs so they're re-registered as
            # group-keyed jobs when the scheduler starts.
            try:
                conn.execute(text("DELETE FROM apscheduler_jobs"))
            except Exception:
                pass  # table may not exist on fresh install

        conn.commit()


def make_session_factory(engine: Engine) -> sessionmaker:
    return sessionmaker(engine, expire_on_commit=False)
