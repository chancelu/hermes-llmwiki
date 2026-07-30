"""hermes-llmwiki: Karpathy-native memory provider for Hermes Agent.

Implements the MemoryProvider ABC. Provides:
  - sync_turn() → auto-capture to chronicle/daily/
  - prefetch()  → search compiled wiki for context injection
  - on_session_end() → session summary
  - on_pre_compress() → extract insights before context loss
  - Tools: search_wiki, append_note, create_entity
"""

from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

# Hermes imports (may not be available during standalone testing)
try:
    from agent.memory_provider import MemoryProvider
except ImportError:
    # Stub for standalone dev / testing
    from abc import ABC, abstractmethod

    class MemoryProvider(ABC):
        @property
        @abstractmethod
        def name(self) -> str: ...

        @abstractmethod
        def is_available(self) -> bool: ...

        @abstractmethod
        def initialize(self, session_id: str, **kwargs) -> None: ...

        @abstractmethod
        def get_tool_schemas(self) -> List[Dict[str, Any]]: ...

        def sync_turn(self, user: str, assistant: str, **kwargs) -> None:
            pass

        def prefetch(self, query: str) -> str:
            return ""

        def shutdown(self) -> None:
            pass

        def on_turn_start(self, turn_number: int, message: str) -> None:
            pass

        def on_session_end(self, messages: List[Dict[str, Any]]) -> None:
            pass

        def on_pre_compress(self, messages: List[Dict[str, Any]]) -> Optional[str]:
            return None

        def on_memory_write(self, action: str, target: str, content: str) -> None:
            pass

        def on_delegation(self, task: str, result: Any) -> None:
            pass

        def post_setup(self, hermes_home: Path, config: Dict[str, Any]) -> None:
            pass

        def get_config_schema(self) -> Dict[str, Any]:
            from .config_schema import get_config_schema

            return get_config_schema()

        def save_config(self, values: Dict[str, Any], hermes_home: Path) -> None:
            pass


from . import search
from .curator import curate_vault
from .writer import atomic_write_text, ensure_dir, expand_path

__all__ = ["LlmwikiMemoryProvider", "curate_vault", "register"]

logger = logging.getLogger(__name__)


class LlmwikiMemoryProvider(MemoryProvider):
    """Karpathy-native local Markdown wiki memory provider."""

    # ------------------------------------------------------------------
    # Core identity
    # ------------------------------------------------------------------
    @property
    def name(self) -> str:
        return "llmwiki"

    def is_available(self) -> bool:
        """Quick config check — no network calls."""
        try:
            cfg = self._load_hermes_config()
            path_str = cfg.get("memory", {}).get("llmwiki", {}).get("vault_path", "")
            return bool(path_str) and expand_path(path_str).exists()
        except Exception:
            return False

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    def initialize(self, session_id: str, **kwargs) -> None:
        self._session_id = session_id
        self._hermes_home = Path(kwargs.get("hermes_home", os.path.expanduser("~/.hermes")))
        self._config = self._resolve_config()
        self._vault_path = expand_path(self._config["vault_path"])

        # Ensure vault directory structure exists (match _resolve_config defaults)
        default_schema = {
            "raw": "raw/",
            "daily": "chronicle/daily/",
            "entities": "entities/",
            "concepts": "concepts/",
            "comparisons": "comparisons/",
            "projects": "projects/",
            "queries": "queries/",
        }
        schema = {**default_schema, **self._config.get("schema", {})}
        for key in default_schema:
            ensure_dir(self._vault_path / schema[key])

        logger.info("[llmwiki] Initialized vault: %s", self._vault_path)

    def shutdown(self) -> None:
        logger.info("[llmwiki] Shutdown")

    # ------------------------------------------------------------------
    # Per-turn hooks
    # ------------------------------------------------------------------
    def sync_turn(self, user: str, assistant: str, **kwargs) -> None:
        """Append this turn to today's chronicle note (Layer 2)."""
        if not self._vault_path:
            return

        schema = self._config.get("schema", {})
        daily_dir = self._vault_path / schema.get("daily", "chronicle/daily/")
        ensure_dir(daily_dir)

        today = datetime.now().strftime("%Y-%m-%d")
        note_path = daily_dir / f"{today}.md"

        # Build entry
        timestamp = datetime.now().strftime("%H:%M")
        entry = (
            f"\n## {timestamp}\n\n"
            f"**User:** {user[:500]}\n\n"
            f"**Assistant:** {assistant[:2000]}\n"
        )

        if note_path.exists():
            existing = note_path.read_text(encoding="utf-8")
            content = existing.rstrip() + "\n" + entry
        else:
            header = f"# Daily Chronicle: {today}\n\n"
            content = header + entry

        atomic_write_text(note_path, content)
        logger.debug("[llmwiki] Captured turn to %s", note_path)

    def prefetch(self, query: str) -> str:
        """Search compiled wiki and return relevant snippets for prompt injection."""
        if not self._vault_path:
            return ""

        search_cfg = self._config.get("search", {})
        results = search.search_wiki(
            vault_path=self._vault_path,
            query=query,
            engine=search_cfg.get("engine", "ripgrep"),
            max_results=search_cfg.get("max_results", 10),
            context_lines=search_cfg.get("context_lines", 3),
        )

        if not results:
            return ""

        # Build a compact context block
        lines = ["## Wiki Context", ""]
        for r in results[:5]:  # cap at 5 for token budget
            lines.append(f"### {r['title']}")
            lines.append(f"*{r['path']}*")
            lines.append(r["snippet"][:800])  # truncate per snippet
            lines.append("")

        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Session hooks
    # ------------------------------------------------------------------
    def on_session_end(self, messages: List[Dict[str, Any]]) -> None:
        """Generate a session summary and append to today's daily note."""
        if not self._vault_path or not messages:
            return

        schema = self._config.get("schema", {})
        daily_dir = self._vault_path / schema.get("daily", "chronicle/daily/")
        ensure_dir(daily_dir)

        today = datetime.now().strftime("%Y-%m-%d")
        note_path = daily_dir / f"{today}.md"

        # Simple extraction: last user message + topic detection
        topics = set()
        for msg in messages[-10:]:
            content = msg.get("content", "")
            if isinstance(content, str) and len(content) > 5:
                # Very naive topic extraction — could be LLM-powered later
                words = content.lower().split()[:5]
                topics.add(" ".join(words))

        topic_str = " | ".join(list(topics)[:3]) if topics else "general"

        summary = (
            f"\n---\n"
            f"**Session End:** {datetime.now().strftime('%H:%M')}\n"
            f"**Topics:** {topic_str}\n"
            f"**Turns:** {len(messages)}\n"
        )

        if note_path.exists():
            existing = note_path.read_text(encoding="utf-8")
            content = existing.rstrip() + "\n" + summary
        else:
            content = f"# Daily Chronicle: {today}\n\n" + summary

        atomic_write_text(note_path, content)

    def on_pre_compress(self, messages: List[Dict[str, Any]]) -> Optional[str]:
        """Before context compression, extract key insights to raw/ (Layer 1)."""
        if not self._vault_path or not messages:
            return None

        schema = self._config.get("schema", {})
        raw_dir = self._vault_path / schema.get("raw", "raw/")
        ensure_dir(raw_dir)

        # Save the about-to-be-compressed messages as a raw snapshot
        session_id = getattr(self, "_session_id", "unknown")
        snap_path = (
            raw_dir / f"session-{session_id}-compress-{datetime.now().strftime('%H%M%S')}.md"
        )

        lines = [f"# Raw Snapshot: {session_id}\n", f"Time: {datetime.now().isoformat()}\n"]
        for msg in messages:
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            if isinstance(content, str):
                lines.append(f"\n## {role}\n{content[:1000]}\n")

        atomic_write_text(snap_path, "\n".join(lines))
        logger.debug("[llmwiki] Saved pre-compress snapshot: %s", snap_path)
        return None  # no extra context to inject

    # ------------------------------------------------------------------
    # Tools exposed to the agent
    # ------------------------------------------------------------------
    def get_tool_schemas(self) -> List[Dict[str, Any]]:
        return [
            {
                "type": "function",
                "function": {
                    "name": "search_wiki",
                    "description": "Search the compiled wiki for relevant knowledge.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {
                                "type": "string",
                                "description": "Search query",
                            }
                        },
                        "required": ["query"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "append_note",
                    "description": "Append a fact or insight to today's daily note.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "section": {
                                "type": "string",
                                "description": "Section header (e.g. 'Entity', 'Concept', 'Decision')",
                            },
                            "title": {"type": "string", "description": "Note title"},
                            "content": {"type": "string", "description": "Note body"},
                        },
                        "required": ["section", "title", "content"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "create_entity",
                    "description": "Create or update an entity page in the compiled wiki.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string", "description": "Entity name"},
                            "type": {
                                "type": "string",
                                "enum": ["entity", "concept", "comparison", "project"],
                                "description": "Note type",
                            },
                            "content": {"type": "string", "description": "Body content"},
                            "tags": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "Tags",
                            },
                        },
                        "required": ["name", "type", "content"],
                    },
                },
            },
        ]

    def handle_tool_call(self, name: str, args: Dict[str, Any]) -> str:
        if name == "search_wiki":
            return self._tool_search_wiki(args.get("query", ""))
        elif name == "append_note":
            return self._tool_append_note(
                args.get("section", "Note"),
                args.get("title", ""),
                args.get("content", ""),
            )
        elif name == "create_entity":
            return self._tool_create_entity(
                args.get("name", ""),
                args.get("type", "entity"),
                args.get("content", ""),
                args.get("tags", []),
            )
        return f"[llmwiki] Unknown tool: {name}"

    def _tool_search_wiki(self, query: str) -> str:
        search_cfg = self._config.get("search", {})
        results = search.search_wiki(
            vault_path=self._vault_path,
            query=query,
            engine=search_cfg.get("engine", "ripgrep"),
            max_results=search_cfg.get("max_results", 10),
            context_lines=search_cfg.get("context_lines", 3),
        )
        return json.dumps(results[:5], ensure_ascii=False, indent=2)

    def _tool_append_note(self, section: str, title: str, content: str) -> str:
        schema = self._config.get("schema", {})
        daily_dir = self._vault_path / schema.get("daily", "chronicle/daily/")
        ensure_dir(daily_dir)

        today = datetime.now().strftime("%Y-%m-%d")
        note_path = daily_dir / f"{today}.md"

        entry = f"\n### {section}: {title}\n{content}\n"

        if note_path.exists():
            existing = note_path.read_text(encoding="utf-8")
            existing = existing.replace("\r\n", "\n")
            text = existing.rstrip() + "\n" + entry
        else:
            text = f"# Daily Chronicle: {today}\n\n" + entry

        atomic_write_text(note_path, text)
        return f"Appended to {note_path}"

    def _tool_create_entity(self, name: str, note_type: str, content: str, tags: List[str]) -> str:
        schema = self._config.get("schema", {})
        dir_map = {
            "entity": "entities",
            "concept": "concepts",
            "comparison": "comparisons",
            "project": "projects",
        }
        target_dir = self._vault_path / schema.get(
            dir_map.get(note_type, "entities"), f"{note_type}s/"
        )
        ensure_dir(target_dir)

        safe_name = re.sub(r'[<>:"/\\|?*]', "_", name).strip(". ") or "untitled"
        note_path = target_dir / f"{safe_name}.md"

        fm = [
            "---",
            f"type: {note_type}",
            f'name: "{name}"',
            f'date: {datetime.now().strftime("%Y-%m-%d")}',
            "ai-first: true",
            "confidence: high",
        ]
        if tags:
            fm.append(f"tags: {json.dumps(tags)}")
        fm.append("---")

        body = f"\n## For future Claude\n{content}\n"
        text = "\n".join(fm) + "\n" + body + "\n"

        atomic_write_text(note_path, text)
        return f"Created {note_path}"

    # ------------------------------------------------------------------
    # Setup / Config
    # ------------------------------------------------------------------
    def post_setup(self, hermes_home: Path, config: Dict[str, Any]) -> None:
        """Initialize vault structure after hermes memory setup wizard."""
        vault_path = expand_path(config.get("vault_path", "~/Documents/selfwiki"))
        ensure_dir(vault_path)

        # Default schema must match _resolve_config() defaults
        default_schema = {
            "raw": "raw/",
            "daily": "chronicle/daily/",
            "entities": "entities/",
            "concepts": "concepts/",
            "comparisons": "comparisons/",
            "projects": "projects/",
            "queries": "queries/",
        }
        schema = {**default_schema, **config.get("schema", {})}
        for key in default_schema:
            ensure_dir(vault_path / schema[key])

        # Write SCHEMA.md as documentation
        schema_md = vault_path / "SCHEMA.md"
        if not schema_md.exists():
            atomic_write_text(schema_md, _SCHEMA_MD_TEMPLATE)

        logger.info("[llmwiki] Vault initialized at %s", vault_path)

    def get_config_schema(self) -> Dict[str, Any]:
        from .config_schema import get_config_schema

        return get_config_schema()

    def save_config(self, values: Dict[str, Any], hermes_home: Path) -> None:
        # Handled by Hermes config system; we just validate here if needed
        pass

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _load_hermes_config(self) -> Dict[str, Any]:
        """Read ~/.hermes/config.yaml if available."""
        cfg_path = Path.home() / ".hermes" / "config.yaml"
        if not cfg_path.exists():
            return {}
        try:
            import yaml

            with open(cfg_path, encoding="utf-8") as f:
                return yaml.safe_load(f) or {}
        except Exception:
            return {}

    def _resolve_config(self) -> Dict[str, Any]:
        """Merge Hermes config with defaults."""
        hermes_cfg = self._load_hermes_config()
        user_cfg = hermes_cfg.get("memory", {}).get("llmwiki", {})

        defaults = {
            "vault_path": "~/Documents/selfwiki",
            "schema": {
                "raw": "raw/",
                "daily": "chronicle/daily/",
                "entities": "entities/",
                "concepts": "concepts/",
                "comparisons": "comparisons/",
                "projects": "projects/",
                "queries": "queries/",
            },
            "auto_curate": {
                "enabled": True,
                "archive_after_days": 30,
                "preserve_frontmatter": True,
            },
            "search": {"engine": "ripgrep", "max_results": 10, "context_lines": 3},
            "features": {
                "wikilinks": True,
                "frontmatter": True,
                "backlinks": True,
                "ai_first_format": True,
            },
        }

        # Shallow merge
        merged = dict(defaults)
        merged.update({k: v for k, v in user_cfg.items() if v is not None})
        if "schema" in user_cfg:
            merged["schema"] = {**defaults["schema"], **user_cfg["schema"]}
        if "auto_curate" in user_cfg:
            merged["auto_curate"] = {**defaults["auto_curate"], **user_cfg["auto_curate"]}
        if "search" in user_cfg:
            merged["search"] = {**defaults["search"], **user_cfg["search"]}
        if "features" in user_cfg:
            merged["features"] = {**defaults["features"], **user_cfg["features"]}

        return merged


# ------------------------------------------------------------------------------
# Plugin registration entry point
# ------------------------------------------------------------------------------


def register(ctx):
    """Standard Hermes plugin entry point."""
    ctx.register_memory_provider(LlmwikiMemoryProvider())


_SCHEMA_MD_TEMPLATE = """# Vault Schema

This vault follows the Karpathy LLM Wiki pattern (3-layer architecture).

## Layer 1: Raw
`raw/` — Session dumps, temporary captures, pre-compression snapshots.
Disposable. Regenerated on demand.

## Layer 2: Chronicle
`chronicle/daily/` — Daily timeline notes, append-only.
Human-readable conversation log. Auto-captured by Hermes.

## Layer 3: Compiled
- `entities/` — People, companies, tools, concrete things
- `concepts/` — Ideas, methods, patterns, decisions
- `comparisons/` — A vs B analyses, trade-off tables
- `projects/` — Active and completed projects
- `queries/` — Standing questions, research threads

Each compiled note should be AI-First: self-contained, frontmatter-rich,
with `## For future Claude` preamble and cross-references via `[[wikilinks]]`.
"""
