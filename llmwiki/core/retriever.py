"""Retriever — multi-strategy knowledge recall from the wiki.

Supports:
  - Keyword search (via registered search engines)
  - Graph traversal (follow wikilinks from hit nodes)
  - Temporal search (recent chronicle entries)
  - Fusion: RRF (Reciprocal Rank Fusion)
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

from llmwiki.core.indexer import IndexRegistry

logger = logging.getLogger(__name__)


def rrf_fusion(
    results_lists: List[List[Dict]], k: int = 60
) -> List[Dict]:
    """Reciprocal Rank Fusion: combine multiple ranked lists into one.

    score = sum(1 / (k + rank)) for each list where the item appears.
    Higher score = better.
    """
    scores: Dict[str, float] = {}
    items: Dict[str, Dict] = {}

    for results in results_lists:
        for rank, item in enumerate(results, start=1):
            key = item["path"]
            items[key] = item
            scores[key] = scores.get(key, 0.0) + 1.0 / (k + rank)

    # Sort by fused score descending
    fused = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    return [
        {**items[key], "score": score, "fusion": "rrf"}
        for key, score in fused
    ]


class Retriever:
    """Multi-strategy retriever for the wiki vault."""

    def __init__(self, registry: IndexRegistry, vault_path: Path):
        self.registry = registry
        self.vault_path = Path(vault_path)

    def retrieve(
        self,
        query: str,
        top_k: int = 5,
        strategies: Optional[List[str]] = None,
        fusion: str = "rrf",
        days_back: int = 7,
    ) -> List[Dict]:
        """Retrieve relevant knowledge chunks using multiple strategies.

        Args:
            query: The search query (user message or topic).
            top_k: Number of results to return.
            strategies: List of strategies to use. Defaults to ["keyword"].
            fusion: How to merge results from multiple strategies (rrf | concat).
            days_back: For temporal strategy, how many days of chronicle to include.

        Returns:
            List of result dicts with path, title, snippet, score.
        """
        if strategies is None:
            strategies = ["keyword"]

        results_by_strategy: List[List[Dict]] = []

        if "keyword" in strategies:
            try:
                keyword_results = self._keyword_search(query, top_k * 2)
                if keyword_results:
                    results_by_strategy.append(keyword_results)
            except Exception as e:
                logger.warning("Keyword search failed: %s", e)

        if "graph" in strategies:
            try:
                graph_results = self._graph_search(query, top_k)
                if graph_results:
                    results_by_strategy.append(graph_results)
            except Exception as e:
                logger.warning("Graph search failed: %s", e)

        if "temporal" in strategies:
            try:
                temporal_results = self._temporal_search(query, days_back, top_k)
                if temporal_results:
                    results_by_strategy.append(temporal_results)
            except Exception as e:
                logger.warning("Temporal search failed: %s", e)

        if not results_by_strategy:
            return []

        if len(results_by_strategy) == 1 or fusion == "concat":
            # Simple concatenation and dedup
            seen = set()
            merged = []
            for results in results_by_strategy:
                for r in results:
                    if r["path"] not in seen:
                        seen.add(r["path"])
                        merged.append(r)
            return merged[:top_k]

        # RRF fusion
        fused = rrf_fusion(results_by_strategy)
        return fused[:top_k]

    def _keyword_search(self, query: str, top_k: int) -> List[Dict]:
        """Standard keyword search via the index registry."""
        return self.registry.search(query, top_k=top_k)

    def _graph_search(self, query: str, top_k: int) -> List[Dict]:
        """Graph traversal: find initial hits, then follow wikilinks 1-2 hops."""
        # First, get seed hits
        seeds = self.registry.search(query, top_k=top_k)
        if not seeds:
            return []

        # Extract wikilinks from seed documents
        linked_paths = set()
        wikilink_pattern = re.compile(r"\[\[([^\]]+)\]\]")

        for seed in seeds:
            seed_path = self.vault_path / seed["path"]
            if not seed_path.exists():
                continue
            try:
                text = seed_path.read_text(encoding="utf-8")
                for m in wikilink_pattern.finditer(text):
                    link_name = m.group(1).strip()
                    # Try to resolve the link to a file path
                    resolved = self._resolve_wikilink(link_name)
                    if resolved:
                        linked_paths.add(str(resolved.relative_to(self.vault_path)))
            except Exception:
                continue

        # Load linked documents as additional results
        graph_results = []
        for linked_path in linked_paths:
            full_path = self.vault_path / linked_path
            if not full_path.exists():
                continue
            try:
                text = full_path.read_text(encoding="utf-8")
                title = self._extract_title(text, full_path)
                snippet = text[:500].replace("\n", " ").strip()
                graph_results.append(
                    {
                        "path": linked_path,
                        "title": title,
                        "snippet": snippet,
                        "score": 3.0,  # Lower than direct hits but still relevant
                        "engine": "graph",
                    }
                )
            except Exception:
                continue

        return graph_results

    def _temporal_search(self, query: str, days_back: int, top_k: int) -> List[Dict]:
        """Search recent chronicle entries (daily notes)."""
        daily_dir = self.vault_path / "chronicle" / "daily"
        if not daily_dir.is_dir():
            return []

        cutoff = datetime.now() - timedelta(days=days_back)
        results = []
        query_lower = query.lower()

        for md_file in sorted(daily_dir.glob("*.md"), reverse=True):
            try:
                # Parse date from filename
                note_date = datetime.strptime(md_file.stem, "%Y-%m-%d")
            except ValueError:
                continue

            if note_date < cutoff:
                continue

            try:
                text = md_file.read_text(encoding="utf-8")
            except Exception:
                continue

            if query_lower not in text.lower():
                continue

            # Extract snippet around match
            idx = text.lower().find(query_lower)
            start = max(0, idx - 200)
            end = min(len(text), idx + 300)
            snippet = text[start:end].replace("\n", " ").strip()

            # Recency scoring: newer = higher
            days_ago = (datetime.now() - note_date).days
            recency_score = max(0.0, 5.0 - days_ago * 0.5)

            results.append(
                {
                    "path": str(md_file.relative_to(self.vault_path)),
                    "title": f"Daily Chronicle: {md_file.stem}",
                    "snippet": snippet,
                    "score": recency_score,
                    "engine": "temporal",
                }
            )

            if len(results) >= top_k:
                break

        return results

    def _resolve_wikilink(self, link_name: str) -> Optional[Path]:
        """Resolve a wikilink like [[Note Name]] to an actual file path."""
        # Try multiple sanitizations
        candidates = [
            link_name,
            link_name.replace(" ", "-"),
            link_name.replace(" ", "_"),
            link_name.replace("-", " "),
            link_name.replace("_", " "),
        ]

        search_dirs = [
            self.vault_path / "entities",
            self.vault_path / "concepts",
            self.vault_path / "comparisons",
            self.vault_path / "projects",
            self.vault_path / "queries",
        ]

        for directory in search_dirs:
            if not directory.is_dir():
                continue
            for candidate in set(candidates):
                for ext in (".md", ""):
                    target = directory / f"{candidate}{ext}"
                    if target.exists():
                        return target

        return None

    @staticmethod
    def _extract_title(text: str, md_path: Path) -> str:
        m = re.search(r"^#\s+(.+)$", text, re.MULTILINE)
        if m:
            return m.group(1).strip()
        return md_path.stem.replace("-", " ").replace("_", " ")
