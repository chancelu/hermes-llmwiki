# Changelog

## 0.2.0 — Framework-Agnostic Rewrite

### Breaking Changes
- **Renamed package**: `hermes-llmwiki` → `llmwiki`
- **Removed Hermes dependency**: No longer a Hermes plugin. Now a standalone framework.
- **Entry point changed**: `hermes_llmwiki` → `llmwiki`

### New Features
- **Multi-engine search**: ripgrep, SQLite FTS5, pure Python fallback
- **Multi-strategy retrieval**: keyword + graph (wikilink traversal) + temporal
- **RRF fusion**: Reciprocal Rank Fusion for combining retrieval strategies
- **Token budget management**: ContextAssembler never overflows context window
- **In-memory LRU cache**: L1 RAM layer for frequent queries
- **OpenClaw adapter**: First-class `OpenClawMemoryHook` for OpenClaw agents
- **YAML-driven configuration**: `llmwiki.yaml` or `~/.config/llmwiki/config.yaml`
- **Environment variable overrides**: `LLMWIKI_VAULT_PATH`, `LLMWIKI_INDEX_ENGINE`, etc.
- **Incremental indexing**: Only re-index changed files via mtime tracking

### Architecture
- **New module structure**:
  - `llmwiki/core/` — Harness, Indexer, Retriever, Assembler, Cache, Config
  - `llmwiki/search/` — Pluggable search engines (ripgrep, sqlite, python)
  - `llmwiki/vault/` — Capture, Curate, Schema, Writer
  - `llmwiki/adapters/` — Framework adapters (OpenClaw first)
  - `llmwiki/cli.py` — Standalone CLI

### Retained from 0.1.x
- Karpathy 3-layer vault architecture (raw → chronicle → compiled)
- AI-First note format with frontmatter
- Atomic file writes
- LLM-driven + regex fallback curation
- Daily chronicle capture
- Wikilink support

## 0.1.x — hermes-llmwiki

- Initial release as Hermes Agent memory plugin
- ripgrep-based search
- 3-layer vault architecture
- Basic curation pipeline
