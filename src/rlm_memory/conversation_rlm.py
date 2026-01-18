"""RLM integration layer for conversation memory.

Uses RLM's recursive decomposition capabilities for intelligent
context retrieval and summarization.
"""

import os
from datetime import datetime
from typing import Any

from rlm_memory.memory_store import MemoryStore
from rlm_memory.retriever import IntelligentRetriever, RetrievalConfig, format_entries_for_context
from rlm_memory.types import MemoryEntry, SummarizeScope, TimeRange, Verbosity


# RLM prompts for memory operations
RETRIEVAL_PROMPT = """You are analyzing conversation memory to find information relevant to a query.

QUERY: {query}

CONVERSATION MEMORY (chronological):
{memory_content}

Your task:
1. Identify which parts of the memory are most relevant to the query
2. Extract the key information that answers or relates to the query
3. Summarize findings concisely while preserving important details

Output format:
- Start with a direct answer if one exists
- Include relevant context and details
- Reference specific interactions when helpful
- If the query cannot be answered from memory, say so clearly

RELEVANT FINDINGS:"""


SUMMARIZATION_PROMPT = """You are creating a summary of conversation memory.

SCOPE: {scope}
{scope_details}

CONVERSATION MEMORY:
{memory_content}

Create a concise but comprehensive summary that:
1. Captures key decisions made
2. Notes important code changes or file operations
3. Preserves critical technical details
4. Highlights unresolved questions or pending tasks

Format the summary with clear sections if appropriate.

SUMMARY:"""


NATURAL_RECALL_PROMPT = """You are helping recall information from conversation memory based on a natural language query.

USER QUERY: {query}
VERBOSITY LEVEL: {verbosity}

CONVERSATION MEMORY:
{memory_content}

Based on the user's query and verbosity level:
- brief: Give a 1-2 sentence answer with just the key facts
- detailed: Provide a thorough answer with context and relevant details
- full: Include everything relevant, with code snippets and exact quotes where helpful

RESPONSE:"""


class ConversationRLM:
    """RLM-powered conversation memory operations.

    Provides intelligent retrieval and summarization using RLM's
    recursive decomposition patterns for processing large contexts.
    """

    def __init__(
        self,
        memory_store: MemoryStore,
        backend: str = "openai",
        backend_kwargs: dict[str, Any] | None = None,
        use_rlm: bool = True,
        max_depth: int = 1,
    ):
        """Initialize ConversationRLM.

        Args:
            memory_store: The memory store to operate on.
            backend: LLM backend to use (openai, anthropic, etc.).
            backend_kwargs: Additional kwargs for the backend client.
            use_rlm: Whether to use RLM for recursive processing. If False,
                    uses simple retriever without LLM calls.
            max_depth: Maximum RLM recursion depth.
        """
        self.memory_store = memory_store
        self.backend = backend
        self.backend_kwargs = backend_kwargs or {}
        self.use_rlm = use_rlm
        self.max_depth = max_depth

        self.retriever = IntelligentRetriever(
            memory_store,
            RetrievalConfig(max_tokens=4000),
        )

        self._rlm = None
        self._client = None

    def _get_rlm(self):
        """Lazy-initialize RLM instance."""
        if self._rlm is None and self.use_rlm:
            try:
                from rlm import RLM

                # Set up backend kwargs with defaults
                kwargs = {"model_name": "gpt-4o-mini"}
                kwargs.update(self.backend_kwargs)

                # Add API key from env if not provided
                if "api_key" not in kwargs:
                    if self.backend == "openai":
                        kwargs["api_key"] = os.environ.get("OPENAI_API_KEY")
                    elif self.backend == "anthropic":
                        kwargs["api_key"] = os.environ.get("ANTHROPIC_API_KEY")

                self._rlm = RLM(
                    backend=self.backend,
                    backend_kwargs=kwargs,
                    environment="local",
                    max_depth=self.max_depth,
                    max_iterations=10,
                    verbose=False,
                )
            except ImportError:
                # RLM not available, fall back to simple retrieval
                self.use_rlm = False
            except Exception:
                # RLM initialization failed, fall back
                self.use_rlm = False

        return self._rlm

    def _get_client(self):
        """Get a simple LLM client for non-RLM operations."""
        if self._client is None:
            try:
                from rlm.clients import get_client

                kwargs = {"model_name": "gpt-4o-mini"}
                kwargs.update(self.backend_kwargs)

                if "api_key" not in kwargs:
                    if self.backend == "openai":
                        kwargs["api_key"] = os.environ.get("OPENAI_API_KEY")
                    elif self.backend == "anthropic":
                        kwargs["api_key"] = os.environ.get("ANTHROPIC_API_KEY")

                self._client = get_client(self.backend, kwargs)
            except Exception:
                self._client = None

        return self._client

    def retrieve_relevant(
        self,
        query: str,
        session_id: str | None = None,
        time_range: TimeRange = "all",
        max_tokens: int = 4000,
    ) -> str:
        """Retrieve relevant context for a query.

        Uses multi-strategy retrieval, optionally enhanced with RLM
        for intelligent filtering and summarization of results.

        Args:
            query: The query to find relevant context for.
            session_id: Optional session filter.
            time_range: Time range filter.
            max_tokens: Maximum tokens to return.

        Returns:
            Formatted relevant context string.
        """
        # First, use retriever to get candidates
        result = self.retriever.retrieve(
            query=query,
            session_id=session_id,
            time_range=time_range,
            max_results=50,
        )

        if not result.entries:
            return "No relevant memories found for this query."

        # Format entries for context
        memory_content = format_entries_for_context(
            result.entries,
            max_tokens=max_tokens,
        )

        # If RLM available and we have substantial content, use it to refine
        rlm = self._get_rlm()
        if rlm and len(result.entries) > 5:
            try:
                prompt = RETRIEVAL_PROMPT.format(
                    query=query,
                    memory_content=memory_content,
                )
                rlm_result = rlm.completion(prompt)
                return rlm_result.response
            except Exception:
                # Fall back to raw retrieval results
                pass

        # Without RLM, try simple LLM call
        client = self._get_client()
        if client and len(result.entries) > 3:
            try:
                prompt = RETRIEVAL_PROMPT.format(
                    query=query,
                    memory_content=memory_content,
                )
                return client.completion(prompt)
            except Exception:
                pass

        # Fall back to formatted entries
        return memory_content

    async def retrieve_relevant_async(
        self,
        query: str,
        session_id: str | None = None,
        time_range: TimeRange = "all",
        max_tokens: int = 4000,
    ) -> str:
        """Retrieve relevant context asynchronously."""
        result = await self.retriever.retrieve_async(
            query=query,
            session_id=session_id,
            time_range=time_range,
            max_results=50,
        )

        if not result.entries:
            return "No relevant memories found for this query."

        memory_content = format_entries_for_context(
            result.entries,
            max_tokens=max_tokens,
        )

        # For async, we use the client's acompletion if available
        client = self._get_client()
        if client and len(result.entries) > 3:
            try:
                prompt = RETRIEVAL_PROMPT.format(
                    query=query,
                    memory_content=memory_content,
                )
                return await client.acompletion(prompt)
            except Exception:
                pass

        return memory_content

    def summarize(
        self,
        scope: SummarizeScope,
        session_id: str | None = None,
        topic: str | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
    ) -> str:
        """Generate an intelligent summary of conversation memory.

        Args:
            scope: Summary scope (session, topic, or range).
            session_id: Session to summarize (for session scope).
            topic: Topic to summarize (for topic scope).
            start_time: Start of range (for range scope).
            end_time: End of range (for range scope).

        Returns:
            Summary text.
        """
        # Build scope details
        scope_details = ""
        entries = []

        if scope == "session":
            if session_id:
                scope_details = f"Session ID: {session_id}"
                entries = self.memory_store.get_entries(session_id=session_id, limit=500)
            else:
                # Get most recent session
                stats = self.memory_store.get_stats()
                if stats.session_count > 0:
                    entries = self.memory_store.get_entries(limit=500)
                    if entries:
                        session_id = entries[0].session_id
                        scope_details = f"Most recent session: {session_id}"

        elif scope == "topic":
            if topic:
                scope_details = f"Topic: {topic}"
                # Use retriever to find topic-related entries
                result = self.retriever.retrieve(query=topic, max_results=100)
                entries = result.entries

        elif scope == "range":
            scope_details = f"Time range: {start_time} to {end_time}"
            entries = self.memory_store.get_entries(limit=500)
            # Filter by time range
            if start_time:
                entries = [e for e in entries if e.timestamp >= start_time]
            if end_time:
                entries = [e for e in entries if e.timestamp <= end_time]

        if not entries:
            return f"No entries found for {scope} summary."

        memory_content = format_entries_for_context(entries, max_tokens=6000)

        # Try to use LLM for intelligent summarization
        client = self._get_client()
        if client:
            try:
                prompt = SUMMARIZATION_PROMPT.format(
                    scope=scope,
                    scope_details=scope_details,
                    memory_content=memory_content,
                )
                return client.completion(prompt)
            except Exception:
                pass

        # Fall back to basic summary from memory store
        if session_id:
            return self.memory_store.get_session_summary(session_id)

        # Very basic summary
        return f"Summary of {len(entries)} entries:\n\n" + memory_content[:2000]

    async def summarize_async(
        self,
        scope: SummarizeScope,
        session_id: str | None = None,
        topic: str | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
    ) -> str:
        """Generate summary asynchronously."""
        scope_details = ""
        entries = []

        if scope == "session":
            if session_id:
                scope_details = f"Session ID: {session_id}"
                entries = await self.memory_store.get_entries_async(session_id=session_id, limit=500)
            else:
                entries = await self.memory_store.get_entries_async(limit=500)
                if entries:
                    session_id = entries[0].session_id
                    scope_details = f"Most recent session: {session_id}"

        elif scope == "topic":
            if topic:
                scope_details = f"Topic: {topic}"
                result = await self.retriever.retrieve_async(query=topic, max_results=100)
                entries = result.entries

        elif scope == "range":
            scope_details = f"Time range: {start_time} to {end_time}"
            entries = await self.memory_store.get_entries_async(limit=500)
            if start_time:
                entries = [e for e in entries if e.timestamp >= start_time]
            if end_time:
                entries = [e for e in entries if e.timestamp <= end_time]

        if not entries:
            return f"No entries found for {scope} summary."

        memory_content = format_entries_for_context(entries, max_tokens=6000)

        client = self._get_client()
        if client:
            try:
                prompt = SUMMARIZATION_PROMPT.format(
                    scope=scope,
                    scope_details=scope_details,
                    memory_content=memory_content,
                )
                return await client.acompletion(prompt)
            except Exception:
                pass

        return f"Summary of {len(entries)} entries:\n\n" + memory_content[:2000]

    def recall(
        self,
        what: str,
        session_id: str | None = None,
        verbosity: Verbosity = "detailed",
    ) -> str:
        """Natural language recall from conversation memory.

        Args:
            what: Natural language query (e.g., "what did we decide about X").
            session_id: Optional session filter.
            verbosity: Response verbosity level.

        Returns:
            Recalled information.
        """
        # Get relevant entries
        result = self.retriever.retrieve(
            query=what,
            session_id=session_id,
            max_results=30,
        )

        if not result.entries:
            return "I don't have any memories related to that query."

        memory_content = format_entries_for_context(
            result.entries,
            max_tokens=4000,
        )

        # Try LLM for natural response
        client = self._get_client()
        if client:
            try:
                prompt = NATURAL_RECALL_PROMPT.format(
                    query=what,
                    verbosity=verbosity,
                    memory_content=memory_content,
                )
                return client.completion(prompt)
            except Exception:
                pass

        # Fallback: return formatted entries with verbosity adjustment
        if verbosity == "brief":
            # Just first few entries, truncated
            brief_entries = result.entries[:3]
            return format_entries_for_context(brief_entries, max_tokens=500)
        elif verbosity == "full":
            return memory_content
        else:  # detailed
            return format_entries_for_context(result.entries[:10], max_tokens=2000)

    async def recall_async(
        self,
        what: str,
        session_id: str | None = None,
        verbosity: Verbosity = "detailed",
    ) -> str:
        """Natural language recall asynchronously."""
        result = await self.retriever.retrieve_async(
            query=what,
            session_id=session_id,
            max_results=30,
        )

        if not result.entries:
            return "I don't have any memories related to that query."

        memory_content = format_entries_for_context(
            result.entries,
            max_tokens=4000,
        )

        client = self._get_client()
        if client:
            try:
                prompt = NATURAL_RECALL_PROMPT.format(
                    query=what,
                    verbosity=verbosity,
                    memory_content=memory_content,
                )
                return await client.acompletion(prompt)
            except Exception:
                pass

        if verbosity == "brief":
            return format_entries_for_context(result.entries[:3], max_tokens=500)
        elif verbosity == "full":
            return memory_content
        else:
            return format_entries_for_context(result.entries[:10], max_tokens=2000)

    def close(self):
        """Clean up resources."""
        if self._rlm is not None:
            try:
                self._rlm.close()
            except Exception:
                pass
            self._rlm = None
        self._client = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False
