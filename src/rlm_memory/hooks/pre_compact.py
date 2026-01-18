"""Pre-compact hook for RLM Memory.

This hook runs before Claude Code performs context compaction. It:
1. Receives the current conversation context
2. Stores the full context in RLM memory before compaction
3. Generates a summary of critical information
4. Returns preserved context hints for the compaction process
"""

import json
import os
import sys
from datetime import datetime

# Add parent to path for imports when run as script
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from rlm_memory.memory_store import MemoryStore
from rlm_memory.conversation_rlm import ConversationRLM
from rlm_memory.types import MemoryEntry


def extract_key_points(content: str, max_points: int = 5) -> list[str]:
    """Extract key points from content for the summary.

    This is a simple extraction that looks for:
    - Decisions (mentions of "decided", "chose", "will use")
    - File operations (file paths)
    - Code changes (function/class names)
    """
    key_points = []
    lines = content.split("\n")

    decision_keywords = ["decided", "chose", "will use", "going to", "approach", "solution"]
    code_keywords = ["function", "class", "def ", "implement", "create", "add"]

    for line in lines:
        line_lower = line.lower()

        # Check for decisions
        if any(kw in line_lower for kw in decision_keywords):
            if len(line) < 200:
                key_points.append(f"Decision: {line.strip()}")

        # Check for code-related
        elif any(kw in line_lower for kw in code_keywords):
            if len(line) < 200:
                key_points.append(f"Code: {line.strip()}")

        # Check for file paths (simple heuristic)
        elif "/" in line or "\\" in line:
            # Looks like it might contain a file path
            if len(line) < 150:
                key_points.append(f"File: {line.strip()}")

        if len(key_points) >= max_points:
            break

    return key_points[:max_points]


def main():
    """Main hook entry point."""
    # Read hook input from stdin
    try:
        raw_input = sys.stdin.read() if not sys.stdin.isatty() else "{}"
        hook_input = json.loads(raw_input) if raw_input.strip() else {}
    except (json.JSONDecodeError, Exception):
        hook_input = {}

    # Get session ID
    session_id = os.environ.get("RLM_SESSION_ID", "unknown")

    # Initialize memory store
    storage_dir = os.environ.get("RLM_STORAGE_DIR", ".rlm-memory")
    store = MemoryStore(storage_dir)
    store.initialize()

    # Extract conversation context from hook input
    conversation = hook_input.get("conversation", "")
    messages = hook_input.get("messages", [])

    # If we have messages, convert to text
    if messages and not conversation:
        conversation_parts = []
        for msg in messages:
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            if isinstance(content, list):
                # Handle content blocks
                content = " ".join(
                    block.get("text", "") for block in content
                    if isinstance(block, dict) and "text" in block
                )
            conversation_parts.append(f"[{role}]: {content}")
        conversation = "\n\n".join(conversation_parts)

    preserved_refs = []

    if conversation:
        # Store the full context before compaction
        entry = MemoryEntry.create(
            session_id=session_id,
            entry_type="summary",
            content=f"Pre-compact context snapshot:\n\n{conversation}",
            metadata={
                "event": "pre_compact",
                "timestamp": datetime.now().isoformat(),
                "message_count": len(messages) if messages else 0,
            },
            importance="high",
        )
        entry_id = store.add_entry(entry)
        preserved_refs.append(f"mem://{session_id}/{entry_id}")

        # Extract and store key points
        key_points = extract_key_points(conversation)
        if key_points:
            points_entry = MemoryEntry.create(
                session_id=session_id,
                entry_type="decision",
                content="Key points before compaction:\n" + "\n".join(f"- {p}" for p in key_points),
                metadata={"event": "pre_compact_summary"},
                importance="high",
            )
            points_id = store.add_entry(points_entry)
            preserved_refs.append(f"mem://{session_id}/{points_id}")

    # Build summary message
    summary_parts = ["Context preserved in RLM memory before compaction."]

    if preserved_refs:
        summary_parts.append(f"Stored {len(preserved_refs)} memory entries.")

    # Get session stats
    session = store.get_session(session_id)
    if session:
        summary_parts.append(f"Session now has {session.entry_count} total entries.")

    summary_parts.append("Use rlm_recall to retrieve past context if needed.")

    # Output hook response
    response = {
        "continue": True,
        "systemMessage": " ".join(summary_parts),
        "hookSpecificOutput": {
            "preservedReferences": preserved_refs,
            "entryCount": session.entry_count if session else 0,
        },
    }

    print(json.dumps(response))


if __name__ == "__main__":
    main()
