# RLM Memory Plugin - Usage Guide

This guide explains how to instruct Claude Code to effectively use the RLM Memory plugin for conversation context management.

## Table of Contents

1. [System Prompt Configuration](#system-prompt-configuration)
2. [In-Chat Instructions](#in-chat-instructions)
3. [Best Practices](#best-practices)
4. [Example Workflows](#example-workflows)

---

## System Prompt Configuration

Add the following to your project's `CLAUDE.md` file to automatically instruct Claude on how to use the memory system.

### Basic Configuration

```markdown
## RLM Memory System

This project uses the RLM Memory plugin for conversation context management. The plugin provides tools to store and retrieve conversation context that persists across context compaction.

### When to Store Memories

- **Decisions**: When we make important architectural or implementation decisions, store them using `rlm_store_decision`
- **File Operations**: Significant file changes are automatically tracked, but you can add context with `rlm_store_file_op`
- **Key Context**: If something seems important for future reference, store it with `rlm_store_message`

### When to Recall Memories

- Before implementing features that may have been discussed earlier
- When I reference past decisions or work ("remember when we...", "like we did before")
- When context seems to be missing about prior work in this session

### Available Commands

- `/memory-status` - Check memory status
- `/memory-search <query>` - Search past context
- `/memory-export` - Export session summary
```

### Comprehensive Configuration

For more proactive memory usage, add this extended configuration:

```markdown
## RLM Memory System

This project uses the RLM Memory plugin for lossless conversation context management.

### Memory Tools Available

| Tool | Purpose | When to Use |
|------|---------|-------------|
| `rlm_store_decision` | Record important decisions | Architecture choices, technology selections, approach decisions |
| `rlm_store_message` | Store key messages | Important context, requirements, constraints |
| `rlm_store_tool_result` | Record tool outputs | Significant command results, search findings |
| `rlm_store_file_op` | Track file changes | Major file modifications with context |
| `rlm_query` | Search memories | Find relevant past context |
| `rlm_recall` | Natural language recall | Answer questions about past work |
| `rlm_summarize` | Generate summaries | Session or topic summaries |
| `rlm_status` | Check memory status | View stored entries and session info |

### Proactive Memory Management

1. **At the start of significant work**: Check if relevant context exists with `rlm_query`
2. **After making decisions**: Store with `rlm_store_decision` including context and alternatives considered
3. **Before context compaction**: The pre-compact hook handles this automatically
4. **When referencing past work**: Use `rlm_recall` to retrieve accurate information

### Memory Recall Triggers

Use memory recall when you see phrases like:
- "remember when we..."
- "like we discussed..."
- "what did we decide about..."
- "earlier we..."
- "go back to..."
- "as we planned..."

### Decision Recording Format

When storing decisions, include:
- The decision itself
- Why it was made (context)
- Alternatives that were considered
```

### Minimal Configuration

If you prefer Claude to use memory only when explicitly requested:

```markdown
## RLM Memory

Memory tools are available via the RLM Memory plugin. Use them when I explicitly ask to:
- Remember something: `rlm_store_decision` or `rlm_store_message`
- Recall something: `rlm_recall` or `rlm_query`
- Check memory: `rlm_status`

Don't proactively store or recall unless I ask.
```

---

## In-Chat Instructions

Use these phrases to instruct Claude on memory usage during conversation.

### Storing Context

```
Remember this decision: [your decision]

Store this for later: [important context]

Make a note that we decided to [decision] because [reason]

Save this architecture decision - we're using [choice] instead of [alternative] because [reasoning]
```

### Recalling Context

```
What did we decide about [topic]?

Recall our earlier discussion about [topic]

What was the approach we planned for [feature]?

Search memory for [keyword]

/memory-search authentication
```

### Session Management

```
Show me the memory status

/memory-status

Summarize what we've done this session

/memory-export

What important decisions have we made?
```

### Proactive Instructions

```
For this session, please:
- Store all architectural decisions
- Record the reasoning behind technology choices
- Note any constraints or requirements we discuss

Before implementing [feature], check if we discussed it earlier

After each major change, briefly note what was done and why
```

### One-Time Instructions

```
Use the memory system to track our decisions during this refactoring

Check memory for any context about the authentication system before we modify it

Store this conversation about [topic] - we might need it later
```

---

## Best Practices

### What to Store

**DO Store:**
- Architectural decisions with reasoning
- Technology choices and why alternatives were rejected
- Important requirements or constraints
- Complex implementation approaches
- Debugging findings that took effort to discover
- Configuration decisions
- API design decisions

**DON'T Store:**
- Trivial changes or routine operations
- Information easily found in code/docs
- Temporary debugging steps
- Every single message

### When to Recall

**DO Recall:**
- Before implementing features discussed earlier
- When user references past decisions
- When context about prior work would help
- Before making changes to previously discussed code

**DON'T Recall:**
- For every single query
- When context is clearly in the current conversation
- For simple, isolated tasks

### Memory Hygiene

```markdown
## Memory Hygiene Guidelines

- Keep stored content concise but complete
- Include context and reasoning, not just facts
- Use appropriate importance levels:
  - `critical`: Must never forget (breaking changes, security decisions)
  - `high`: Important decisions and context
  - `medium`: Useful background (default)
  - `low`: Nice to have
```

---

## Example Workflows

### Feature Development Workflow

```
User: Let's implement user authentication

Claude: Before starting, let me check if we have any prior context about authentication.
[Uses rlm_query with "authentication"]

Claude: I found we previously discussed using JWT tokens. Let me proceed with that approach.
[Implements feature]

Claude: I'll record the key decisions we made.
[Uses rlm_store_decision: "Implemented JWT authentication with refresh tokens,
using httpOnly cookies for storage. Chose this over session-based auth for
better scalability with our planned microservices architecture."]
```

### Long Session Workflow

```
User: We've been working for a while. What have we accomplished?

Claude: [Uses rlm_summarize with scope="session"]

Here's a summary of our session:
- Implemented user authentication with JWT
- Set up database migrations
- Created API endpoints for user management
- Decided to use PostgreSQL over MongoDB for ACID compliance
```

### Context Recovery After Compaction

```
User: Continue with the API implementation we discussed

Claude: Let me recall our API discussion.
[Uses rlm_recall with "API implementation plan"]

Based on our earlier discussion, we planned to:
1. Create RESTful endpoints for users
2. Use OpenAPI for documentation
3. Implement rate limiting with Redis

Let me continue from where we left off...
```

### Decision Documentation Workflow

```
User: Should we use Redis or Memcached for caching?

Claude: [Analyzes requirements, makes recommendation]

I recommend Redis because [reasons]. Memcached would be simpler but lacks
persistence and data structures we need.

[Uses rlm_store_decision:
  decision: "Using Redis for caching layer"
  context: "Need persistence, sorted sets for leaderboards, pub/sub for real-time features"
  alternatives: "Memcached considered but lacks required features"]
```

---

## Quick Reference Card

### Store Commands
| What | Tool | Example |
|------|------|---------|
| Decision | `rlm_store_decision` | Architecture choice with reasoning |
| Message | `rlm_store_message` | Important user requirement |
| Tool Result | `rlm_store_tool_result` | Significant command output |
| File Change | `rlm_store_file_op` | Major code modification |

### Retrieve Commands
| What | Tool | Example |
|------|------|---------|
| Keyword Search | `rlm_query` | Find entries about "authentication" |
| Natural Language | `rlm_recall` | "What did we decide about the API?" |
| Summary | `rlm_summarize` | Session or topic overview |
| Status | `rlm_status` | Memory statistics |

### Slash Commands
| Command | Purpose |
|---------|---------|
| `/memory-status` | Show memory statistics |
| `/memory-search <query>` | Search conversation memory |
| `/memory-clear` | Clear session (with confirmation) |
| `/memory-export` | Export session summary |

---

## Troubleshooting

### Memory Not Being Used

If Claude isn't using memory tools, try:
1. Add explicit instructions to CLAUDE.md
2. Use direct commands: "Use rlm_recall to find..."
3. Reference the tools by name in your request

### Too Much Memory Usage

If Claude is storing too much:
1. Use the minimal configuration
2. Add: "Only store decisions, not routine operations"
3. Specify: "Don't proactively store memories"

### Missing Context After Compaction

The pre-compact hook should preserve context automatically. If context is still missing:
1. Check `/memory-status` to verify entries exist
2. Use explicit recall: "Check memory for [topic]"
3. Verify hooks are configured in `hooks/hooks.json`

---

## Configuration Files Reference

### CLAUDE.md Location
- Project-specific: `<project-root>/CLAUDE.md`
- Global: `~/.claude/CLAUDE.md`

### Plugin Location
- Project-specific: `<project-root>/.claude/plugins/rlm-memory/`
- Global: `~/.claude/plugins/rlm-memory/`

### MCP Server Config
The `.mcp.json` in the plugin directory configures the server. Environment variables:
- `RLM_STORAGE_DIR`: Where to store the database
- `RLM_SESSION_ID`: Custom session identifier
- `RLM_LOG_LEVEL`: Logging verbosity (debug, info, warning, error)
