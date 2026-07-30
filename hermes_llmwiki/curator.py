"""Curation engine: chronicle/daily/ → compiled wiki (Layer 2 → Layer 3).

Supports two extraction modes:
  1. LLM-driven (recommended): Analyzes daily notes and extracts structured
     entities, concepts, decisions, projects using a text-generation callback.
  2. Regex fallback: Matches explicit markers like `### Entity: Name`.
"""

import json
import logging
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable, List, Optional

from .writer import atomic_write_text, expand_path

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Prompt template for LLM-driven extraction
# ---------------------------------------------------------------------------

_CURATION_PROMPT = """You are a knowledge curation assistant. Analyze the following daily note and extract structured knowledge items.

Rules:
- Extract ONLY high-signal items (facts, concepts, decisions, entities, projects). Skip trivial chat.
- Each item must have: type, name, content (1-3 sentences), tags (optional).
- Supported types: entity, concept, comparison, project, decision, finding.
- Output as a JSON array. No markdown, no explanations.

Example output:
[
  {"type": "entity", "name": "Bitcoin", "content": "A decentralized digital currency using proof-of-work consensus.", "tags": ["cryptocurrency", "finance"]},
  {"type": "concept", "name": "Zettelkasten", "content": "A note-taking method using atomic notes with unique IDs and cross-references.", "tags": ["knowledge-management"]}
]

Daily note:
---
{note_text}
---

JSON output:"""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def curate_vault(
    vault_path: Path,
    config: dict,
    llm_generate: Optional[Callable[[str], str]] = None,
) -> dict:
    """Run the full curation pipeline.

    Args:
        vault_path: Root of the Markdown vault.
        config: Plugin configuration dict.
        llm_generate: Optional callback(text) -> response_text. If provided,
            uses LLM to extract structured items from daily notes. Otherwise
            falls back to regex-based extraction.

    Returns a summary dict:
        {
            "status": "ok" | "no_notes",
            "processed": int,
            "created": int,
            "updated": int,
            "archived": int,
            "llm_mode": bool,
        }
    """
    vault_path = expand_path(str(vault_path))
    schema = config.get("schema", {})
    daily_dir = vault_path / schema.get("daily", "chronicle/daily/")
    compiled_dirs = {
        "entities": vault_path / schema.get("entities", "entities/"),
        "concepts": vault_path / schema.get("concepts", "concepts/"),
        "comparisons": vault_path / schema.get("comparisons", "comparisons/"),
        "projects": vault_path / schema.get("projects", "projects/"),
    }

    for d in compiled_dirs.values():
        d.mkdir(parents=True, exist_ok=True)

    daily_notes = _list_daily_notes(daily_dir)
    if not daily_notes:
        return {"status": "no_notes", "processed": 0, "llm_mode": bool(llm_generate)}

    stats = {
        "status": "ok",
        "processed": 0,
        "created": 0,
        "updated": 0,
        "archived": 0,
        "llm_mode": bool(llm_generate),
    }

    for note_path in daily_notes:
        try:
            text = note_path.read_text(encoding="utf-8")
        except Exception as e:
            logger.warning("Failed to read %s: %s", note_path, e)
            continue

        # Skip if the note is too short (trivial chat only)
        if len(text.strip()) < 200:
            logger.debug("Skipping trivial note: %s", note_path.name)
            continue

        items = _extract_items(text, llm_generate)
        for item in items:
            _write_compiled_note(vault_path, compiled_dirs, item)
            stats["created"] += 1

        stats["processed"] += 1

    # Archive old notes
    archive_days = config.get("auto_curate", {}).get("archive_after_days", 30)
    stats["archived"] = _archive_old_notes(daily_dir, archive_days)

    return stats


# ---------------------------------------------------------------------------
# Extraction
# ---------------------------------------------------------------------------


def _extract_items(text: str, llm_generate: Optional[Callable[[str], str]] = None) -> List[dict]:
    """Extract structured items from a daily note.

    If llm_generate is provided, uses LLM. Otherwise falls back to regex.
    """
    if llm_generate:
        items = _extract_with_llm(text, llm_generate)
        if items:
            return items
        logger.debug("LLM extraction returned empty, falling back to regex")

    return _extract_with_regex(text)


def _extract_with_llm(text: str, llm_generate: Callable[[str], str]) -> List[dict]:
    """Use LLM to extract structured items from a daily note."""
    # Truncate very long notes to avoid token overflow
    truncated = text[:6000] if len(text) > 6000 else text
    prompt = _CURATION_PROMPT.replace("{note_text}", truncated)

    try:
        response = llm_generate(prompt)
    except Exception as e:
        logger.warning("LLM extraction failed: %s", e)
        return []

    # Try to parse JSON from the response
    items = _parse_json_from_response(response)
    if not items:
        logger.debug("Could not parse JSON from LLM response, falling back")

    # Validate and clean items
    valid_items = []
    for item in items:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name", "")).strip()
        content = str(item.get("content", "")).strip()
        item_type = str(item.get("type", "note")).lower().strip()

        if not name or not content or len(content) < 20:
            continue

        # Normalize type
        if item_type not in ("entity", "concept", "comparison", "project", "decision", "finding"):
            item_type = "note"

        valid_items.append(
            {
                "type": item_type,
                "name": name,
                "content": content,
                "date": datetime.now().strftime("%Y-%m-%d"),
                "tags": item.get("tags", []),
            }
        )

    return valid_items


def _parse_json_from_response(response: str) -> List[dict]:
    """Extract a JSON array from an LLM response.

    Handles common wrapping artifacts: markdown code blocks, trailing text, etc.
    """
    response = response.strip()

    # Try direct parse first
    try:
        data = json.loads(response)
        if isinstance(data, list):
            return data
        if isinstance(data, dict) and "items" in data:
            return data["items"]
    except json.JSONDecodeError:
        pass

    # Try extracting from markdown code block
    code_block = re.search(r"```(?:json)?\s*([\s\S]*?)```", response)
    if code_block:
        try:
            data = json.loads(code_block.group(1).strip())
            if isinstance(data, list):
                return data
        except json.JSONDecodeError:
            pass

    # Try finding the first [ ... ] array in the response
    array_match = re.search(r"(\[.*\])", response, re.DOTALL)
    if array_match:
        try:
            data = json.loads(array_match.group(1))
            if isinstance(data, list):
                return data
        except json.JSONDecodeError:
            pass

    return []


def _extract_with_regex(text: str) -> List[dict]:
    """Fallback regex-based extraction for explicit markers."""
    items = []
    pattern = re.compile(
        r"^###\s+(Entity|Concept|Comparison|Project|Decision|Finding):\s*(.+?)\r?\n"
        r"(.*?)(?=^###\s|\Z)",
        re.MULTILINE | re.DOTALL | re.IGNORECASE,
    )

    for m in pattern.finditer(text):
        item_type = m.group(1).lower()
        name = m.group(2).strip()
        content = m.group(3).strip()

        if not name or not content:
            continue

        items.append(
            {
                "type": item_type,
                "name": name,
                "content": content,
                "date": datetime.now().strftime("%Y-%m-%d"),
                "tags": [],
            }
        )

    # If no structured markers but note has substance, create a summary entry
    if not items and len(text.strip()) > 300:
        # Try to extract a title from first H1 or first sentence
        title_match = re.search(r"^#\s+(.+)$", text, re.MULTILINE)
        if title_match:
            title = title_match.group(1).strip()
        else:
            first_sentence = text.split(".")[0].strip()
            title = (first_sentence[:60] + "...") if len(first_sentence) > 60 else first_sentence

        items.append(
            {
                "type": "note",
                "name": title or "Daily Summary",
                "content": text[:2000],
                "date": datetime.now().strftime("%Y-%m-%d"),
                "tags": [],
            }
        )

    return items


# ---------------------------------------------------------------------------
# Compiled note writer
# ---------------------------------------------------------------------------


def _write_compiled_note(vault_path: Path, compiled_dirs: dict, item: dict) -> None:
    """Write or update a compiled note with AI-First format."""
    note_type = item["type"]
    name = item["name"]

    type_to_dir = {
        "entity": "entities",
        "concept": "concepts",
        "comparison": "comparisons",
        "project": "projects",
        "decision": "concepts",
        "finding": "entities",
        "note": "concepts",
    }

    target_dir = compiled_dirs.get(type_to_dir.get(note_type, "concepts"))
    safe_name = re.sub(r'[<>:"/\\|?*]', "_", name).strip(". ")
    if not safe_name:
        safe_name = "untitled"

    note_path = target_dir / f"{safe_name}.md"

    # Build frontmatter
    fm = {
        "type": note_type,
        "name": name,
        "date": item["date"],
        "ai-first": True,
        "confidence": "medium",
    }
    tags = item.get("tags", [])
    if tags:
        fm["tags"] = tags

    fm_lines = ["---"]
    for k, v in fm.items():
        if isinstance(v, bool):
            fm_lines.append(f"{k}: {str(v).lower()}")
        elif isinstance(v, list):
            fm_lines.append(f"{k}: {json.dumps(v)}")
        else:
            fm_lines.append(f'{k}: "{v}"')
    fm_lines.append("---")

    # Build body
    body = f"\n## For future Claude\n{item['content']}\n\n## Sources\n- Daily note {item['date']}\n"

    content = "\n".join(fm_lines) + "\n" + body + "\n"

    if note_path.exists():
        existing = note_path.read_text(encoding="utf-8")
        # Avoid duplicating identical content
        if item["content"] in existing:
            logger.debug("Note %s already contains this content, skipping", note_path)
            return
        content = existing.rstrip() + "\n\n## Update\n" + item["content"] + "\n"

    atomic_write_text(note_path, content)
    logger.info("Wrote compiled note: %s", note_path)


# ---------------------------------------------------------------------------
# Daily note listing & archiving
# ---------------------------------------------------------------------------


def _list_daily_notes(daily_dir: Path) -> List[Path]:
    """List unarchived daily notes, sorted by date (newest first)."""
    if not daily_dir.is_dir():
        return []

    notes = []
    for f in daily_dir.glob("*.md"):
        if f.name.startswith(".") or f.name.startswith("_"):
            continue
        # Skip archived subdir
        try:
            rel = f.relative_to(daily_dir)
            if rel.parts and rel.parts[0] == "archive":
                continue
        except ValueError:
            pass
        notes.append(f)

    notes.sort(key=lambda p: p.name, reverse=True)
    return notes


def _archive_old_notes(daily_dir: Path, archive_after_days: int) -> int:
    """Move daily notes older than N days to archive/."""
    if archive_after_days <= 0:
        return 0

    cutoff = datetime.now() - timedelta(days=archive_after_days)
    archive_dir = daily_dir / "archive"
    archive_dir.mkdir(exist_ok=True)

    archived = 0
    for note in daily_dir.glob("*.md"):
        try:
            note_date = datetime.strptime(note.stem, "%Y-%m-%d")
        except ValueError:
            continue

        if note_date < cutoff:
            dest = archive_dir / note.name
            # Avoid overwriting if already archived
            counter = 1
            original_dest = dest
            while dest.exists():
                dest = archive_dir / f"{original_dest.stem}_{counter}{original_dest.suffix}"
                counter += 1
            try:
                note.rename(dest)
                archived += 1
            except Exception as e:
                logger.warning("Failed to archive %s: %s", note, e)

    return archived
