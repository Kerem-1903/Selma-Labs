"""Compatibility alias for the single durable Shorts factory.

All production behavior lives in :mod:`scripts.run_factory`. Keeping this
small alias avoids breaking bookmarks while guaranteeing there is only one
composition root and one stage graph.
"""
from __future__ import annotations

try:
    from scripts.run_factory import build_arg_parser, main
except ModuleNotFoundError:  # pragma: no cover - direct script execution path
    from run_factory import build_arg_parser, main

__all__ = ["build_arg_parser", "main"]


if __name__ == "__main__":
    raise SystemExit(main())
