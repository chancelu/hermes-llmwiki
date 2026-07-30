# Installation Guide

## Prerequisites

- Python 3.10+
- [Hermes Agent](https://github.com/NousResearch/hermes-agent) 0.15.0+
- Optional: [ripgrep](https://github.com/BurntSushi/ripgrep) (for fast search)

## Install

### Option 1: pip (recommended)

```bash
pip install hermes-llmwiki
```

### Option 2: Clone to Hermes plugins directory

```bash
# Linux/macOS
git clone https://github.com/chancelu/hermes-llmwiki.git ~/.hermes/plugins/hermes-llmwiki

# Windows (PowerShell)
git clone https://github.com/chancelu/hermes-llmwiki.git $env:USERPROFILE\.hermes\plugins\hermes-llmwiki
```

## Configure

Edit `~/.hermes/config.yaml`:

```yaml
memory:
  provider: llmwiki
  llmwiki:
    vault_path: ~/Documents/selfwiki   # or your Obsidian vault path
```

Run the setup wizard:

```bash
hermes memory setup
```

This will:
1. Create the vault directory structure
2. Write a `SCHEMA.md` documentation file
3. Verify the configuration

## Verify Installation

```bash
# Check provider is discovered
hermes memory status

# Expected output:
# Active memory provider: llmwiki
# Vault: /home/user/Documents/selfwiki
```

## Upgrade

```bash
pip install --upgrade hermes-llmwiki
```

Or if cloned:

```bash
cd ~/.hermes/plugins/hermes-llmwiki
git pull
```

## Uninstall

```bash
pip uninstall hermes-llmwiki
```

Or remove the plugin directory and update `config.yaml`.
