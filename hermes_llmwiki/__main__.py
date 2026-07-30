"""Allow running as `python -m hermes_llmwiki`."""

import sys


def main():
    """Standalone CLI entry point."""
    # Parse minimal args for standalone usage
    import argparse

    parser = argparse.ArgumentParser(
        prog="hermes-llmwiki",
        description="Karpathy-native local Markdown wiki memory provider",
    )
    sub = parser.add_subparsers(dest="cmd")

    # Re-use the same CLI registration from cli.py
    from hermes_llmwiki.cli import register_cli, llmwiki_command

    register_cli(sub)
    args = parser.parse_args()

    if not args.cmd:
        parser.print_help()
        sys.exit(1)

    sys.exit(llmwiki_command(args))


if __name__ == "__main__":
    main()
