"""SQLite FTS5 search engine — structured queries with incremental updates."""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path
from typing import List

from llmwiki.search.base import SearchEngine, SearchResult

logger = logging.getLogger(__name__)


class SQLiteEngine(SearchEngine):
    """Search engine powered by SQLite FTS5.

    Provides prefix matching, structured queries, and fast incremental updates.
    The index is stored as a `.llmwiki.sqlite` file inside the vault root.
    """

    name = "sqlite"

    def __init__(self, db_name: str = ".llmwiki.sqlite"):
        self.db_name = db_name
        self._conn: sqlite3.Connection | None = None

    def is_available(self) -> bool:
        """SQLite is built into Python since 2.5."""
        return True

    def _db_path(self, vault_path: Path) -> Path:
        return vault_path / self.db_name

    def _connect(self, vault_path: Path) -> sqlite3.Connection:
        if self._conn is None:
            db_path = self._db_path(vault_path)
            self._conn = sqlite3.connect(str(db_path))
            self._conn.row_factory = sqlite3.Row
            self._ensure_schema(vault_path)
        return self._conn

    def _ensure_schema(self, vault_path: Path) -> None:
        conn = self._conn
        if conn is None:
            return

        # Check if FTS5 is available
        try:
            conn.execute("CREATE VIRTUAL TABLE IF NOT EXISTS docs USING fts5(path, title, body)")
        except sqlite3.OperationalError as e:
            if "fts5" in str(e).lower():
                logger.warning("SQLite FTS5 not available, falling back to plain tables")
                conn.execute(
                    "CREATE TABLE IF NOT EXISTS docs (path TEXT PRIMARY KEY, title TEXT, body TEXT)"
                )
                conn.execute("CREATE INDEX IF NOT EXISTS idx_docs_body ON docs(body)")
            else:
                raise

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS index_state (
                key TEXT PRIMARY KEY,
                value TEXT
            )
            """
        )
        conn.commit()

    def index(self, vault_path: Path, schema_dirs: List[str]) -> None:
        """Full rebuild of the SQLite index."""
        conn = self._connect(vault_path)

        # Clear existing
        conn.execute("DELETE FROM docs")

        # Index all markdown files
        count = 0
        for d in schema_dirs:
            root = vault_path / d
            if not root.is_dir():
                continue
            for md_file in root.rglob("*.md"):
                try:
                    text = md_file.read_text(encoding="utf-8")
                except Exception:
                    continue

                rel_path = str(md_file.relative_to(vault_path))
                title = _extract_title(text, md_file)
                body = _strip_frontmatter(text)

                conn.execute(
                    "INSERT OR REPLACE INTO docs (path, title, body) VALUES (?, ?, ?)",
                    (rel_path, title, body),
                )
                count += 1

        conn.execute(
            "INSERT OR REPLACE INTO index_state (key, value) VALUES (?, ?)",
            ("last_full_index", str(Path(__file__).stat().st_mtime)),
        )
        conn.commit()
        logger.info("SQLite index rebuilt: %d documents", count)

    def update(self, changed_files: List[Path]) -> None:
        """Incrementally update index for changed files."""
        if not self._conn or not changed_files:
            return

        for md_file in changed_files:
            if not md_file.suffix.lower() == ".md":
                continue
            try:
                text = md_file.read_text(encoding="utf-8")
                # Need vault_path to compute relative path — skip if can't determine
                vault_path = _infer_vault_path(md_file)
                if vault_path is None:
                    continue
                rel_path = str(md_file.relative_to(vault_path))
                title = _extract_title(text, md_file)
                body = _strip_frontmatter(text)

                self._conn.execute(
                    "INSERT OR REPLACE INTO docs (path, title, body) VALUES (?, ?, ?)",
                    (rel_path, title, body),
                )
            except Exception as e:
                logger.warning("Failed to index %s: %s", md_file, e)

        self._conn.commit()

    def search(
        self,
        query: str,
        vault_path: Path,
        schema_dirs: List[str],
        top_k: int = 10,
        context_lines: int = 3,
    ) -> List[SearchResult]:
        conn = self._connect(vault_path)

        # Try FTS5 query first
        try:
            rows = conn.execute(
                """
                SELECT path, title, body, rank
                FROM docs
                WHERE docs MATCH ?
                ORDER BY rank
                LIMIT ?
                """,
                (query, top_k * 2),
            ).fetchall()
        except sqlite3.OperationalError:
            # Fallback to LIKE search
            rows = conn.execute(
                """
                SELECT path, title, body, 0 as rank
                FROM docs
                WHERE body LIKE ? OR title LIKE ?
                LIMIT ?
                """,
                (f"%{query}%", f"%{query}%", top_k * 2),
            ).fetchall()

        results = []
        for row in rows:
            body = row["body"]
            snippet = _extract_snippet(body, query, context_lines)
            score = 10.0 + (1.0 / (abs(row["rank"]) + 1.0)) if row["rank"] else 5.0

            results.append(
                SearchResult(
                    path=row["path"],
                    title=row["title"],
                    snippet=snippet,
                    score=score,
                    engine="sqlite",
                )
            )

        results.sort(key=lambda r: r.score, reverse=True)
        return results[:top_k]


def _extract_title(text: str, md_path: Path) -> str:
    import re
    m = re.search(r"^#\s+(.+)$", text, re.MULTILINE)
    if m:
        return m.group(1).strip()
    return md_path.stem.replace("-", " ").replace("_", " ")


def _strip_frontmatter(text: str) -> str:
    """Remove YAML frontmatter from markdown text."""
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) >= 3:
            return parts[2].strip()
    return text.strip()


def _extract_snippet(body: str, query: str, context_lines: int) -> str:
    """Extract a snippet around the first match of query."""
    idx = body.lower().find(query.lower())
    if idx == -1:
        return body[:300]

    lines = body[:idx].split("\n")
    start_line = max(0, len(lines) - context_lines)
    end_line = min(len(lines) + context_lines, len(body.split("\n")))

    all_lines = body.split("\n")
    snippet_lines = all_lines[start_line:end_line]
    return "\n".join(snippet_lines).strip()[:500]


def _infer_vault_path(md_file: Path) -> Path | None:
    """Try to infer the vault root from a markdown file path."""
    # Walk up looking for entities/ or chronicle/ or SCHEMA.md
    for parent in md_file.parents:
        if any((parent / d).is_dir() for d in ["entities", "concepts", "chronicle"]):
            return parent
    return None
