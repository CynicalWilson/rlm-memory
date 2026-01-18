---
name: memory-search
description: Search conversation memory for relevant context
allowed-tools: ["mcp__plugin_rlm-memory_rlm-memory__rlm_query", "mcp__plugin_rlm-memory_rlm-memory__rlm_recall"]
---

Search the conversation memory for: $ARGUMENTS

If the search query is a natural language question (like "what did we decide about X" or "show me the code for Y"), use the rlm_recall tool with the appropriate verbosity level.

If the search query is more of a keyword or topic search, use the rlm_query tool to find relevant entries.

Present the results clearly, highlighting the most relevant information found.
