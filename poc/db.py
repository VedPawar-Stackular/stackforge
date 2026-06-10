"""
PostgreSQL connection helpers using pg8000 (pure Python — no pg_config needed).

pg8000 cursors do not support the context manager protocol, so we use them
directly (create, use, close). The DB context manager opens a fresh connection
per use and commits or rolls back on exit.
"""

import ssl
from urllib.parse import urlparse

import pg8000.dbapi

from config import DATABASE_URL


def _conn_kwargs() -> dict:
    """Parse DATABASE_URL into pg8000.dbapi.connect() kwargs."""
    p = urlparse(DATABASE_URL)
    kwargs = {
        "host": p.hostname or "localhost",
        "port": p.port or 5432,
        "user": p.username or "postgres",
        "password": p.password or "",
        "database": p.path.lstrip("/"),
    }
    # Neon and other hosted providers require SSL.
    # server_hostname is passed explicitly to fix pg8000 SNI on some platforms.
    # Cert verification is intentionally left enabled (no CERT_NONE) to prevent MITM.
    if "sslmode=require" in DATABASE_URL:
        ctx = ssl.create_default_context()
        kwargs["ssl_context"] = ctx
        kwargs["server_hostname"] = kwargs["host"]
    return kwargs


class DB:
    """Context manager: opens a connection, commits on clean exit, rolls back on error."""

    def __enter__(self):
        self.conn = pg8000.dbapi.connect(**_conn_kwargs())
        self.conn.autocommit = False
        return self

    def __exit__(self, exc_type, *_):
        if exc_type:
            self.conn.rollback()
        else:
            self.conn.commit()
        self.conn.close()

    # ── Query helpers ─────────────────────────────────────────────────────────

    def _to_dicts(self, cur) -> list[dict]:
        if cur.description is None:
            return []
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]

    def fetch_one(self, sql: str, params=None) -> dict | None:
        cur = self.conn.cursor()
        cur.execute(sql, params or ())
        rows = self._to_dicts(cur)
        cur.close()
        return rows[0] if rows else None

    def fetch_all(self, sql: str, params=None) -> list[dict]:
        cur = self.conn.cursor()
        cur.execute(sql, params or ())
        result = self._to_dicts(cur)
        cur.close()
        return result

    def execute(self, sql: str, params=None) -> None:
        cur = self.conn.cursor()
        cur.execute(sql, params or ())
        cur.close()

    def execute_many(self, sql: str, rows: list) -> None:
        cur = self.conn.cursor()
        for row in rows:
            cur.execute(sql, row)
        cur.close()
