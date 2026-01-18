"""Session start hook for RLM Memory.

This hook runs when a Claude Code session starts. It:
1. Initializes or resumes a session in the memory store
2. Loads session metadata
3. Outputs a system message with memory status
"""

import json
import os
import sys
import uuid
from datetime import datetime

# Add parent to path for imports when run as script
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from rlm_memory.memory_store import MemoryStore
from rlm_memory.types import MemoryEntry


def main():
    """Main hook entry point."""
    # Read hook input from stdin
    try:
        hook_input = json.loads(sys.stdin.read()) if not sys.stdin.isatty() else {}
    except (json.JSONDecodeError, Exception):
        hook_input = {}

    # Get or create session ID
    session_id = os.environ.get("RLM_SESSION_ID")
    if not session_id:
        # Generate a new session ID
        session_id = str(uuid.uuid4())[:8]
        # Note: We can't set env vars for the parent process,
        # but we output it for Claude to use

    # Initialize memory store
    storage_dir = os.environ.get("RLM_STORAGE_DIR", ".rlm-memory")
    store = MemoryStore(storage_dir)
    store.initialize()

    # Check for existing session
    session = store.get_session(session_id)

    # Build status message
    if session:
        # Resuming existing session
        duration = datetime.now() - session.started_at
        hours = duration.total_seconds() / 3600

        status_parts = [
            f"RLM Memory session resumed (ID: {session_id})",
            f"Session has {session.entry_count} stored entries",
            f"Session duration: {hours:.1f} hours",
        ]

        # Get recent high-importance entries
        recent = store.get_entries(
            session_id=session_id,
            importance=["high", "critical"],
            limit=3,
        )

        if recent:
            status_parts.append("Recent important context available:")
            for entry in recent:
                preview = entry.content[:100].replace("\n", " ")
                status_parts.append(f"  - [{entry.entry_type}] {preview}...")
    else:
        # New session
        status_parts = [
            f"RLM Memory initialized (Session ID: {session_id})",
            "Conversation memory is active and ready to store context.",
        ]

        # Store session start entry
        entry = MemoryEntry.create(
            session_id=session_id,
            entry_type="assistant_message",
            content=f"Session started at {datetime.now().isoformat()}",
            metadata={"event": "session_start"},
            importance="low",
        )
        store.add_entry(entry)

    # Get overall stats
    stats = store.get_stats()
    if stats.total_entries > 0:
        status_parts.append(f"Total memory: {stats.total_entries} entries across {stats.session_count} sessions")

    # Output hook response
    response = {
        "continue": True,
        "systemMessage": "\n".join(status_parts),
        "hookSpecificOutput": {
            "sessionId": session_id,
            "isNewSession": session is None,
            "entryCount": session.entry_count if session else 0,
        },
    }

    print(json.dumps(response))


if __name__ == "__main__":
    main()
