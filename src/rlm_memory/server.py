"""MCP Server for RLM Memory.

Provides conversation memory tools for Claude Code through the
Model Context Protocol.
"""

import logging
import os
import uuid
from datetime import datetime
from typing import Literal

from mcp.server.fastmcp import FastMCP

from rlm_memory.conversation_rlm import ConversationRLM
from rlm_memory.memory_store import MemoryStore
from rlm_memory.types import EntryType, Importance, MemoryEntry, TimeRange, Verbosity

# Configure logging (never use print in STDIO servers!)
logging.basicConfig(
    level=getattr(logging, os.environ.get("RLM_LOG_LEVEL", "INFO").upper()),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("rlm-memory")

# Initialize FastMCP server
mcp = FastMCP("rlm-memory")

# Global state (initialized on first tool call)
_memory_store: MemoryStore | None = None
_conversation_rlm: ConversationRLM | None = None
_current_session_id: str | None = None


def _get_memory_store() -> MemoryStore:
    """Get or initialize the memory store."""
    global _memory_store
    if _memory_store is None:
        storage_dir = os.environ.get("RLM_STORAGE_DIR", ".rlm-memory")
        _memory_store = MemoryStore(storage_dir)
        _memory_store.initialize()
        logger.info(f"Initialized memory store at {storage_dir}")
    return _memory_store


def _get_conversation_rlm() -> ConversationRLM:
    """Get or initialize the ConversationRLM."""
    global _conversation_rlm
    if _conversation_rlm is None:
        store = _get_memory_store()
        backend = os.environ.get("RLM_BACKEND", "openai")
        _conversation_rlm = ConversationRLM(
            memory_store=store,
            backend=backend,
            use_rlm=os.environ.get("RLM_USE_RLM", "true").lower() == "true",
        )
        logger.info(f"Initialized ConversationRLM with backend: {backend}")
    return _conversation_rlm


def _get_session_id() -> str:
    """Get or create the current session ID."""
    global _current_session_id
    if _current_session_id is None:
        _current_session_id = os.environ.get(
            "RLM_SESSION_ID",
            str(uuid.uuid4())[:8],
        )
        logger.info(f"Session ID: {_current_session_id}")
    return _current_session_id


# =============================================================================
# MCP Tools
# =============================================================================


@mcp.tool()
async def rlm_store_message(
    role: Literal["user", "assistant"],
    content: str,
    session_id: str | None = None,
    importance: Literal["low", "medium", "high", "critical"] = "medium",
) -> str:
    """Store a conversation message in RLM memory.

    Use this to preserve important messages that may be needed later,
    especially before context compaction occurs.

    Args:
        role: The role of the message sender (user or assistant)
        content: The message content to store
        session_id: Optional session ID (uses current session if not provided)
        importance: Importance level for retrieval prioritization

    Returns:
        Confirmation message with entry ID
    """
    store = _get_memory_store()
    sid = session_id or _get_session_id()

    entry_type: EntryType = "user_message" if role == "user" else "assistant_message"

    entry = MemoryEntry.create(
        session_id=sid,
        entry_type=entry_type,
        content=content,
        metadata={"role": role},
        importance=importance,
    )

    entry_id = await store.add_entry_async(entry)
    logger.info(f"Stored {role} message: {entry_id}")

    return f"Message stored successfully. Entry ID: {entry_id}"


@mcp.tool()
async def rlm_store_tool_result(
    tool_name: str,
    input_summary: str,
    output_summary: str,
    full_output: str | None = None,
    importance: Literal["low", "medium", "high", "critical"] = "medium",
) -> str:
    """Store tool execution results in memory.

    Use this to record significant tool operations like file edits,
    bash commands, or search results.

    Args:
        tool_name: Name of the tool that was executed
        input_summary: Brief summary of the tool input/parameters
        output_summary: Brief summary of the tool result
        full_output: Optional full output (stored separately if large)
        importance: Importance level for retrieval prioritization

    Returns:
        Confirmation message with entry ID
    """
    store = _get_memory_store()
    sid = _get_session_id()

    content = f"Tool: {tool_name}\nInput: {input_summary}\nResult: {output_summary}"
    if full_output:
        content += f"\n\nFull Output:\n{full_output}"

    entry = MemoryEntry.create(
        session_id=sid,
        entry_type="tool_result",
        content=content,
        metadata={
            "tool_name": tool_name,
            "input_summary": input_summary,
            "output_summary": output_summary,
        },
        importance=importance,
    )

    entry_id = await store.add_entry_async(entry)
    logger.info(f"Stored tool result for {tool_name}: {entry_id}")

    return f"Tool result stored. Entry ID: {entry_id}"


@mcp.tool()
async def rlm_store_decision(
    decision: str,
    context: str | None = None,
    alternatives_considered: str | None = None,
) -> str:
    """Store an important decision made during the conversation.

    Use this to record key decisions about architecture, approach,
    or implementation choices that may need to be referenced later.

    Args:
        decision: The decision that was made
        context: Why this decision was made
        alternatives_considered: Other options that were considered

    Returns:
        Confirmation message
    """
    store = _get_memory_store()
    sid = _get_session_id()

    content_parts = [f"Decision: {decision}"]
    if context:
        content_parts.append(f"Context: {context}")
    if alternatives_considered:
        content_parts.append(f"Alternatives considered: {alternatives_considered}")

    entry = MemoryEntry.create(
        session_id=sid,
        entry_type="decision",
        content="\n".join(content_parts),
        metadata={
            "decision": decision,
            "context": context,
            "alternatives": alternatives_considered,
        },
        importance="high",
    )

    entry_id = await store.add_entry_async(entry)
    logger.info(f"Stored decision: {entry_id}")

    return f"Decision recorded. Entry ID: {entry_id}"


@mcp.tool()
async def rlm_store_file_op(
    operation: Literal["read", "write", "edit", "delete"],
    file_path: str,
    summary: str,
    details: str | None = None,
) -> str:
    """Store a file operation in memory.

    Use this to track file modifications for later reference.

    Args:
        operation: Type of file operation
        file_path: Path to the file
        summary: Brief summary of what was done
        details: Optional detailed description or diff

    Returns:
        Confirmation message
    """
    store = _get_memory_store()
    sid = _get_session_id()

    content = f"File {operation}: {file_path}\nSummary: {summary}"
    if details:
        content += f"\n\nDetails:\n{details}"

    entry = MemoryEntry.create(
        session_id=sid,
        entry_type="file_op",
        content=content,
        metadata={
            "operation": operation,
            "file_path": file_path,
            "summary": summary,
        },
        importance="medium",
    )

    entry_id = await store.add_entry_async(entry)
    logger.info(f"Stored file operation: {operation} on {file_path}")

    return f"File operation recorded. Entry ID: {entry_id}"


@mcp.tool()
async def rlm_query(
    query: str,
    time_range: Literal["recent", "today", "week", "all"] = "all",
    entry_types: list[str] | None = None,
    max_tokens: int = 4000,
) -> str:
    """Query memory using intelligent retrieval.

    Searches conversation memory to find entries relevant to the query,
    using multiple strategies including keyword matching, temporal
    relevance, and importance scoring.

    Args:
        query: The search query or question
        time_range: Filter by time range (recent=1hr, today, week, all)
        entry_types: Optional filter by entry types (user_message, assistant_message, tool_result, file_op, decision)
        max_tokens: Maximum tokens to return in the response

    Returns:
        Relevant context from memory, formatted for use
    """
    rlm = _get_conversation_rlm()
    sid = _get_session_id()

    logger.info(f"Querying memory: {query[:50]}...")

    result = await rlm.retrieve_relevant_async(
        query=query,
        session_id=sid,
        time_range=time_range,
        max_tokens=max_tokens,
    )

    return result


@mcp.tool()
async def rlm_recall(
    what: str,
    verbosity: Literal["brief", "detailed", "full"] = "detailed",
) -> str:
    """Natural language recall from conversation memory.

    Use natural language to ask about past conversations, decisions,
    or actions. For example: "what did we decide about the API design"
    or "show me the code we wrote for authentication".

    Args:
        what: Natural language description of what to recall
        verbosity: Response detail level (brief=1-2 sentences, detailed=thorough, full=everything)

    Returns:
        Recalled information formatted according to verbosity
    """
    rlm = _get_conversation_rlm()
    sid = _get_session_id()

    logger.info(f"Recalling: {what[:50]}...")

    result = await rlm.recall_async(
        what=what,
        session_id=sid,
        verbosity=verbosity,
    )

    return result


@mcp.tool()
async def rlm_summarize(
    scope: Literal["session", "topic", "range"],
    topic: str | None = None,
    start_time: str | None = None,
    end_time: str | None = None,
) -> str:
    """Generate an intelligent summary of conversation context.

    Creates a summary of conversation memory, preserving key decisions,
    code changes, and important context.

    Args:
        scope: Summary scope - session (current session), topic (specific topic), or range (time range)
        topic: Topic to summarize (required for topic scope)
        start_time: ISO format start time (for range scope)
        end_time: ISO format end time (for range scope)

    Returns:
        Generated summary text
    """
    rlm = _get_conversation_rlm()
    sid = _get_session_id()

    logger.info(f"Generating {scope} summary...")

    # Parse times if provided
    start_dt = datetime.fromisoformat(start_time) if start_time else None
    end_dt = datetime.fromisoformat(end_time) if end_time else None

    result = await rlm.summarize_async(
        scope=scope,
        session_id=sid if scope == "session" else None,
        topic=topic,
        start_time=start_dt,
        end_time=end_dt,
    )

    return result


@mcp.tool()
async def rlm_status() -> str:
    """Get current memory status and statistics.

    Returns information about the memory store including:
    - Total entries stored
    - Session information
    - Storage usage
    - Entry breakdown by type

    Returns:
        Formatted status report
    """
    store = _get_memory_store()
    sid = _get_session_id()

    stats = await store.get_stats_async()
    session = await store.get_session_async(sid)

    # Format storage size
    size_kb = stats.storage_size_bytes / 1024
    if size_kb > 1024:
        size_str = f"{size_kb / 1024:.1f} MB"
    else:
        size_str = f"{size_kb:.1f} KB"

    lines = [
        "# RLM Memory Status",
        "",
        "## Current Session",
        f"- Session ID: {sid}",
    ]

    if session:
        duration = session.last_activity - session.started_at
        hours = duration.total_seconds() / 3600
        lines.extend([
            f"- Started: {session.started_at.strftime('%Y-%m-%d %H:%M')}",
            f"- Duration: {hours:.1f} hours",
            f"- Entries in session: {session.entry_count}",
        ])
    else:
        lines.append("- Status: New session (no entries yet)")

    lines.extend([
        "",
        "## Overall Statistics",
        f"- Total entries: {stats.total_entries}",
        f"- Total sessions: {stats.session_count}",
        f"- Storage size: {size_str}",
    ])

    if stats.entries_by_type:
        lines.extend(["", "## Entry Breakdown"])
        for entry_type, count in sorted(stats.entries_by_type.items()):
            lines.append(f"- {entry_type}: {count}")

    if stats.oldest_entry and stats.newest_entry:
        lines.extend([
            "",
            "## Time Range",
            f"- Oldest entry: {stats.oldest_entry.strftime('%Y-%m-%d %H:%M')}",
            f"- Newest entry: {stats.newest_entry.strftime('%Y-%m-%d %H:%M')}",
        ])

    return "\n".join(lines)


@mcp.tool()
async def rlm_clear_session(session_id: str | None = None, confirm: bool = False) -> str:
    """Clear all entries for a session.

    WARNING: This permanently deletes all memory entries for the specified session.

    Args:
        session_id: Session ID to clear (uses current session if not provided)
        confirm: Must be True to actually delete (safety check)

    Returns:
        Confirmation of deletion or error message
    """
    if not confirm:
        return "Safety check: Set confirm=True to actually delete the session data."

    store = _get_memory_store()
    sid = session_id or _get_session_id()

    deleted = await store.clear_session_async(sid)
    logger.info(f"Cleared session {sid}: {deleted} entries deleted")

    return f"Session {sid} cleared. {deleted} entries deleted."


# =============================================================================
# Server Entry Point
# =============================================================================


def main():
    """Run the MCP server."""
    logger.info("Starting RLM Memory MCP server...")
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
