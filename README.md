# RLM Memory - Conversation Memory for Claude Code

RLM Memory is a Claude Code plugin that provides lossless conversation memory using Recursive Language Models (RLM). Instead of losing information during context compaction, RLM Memory stores full conversation history externally and retrieves only what's relevant for each query.

## Features

- **Lossless Context Storage**: Preserves full conversation history, tool results, and file operations
- **Intelligent Retrieval**: Multi-strategy retrieval combining keyword matching, temporal relevance, and importance scoring
- **Natural Language Recall**: Ask questions like "what did we decide about X" and get relevant context
- **Automatic Tracking**: Hooks automatically capture significant tool operations
- **Session Management**: Track and manage multiple conversation sessions
- **RLM Integration**: Optional recursive LLM calls for intelligent summarization and retrieval

## Installation

### Prerequisites

- Python 3.11 or higher
- [uv](https://docs.astral.sh/uv/) package manager
- Claude Code CLI

### Install the Plugin

1. Clone or copy the `rlm-memory` directory to your Claude Code plugins location:

```bash
# Copy to your project or global plugins directory
cp -r rlm-memory ~/.claude/plugins/
```

2. Install dependencies:

```bash
cd ~/.claude/plugins/rlm-memory
uv sync
```

3. The plugin will be automatically discovered by Claude Code on next startup.

### Manual Configuration

If auto-discovery doesn't work, add the MCP server manually to your Claude Code settings:

```json
{
  "mcpServers": {
    "rlm-memory": {
      "command": "uv",
      "args": ["run", "--directory", "/path/to/rlm-memory", "python", "-m", "rlm_memory.server"],
      "env": {
        "RLM_STORAGE_DIR": ".rlm-memory"
      }
    }
  }
}
```

## Usage

For detailed instructions on configuring Claude Code to use this plugin effectively, see the **[Usage Guide](USAGE_GUIDE.md)**.

### Quick Start: Add to CLAUDE.md

Add this to your project's `CLAUDE.md` to enable proactive memory usage:

```markdown
## RLM Memory System

This project uses RLM Memory for conversation context management.

- Store important decisions with `rlm_store_decision`
- Recall past context with `rlm_recall` when I reference earlier work
- Check memory status with `/memory-status`
```

### MCP Tools

The plugin provides the following tools accessible to Claude:

#### Storage Tools

- **`rlm_store_message`** - Store conversation messages
  ```
  Store important messages that may be needed later
  ```

- **`rlm_store_tool_result`** - Store tool execution results
  ```
  Record significant tool operations like file edits or bash commands
  ```

- **`rlm_store_decision`** - Store important decisions
  ```
  Record key decisions about architecture or implementation
  ```

- **`rlm_store_file_op`** - Store file operations
  ```
  Track file modifications for later reference
  ```

#### Retrieval Tools

- **`rlm_query`** - Search memory with intelligent retrieval
  ```
  Search conversation memory for entries relevant to a query
  ```

- **`rlm_recall`** - Natural language recall
  ```
  Ask questions like "what did we decide about the API design"
  ```

- **`rlm_summarize`** - Generate intelligent summaries
  ```
  Create summaries of sessions, topics, or time ranges
  ```

#### Management Tools

- **`rlm_status`** - Get memory status and statistics
- **`rlm_clear_session`** - Clear session data (requires confirmation)

### Plugin Commands

Use these slash commands in Claude Code:

- `/memory-status` - Show current memory status
- `/memory-search <query>` - Search conversation memory
- `/memory-clear` - Clear current session (with confirmation)
- `/memory-export` - Export session summary

### Hooks

The plugin automatically captures context through hooks:

- **SessionStart**: Initializes memory session on startup
- **PreCompact**: Stores full context before compaction
- **PostToolUse**: Records significant tool operations (Write, Edit, Bash)
- **UserPromptSubmit**: Suggests using recall for context-referencing queries

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `RLM_STORAGE_DIR` | `.rlm-memory` | Directory for SQLite database |
| `RLM_SESSION_ID` | Auto-generated | Session identifier |
| `RLM_LOG_LEVEL` | `info` | Logging level |
| `RLM_BACKEND` | `openai` | LLM backend for intelligent retrieval |
| `RLM_USE_RLM` | `true` | Enable RLM recursive processing |
| `OPENAI_API_KEY` | - | Required for intelligent retrieval |

### Storage Location

By default, memory is stored in `.rlm-memory/memory.db` in your project directory. This keeps memory project-specific. For global memory, set `RLM_STORAGE_DIR` to a global path.

## Architecture

```
rlm-memory/
├── .claude-plugin/
│   └── plugin.json          # Plugin manifest
├── .mcp.json                 # MCP server configuration
├── commands/                 # Slash commands
│   ├── memory-status.md
│   ├── memory-search.md
│   ├── memory-clear.md
│   └── memory-export.md
├── hooks/
│   └── hooks.json           # Hook configuration
├── src/rlm_memory/
│   ├── server.py            # MCP server with tools
│   ├── memory_store.py      # SQLite storage layer
│   ├── conversation_rlm.py  # RLM integration
│   ├── retriever.py         # Intelligent retrieval
│   ├── types.py             # Data types
│   └── hooks/               # Hook scripts
│       ├── session_start.py
│       ├── pre_compact.py
│       └── post_tool.py
├── tests/                   # Unit and integration tests
├── pyproject.toml
└── README.md
```

## Development

### Running Tests

```bash
cd rlm-memory
uv run pytest
```

### Running the Server Directly

```bash
uv run python -m rlm_memory.server
```

### Debugging

Set `RLM_LOG_LEVEL=debug` for verbose logging:

```bash
RLM_LOG_LEVEL=debug uv run python -m rlm_memory.server
```

## How It Works

### Storage

Memory entries are stored in SQLite with the following schema:

- **entries**: Main table with id, session_id, timestamp, entry_type, content, metadata, importance
- **sessions**: Session tracking with start time and last activity
- **large_content**: Separate storage for entries >10KB

### Retrieval

The IntelligentRetriever uses multiple strategies:

1. **Keyword matching**: Extracts keywords and calculates Jaccard similarity
2. **Temporal relevance**: Favors recent entries with configurable decay
3. **Importance scoring**: Prioritizes high-importance entries
4. **Optional RLM processing**: Uses recursive LLM calls for complex queries

### Entry Types

- `user_message` - User conversation messages
- `assistant_message` - Assistant responses
- `tool_call` - Tool invocations
- `tool_result` - Tool execution results
- `file_op` - File operations (read/write/edit/delete)
- `decision` - Important decisions
- `summary` - Generated summaries

### Importance Levels

- `low` - Background information
- `medium` - Standard entries (default)
- `high` - Important context
- `critical` - Must-preserve information

## Troubleshooting

### Plugin Not Loading

1. Check that uv is installed and in PATH
2. Verify the plugin directory structure
3. Check Claude Code logs for errors

### Memory Not Persisting

1. Verify `RLM_STORAGE_DIR` is writable
2. Check that the database file exists
3. Look for SQLite errors in logs

### Retrieval Not Finding Entries

1. Use `/memory-status` to verify entries are stored
2. Try broader search terms
3. Check time range filters

### Hooks Not Firing

1. Verify hooks.json syntax
2. Check hook script permissions
3. Review hook timeout settings

## License

MIT License - see [LICENSE](LICENSE) file for details.
