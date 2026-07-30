"""Search the compiled wiki layer."""

import json
import logging
import re
import shutil
import subprocess
from pathlib import Path
from typing import List

logger = logging.getLogger(__name__)


def search_wiki(
    vault_path: Path,
    query: str,
    engine: str = "ripgrep",
    max_results: int = 10,
    context_lines: int = 3,
) -> List[dict]:
    """Search the compiled wiki layer for *query*.

    Returns a list of result dicts with keys:
      - path: relative path from vault root
      - title: extracted from first H1 or filename
      - snippet: matching context
      - score: rough relevance score (higher = better)
    """
    vault_path = Path(vault_path)
    compiled_dirs = ["entities", "concepts", "comparisons", "projects", "queries"]

    # Build list of directories to search
    search_roots: List[Path] = []
    for d in compiled_dirs:
        p = vault_path / d
        if p.is_dir():
            search_roots.append(p)

    if not search_roots:
        return []

    if engine == "ripgrep" and shutil.which("rg"):
        return _search_ripgrep(search_roots, query, max_results, context_lines)
    elif engine == "grep" and shutil.which("grep"):
        return _search_grep(search_roots, query, max_results, context_lines)
    else:
        return _search_python(search_roots, query, max_results)


def _search_ripgrep(
    roots: List[Path], query: str, max_results: int, context_lines: int
) -> List[dict]:
    """Use ripgrep for fast regex search with context."""
    cmd = [
        "rg",
        "--json",
        "--smart-case",
        "--context",
        str(context_lines),
        "--max-count",
        str(max_results * 3),  # overfetch, then rank
        "--markdown",
        "-e",
        query,
    ] + [str(r) for r in roots]

    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=30, encoding="utf-8")
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        logger.warning("ripgrep failed: %s", e)
        return _search_python(roots, query, max_results)

    results: List[dict] = []
    current_file = None
    current_snippets: List[str] = []

    for line in proc.stdout.splitlines():
        if not line.strip():
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue

        msg_type = obj.get("type")
        if msg_type == "begin":
            current_file = obj.get("data", {}).get("path", {}).get("text", "")
            current_snippets = []
        elif msg_type == "match":
            lines_data = obj.get("data", {}).get("lines", {})
            text = lines_data.get("text", "")
            if text:
                current_snippets.append(text.strip())
        elif msg_type == "end" and current_file:
            if current_snippets:
                results.append(
                    {
                        "path": current_file,
                        "title": _extract_title(Path(current_file)),
                        "snippet": "\n".join(current_snippets[:3]),
                        "score": _score_result(current_file, query, current_snippets),
                    }
                )
            current_file = None

    results.sort(key=lambda x: x["score"], reverse=True)
    return results[:max_results]


def _search_grep(roots: List[Path], query: str, max_results: int, context_lines: int) -> List[dict]:
    """Fallback to grep."""
    # Grep doesn't give structured output easily; fall back to python
    return _search_python(roots, query, max_results)


def _search_python(roots: List[Path], query: str, max_results: int) -> List[dict]:
    """Pure-Python search as final fallback."""
    results: List[dict] = []
    query_lower = query.lower()
    pattern = re.compile(re.escape(query), re.IGNORECASE)

    for root in roots:
        for md_file in root.rglob("*.md"):
            try:
                text = md_file.read_text(encoding="utf-8")
            except Exception:
                continue

            if query_lower not in text.lower():
                continue

            # Extract snippets around matches
            snippets = []
            for m in pattern.finditer(text):
                start = max(0, m.start() - 200)
                end = min(len(text), m.end() + 200)
                snippet = text[start:end].replace("\n", " ").strip()
                snippets.append(snippet)
                if len(snippets) >= 3:
                    break

            rel_path = str(md_file.relative_to(root.parent))
            results.append(
                {
                    "path": rel_path,
                    "title": _extract_title(md_file),
                    "snippet": " ... ".join(snippets) if snippets else "",
                    "score": _score_result(rel_path, query, snippets),
                }
            )

            if len(results) >= max_results * 2:
                break

    results.sort(key=lambda x: x["score"], reverse=True)
    return results[:max_results]


def _extract_title(md_path: Path) -> str:
    """Extract title from H1 or filename."""
    try:
        text = md_path.read_text(encoding="utf-8")[:2048]
        m = re.search(r"^#\s+(.+)$", text, re.MULTILINE)
        if m:
            return m.group(1).strip()
    except Exception:
        pass
    return md_path.stem.replace("-", " ").replace("_", " ")


def _score_result(path: str, query: str, snippets: List[str]) -> int:
    """Rough relevance scoring. Higher = better."""
    score = 0
    query_lower = query.lower()

    # Title/filename match is strong signal
    if query_lower in path.lower():
        score += 10

    # Matches in entities/concepts are higher value
    if "entities/" in path:
        score += 5
    elif "concepts/" in path:
        score += 4
    elif "comparisons/" in path:
        score += 3

    # Snippet density
    for snippet in snippets:
        score += snippet.lower().count(query_lower)

    return score
