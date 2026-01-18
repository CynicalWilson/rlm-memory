---
name: memory-clear
description: Clear conversation memory for the current session
allowed-tools: ["mcp__plugin_rlm-memory_rlm-memory__rlm_clear_session", "mcp__plugin_rlm-memory_rlm-memory__rlm_status"]
---

Clear the RLM memory for the current session.

**WARNING**: This will permanently delete all stored memories for this session.

Before clearing:
1. First show the current memory status using rlm_status
2. Ask the user to confirm they want to delete all memories
3. Only if confirmed, use rlm_clear_session with confirm=True

After clearing, show the updated status to confirm the memory was cleared.
