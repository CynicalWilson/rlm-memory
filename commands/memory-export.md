---
name: memory-export
description: Export conversation memory to a summary
allowed-tools: ["mcp__plugin_rlm-memory_rlm-memory__rlm_summarize", "mcp__plugin_rlm-memory_rlm-memory__rlm_status"]
---

Export and summarize the conversation memory.

Arguments: $ARGUMENTS

If arguments specify a topic, use rlm_summarize with scope="topic" and the specified topic.
If arguments specify a time range, use rlm_summarize with scope="range".
Otherwise, use rlm_summarize with scope="session" to get a full session summary.

The summary will include:
- Key decisions made
- Important code changes
- File operations
- Critical technical details

Present the summary in a clear, organized format.
