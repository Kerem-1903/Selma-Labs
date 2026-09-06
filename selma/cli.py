"""Short command entry point for character-studio operations."""

from __future__ import annotations

import sys

from cli.main import main as _main


def main() -> int:
    arguments = sys.argv[1:]
    if arguments and arguments[0] == "approve-view-pack":
        arguments = ["character", *arguments]
    return _main(arguments)


if __name__ == "__main__":
    raise SystemExit(main())
