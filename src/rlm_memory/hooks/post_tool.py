"""Post-tool hook for RLM Memory.

This hook runs after significant tool operations (Write, Edit, Bash).
It captures tool call details and stores important results in memory.
"""

import json
import os
import sys
from datetime import datetime

# Add parent to path for imports when run as script
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from rlm_memory.memory_store import MemoryStore
from rlm_memory.types import MemoryEntry


def determine_importance(tool_name: str, result: dict) -> str:
    """Determine the importance level of a tool result."""
    # File operations are generally important
    if tool_name in ("Write", "Edit"):
        return "high"

    # Bash commands - check if there was an error
    if tool_name == "Bash":
        if result.get("exitCode", 0) != 0:
            return "high"  # Errors are important to remember
        # Check for significant operations
        command = result.get("command", "")
        if any(kw in command for kw in ["git commit", "git push", "npm install", "pip install", "make"]):
            return "high"
        return "medium"

    return "medium"


def summarize_tool_result(tool_name: str, tool_input: dict, result: dict) -> tuple[str, str, str]:
    """Generate summaries for a tool result.

    Returns:
        Tuple of (input_summary, output_summary, details)
    """
    if tool_name == "Write":
        file_path = tool_input.get("file_path", "unknown")
        content = tool_input.get("content", "")
        lines = content.count("\n") + 1
        input_summary = f"Write to {file_path}"
        output_summary = f"Created/updated file with {lines} lines"
        details = f"File: {file_path}\nContent preview:\n{content[:500]}..."
        return input_summary, output_summary, details

    elif tool_name == "Edit":
        file_path = tool_input.get("file_path", "unknown")
        old_string = tool_input.get("old_string", "")[:100]
        new_string = tool_input.get("new_string", "")[:100]
        input_summary = f"Edit {file_path}"
        output_summary = f"Replaced content in file"
        details = f"File: {file_path}\nOld: {old_string}...\nNew: {new_string}..."
        return input_summary, output_summary, details

    elif tool_name == "Bash":
        command = tool_input.get("command", "unknown")
        exit_code = result.get("exitCode", 0)
        stdout = result.get("stdout", "")[:500]
        stderr = result.get("stderr", "")[:200]

        input_summary = f"Command: {command[:100]}"

        if exit_code == 0:
            output_summary = f"Success"
            if stdout:
                output_summary += f" - {stdout[:100]}..."
        else:
            output_summary = f"Failed (exit {exit_code})"
            if stderr:
                output_summary += f": {stderr[:100]}"

        details = f"Command: {command}\nExit code: {exit_code}\n"
        if stdout:
            details += f"Output:\n{stdout[:1000]}"
        if stderr:
            details += f"\nErrors:\n{stderr[:500]}"

        return input_summary, output_summary, details

    # Default
    return str(tool_input)[:100], str(result)[:100], ""


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

    # Extract tool information
    tool_name = hook_input.get("toolName", "")
    tool_input = hook_input.get("toolInput", {})
    tool_result = hook_input.get("toolResult", {})

    # Skip if we don't have enough info
    if not tool_name:
        # Output minimal response
        print(json.dumps({"continue": True}))
        return

    # Initialize memory store
    storage_dir = os.environ.get("RLM_STORAGE_DIR", ".rlm-memory")
    store = MemoryStore(storage_dir)
    store.initialize()

    # Determine importance
    importance = determine_importance(tool_name, tool_result)

    # Generate summaries
    input_summary, output_summary, details = summarize_tool_result(
        tool_name, tool_input, tool_result
    )

    # Create entry type based on tool
    if tool_name in ("Write", "Edit"):
        entry_type = "file_op"
    else:
        entry_type = "tool_result"

    # Build content
    content = f"Tool: {tool_name}\nInput: {input_summary}\nResult: {output_summary}"
    if details:
        content += f"\n\nDetails:\n{details}"

    # Store the entry
    entry = MemoryEntry.create(
        session_id=session_id,
        entry_type=entry_type,
        content=content,
        metadata={
            "tool_name": tool_name,
            "input_summary": input_summary,
            "output_summary": output_summary,
            "timestamp": datetime.now().isoformat(),
        },
        importance=importance,
    )

    entry_id = store.add_entry(entry)

    # Output hook response (minimal - we don't want to add system messages for every tool)
    response = {
        "continue": True,
        "hookSpecificOutput": {
            "entryId": entry_id,
            "toolName": tool_name,
            "importance": importance,
        },
    }

    print(json.dumps(response))


if __name__ == "__main__":
    main()
