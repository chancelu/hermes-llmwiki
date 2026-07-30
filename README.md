# hermes-llmwiki

> **"Obsidian is the IDE; the LLM is the programmer; the wiki is the codebase."** — Andrej Karpathy

A **Karpathy-native**, **zero-infrastructure** memory provider for [Hermes Agent](https://github.com/NousResearch/hermes-agent). Turns your local Markdown vault into a compounding knowledge system — no Docker, no cloud, no vector DB.

## Why This Exists

Every serious Hermes user hits the same wall: the agent forgets everything between sessions. Existing memory providers either:

- Lock you into a SaaS (Honcho, Mem0, Supermemory)
- Require Docker + Qdrant + Redis (Memory OS)
- Are read-only (hermes-homie-memory)
- Don't follow a structured curation model (Open Second Brain)

**hermes-llmwiki** is different:

| | hermes-llmwiki | Others |
|---|---|---|
| **Karpathy 3-layer architecture** | ✅ Native | ❌ |
| **AI-First note format** | ✅ Optimized for LLM retrieval | ❌ Human-first |
| **Zero dependencies** | ✅ Python + ripgrep + optional SQLite | ❌ Docker/SaaS |
| **Schema configurable** | ✅ `SCHEMA.md` drives your vault | ❌ Fixed structure |
| **Write + Read** | ✅ Bidirectional | ⚠️ Some read-only |

## Karpathy 3-Layer Architecture

```
┌─────────────────────────────────────────┐
│ Layer 3: Compiled Wiki (Query)          │
│  entities/  concepts/  comparisons/     │
│  projects/  queries/                    │
│         ↑  LLM curation (nightly)       │
├─────────────────────────────────────────┤
│ Layer 2: Chronicle (Daily Notes)        │
│  chronicle/daily/YYYY-MM-DD.md          │
│         ↑  auto-capture from sync_turn  │
├─────────────────────────────────────────┤
│ Layer 1: Raw (Session Exports)          │
│  raw/session-{id}.md                    │
│         ↑  on_session_end / on_pre_compress│
└─────────────────────────────────────────┘
```

- **Layer 1 (Raw)**: Session dumps, temporary, disposable
- **Layer 2 (Chronicle)**: Daily timeline, append-only, human-readable
- **Layer 3 (Compiled)**: Atomic notes with wikilinks, cross-references, frontmatter — the "source of truth"

## Install

```bash
# Option 1: pip
pip install hermes-llmwiki

# Option 2: clone to Hermes plugins directory
git clone https://github.com/chancelu/hermes-llmwiki.git ~/.hermes/plugins/hermes-llmwiki
```

Then activate in `~/.hermes/config.yaml`:

```yaml
memory:
  provider: llmwiki
  llmwiki:
    vault_path: ~/Documents/selfwiki   # or your Obsidian vault
```

Run setup wizard:

```bash
hermes memory setup
```

## CLI Commands

```bash
hermes llmwiki curate              # Manually trigger: daily notes → compiled wiki
hermes llmwiki stats               # Vault statistics
hermes llmwiki search "prompt injection"   # Search compiled layer
hermes llmwiki health              # Dead links, orphans, stale notes
hermes llmwiki export --format json        # Export wiki to JSON
```

## AI-First Note Format

Every compiled note follows Karpathy's AI-First Vault Principle:

```markdown
---
type: concept
name: "Prompt Injection"
date: 2026-07-29
tags: [security, llm]
ai-first: true
confidence: high
sources: ["https://..."]
---

## For future Claude
Prompt injection is an attack where malicious input overrides the LLM's
system instructions. This page is the canonical reference.

## Key claims
- Direct injection: user input contains hidden instructions
- Indirect injection: data from external source carries payload
- Source: OWASP LLM Top 10, 2026 edition

## Related
[[LLM Security]] · [[Jailbreak]] · [[System Prompt Hardening]]
```

## Configuration

Full config reference in [`CONFIG.md`](CONFIG.md).

## License

MIT
