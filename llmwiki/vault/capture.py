"""Turn capture — append conversation turns to chronicle/daily/ notes."""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Dict

from llmwiki.vault.writer import atomic_write_text, ensure_dir

logger = logging.getLogger(__name__)


class TurnCapture:
    """Captures conversation turns to daily chronicle notes."""

    def __init__(self, vault_path: Path, schema: Dict[str, str]):
        self.vault_path = Path(vault_path)
        self.daily_dir = self.vault_path / schema.get("daily", "chronicle/daily/")

    def append(
        self,
        user_content: str,
        assistant_content: str,
        *,
        session_id: str = "",
    ) -> Path:
        """Append a turn to today's chronicle note.

        Args:
            user_content: User message.
            assistant_content: Assistant response.
            session_id: Optional session ID.

        Returns:
            Path to the written note.
        """
        ensure_dir(self.daily_dir)

        today = datetime.now().strftime("%Y-%m-%d")
        note_path = self.daily_dir / f"{today}.md"

        timestamp = datetime.now().strftime("%H:%M")
        session_tag = f" (session: {session_id})" if session_id else ""

        entry = (
            f"\n## {timestamp}{session_tag}\n\n"
            f"**User:** {user_content[:500]}\n\n"
            f"**Assistant:** {assistant_content[:2000]}\n"
        )

        if note_path.exists():
            existing = note_path.read_text(encoding="utf-8")
            content = existing.rstrip() + "\n" + entry
        else:
            header = f"# Daily Chronicle: {today}\n\n"
            content = header + entry

        atomic_write_text(note_path, content)
        logger.debug("Captured turn to %s", note_path)
        return note_path

    def append_insight(
        self,
        section: str,
        title: str,
        content: str,
    ) -> Path:
        """Append a structured insight to today's note.

        Args:
            section: Section header (e.g., 'Entity', 'Concept', 'Decision').
            title: Note title.
            content: Note body.

        Returns:
            Path to the written note.
        """
        ensure_dir(self.daily_dir)

        today = datetime.now().strftime("%Y-%m-%d")
        note_path = self.daily_dir / f"{today}.md"

        entry = f"\n### {section}: {title}\n{content}\n"

        if note_path.exists():
            existing = note_path.read_text(encoding="utf-8")
            existing = existing.replace("\r\n", "\n")
            text = existing.rstrip() + "\n" + entry
        else:
            text = f"# Daily Chronicle: {today}\n\n" + entry

        atomic_write_text(note_path, text)
        return note_path

    def append_session_summary(
        self,
        topics: list,
        turn_count: int,
        session_id: str = "",
    ) -> Path:
        """Append a session summary to today's note."""
        ensure_dir(self.daily_dir)

        today = datetime.now().strftime("%Y-%m-%d")
        note_path = self.daily_dir / f"{today}.md"

        topic_str = " | ".join(topics[:3]) if topics else "general"

        summary = (
            f"\n---\n"
            f"**Session End:** {datetime.now().strftime('%H:%M')}\n"
            f"**Topics:** {topic_str}\n"
            f"**Turns:** {turn_count}\n"
        )
        if session_id:
            summary += f"**Session ID:** {session_id}\n"

        if note_path.exists():
            existing = note_path.read_text(encoding="utf-8")
            content = existing.rstrip() + "\n" + summary
        else:
            content = f"# Daily Chronicle: {today}\n\n" + summary

        atomic_write_text(note_path, content)
        return note_path
