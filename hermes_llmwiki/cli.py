"""CLI commands for hermes-llmwiki: `hermes llmwiki <cmd>`."""

import json
import logging
import os
from pathlib import Path
from typing import Callable, Optional

from hermes_llmwiki.curator import curate_vault
from hermes_llmwiki.search import search_wiki
from hermes_llmwiki.writer import expand_path

logger = logging.getLogger(__name__)


def register_cli(subparser):
    """Register `hermes llmwiki` subcommands."""
    parser = subparser.add_parser(
        "llmwiki",
        help="Manage llmwiki memory vault",
        description="Karpathy-native local Markdown wiki memory provider",
    )
    sub = parser.add_subparsers(dest="llmwiki_cmd")

    # curate
    curate_p = sub.add_parser("curate", help="Run curation: daily notes → compiled wiki")
    curate_p.add_argument("--vault", help="Override vault path")

    # stats
    stats_p = sub.add_parser("stats", help="Show vault statistics")
    stats_p.add_argument("--vault", help="Override vault path")

    # search
    search_p = sub.add_parser("search", help="Search compiled wiki")
    search_p.add_argument("query", help="Search query")
    search_p.add_argument("--vault", help="Override vault path")
    search_p.add_argument("--json", action="store_true", help="Output JSON")

    # health
    health_p = sub.add_parser("health", help="Check vault health")
    health_p.add_argument("--vault", help="Override vault path")

    # export
    export_p = sub.add_parser("export", help="Export wiki to JSON")
    export_p.add_argument("--vault", help="Override vault path")
    export_p.add_argument("--output", "-o", default="-", help="Output file (default: stdout)")

    return parser


def llmwiki_command(args):
    """Dispatch to the appropriate handler."""
    cmd = getattr(args, "llmwiki_cmd", None)
    vault_path = _resolve_vault(args)

    if cmd == "curate":
        return _cmd_curate(vault_path)
    elif cmd == "stats":
        return _cmd_stats(vault_path)
    elif cmd == "search":
        return _cmd_search(vault_path, args)
    elif cmd == "health":
        return _cmd_health(vault_path)
    elif cmd == "export":
        return _cmd_export(vault_path, args)
    else:
        print("Usage: hermes llmwiki {curate|stats|search|health|export}")
        return 1


def _resolve_vault(args) -> Path:
    """Resolve vault path from CLI arg, env var, or default."""
    if hasattr(args, "vault") and args.vault:
        return expand_path(args.vault)
    env_path = os.environ.get("LLMWIKI_VAULT")
    if env_path:
        return expand_path(env_path)
    # Try Hermes config
    try:
        import yaml

        cfg_path = Path.home() / ".hermes" / "config.yaml"
        if cfg_path.exists():
            with open(cfg_path, encoding="utf-8") as f:
                cfg = yaml.safe_load(f) or {}
            v = cfg.get("memory", {}).get("llmwiki", {}).get("vault_path")
            if v:
                return expand_path(v)
    except Exception:
        pass
    return expand_path("~/Documents/selfwiki")


def _cmd_curate(vault_path: Path, args=None) -> int:
    """Run curation pipeline."""
    if not vault_path.exists():
        print(f"Vault not found: {vault_path}")
        return 1

    print(f"Running curation on {vault_path} ...")
    config = _load_config(vault_path)

    llm_generate = None
    if getattr(args, "llm", False):
        llm_generate = _make_llm_generate(getattr(args, "model", ""))
        if llm_generate:
            print("Using LLM-driven extraction...")
        else:
            print("WARN: LLM mode requested but no endpoint configured. Falling back to regex.")

    stats = curate_vault(vault_path, config, llm_generate=llm_generate)
    print(json.dumps(stats, indent=2))
    return 0


def _make_llm_generate(model: str = "") -> Optional[Callable[[str], str]]:
    """Build an LLM generate callback from environment or config."""
    endpoint = os.environ.get("HERMES_LLM_ENDPOINT", "")
    api_key = os.environ.get("HERMES_LLM_API_KEY", "")

    if not endpoint:
        # Try to infer from Hermes config
        try:
            import yaml

            cfg_path = Path.home() / ".hermes" / "config.yaml"
            if cfg_path.exists():
                with open(cfg_path, encoding="utf-8") as f:
                    cfg = yaml.safe_load(f) or {}
                custom = cfg.get("custom_providers", {})
                # Use first available provider as fallback
                for name, prov in custom.items():
                    if prov.get("base_url"):
                        endpoint = prov["base_url"]
                        api_key = prov.get("api_key", "")
                        if not model:
                            model = prov.get("model", "")
                        break
        except Exception:
            pass

    if not endpoint:
        return None

    # Build a simple HTTP-based generate function
    def generate(prompt: str) -> str:
        import urllib.error
        import urllib.request

        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        payload = json.dumps(
            {
                "model": model or "default",
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.2,
                "max_tokens": 2000,
            }
        ).encode("utf-8")

        req = urllib.request.Request(
            endpoint.rstrip("/") + "/v1/chat/completions",
            data=payload,
            headers=headers,
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return data["choices"][0]["message"]["content"]
        except Exception as e:
            raise RuntimeError(f"LLM request failed: {e}")

    return generate


def _cmd_stats(vault_path: Path) -> int:
    """Show vault statistics."""
    if not vault_path.exists():
        print(f"Vault not found: {vault_path}")
        return 1

    compiled_dirs = ["entities", "concepts", "comparisons", "projects", "queries"]
    stats = {"vault": str(vault_path), "compiled": {}, "daily": 0, "raw": 0}

    for d in compiled_dirs:
        p = vault_path / d
        if p.is_dir():
            count = len(list(p.rglob("*.md")))
            stats["compiled"][d] = count

    daily_dir = vault_path / "chronicle" / "daily"
    if daily_dir.is_dir():
        stats["daily"] = len(list(daily_dir.glob("*.md")))

    raw_dir = vault_path / "raw"
    if raw_dir.is_dir():
        stats["raw"] = len(list(raw_dir.glob("*.md")))

    print(json.dumps(stats, indent=2))
    return 0


def _cmd_search(vault_path: Path, args) -> int:
    """Search the compiled wiki."""
    if not vault_path.exists():
        print(f"Vault not found: {vault_path}")
        return 1

    config = _load_config(vault_path)
    search_cfg = config.get("search", {})

    results = search_wiki(
        vault_path=vault_path,
        query=args.query,
        engine=search_cfg.get("engine", "ripgrep"),
        max_results=search_cfg.get("max_results", 10),
        context_lines=search_cfg.get("context_lines", 3),
    )

    if getattr(args, "json", False):
        print(json.dumps(results, indent=2, ensure_ascii=False))
    else:
        for i, r in enumerate(results, 1):
            print(f"\n{i}. {r['title']}")
            print(f"   {r['path']}")
            print(f"   {r['snippet'][:300]}...")

    return 0


def _cmd_health(vault_path: Path) -> int:
    """Check vault health: dead links, orphans, etc."""
    if not vault_path.exists():
        print(f"Vault not found: {vault_path}")
        return 1

    issues = []
    compiled_dirs = ["entities", "concepts", "comparisons", "projects", "queries"]
    all_notes: dict = {}
    all_wikilinks: set = set()

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
            # Find [[wikilinks]]
            import re

            for m in re.finditer(r"\[\[([^\]]+)\]\]", text):
                all_wikilinks.add(m.group(1).strip())

    # Check for dead wikilinks
    for link in all_wikilinks:
        found = False
        for rel, md in all_notes.items():
            if link.lower() in rel.lower().replace("-", " ").replace("_", " "):
                found = True
                break
        if not found:
            issues.append({"type": "dead_link", "target": link})

    # Check for orphans (notes with no incoming links)
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


def _cmd_export(vault_path: Path, args) -> int:
    """Export wiki to JSON."""
    if not vault_path.exists():
        print(f"Vault not found: {vault_path}")
        return 1

    compiled_dirs = ["entities", "concepts", "comparisons", "projects", "queries"]
    export_data = []

    for d in compiled_dirs:
        p = vault_path / d
        if not p.is_dir():
            continue
        for md in p.rglob("*.md"):
            try:
                text = md.read_text(encoding="utf-8")
            except Exception:
                continue
            export_data.append(
                {
                    "path": str(md.relative_to(vault_path)),
                    "content": text,
                }
            )

    output = json.dumps(export_data, indent=2, ensure_ascii=False)
    out_path = getattr(args, "output", "-")
    if out_path == "-":
        print(output)
    else:
        Path(out_path).write_text(output, encoding="utf-8")
        print(f"Exported {len(export_data)} notes to {out_path}")

    return 0


def _load_config(vault_path: Path) -> dict:
    """Load config from Hermes config or return defaults."""
    try:
        import yaml

        cfg_path = Path.home() / ".hermes" / "config.yaml"
        if cfg_path.exists():
            with open(cfg_path, encoding="utf-8") as f:
                cfg = yaml.safe_load(f) or {}
            return cfg.get("memory", {}).get("llmwiki", {})
    except Exception:
        pass
    return {}
