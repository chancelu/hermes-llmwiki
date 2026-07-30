# Usage Guide

## Daily Workflow

hermes-llmwiki works automatically during your Hermes sessions:

1. **Every turn** → `sync_turn()` appends to `chronicle/daily/YYYY-MM-DD.md`
2. **Session end** → `on_session_end()` adds a summary
3. **Context compression** → `on_pre_compress()` saves snapshots to `raw/`
4. **Before LLM call** → `prefetch()` injects relevant wiki context into prompt

## Manual Curation

Run curation to promote daily notes to compiled wiki:

```bash
# Regex-based extraction (default)
hermes llmwiki curate

# LLM-driven extraction (higher quality)
hermes llmwiki curate --llm

# With specific model
hermes llmwiki curate --llm --model gpt-4o
```

For LLM mode, set environment variables:

```bash
export HERMES_LLM_ENDPOINT="https://api.openai.com"
export HERMES_LLM_API_KEY="sk-..."
```

Or the plugin auto-discovers from your `custom_providers` in `config.yaml`.

## Searching

```bash
# Search compiled wiki
hermes llmwiki search "prompt injection"

# JSON output for scripting
hermes llmwiki search "bitcoin" --json
```

## Health Check

```bash
hermes llmwiki health
```

Reports:
- Dead wikilinks (links to non-existent notes)
- Orphan notes (no incoming links)
- Note counts per category

## Vault Statistics

```bash
hermes llmwiki stats
```

Example output:
```json
{
  "vault": "/home/user/Documents/selfwiki",
  "compiled": {
    "entities": 42,
    "concepts": 85,
    "comparisons": 12,
    "projects": 7
  },
  "daily": 30,
  "raw": 15
}
```

## Export

```bash
# Export compiled wiki to JSON
hermes llmwiki export -o wiki-backup.json
```

## AI-First Note Format

When creating notes manually or via tools, follow this pattern:

```markdown
---
type: concept
name: "Prompt Injection"
date: 2026-07-29
tags: [security, llm]
ai-first: true
confidence: high
---

## For future Claude
Prompt injection is an attack where malicious input overrides...

## Key claims
- Direct injection: user input contains hidden instructions
- Indirect injection: data from external source carries payload

## Related
[[LLM Security]] · [[Jailbreak]]
```

This format is optimized for LLM retrieval — the `## For future Claude` section ensures the note is self-contained when injected into context.

## Cron / Heartbeat Automation

Add to your `HEARTBEAT.md` or a cron job:

```bash
# Nightly curation (2 AM)
0 2 * * * hermes llmwiki curate --llm

# Weekly health check (Sunday)
0 9 * * 0 hermes llmwiki health
```

## Multi-Agent Setup

Point all your agents to the same vault:

```yaml
# Agent A config
memory:
  provider: llmwiki
  llmwiki:
    vault_path: ~/shared-vault

# Agent B config (same vault)
memory:
  provider: llmwiki
  llmwiki:
    vault_path: ~/shared-vault
```

Both agents read and write the same compiled layer. Each agent still has its own daily chronicle (session-level), but the compiled wiki is shared.
