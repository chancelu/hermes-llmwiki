"""Configuration schema for hermes-llmwiki memory provider."""

from typing import Any, Dict


def get_config_schema() -> Dict[str, Any]:
    """Return the configuration schema for hermes memory setup wizard."""
    return {
        "vault_path": {
            "type": "path",
            "description": "Path to your Markdown vault (e.g. ~/Documents/selfwiki or Obsidian vault)",
            "required": True,
            "default": "~/Documents/selfwiki",
        },
        "schema": {
            "type": "dict",
            "description": "Directory structure for the 3-layer wiki",
            "required": False,
            "default": {
                "raw": "raw/",
                "daily": "chronicle/daily/",
                "entities": "entities/",
                "concepts": "concepts/",
                "comparisons": "comparisons/",
                "projects": "projects/",
                "queries": "queries/",
            },
        },
        "auto_curate": {
            "type": "dict",
            "description": "Automatic curation settings",
            "required": False,
            "default": {
                "enabled": True,
                "archive_after_days": 30,
                "preserve_frontmatter": True,
            },
        },
        "search": {
            "type": "dict",
            "description": "Search engine configuration",
            "required": False,
            "default": {
                "engine": "ripgrep",  # ripgrep | grep | python
                "max_results": 10,
                "context_lines": 3,
            },
        },
        "features": {
            "type": "dict",
            "description": "Feature toggles",
            "required": False,
            "default": {
                "wikilinks": True,
                "frontmatter": True,
                "backlinks": True,
                "ai_first_format": True,
            },
        },
    }
