"""Allow running as `python -m llmwiki`."""

from llmwiki.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
