"""Search engine base class and shared types."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional


@dataclass
class SearchResult:
    """A single search result from any engine."""

    path: str  # Relative path from vault root
    title: str
    snippet: str
    score: float = 0.0
    engine: str = ""  # Which engine produced this result
    metadata: Optional[dict] = None


class SearchEngine(ABC):
    """Abstract base class for wiki search engines."""

    name: str = ""

    @abstractmethod
    def index(self, vault_path: Path, schema_dirs: List[str]) -> None:
        """Build or update the search index for the given vault."""
        ...

    @abstractmethod
    def search(
        self,
        query: str,
        vault_path: Path,
        schema_dirs: List[str],
        top_k: int = 10,
        context_lines: int = 3,
    ) -> List[SearchResult]:
        """Search the indexed vault and return ranked results."""
        ...

    @abstractmethod
    def is_available(self) -> bool:
        """Check if this engine's dependencies are available."""
        ...

    def update(self, changed_files: List[Path]) -> None:
        """Incrementally update the index for changed files.

        Default implementation does nothing (engines that don't support
        incremental updates can override or ignore).
        """
        pass
