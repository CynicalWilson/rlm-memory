"""Core types for RLM Memory system."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal
import uuid


EntryType = Literal["user_message", "assistant_message", "tool_call", "tool_result", "file_op", "decision", "summary"]
Importance = Literal["low", "medium", "high", "critical"]
TimeRange = Literal["recent", "today", "week", "all"]
Verbosity = Literal["brief", "detailed", "full"]
SummarizeScope = Literal["session", "topic", "range"]


@dataclass
class MemoryEntry:
    """A single entry in the conversation memory store."""

    id: str
    session_id: str
    timestamp: datetime
    entry_type: EntryType
    content: str
    metadata: dict = field(default_factory=dict)
    embedding: list[float] | None = None
    importance: Importance = "medium"

    @classmethod
    def create(
        cls,
        session_id: str,
        entry_type: EntryType,
        content: str,
        metadata: dict | None = None,
        importance: Importance = "medium",
    ) -> "MemoryEntry":
        """Factory method to create a new memory entry with auto-generated ID and timestamp."""
        return cls(
            id=str(uuid.uuid4()),
            session_id=session_id,
            timestamp=datetime.now(),
            entry_type=entry_type,
            content=content,
            metadata=metadata or {},
            importance=importance,
        )


@dataclass
class SessionInfo:
    """Information about a conversation session."""

    session_id: str
    started_at: datetime
    last_activity: datetime
    entry_count: int
    metadata: dict = field(default_factory=dict)


@dataclass
class MemoryStats:
    """Statistics about the memory store."""

    total_entries: int
    session_count: int
    entries_by_type: dict[str, int]
    storage_size_bytes: int
    oldest_entry: datetime | None
    newest_entry: datetime | None


@dataclass
class RetrievalResult:
    """Result from a memory retrieval operation."""

    entries: list[MemoryEntry]
    query: str
    relevance_scores: list[float]
    retrieval_time_ms: float
    tokens_used: int
