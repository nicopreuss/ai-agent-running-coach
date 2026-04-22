"""Database client: loads connection config from the environment and exposes get_connection()."""

import os

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.engine import Connection, Engine

load_dotenv()

_engine: Engine | None = None


def _get_engine() -> Engine:
    """Return a singleton SQLAlchemy engine, creating it on first call."""
    global _engine
    if _engine is None:
        database_url = os.environ["DATABASE_URL"]
        _engine = create_engine(database_url, pool_pre_ping=True)
    return _engine


def get_connection() -> Connection:
    """Return an open SQLAlchemy connection from the connection pool.

    Usage::

        with get_connection() as conn:
            result = conn.execute(text("SELECT 1"))
    """
    return _get_engine().connect()
