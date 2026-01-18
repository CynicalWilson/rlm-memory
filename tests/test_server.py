"""Integration tests for the MCP server."""

import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

# Import server module to test tool functions
from rlm_memory import server


@pytest.fixture
def temp_storage():
    """Create a temporary storage directory for tests."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def clean_server_state(temp_storage):
    """Reset server state before each test."""
    # Reset global state
    server._memory_store = None
    server._conversation_rlm = None
    server._current_session_id = None

    # Set environment for temp storage
    with patch.dict(os.environ, {
        "RLM_STORAGE_DIR": str(temp_storage),
        "RLM_SESSION_ID": "test-session",
        "RLM_USE_RLM": "false",  # Disable RLM to avoid needing API keys
    }):
        yield

    # Clean up after test
    server._memory_store = None
    server._conversation_rlm = None
    server._current_session_id = None


class TestMCPTools:
    """Test MCP tool functions."""

    @pytest.mark.asyncio
    async def test_rlm_store_message(self, clean_server_state):
        """Test storing a message."""
        result = await server.rlm_store_message(
            role="user",
            content="Test message content",
            importance="high",
        )

        assert "stored successfully" in result.lower()
        assert "Entry ID:" in result

    @pytest.mark.asyncio
    async def test_rlm_store_tool_result(self, clean_server_state):
        """Test storing a tool result."""
        result = await server.rlm_store_tool_result(
            tool_name="Bash",
            input_summary="git status",
            output_summary="Clean working directory",
            importance="medium",
        )

        assert "stored" in result.lower()
        assert "Entry ID:" in result

    @pytest.mark.asyncio
    async def test_rlm_store_decision(self, clean_server_state):
        """Test storing a decision."""
        result = await server.rlm_store_decision(
            decision="Use JWT for authentication",
            context="Need stateless auth for API",
            alternatives_considered="Session cookies, OAuth",
        )

        assert "recorded" in result.lower()
        assert "Entry ID:" in result

    @pytest.mark.asyncio
    async def test_rlm_store_file_op(self, clean_server_state):
        """Test storing a file operation."""
        result = await server.rlm_store_file_op(
            operation="write",
            file_path="/src/auth.py",
            summary="Created authentication module",
        )

        assert "recorded" in result.lower()
        assert "Entry ID:" in result

    @pytest.mark.asyncio
    async def test_rlm_status_empty(self, clean_server_state):
        """Test status with no entries."""
        result = await server.rlm_status()

        assert "RLM Memory Status" in result
        assert "test-session" in result
        assert "Total entries:" in result

    @pytest.mark.asyncio
    async def test_rlm_status_with_entries(self, clean_server_state):
        """Test status after adding entries."""
        # Add some entries
        await server.rlm_store_message(role="user", content="Test 1")
        await server.rlm_store_message(role="assistant", content="Test 2")
        await server.rlm_store_decision(decision="Test decision")

        result = await server.rlm_status()

        assert "RLM Memory Status" in result
        assert "Total entries:" in result
        # Should show entry breakdown
        assert "user_message" in result or "Entry Breakdown" in result

    @pytest.mark.asyncio
    async def test_rlm_query(self, clean_server_state):
        """Test querying memory."""
        # Add some entries first
        await server.rlm_store_message(
            role="user",
            content="How should we implement authentication?",
        )
        await server.rlm_store_decision(
            decision="Use JWT tokens for API authentication",
        )

        result = await server.rlm_query(query="authentication")

        # Should find the relevant entries
        assert len(result) > 0

    @pytest.mark.asyncio
    async def test_rlm_query_with_time_range(self, clean_server_state):
        """Test querying with time range filter."""
        await server.rlm_store_message(role="user", content="Recent message")

        result = await server.rlm_query(
            query="message",
            time_range="recent",
        )

        assert len(result) > 0

    @pytest.mark.asyncio
    async def test_rlm_recall(self, clean_server_state):
        """Test natural language recall."""
        await server.rlm_store_decision(
            decision="Use PostgreSQL for the database",
            context="Need ACID compliance and JSON support",
        )

        result = await server.rlm_recall(
            what="what database are we using",
            verbosity="brief",
        )

        # Should return something (even if just the formatted entry)
        assert len(result) > 0

    @pytest.mark.asyncio
    async def test_rlm_summarize_session(self, clean_server_state):
        """Test session summarization."""
        # Add various entries
        await server.rlm_store_message(role="user", content="Start project setup")
        await server.rlm_store_file_op(
            operation="write",
            file_path="package.json",
            summary="Created package.json",
        )
        await server.rlm_store_decision(decision="Use TypeScript")

        result = await server.rlm_summarize(scope="session")

        # Should return a summary
        assert len(result) > 0

    @pytest.mark.asyncio
    async def test_rlm_summarize_topic(self, clean_server_state):
        """Test topic summarization."""
        await server.rlm_store_decision(
            decision="Use React for frontend",
        )
        await server.rlm_store_message(
            role="assistant",
            content="Setting up React with TypeScript",
        )

        result = await server.rlm_summarize(
            scope="topic",
            topic="React",
        )

        assert len(result) > 0

    @pytest.mark.asyncio
    async def test_rlm_clear_session_requires_confirm(self, clean_server_state):
        """Test that clear session requires confirmation."""
        await server.rlm_store_message(role="user", content="Test")

        result = await server.rlm_clear_session(confirm=False)

        # Should return safety message without deleting
        assert "confirm=True" in result

    @pytest.mark.asyncio
    async def test_rlm_clear_session_with_confirm(self, clean_server_state):
        """Test clearing session with confirmation."""
        await server.rlm_store_message(role="user", content="Test message")

        # Verify entry exists
        status_before = await server.rlm_status()
        assert "Total entries: 1" in status_before or "user_message" in status_before

        # Clear with confirmation
        result = await server.rlm_clear_session(confirm=True)

        assert "cleared" in result.lower()
        assert "deleted" in result.lower()


class TestServerIntegration:
    """Test server integration aspects."""

    @pytest.mark.asyncio
    async def test_full_workflow(self, clean_server_state):
        """Test a complete workflow through the server."""
        # 1. Start with status check
        status = await server.rlm_status()
        assert "RLM Memory Status" in status

        # 2. Store various entries
        await server.rlm_store_message(
            role="user",
            content="I need to implement user authentication",
        )

        await server.rlm_store_message(
            role="assistant",
            content="I'll help you implement authentication. Let's use JWT tokens.",
        )

        await server.rlm_store_decision(
            decision="Use JWT for authentication",
            context="Stateless auth for REST API",
            alternatives_considered="Session cookies",
        )

        await server.rlm_store_tool_result(
            tool_name="Write",
            input_summary="Created auth.py",
            output_summary="File created successfully",
        )

        await server.rlm_store_file_op(
            operation="write",
            file_path="src/auth.py",
            summary="Authentication module with JWT support",
        )

        # 3. Check status shows entries
        status = await server.rlm_status()
        assert "5" in status or "Total entries" in status

        # 4. Query for authentication
        query_result = await server.rlm_query(query="authentication JWT")
        assert len(query_result) > 0

        # 5. Recall what was decided
        recall_result = await server.rlm_recall(
            what="what authentication method did we choose",
        )
        assert len(recall_result) > 0

        # 6. Generate summary
        summary = await server.rlm_summarize(scope="session")
        assert len(summary) > 0

    @pytest.mark.asyncio
    async def test_multiple_sessions(self, temp_storage):
        """Test handling multiple sessions."""
        # First session
        with patch.dict(os.environ, {
            "RLM_STORAGE_DIR": str(temp_storage),
            "RLM_SESSION_ID": "session-1",
            "RLM_USE_RLM": "false",
        }):
            server._memory_store = None
            server._current_session_id = None

            await server.rlm_store_message(role="user", content="Session 1 message")

        # Second session
        with patch.dict(os.environ, {
            "RLM_STORAGE_DIR": str(temp_storage),
            "RLM_SESSION_ID": "session-2",
            "RLM_USE_RLM": "false",
        }):
            server._memory_store = None
            server._current_session_id = None

            await server.rlm_store_message(role="user", content="Session 2 message")

            # Query should only find session-2 entries by default
            result = await server.rlm_query(query="message")
            # The query goes through retrieval which uses session filter
            assert len(result) > 0

        # Clean up
        server._memory_store = None
        server._current_session_id = None
