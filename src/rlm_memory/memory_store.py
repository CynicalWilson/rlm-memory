"""Memory storage layer with SQLite backend."""

import json
import os
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import AsyncIterator
import aiosqlite

from rlm_memory.types import (
    EntryType,
    Importance,
    MemoryEntry,
    MemoryStats,
    SessionInfo,
    TimeRange,
)


class MemoryStore:
    """SQLite-backed storage for conversation memory entries.

    Provides both synchronous and asynchronous APIs for storing and retrieving
    memory entries, with support for session management and various query patterns.
    """

    SCHEMA = """
    CREATE TABLE IF NOT EXISTS entries (
        id TEXT PRIMARY KEY,
        session_id TEXT NOT NULL,
        timestamp TEXT NOT NULL,
        entry_type TEXT NOT NULL,
        content TEXT NOT NULL,
        metadata TEXT DEFAULT '{}',
        embedding TEXT DEFAULT NULL,
        importance TEXT DEFAULT 'medium',
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    );

    CREATE INDEX IF NOT EXISTS idx_entries_session ON entries(session_id);
    CREATE INDEX IF NOT EXISTS idx_entries_timestamp ON entries(timestamp DESC);
    CREATE INDEX IF NOT EXISTS idx_entries_type ON entries(entry_type);
    CREATE INDEX IF NOT EXISTS idx_entries_importance ON entries(importance);

    CREATE TABLE IF NOT EXISTS sessions (
        session_id TEXT PRIMARY KEY,
        started_at TEXT NOT NULL,
        last_activity TEXT NOT NULL,
        metadata TEXT DEFAULT '{}'
    );

    CREATE TABLE IF NOT EXISTS large_content (
        entry_id TEXT PRIMARY KEY,
        content TEXT NOT NULL,
        FOREIGN KEY (entry_id) REFERENCES entries(id) ON DELETE CASCADE
    );
    """

    def __init__(self, storage_dir: str | Path | None = None):
        """Initialize the memory store.

        Args:
            storage_dir: Directory to store the SQLite database. Defaults to
                        RLM_STORAGE_DIR env var or .rlm-memory in current directory.
        """
        if storage_dir is None:
            storage_dir = os.environ.get("RLM_STORAGE_DIR", ".rlm-memory")

        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = self.storage_dir / "memory.db"
        self._initialized = False

    def _get_connection(self) -> sqlite3.Connection:
        """Get a synchronous database connection."""
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    async def _get_async_connection(self) -> aiosqlite.Connection:
        """Get an asynchronous database connection."""
        conn = await aiosqlite.connect(str(self.db_path))
        conn.row_factory = aiosqlite.Row
        return conn

    def initialize(self) -> None:
        """Initialize the database schema synchronously."""
        if self._initialized:
            return
        with self._get_connection() as conn:
            conn.executescript(self.SCHEMA)
            conn.commit()
        self._initialized = True

    async def initialize_async(self) -> None:
        """Initialize the database schema asynchronously."""
        if self._initialized:
            return
        async with await self._get_async_connection() as conn:
            await conn.executescript(self.SCHEMA)
            await conn.commit()
        self._initialized = True

    def _row_to_entry(self, row: sqlite3.Row) -> MemoryEntry:
        """Convert a database row to a MemoryEntry."""
        return MemoryEntry(
            id=row["id"],
            session_id=row["session_id"],
            timestamp=datetime.fromisoformat(row["timestamp"]),
            entry_type=row["entry_type"],
            content=row["content"],
            metadata=json.loads(row["metadata"]) if row["metadata"] else {},
            embedding=json.loads(row["embedding"]) if row["embedding"] else None,
            importance=row["importance"],
        )

    # -------------------------------------------------------------------------
    # Entry Operations
    # -------------------------------------------------------------------------

    def add_entry(self, entry: MemoryEntry) -> str:
        """Add a memory entry to the store.

        Args:
            entry: The memory entry to add.

        Returns:
            The ID of the added entry.
        """
        self.initialize()

        # Handle large content (>10KB) separately
        content = entry.content
        is_large = len(content) > 10240

        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO entries (id, session_id, timestamp, entry_type, content, metadata, embedding, importance)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    entry.id,
                    entry.session_id,
                    entry.timestamp.isoformat(),
                    entry.entry_type,
                    content[:1000] + "..." if is_large else content,
                    json.dumps(entry.metadata),
                    json.dumps(entry.embedding) if entry.embedding else None,
                    entry.importance,
                ),
            )

            if is_large:
                conn.execute(
                    "INSERT INTO large_content (entry_id, content) VALUES (?, ?)",
                    (entry.id, content),
                )

            # Update session last activity
            conn.execute(
                """
                INSERT INTO sessions (session_id, started_at, last_activity, metadata)
                VALUES (?, ?, ?, '{}')
                ON CONFLICT(session_id) DO UPDATE SET last_activity = excluded.last_activity
                """,
                (entry.session_id, entry.timestamp.isoformat(), entry.timestamp.isoformat()),
            )

            conn.commit()

        return entry.id

    async def add_entry_async(self, entry: MemoryEntry) -> str:
        """Add a memory entry asynchronously."""
        await self.initialize_async()

        content = entry.content
        is_large = len(content) > 10240

        async with await self._get_async_connection() as conn:
            await conn.execute(
                """
                INSERT INTO entries (id, session_id, timestamp, entry_type, content, metadata, embedding, importance)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    entry.id,
                    entry.session_id,
                    entry.timestamp.isoformat(),
                    entry.entry_type,
                    content[:1000] + "..." if is_large else content,
                    json.dumps(entry.metadata),
                    json.dumps(entry.embedding) if entry.embedding else None,
                    entry.importance,
                ),
            )

            if is_large:
                await conn.execute(
                    "INSERT INTO large_content (entry_id, content) VALUES (?, ?)",
                    (entry.id, content),
                )

            await conn.execute(
                """
                INSERT INTO sessions (session_id, started_at, last_activity, metadata)
                VALUES (?, ?, ?, '{}')
                ON CONFLICT(session_id) DO UPDATE SET last_activity = excluded.last_activity
                """,
                (entry.session_id, entry.timestamp.isoformat(), entry.timestamp.isoformat()),
            )

            await conn.commit()

        return entry.id

    def get_entry(self, entry_id: str, full_content: bool = False) -> MemoryEntry | None:
        """Get a single entry by ID.

        Args:
            entry_id: The ID of the entry to retrieve.
            full_content: If True, retrieve full content for large entries.

        Returns:
            The memory entry, or None if not found.
        """
        self.initialize()

        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM entries WHERE id = ?", (entry_id,)
            ).fetchone()

            if not row:
                return None

            entry = self._row_to_entry(row)

            if full_content and entry.content.endswith("..."):
                large_row = conn.execute(
                    "SELECT content FROM large_content WHERE entry_id = ?", (entry_id,)
                ).fetchone()
                if large_row:
                    entry.content = large_row["content"]

            return entry

    def get_entries(
        self,
        session_id: str | None = None,
        entry_types: list[EntryType] | None = None,
        importance: list[Importance] | None = None,
        time_range: TimeRange = "all",
        limit: int = 100,
        offset: int = 0,
    ) -> list[MemoryEntry]:
        """Get entries matching the specified criteria.

        Args:
            session_id: Filter by session ID.
            entry_types: Filter by entry types.
            importance: Filter by importance levels.
            time_range: Filter by time range.
            limit: Maximum number of entries to return.
            offset: Number of entries to skip.

        Returns:
            List of matching memory entries.
        """
        self.initialize()

        conditions = []
        params: list = []

        if session_id:
            conditions.append("session_id = ?")
            params.append(session_id)

        if entry_types:
            placeholders = ",".join("?" * len(entry_types))
            conditions.append(f"entry_type IN ({placeholders})")
            params.extend(entry_types)

        if importance:
            placeholders = ",".join("?" * len(importance))
            conditions.append(f"importance IN ({placeholders})")
            params.extend(importance)

        if time_range != "all":
            now = datetime.now()
            if time_range == "recent":
                cutoff = now - timedelta(hours=1)
            elif time_range == "today":
                cutoff = now.replace(hour=0, minute=0, second=0, microsecond=0)
            elif time_range == "week":
                cutoff = now - timedelta(days=7)
            else:
                cutoff = datetime.min

            conditions.append("timestamp >= ?")
            params.append(cutoff.isoformat())

        where_clause = " AND ".join(conditions) if conditions else "1=1"

        query = f"""
            SELECT * FROM entries
            WHERE {where_clause}
            ORDER BY timestamp DESC
            LIMIT ? OFFSET ?
        """
        params.extend([limit, offset])

        with self._get_connection() as conn:
            rows = conn.execute(query, params).fetchall()
            return [self._row_to_entry(row) for row in rows]

    async def get_entries_async(
        self,
        session_id: str | None = None,
        entry_types: list[EntryType] | None = None,
        importance: list[Importance] | None = None,
        time_range: TimeRange = "all",
        limit: int = 100,
        offset: int = 0,
    ) -> list[MemoryEntry]:
        """Get entries asynchronously."""
        await self.initialize_async()

        conditions = []
        params: list = []

        if session_id:
            conditions.append("session_id = ?")
            params.append(session_id)

        if entry_types:
            placeholders = ",".join("?" * len(entry_types))
            conditions.append(f"entry_type IN ({placeholders})")
            params.extend(entry_types)

        if importance:
            placeholders = ",".join("?" * len(importance))
            conditions.append(f"importance IN ({placeholders})")
            params.extend(importance)

        if time_range != "all":
            now = datetime.now()
            if time_range == "recent":
                cutoff = now - timedelta(hours=1)
            elif time_range == "today":
                cutoff = now.replace(hour=0, minute=0, second=0, microsecond=0)
            elif time_range == "week":
                cutoff = now - timedelta(days=7)
            else:
                cutoff = datetime.min

            conditions.append("timestamp >= ?")
            params.append(cutoff.isoformat())

        where_clause = " AND ".join(conditions) if conditions else "1=1"

        query = f"""
            SELECT * FROM entries
            WHERE {where_clause}
            ORDER BY timestamp DESC
            LIMIT ? OFFSET ?
        """
        params.extend([limit, offset])

        async with await self._get_async_connection() as conn:
            cursor = await conn.execute(query, params)
            rows = await cursor.fetchall()
            return [self._row_to_entry(row) for row in rows]

    def search_entries(
        self,
        query: str,
        session_id: str | None = None,
        limit: int = 20,
    ) -> list[MemoryEntry]:
        """Search entries using simple text matching.

        For more intelligent search, use the IntelligentRetriever.

        Args:
            query: Search query string.
            session_id: Optional session ID filter.
            limit: Maximum results.

        Returns:
            List of matching entries.
        """
        self.initialize()

        conditions = ["content LIKE ?"]
        params: list = [f"%{query}%"]

        if session_id:
            conditions.append("session_id = ?")
            params.append(session_id)

        where_clause = " AND ".join(conditions)

        with self._get_connection() as conn:
            rows = conn.execute(
                f"""
                SELECT * FROM entries
                WHERE {where_clause}
                ORDER BY timestamp DESC
                LIMIT ?
                """,
                params + [limit],
            ).fetchall()
            return [self._row_to_entry(row) for row in rows]

    async def search_entries_async(
        self,
        query: str,
        session_id: str | None = None,
        limit: int = 20,
    ) -> list[MemoryEntry]:
        """Search entries asynchronously."""
        await self.initialize_async()

        conditions = ["content LIKE ?"]
        params: list = [f"%{query}%"]

        if session_id:
            conditions.append("session_id = ?")
            params.append(session_id)

        where_clause = " AND ".join(conditions)

        async with await self._get_async_connection() as conn:
            cursor = await conn.execute(
                f"""
                SELECT * FROM entries
                WHERE {where_clause}
                ORDER BY timestamp DESC
                LIMIT ?
                """,
                params + [limit],
            )
            rows = await cursor.fetchall()
            return [self._row_to_entry(row) for row in rows]

    # -------------------------------------------------------------------------
    # Session Operations
    # -------------------------------------------------------------------------

    def get_session(self, session_id: str) -> SessionInfo | None:
        """Get session information."""
        self.initialize()

        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM sessions WHERE session_id = ?", (session_id,)
            ).fetchone()

            if not row:
                return None

            entry_count = conn.execute(
                "SELECT COUNT(*) as count FROM entries WHERE session_id = ?", (session_id,)
            ).fetchone()["count"]

            return SessionInfo(
                session_id=row["session_id"],
                started_at=datetime.fromisoformat(row["started_at"]),
                last_activity=datetime.fromisoformat(row["last_activity"]),
                entry_count=entry_count,
                metadata=json.loads(row["metadata"]) if row["metadata"] else {},
            )

    async def get_session_async(self, session_id: str) -> SessionInfo | None:
        """Get session information asynchronously."""
        await self.initialize_async()

        async with await self._get_async_connection() as conn:
            cursor = await conn.execute(
                "SELECT * FROM sessions WHERE session_id = ?", (session_id,)
            )
            row = await cursor.fetchone()

            if not row:
                return None

            count_cursor = await conn.execute(
                "SELECT COUNT(*) as count FROM entries WHERE session_id = ?", (session_id,)
            )
            entry_count = (await count_cursor.fetchone())["count"]

            return SessionInfo(
                session_id=row["session_id"],
                started_at=datetime.fromisoformat(row["started_at"]),
                last_activity=datetime.fromisoformat(row["last_activity"]),
                entry_count=entry_count,
                metadata=json.loads(row["metadata"]) if row["metadata"] else {},
            )

    def get_session_summary(self, session_id: str) -> str:
        """Generate a text summary of a session.

        Args:
            session_id: The session ID to summarize.

        Returns:
            A human-readable summary string.
        """
        session = self.get_session(session_id)
        if not session:
            return f"No session found with ID: {session_id}"

        entries = self.get_entries(session_id=session_id, limit=1000)

        # Count by type
        type_counts: dict[str, int] = {}
        for entry in entries:
            type_counts[entry.entry_type] = type_counts.get(entry.entry_type, 0) + 1

        # Get high importance entries
        important = [e for e in entries if e.importance in ("high", "critical")]

        duration = session.last_activity - session.started_at
        hours = duration.total_seconds() / 3600

        summary_parts = [
            f"Session: {session_id}",
            f"Duration: {hours:.1f} hours ({session.started_at.strftime('%Y-%m-%d %H:%M')} - {session.last_activity.strftime('%H:%M')})",
            f"Total entries: {session.entry_count}",
            "",
            "Entry breakdown:",
        ]

        for entry_type, count in sorted(type_counts.items()):
            summary_parts.append(f"  - {entry_type}: {count}")

        if important:
            summary_parts.extend(["", f"Important entries ({len(important)}):"])
            for entry in important[:5]:
                content_preview = entry.content[:100].replace("\n", " ")
                summary_parts.append(f"  [{entry.importance}] {content_preview}...")

        return "\n".join(summary_parts)

    def clear_session(self, session_id: str) -> int:
        """Clear all entries for a session.

        Args:
            session_id: The session ID to clear.

        Returns:
            Number of entries deleted.
        """
        self.initialize()

        with self._get_connection() as conn:
            # Delete large content first (foreign key)
            conn.execute(
                """
                DELETE FROM large_content
                WHERE entry_id IN (SELECT id FROM entries WHERE session_id = ?)
                """,
                (session_id,),
            )

            cursor = conn.execute(
                "DELETE FROM entries WHERE session_id = ?", (session_id,)
            )
            deleted = cursor.rowcount

            conn.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))
            conn.commit()

        return deleted

    async def clear_session_async(self, session_id: str) -> int:
        """Clear session asynchronously."""
        await self.initialize_async()

        async with await self._get_async_connection() as conn:
            await conn.execute(
                """
                DELETE FROM large_content
                WHERE entry_id IN (SELECT id FROM entries WHERE session_id = ?)
                """,
                (session_id,),
            )

            cursor = await conn.execute(
                "DELETE FROM entries WHERE session_id = ?", (session_id,)
            )
            deleted = cursor.rowcount

            await conn.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))
            await conn.commit()

        return deleted

    # -------------------------------------------------------------------------
    # Statistics
    # -------------------------------------------------------------------------

    def get_stats(self) -> MemoryStats:
        """Get memory store statistics."""
        self.initialize()

        with self._get_connection() as conn:
            total = conn.execute("SELECT COUNT(*) as count FROM entries").fetchone()["count"]

            session_count = conn.execute(
                "SELECT COUNT(*) as count FROM sessions"
            ).fetchone()["count"]

            type_rows = conn.execute(
                "SELECT entry_type, COUNT(*) as count FROM entries GROUP BY entry_type"
            ).fetchall()
            entries_by_type = {row["entry_type"]: row["count"] for row in type_rows}

            oldest = conn.execute(
                "SELECT MIN(timestamp) as ts FROM entries"
            ).fetchone()["ts"]
            newest = conn.execute(
                "SELECT MAX(timestamp) as ts FROM entries"
            ).fetchone()["ts"]

            # Get file size
            storage_size = self.db_path.stat().st_size if self.db_path.exists() else 0

            return MemoryStats(
                total_entries=total,
                session_count=session_count,
                entries_by_type=entries_by_type,
                storage_size_bytes=storage_size,
                oldest_entry=datetime.fromisoformat(oldest) if oldest else None,
                newest_entry=datetime.fromisoformat(newest) if newest else None,
            )

    async def get_stats_async(self) -> MemoryStats:
        """Get statistics asynchronously."""
        await self.initialize_async()

        async with await self._get_async_connection() as conn:
            cursor = await conn.execute("SELECT COUNT(*) as count FROM entries")
            total = (await cursor.fetchone())["count"]

            cursor = await conn.execute("SELECT COUNT(*) as count FROM sessions")
            session_count = (await cursor.fetchone())["count"]

            cursor = await conn.execute(
                "SELECT entry_type, COUNT(*) as count FROM entries GROUP BY entry_type"
            )
            type_rows = await cursor.fetchall()
            entries_by_type = {row["entry_type"]: row["count"] for row in type_rows}

            cursor = await conn.execute("SELECT MIN(timestamp) as ts FROM entries")
            oldest = (await cursor.fetchone())["ts"]

            cursor = await conn.execute("SELECT MAX(timestamp) as ts FROM entries")
            newest = (await cursor.fetchone())["ts"]

            storage_size = self.db_path.stat().st_size if self.db_path.exists() else 0

            return MemoryStats(
                total_entries=total,
                session_count=session_count,
                entries_by_type=entries_by_type,
                storage_size_bytes=storage_size,
                oldest_entry=datetime.fromisoformat(oldest) if oldest else None,
                newest_entry=datetime.fromisoformat(newest) if newest else None,
            )
