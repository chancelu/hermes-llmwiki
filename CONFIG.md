# Configuration Reference

All configuration lives under `memory.llmwiki` in `~/.hermes/config.yaml`.

## Full Example

```yaml
memory:
  provider: llmwiki
  llmwiki:
    # Where your Markdown vault lives
    vault_path: ~/Documents/selfwiki

    # Directory structure (all relative to vault_path)
    schema:
      raw: "raw/"
      daily: "chronicle/daily/"
      entities: "entities/"
      concepts: "concepts/"
      comparisons: "comparisons/"
      projects: "projects/"
      queries: "queries/"

    # Automatic curation settings
    auto_curate:
      enabled: true
      archive_after_days: 30
      preserve_frontmatter: true

    # Search engine configuration
    search:
      engine: ripgrep       # ripgrep | grep | python
      max_results: 10
      context_lines: 3

    # Feature toggles
    features:
      wikilinks: true
      frontmatter: true
      backlinks: true
      ai_first_format: true
```

## Field Reference

### `vault_path`

- **Type**: `string` (path)
- **Required**: yes
- **Default**: `~/Documents/selfwiki`

Root directory of your Markdown vault. Can be an Obsidian vault or any folder.

### `schema`

- **Type**: `dict`
- **Required**: no

Directory structure for the 3-layer architecture. All paths are relative to `vault_path`.

| Key | Default | Description |
|-----|---------|-------------|
| `raw` | `raw/` | Layer 1: Session dumps and snapshots |
| `daily` | `chronicle/daily/` | Layer 2: Daily chronicle notes |
| `entities` | `entities/` | Layer 3: Concrete things (people, tools, companies) |
| `concepts` | `concepts/` | Layer 3: Abstract ideas, methods, patterns |
| `comparisons` | `comparisons/` | Layer 3: A vs B analyses |
| `projects` | `projects/` | Layer 3: Active and completed projects |
| `queries` | `queries/` | Layer 3: Standing questions and research threads |

### `auto_curate`

- **Type**: `dict`
- **Required**: no

| Key | Default | Description |
|-----|---------|-------------|
| `enabled` | `true` | Enable automatic curation |
| `archive_after_days` | `30` | Move daily notes older than N days to `archive/` |
| `preserve_frontmatter` | `true` | Keep frontmatter when merging notes |

### `search`

- **Type**: `dict`
- **Required**: no

| Key | Default | Description |
|-----|---------|-------------|
| `engine` | `ripgrep` | Search engine. `ripgrep` (fastest) > `grep` > `python` (fallback) |
| `max_results` | `10` | Maximum results per query |
| `context_lines` | `3` | Lines of context around each match |

### `features`

- **Type**: `dict`
- **Required**: no

| Key | Default | Description |
|-----|---------|-------------|
| `wikilinks` | `true` | Enable `[[Wiki Link]]` parsing |
| `frontmatter` | `true` | Enable YAML frontmatter parsing |
| `backlinks` | `true` | Track backlinks between notes |
| `ai_first_format` | `true` | Enforce AI-First note format (preamble, self-contained) |

## Environment Variables

| Variable | Description |
|----------|-------------|
| `LLMWIKI_VAULT` | Override `vault_path` for CLI commands |
| `HERMES_LLM_ENDPOINT` | LLM API endpoint for `curate --llm` (e.g. `https://api.openai.com`) |
| `HERMES_LLM_API_KEY` | API key for LLM endpoint |

## Obsidian Integration

If you use Obsidian, set `vault_path` to your Obsidian vault root:

```yaml
llmwiki:
  vault_path: ~/Documents/Obsidian Vault
```

The plugin will:
- Create directories inside your vault (won't interfere with existing notes)
- Generate notes with YAML frontmatter (Obsidian supports this natively)
- Use `[[wikilinks]]` syntax (Obsidian renders these as clickable links)

No Obsidian plugin required — it's just Markdown.
