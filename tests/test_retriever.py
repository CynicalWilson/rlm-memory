"""Tests for IntelligentRetriever."""

import tempfile
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from rlm_memory.memory_store import MemoryStore
from rlm_memory.retriever import (
    IntelligentRetriever,
    RetrievalConfig,
    format_entries_for_context,
)
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


@pytest.fixture
def populated_store(memory_store):
    """Create a MemoryStore with some test data."""
    entries = [
        ("Implementing user authentication with JWT tokens", "decision", "high"),
        ("Created auth.py file with login endpoint", "file_op", "medium"),
        ("Database schema design for users table", "assistant_message", "medium"),
        ("Testing authentication flow", "tool_result", "low"),
        ("Bug fix in token refresh logic", "assistant_message", "high"),
        ("API endpoint documentation", "assistant_message", "low"),
    ]

    for content, entry_type, importance in entries:
        entry = MemoryEntry.create(
            session_id="test-session",
            entry_type=entry_type,
            content=content,
            importance=importance,
        )
        memory_store.add_entry(entry)

    return memory_store


@pytest.fixture
def retriever(populated_store):
    """Create an IntelligentRetriever instance."""
    return IntelligentRetriever(populated_store)


class TestKeywordExtraction:
    """Test keyword extraction functionality."""

    def test_extracts_meaningful_words(self, retriever):
        """Test that meaningful keywords are extracted."""
        text = "Implementing user authentication with JWT tokens"
        keywords = retriever._extract_keywords(text)

        assert "implementing" in keywords
        assert "user" in keywords
        assert "authentication" in keywords
        assert "jwt" in keywords
        assert "tokens" in keywords

        # Stop words should be excluded
        assert "with" not in keywords
        assert "the" not in keywords

    def test_handles_code_identifiers(self, retriever):
        """Test that code identifiers are preserved."""
        text = "The function_name uses snake_case naming"
        keywords = retriever._extract_keywords(text)

        assert "function_name" in keywords
        assert "snake_case" in keywords


class TestRelevanceScoring:
    """Test relevance scoring functionality."""

    def test_keyword_matching_increases_score(self, retriever):
        """Test that keyword matches increase relevance score."""
        entry = MemoryEntry.create(
            session_id="test",
            entry_type="user_message",
            content="Implementing user authentication",
        )

        # Query with matching keywords
        matching_score = retriever._calculate_relevance_score(
            entry, "authentication", {"authentication"}
        )

        # Query with non-matching keywords
        non_matching_score = retriever._calculate_relevance_score(
            entry, "database", {"database"}
        )

        assert matching_score > non_matching_score

    def test_importance_affects_score(self, retriever):
        """Test that entry importance affects relevance score."""
        high_importance = MemoryEntry.create(
            session_id="test",
            entry_type="decision",
            content="Important decision",
            importance="high",
        )

        low_importance = MemoryEntry.create(
            session_id="test",
            entry_type="decision",
            content="Important decision",
            importance="low",
        )

        high_score = retriever._importance_score(high_importance)
        low_score = retriever._importance_score(low_importance)

        assert high_score > low_score

    def test_temporal_score_favors_recent(self, retriever):
        """Test that temporal scoring favors recent entries."""
        recent = MemoryEntry(
            id="1",
            session_id="test",
            timestamp=datetime.now(),
            entry_type="user_message",
            content="Recent message",
        )

        old = MemoryEntry(
            id="2",
            session_id="test",
            timestamp=datetime.now() - timedelta(days=30),
            entry_type="user_message",
            content="Old message",
        )

        recent_score = retriever._temporal_score(recent)
        old_score = retriever._temporal_score(old)

        assert recent_score > old_score


class TestRetrieval:
    """Test the main retrieval functionality."""

    def test_retrieve_finds_relevant_entries(self, retriever):
        """Test that retrieval finds relevant entries."""
        result = retriever.retrieve("authentication JWT")

        assert len(result.entries) > 0
        assert result.query == "authentication JWT"

        # Check that auth-related entries are found
        contents = [e.content for e in result.entries]
        assert any("authentication" in c.lower() for c in contents)

    def test_retrieve_returns_relevance_scores(self, retriever):
        """Test that retrieval returns relevance scores."""
        result = retriever.retrieve("authentication")

        assert len(result.relevance_scores) == len(result.entries)
        assert all(0 <= score <= 1 for score in result.relevance_scores)

        # Scores should be in descending order
        for i in range(len(result.relevance_scores) - 1):
            assert result.relevance_scores[i] >= result.relevance_scores[i + 1]

    def test_retrieve_respects_max_results(self, retriever):
        """Test that retrieval respects max_results parameter."""
        result = retriever.retrieve("the", max_results=2)
        assert len(result.entries) <= 2

    def test_retrieve_filters_by_session(self, populated_store):
        """Test that retrieval can filter by session."""
        # Add entry for different session
        entry = MemoryEntry.create(
            session_id="other-session",
            entry_type="user_message",
            content="Different session authentication",
        )
        populated_store.add_entry(entry)

        retriever = IntelligentRetriever(populated_store)
        result = retriever.retrieve("authentication", session_id="test-session")

        # Should only find entries from test-session
        assert all(e.session_id == "test-session" for e in result.entries)

    def test_retrieve_empty_for_no_matches(self, retriever):
        """Test that retrieval returns empty for no matches."""
        result = retriever.retrieve("xyznonexistentterm123")
        assert len(result.entries) == 0

    @pytest.mark.asyncio
    async def test_async_retrieve(self, populated_store):
        """Test async retrieval."""
        retriever = IntelligentRetriever(populated_store)
        result = await retriever.retrieve_async("authentication")

        assert len(result.entries) > 0
        assert result.query == "authentication"


class TestFormatting:
    """Test entry formatting for context."""

    def test_format_entries_basic(self, populated_store):
        """Test basic entry formatting."""
        entries = populated_store.get_entries(limit=3)
        formatted = format_entries_for_context(entries)

        assert len(formatted) > 0
        assert "---" in formatted  # Separator between entries

    def test_format_entries_respects_token_limit(self, populated_store):
        """Test that formatting respects token limit."""
        entries = populated_store.get_entries(limit=100)
        formatted = format_entries_for_context(entries, max_tokens=100)

        # Should be truncated
        estimated_tokens = len(formatted) * 0.25
        assert estimated_tokens <= 200  # Allow some slack

    def test_format_entries_includes_metadata(self, populated_store):
        """Test that formatting includes metadata when requested."""
        entries = populated_store.get_entries(limit=1)
        formatted = format_entries_for_context(entries, include_metadata=True)

        # Should include entry type in brackets
        assert "[" in formatted and "]" in formatted

    def test_format_entries_handles_empty(self):
        """Test formatting handles empty list."""
        formatted = format_entries_for_context([])
        assert "No relevant memories" in formatted


class TestRetrievalConfig:
    """Test retrieval configuration."""

    def test_custom_config(self, populated_store):
        """Test retrieval with custom configuration."""
        config = RetrievalConfig(
            keyword_weight=0.8,
            temporal_weight=0.1,
            importance_weight=0.1,
            min_relevance_score=0.01,
        )

        retriever = IntelligentRetriever(populated_store, config)
        result = retriever.retrieve("authentication")

        # Should still work with custom weights
        assert len(result.entries) > 0

    def test_high_min_relevance_filters_more(self, populated_store):
        """Test that high min_relevance_score filters more entries."""
        low_threshold = RetrievalConfig(min_relevance_score=0.01)
        high_threshold = RetrievalConfig(min_relevance_score=0.9)

        low_retriever = IntelligentRetriever(populated_store, low_threshold)
        high_retriever = IntelligentRetriever(populated_store, high_threshold)

        low_result = low_retriever.retrieve("test")
        high_result = high_retriever.retrieve("test")

        assert len(low_result.entries) >= len(high_result.entries)
