"""SQLite-backed memory store with session + long-term scopes."""

from __future__ import annotations

import json
import sqlite3
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator


@dataclass
class MemoryEntry:
    agent: str
    scope: str
    key: str
    value: Any
    updated_at: float


class MemoryStore:
    """Persist small KV memories for each agent.

    - ``session`` scope: kept in a per-run table, wiped on ``close_session``.
    - ``long_term`` scope: persisted across runs.
    """

    def __init__(self, path: str | Path = ":memory:") -> None:
        self._path = str(path)
        self._conn = sqlite3.connect(self._path)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._create_schema()

    def _create_schema(self) -> None:
        with self._tx() as c:
            c.execute(
                """
                CREATE TABLE IF NOT EXISTS memory (
                    agent TEXT NOT NULL,
                    scope TEXT NOT NULL,
                    key   TEXT NOT NULL,
                    value TEXT NOT NULL,
                    updated_at REAL NOT NULL,
                    PRIMARY KEY (agent, scope, key)
                )
                """
            )

    @contextmanager
    def _tx(self) -> Iterator[sqlite3.Cursor]:
        cursor = self._conn.cursor()
        try:
            yield cursor
            self._conn.commit()
        except Exception:
            self._conn.rollback()
            raise
        finally:
            cursor.close()

    def save(self, agent: str, scope: str, key: str, value: Any) -> None:
        if scope not in {"session", "long_term"}:
            raise ValueError(f"invalid memory scope {scope!r}")
        payload = json.dumps(value, default=str)
        with self._tx() as c:
            c.execute(
                """
                INSERT INTO memory(agent, scope, key, value, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(agent, scope, key)
                DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at
                """,
                (agent, scope, key, payload, time.time()),
            )

    def recall(self, agent: str, scope: str, key: str) -> Any:
        with self._tx() as c:
            c.execute(
                "SELECT value FROM memory WHERE agent=? AND scope=? AND key=?",
                (agent, scope, key),
            )
            row = c.fetchone()
        if row is None:
            return None
        return json.loads(row["value"])

    def list_entries(self, agent: str, scope: str | None = None) -> list[MemoryEntry]:
        query = "SELECT * FROM memory WHERE agent=?"
        params: list[Any] = [agent]
        if scope is not None:
            query += " AND scope=?"
            params.append(scope)
        with self._tx() as c:
            c.execute(query, params)
            rows = c.fetchall()
        return [
            MemoryEntry(
                agent=r["agent"],
                scope=r["scope"],
                key=r["key"],
                value=json.loads(r["value"]),
                updated_at=r["updated_at"],
            )
            for r in rows
        ]

    def close_session(self, agent: str) -> None:
        with self._tx() as c:
            c.execute(
                "DELETE FROM memory WHERE agent=? AND scope='session'", (agent,)
            )

    def close(self) -> None:
        self._conn.close()
