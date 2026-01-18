"""Tests for MemoryStore."""

import tempfile
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from rlm_memory.memory_store import MemoryStore
from rlm_memory.types import MemoryEntry


@pytest.fixture
def temp_storage():
    """Create a temporary storage directory for tests."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def memory_store(temp_storage):
    """Create a MemoryStore instance with temporary storage."""
    store = MemoryStore(temp_storage)
    store.initialize()
    return store


class TestMemoryStoreBasics:
    """Test basic MemoryStore operations."""

    def test_initialize_creates_db(self, temp_storage):
        """Test that initialization creates the database file."""
        store = MemoryStore(temp_storage)
        store.initialize()

        db_path = temp_storage / "memory.db"
        assert db_path.exists()

    def test_add_and_get_entry(self, memory_store):
        """Test adding and retrieving a single entry."""
        entry = MemoryEntry.create(
            session_id="test-session",
            entry_type="user_message",
            content="Hello, world!",
            importance="medium",
        )

        entry_id = memory_store.add_entry(entry)
        assert entry_id == entry.id

        retrieved = memory_store.get_entry(entry_id)
        assert retrieved is not None
        assert retrieved.content == "Hello, world!"
        assert retrieved.session_id == "test-session"
        assert retrieved.entry_type == "user_message"

    def test_get_nonexistent_entry(self, memory_store):
        """Test that getting a nonexistent entry returns None."""
        result = memory_store.get_entry("nonexistent-id")
        assert result is None

    def test_large_content_handling(self, memory_store):
        """Test that large content is handled correctly."""
        large_content = "x" * 20000  # 20KB of content

        entry = MemoryEntry.create(
            session_id="test-session",
            entry_type="tool_result",
            content=large_content,
        )

        entry_id = memory_store.add_entry(entry)

        # Without full_content, should be truncated
        retrieved = memory_store.get_entry(entry_id, full_content=False)
        assert retrieved is not None
        assert retrieved.content.endswith("...")
        assert len(retrieved.content) < 2000

        # With full_content, should get everything
        retrieved_full = memory_store.get_entry(entry_id, full_content=True)
        assert retrieved_full is not None
        assert retrieved_full.content == large_content


class TestMemoryStoreQueries:
    """Test MemoryStore query operations."""

    def test_get_entries_by_session(self, memory_store):
        """Test filtering entries by session ID."""
        # Add entries for two sessions
        for i in range(3):
            entry = MemoryEntry.create(
                session_id="session-a",
                entry_type="user_message",
                content=f"Session A message {i}",
            )
            memory_store.add_entry(entry)

        for i in range(2):
            entry = MemoryEntry.create(
                session_id="session-b",
                entry_type="user_message",
                content=f"Session B message {i}",
            )
            memory_store.add_entry(entry)

        # Query by session
        session_a_entries = memory_store.get_entries(session_id="session-a")
        assert len(session_a_entries) == 3

        session_b_entries = memory_store.get_entries(session_id="session-b")
        assert len(session_b_entries) == 2

    def test_get_entries_by_type(self, memory_store):
        """Test filtering entries by entry type."""
        entry_types = ["user_message", "assistant_message", "tool_result"]

        for entry_type in entry_types:
            entry = MemoryEntry.create(
                session_id="test-session",
                entry_type=entry_type,
                content=f"Content for {entry_type}",
            )
            memory_store.add_entry(entry)

        # Filter by single type
        user_entries = memory_store.get_entries(entry_types=["user_message"])
        assert len(user_entries) == 1
        assert user_entries[0].entry_type == "user_message"

        # Filter by multiple types
        msg_entries = memory_store.get_entries(
            entry_types=["user_message", "assistant_message"]
        )
        assert len(msg_entries) == 2

    def test_get_entries_by_importance(self, memory_store):
        """Test filtering entries by importance level."""
        importance_levels = ["low", "medium", "high", "critical"]

        for level in importance_levels:
            entry = MemoryEntry.create(
                session_id="test-session",
                entry_type="decision",
                content=f"{level} importance entry",
                importance=level,
            )
            memory_store.add_entry(entry)

        # Get high importance entries
        high_entries = memory_store.get_entries(importance=["high", "critical"])
        assert len(high_entries) == 2

    def test_get_entries_with_limit_and_offset(self, memory_store):
        """Test pagination with limit and offset."""
        # Add 10 entries
        for i in range(10):
            entry = MemoryEntry.create(
                session_id="test-session",
                entry_type="user_message",
                content=f"Message {i}",
            )
            memory_store.add_entry(entry)

        # Get first 5
        first_page = memory_store.get_entries(limit=5, offset=0)
        assert len(first_page) == 5

        # Get next 5
        second_page = memory_store.get_entries(limit=5, offset=5)
        assert len(second_page) == 5

        # Entries should be different
        first_ids = {e.id for e in first_page}
        second_ids = {e.id for e in second_page}
        assert first_ids.isdisjoint(second_ids)

    def test_search_entries(self, memory_store):
        """Test text search functionality."""
        entries_data = [
            ("Implementing authentication", "auth"),
            ("Database migration script", "database"),
            ("Authentication token refresh", "auth"),
            ("API endpoint design", "api"),
        ]

        for content, _ in entries_data:
            entry = MemoryEntry.create(
                session_id="test-session",
                entry_type="assistant_message",
                content=content,
            )
            memory_store.add_entry(entry)

        # Search for "auth"
        auth_results = memory_store.search_entries("auth")
        assert len(auth_results) == 2

        # Search for "database"
        db_results = memory_store.search_entries("database")
        assert len(db_results) == 1


class TestSessionManagement:
    """Test session management features."""

    def test_get_session_info(self, memory_store):
        """Test retrieving session information."""
        # Add some entries
        for i in range(5):
            entry = MemoryEntry.create(
                session_id="test-session",
                entry_type="user_message",
                content=f"Message {i}",
            )
            memory_store.add_entry(entry)

        session = memory_store.get_session("test-session")
        assert session is not None
        assert session.session_id == "test-session"
        assert session.entry_count == 5

    def test_get_session_summary(self, memory_store):
        """Test session summary generation."""
        # Add various entry types
        entry_types = [
            ("user_message", "What is the authentication flow?", "medium"),
            ("assistant_message", "The auth flow uses JWT tokens.", "medium"),
            ("decision", "Using JWT for authentication", "high"),
            ("tool_result", "File created: auth.py", "medium"),
        ]

        for entry_type, content, importance in entry_types:
            entry = MemoryEntry.create(
                session_id="test-session",
                entry_type=entry_type,
                content=content,
                importance=importance,
            )
            memory_store.add_entry(entry)

        summary = memory_store.get_session_summary("test-session")

        assert "test-session" in summary
        assert "Total entries: 4" in summary
        assert "user_message" in summary

    def test_clear_session(self, memory_store):
        """Test clearing a session."""
        # Add entries
        for i in range(5):
            entry = MemoryEntry.create(
                session_id="test-session",
                entry_type="user_message",
                content=f"Message {i}",
            )
            memory_store.add_entry(entry)

        # Verify entries exist
        entries = memory_store.get_entries(session_id="test-session")
        assert len(entries) == 5

        # Clear session
        deleted = memory_store.clear_session("test-session")
        assert deleted == 5

        # Verify entries are gone
        entries = memory_store.get_entries(session_id="test-session")
        assert len(entries) == 0


class TestMemoryStats:
    """Test memory statistics."""

    def test_get_stats(self, memory_store):
        """Test retrieving memory statistics."""
        # Add entries of various types
        for entry_type in ["user_message", "assistant_message", "tool_result"]:
            for i in range(2):
                entry = MemoryEntry.create(
                    session_id=f"session-{i}",
                    entry_type=entry_type,
                    content=f"Content {entry_type} {i}",
                )
                memory_store.add_entry(entry)

        stats = memory_store.get_stats()

        assert stats.total_entries == 6
        assert stats.session_count == 2
        assert stats.entries_by_type["user_message"] == 2
        assert stats.entries_by_type["assistant_message"] == 2
        assert stats.entries_by_type["tool_result"] == 2
        assert stats.storage_size_bytes > 0


class TestAsyncOperations:
    """Test async operations."""

    @pytest.mark.asyncio
    async def test_async_add_and_get(self, temp_storage):
        """Test async add and get operations."""
        store = MemoryStore(temp_storage)
        await store.initialize_async()

        entry = MemoryEntry.create(
            session_id="test-session",
            entry_type="user_message",
            content="Async test message",
        )

        entry_id = await store.add_entry_async(entry)
        assert entry_id == entry.id

        # Get entries async
        entries = await store.get_entries_async(session_id="test-session")
        assert len(entries) == 1
        assert entries[0].content == "Async test message"

    @pytest.mark.asyncio
    async def test_async_search(self, temp_storage):
        """Test async search operation."""
        store = MemoryStore(temp_storage)
        await store.initialize_async()

        entry = MemoryEntry.create(
            session_id="test-session",
            entry_type="user_message",
            content="Testing async search functionality",
        )
        await store.add_entry_async(entry)

        results = await store.search_entries_async("async search")
        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_async_stats(self, temp_storage):
        """Test async stats retrieval."""
        store = MemoryStore(temp_storage)
        await store.initialize_async()

        entry = MemoryEntry.create(
            session_id="test-session",
            entry_type="user_message",
            content="Test entry",
        )
        await store.add_entry_async(entry)

        stats = await store.get_stats_async()
        assert stats.total_entries == 1
