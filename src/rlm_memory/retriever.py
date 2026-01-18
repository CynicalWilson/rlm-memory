"""Intelligent retrieval strategies for memory entries."""

import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from rlm_memory.types import MemoryEntry, RetrievalResult, TimeRange


@dataclass
class RetrievalConfig:
    """Configuration for retrieval operations."""

    max_tokens: int = 4000
    semantic_weight: float = 0.4
    temporal_weight: float = 0.3
    importance_weight: float = 0.2
    keyword_weight: float = 0.1
    min_relevance_score: float = 0.1


class IntelligentRetriever:
    """Multi-strategy retriever for memory entries.

    Combines multiple retrieval strategies to find the most relevant memories:
    1. Keyword matching - exact and fuzzy text matching
    2. Temporal relevance - prioritizes recent entries
    3. Importance scoring - considers entry importance levels
    4. Type filtering - filters by entry types when relevant
    """

    def __init__(self, memory_store: "MemoryStore", config: RetrievalConfig | None = None):
        """Initialize the retriever.

        Args:
            memory_store: The memory store to retrieve from.
            config: Optional retrieval configuration.
        """
        self.memory_store = memory_store
        self.config = config or RetrievalConfig()

    def retrieve(
        self,
        query: str,
        session_id: str | None = None,
        time_range: TimeRange = "all",
        entry_types: list[str] | None = None,
        max_results: int = 20,
    ) -> RetrievalResult:
        """Retrieve relevant memories using multiple strategies.

        Args:
            query: The search query.
            session_id: Optional session filter.
            time_range: Time range filter.
            entry_types: Optional entry type filters.
            max_results: Maximum number of results.

        Returns:
            RetrievalResult with scored entries.
        """
        start_time = time.time()

        # Get candidate entries
        candidates = self.memory_store.get_entries(
            session_id=session_id,
            entry_types=entry_types,
            time_range=time_range,
            limit=max_results * 5,  # Get more candidates for scoring
        )

        if not candidates:
            return RetrievalResult(
                entries=[],
                query=query,
                relevance_scores=[],
                retrieval_time_ms=0,
                tokens_used=0,
            )

        # Score each candidate
        scored_entries: list[tuple[MemoryEntry, float]] = []
        query_keywords = self._extract_keywords(query)

        for entry in candidates:
            score = self._calculate_relevance_score(entry, query, query_keywords)
            if score >= self.config.min_relevance_score:
                scored_entries.append((entry, score))

        # Sort by score and take top results
        scored_entries.sort(key=lambda x: x[1], reverse=True)
        top_entries = scored_entries[:max_results]

        # Estimate tokens used
        tokens_used = sum(len(e.content.split()) for e, _ in top_entries)

        elapsed_ms = (time.time() - start_time) * 1000

        return RetrievalResult(
            entries=[e for e, _ in top_entries],
            query=query,
            relevance_scores=[s for _, s in top_entries],
            retrieval_time_ms=elapsed_ms,
            tokens_used=tokens_used,
        )

    async def retrieve_async(
        self,
        query: str,
        session_id: str | None = None,
        time_range: TimeRange = "all",
        entry_types: list[str] | None = None,
        max_results: int = 20,
    ) -> RetrievalResult:
        """Retrieve relevant memories asynchronously."""
        start_time = time.time()

        candidates = await self.memory_store.get_entries_async(
            session_id=session_id,
            entry_types=entry_types,
            time_range=time_range,
            limit=max_results * 5,
        )

        if not candidates:
            return RetrievalResult(
                entries=[],
                query=query,
                relevance_scores=[],
                retrieval_time_ms=0,
                tokens_used=0,
            )

        scored_entries: list[tuple[MemoryEntry, float]] = []
        query_keywords = self._extract_keywords(query)

        for entry in candidates:
            score = self._calculate_relevance_score(entry, query, query_keywords)
            if score >= self.config.min_relevance_score:
                scored_entries.append((entry, score))

        scored_entries.sort(key=lambda x: x[1], reverse=True)
        top_entries = scored_entries[:max_results]

        tokens_used = sum(len(e.content.split()) for e, _ in top_entries)
        elapsed_ms = (time.time() - start_time) * 1000

        return RetrievalResult(
            entries=[e for e, _ in top_entries],
            query=query,
            relevance_scores=[s for _, s in top_entries],
            retrieval_time_ms=elapsed_ms,
            tokens_used=tokens_used,
        )

    def _calculate_relevance_score(
        self,
        entry: MemoryEntry,
        query: str,
        query_keywords: set[str],
    ) -> float:
        """Calculate combined relevance score for an entry."""
        keyword_score = self._keyword_score(entry, query, query_keywords)
        temporal_score = self._temporal_score(entry)
        importance_score = self._importance_score(entry)

        # Weighted combination
        total_score = (
            self.config.keyword_weight * keyword_score
            + self.config.temporal_weight * temporal_score
            + self.config.importance_weight * importance_score
        )

        # Normalize to 0-1
        max_weight = (
            self.config.keyword_weight
            + self.config.temporal_weight
            + self.config.importance_weight
        )

        return total_score / max_weight if max_weight > 0 else 0

    def _extract_keywords(self, text: str) -> set[str]:
        """Extract keywords from text."""
        # Remove common stop words and extract meaningful terms
        stop_words = {
            "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
            "have", "has", "had", "do", "does", "did", "will", "would", "could",
            "should", "may", "might", "must", "shall", "can", "need", "dare",
            "ought", "used", "to", "of", "in", "for", "on", "with", "at", "by",
            "from", "as", "into", "through", "during", "before", "after", "above",
            "below", "between", "under", "again", "further", "then", "once", "here",
            "there", "when", "where", "why", "how", "all", "each", "few", "more",
            "most", "other", "some", "such", "no", "nor", "not", "only", "own",
            "same", "so", "than", "too", "very", "just", "and", "but", "if", "or",
            "because", "until", "while", "this", "that", "these", "those", "what",
            "which", "who", "whom", "it", "its", "i", "me", "my", "we", "our", "you",
            "your", "he", "him", "his", "she", "her", "they", "them", "their",
        }

        # Extract words and filter
        words = re.findall(r'\b[a-zA-Z_][a-zA-Z0-9_]*\b', text.lower())
        keywords = {w for w in words if len(w) > 2 and w not in stop_words}

        return keywords

    def _keyword_score(
        self,
        entry: MemoryEntry,
        query: str,
        query_keywords: set[str],
    ) -> float:
        """Calculate keyword matching score."""
        if not query_keywords:
            return 0.5  # Neutral score if no keywords

        entry_text = f"{entry.content} {entry.entry_type}"
        if entry.metadata:
            entry_text += f" {' '.join(str(v) for v in entry.metadata.values())}"

        entry_keywords = self._extract_keywords(entry_text)

        if not entry_keywords:
            return 0.0

        # Calculate Jaccard similarity
        intersection = query_keywords & entry_keywords
        union = query_keywords | entry_keywords

        jaccard = len(intersection) / len(union) if union else 0

        # Bonus for exact phrase match
        query_lower = query.lower()
        content_lower = entry.content.lower()
        phrase_bonus = 0.3 if query_lower in content_lower else 0

        return min(1.0, jaccard + phrase_bonus)

    def _temporal_score(self, entry: MemoryEntry) -> float:
        """Calculate temporal relevance score (recent = higher)."""
        now = datetime.now()
        age = now - entry.timestamp

        # Decay function: 1.0 for very recent, declining with age
        hours = age.total_seconds() / 3600

        if hours < 1:
            return 1.0
        elif hours < 24:
            return 0.8
        elif hours < 168:  # 1 week
            return 0.5
        elif hours < 720:  # 30 days
            return 0.3
        else:
            return 0.1

    def _importance_score(self, entry: MemoryEntry) -> float:
        """Calculate importance-based score."""
        importance_values = {
            "critical": 1.0,
            "high": 0.8,
            "medium": 0.5,
            "low": 0.2,
        }
        return importance_values.get(entry.importance, 0.5)


def format_entries_for_context(
    entries: list[MemoryEntry],
    max_tokens: int = 4000,
    include_metadata: bool = True,
) -> str:
    """Format memory entries for inclusion in LLM context.

    Args:
        entries: List of memory entries to format.
        max_tokens: Approximate token budget.
        include_metadata: Whether to include entry metadata.

    Returns:
        Formatted string suitable for LLM context.
    """
    if not entries:
        return "No relevant memories found."

    result_parts = []
    estimated_tokens = 0
    tokens_per_char = 0.25  # Rough estimate

    for entry in entries:
        entry_text = _format_single_entry(entry, include_metadata)
        entry_tokens = int(len(entry_text) * tokens_per_char)

        if estimated_tokens + entry_tokens > max_tokens:
            # Truncate or skip
            remaining_tokens = max_tokens - estimated_tokens
            if remaining_tokens > 100:
                # Include truncated version
                max_chars = int(remaining_tokens / tokens_per_char)
                entry_text = entry_text[:max_chars] + "..."
                result_parts.append(entry_text)
            break

        result_parts.append(entry_text)
        estimated_tokens += entry_tokens

    return "\n\n---\n\n".join(result_parts)


def _format_single_entry(entry: MemoryEntry, include_metadata: bool) -> str:
    """Format a single memory entry."""
    parts = [
        f"[{entry.entry_type.upper()}] ({entry.timestamp.strftime('%Y-%m-%d %H:%M')})",
    ]

    if include_metadata and entry.metadata:
        meta_str = ", ".join(f"{k}={v}" for k, v in entry.metadata.items() if v)
        if meta_str:
            parts.append(f"  Metadata: {meta_str}")

    parts.append(entry.content)

    return "\n".join(parts)
