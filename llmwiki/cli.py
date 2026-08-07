"""Standalone CLI for LLMWiki.

Usage:
    llmwiki init <path>           Initialize a new vault
    llmwiki index [--force]       Build or update search index
    llmwiki search <query>        Search the wiki
    llmwiki curate [--llm]        Run curation pipeline
    llmwiki stats                 Show vault statistics
    llmwiki health                Check vault health
    llmwiki config                Show current configuration
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path
from typing import Optional

from llmwiki.core.config import load_config, save_config
from llmwiki.core.harness import ContextMemoryHarness
from llmwiki.vault.schema import VaultSchema

logger = logging.getLogger(__name__)


def main(argv: Optional[list] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="llmwiki",
        description="LLMWiki: Context-Memory Harness for AI Agents",
    )
    parser.add_argument(
        "-v", "--vault", help="Path to vault (overrides config)"
    )
    parser.add_argument(
        "-c", "--config", help="Path to config file"
    )
    parser.add_argument(
        "--verbose", action="store_true", help="Enable verbose logging"
    )

    sub = parser.add_subparsers(dest="cmd")

    # init
    init_p = sub.add_parser("init", help="Initialize a new vault")
    init_p.add_argument("path", nargs="?", default="~/Documents/selfwiki")

    # index
    index_p = sub.add_parser("index", help="Build or update search index")
    index_p.add_argument("--force", action="store_true", help="Force rebuild")

    # search
    search_p = sub.add_parser("search", help="Search the wiki")
    search_p.add_argument("query", help="Search query")
    search_p.add_argument("-n", "--top-k", type=int, default=5)
    search_p.add_argument("--json", action="store_true", help="Output JSON")

    # curate
    curate_p = sub.add_parser("curate", help="Run curation: chronicle → compiled")
    curate_p.add_argument("--llm", action="store_true", help="Use LLM-driven extraction")

    # stats
    sub.add_parser("stats", help="Show vault statistics")

    # health
    sub.add_parser("health", help="Check vault health")

    # config
    sub.add_parser("config", help="Show configuration")

    args = parser.parse_args(argv)

    if args.verbose:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.INFO)

    if not args.cmd:
        parser.print_help()
        return 1

    # Load config
    config_path = Path(args.config) if args.config else None
    config = load_config(path=config_path)
    if args.vault:
        config["vault"]["path"] = args.vault

    vault_path = Path(config["vault"]["path"]).expanduser()

    if args.cmd == "init":
        return _cmd_init(args, config)
    elif args.cmd == "index":
        return _cmd_index(args, config)
    elif args.cmd == "search":
        return _cmd_search(args, config)
    elif args.cmd == "curate":
        return _cmd_curate(args, config)
    elif args.cmd == "stats":
        return _cmd_stats(args, config)
    elif args.cmd == "health":
        return _cmd_health(args, config)
    elif args.cmd == "config":
        return _cmd_config(args, config)

    return 0


def _cmd_init(args, config) -> int:
    path = Path(args.path).expanduser()
    schema = VaultSchema(path, config["vault"]["schema"])
    schema.init_vault()
    print(f"Initialized vault at: {path}")
    print("Directory structure:")
    for key, dir_path in config["vault"]["schema"].items():
        print(f"  {key}/ -> {path / dir_path}")
    return 0


def _cmd_index(args, config) -> int:
    harness = ContextMemoryHarness(config=config)
    harness.build_index(force=args.force)
    print("Index built successfully.")
    return 0


def _cmd_search(args, config) -> int:
    harness = ContextMemoryHarness(config=config)
    results = harness.search_wiki(args.query, top_k=args.top_k)

    if args.json:
        print(json.dumps(results, indent=2, ensure_ascii=False))
    else:
        for i, r in enumerate(results, 1):
            print(f"\n{i}. {r['title']}")
            print(f"   {r['path']}")
            print(f"   {r['snippet'][:300]}...")

    return 0


def _cmd_curate(args, config) -> int:
    harness = ContextMemoryHarness(config=config)

    llm_generate = None
    if args.llm:
        llm_generate = _make_llm_generate()
        if llm_generate:
            print("Using LLM-driven extraction...")
        else:
            print("WARN: LLM not configured. Falling back to regex.")

    stats = harness.curate(llm_generate=llm_generate)
    print(json.dumps(stats, indent=2))
    return 0


def _cmd_stats(args, config) -> int:
    harness = ContextMemoryHarness(config=config)
    stats = harness.stats()
    print(json.dumps(stats, indent=2))
    return 0


def _cmd_health(args, config) -> int:
    harness = ContextMemoryHarness(config=config)
    vault_path = harness.vault_path

    issues = []
    compiled_dirs = ["entities", "concepts", "comparisons", "projects", "queries"]
    all_notes: dict = {}
    all_wikilinks: set = set()
    import re

    for d in compiled_dirs:
        p = vault_path / d
        if not p.is_dir():
            continue
        for md in p.rglob("*.md"):
            rel = str(md.relative_to(vault_path))
            all_notes[rel] = md
            try:
                text = md.read_text(encoding="utf-8")
            except Exception:
                continue
            for m in re.finditer(r"\[\[([^\]]+)\]\]", text):
                all_wikilinks.add(m.group(1).strip())

    # Dead links
    for link in all_wikilinks:
        found = False
        for rel in all_notes:
            if link.lower() in rel.lower().replace("-", " ").replace("_", " "):
                found = True
                break
        if not found:
            issues.append({"type": "dead_link", "target": link})

    # Orphans
    linked_targets = set()
    for link in all_wikilinks:
        for rel in all_notes:
            if link.lower() in rel.lower().replace("-", " ").replace("_", " "):
                linked_targets.add(rel)
                break

    for rel in all_notes:
        if rel not in linked_targets:
            issues.append({"type": "orphan", "file": rel})

    print(json.dumps({"notes": len(all_notes), "issues": issues}, indent=2))
    return 0


def _cmd_config(args, config) -> int:
    print(json.dumps(config, indent=2))
    return 0


def _make_llm_generate():
    """Build an LLM generate callback from environment."""
    endpoint = os.environ.get("LLMWIKI_LLM_ENDPOINT", "")
    api_key = os.environ.get("LLMWIKI_LLM_API_KEY", "")
    model = os.environ.get("LLMWIKI_LLM_MODEL", "")

    if not endpoint:
        return None

    def generate(prompt: str) -> str:
        import urllib.request
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        payload = json.dumps({
            "model": model or "default",
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.2,
            "max_tokens": 2000,
        }).encode("utf-8")

        req = urllib.request.Request(
            endpoint.rstrip("/") + "/v1/chat/completions",
            data=payload,
            headers=headers,
            method="POST",
        )

        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data["choices"]["message"]["content"]

    return generate


if __name__ == "__main__":
    sys.exit(main())
