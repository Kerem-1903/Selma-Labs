"""The CLI surface is composed from per-family builders in ``cli.parsers``.

``cli/main.py`` keeps ``build_parser`` as its public name so scripts and tests
that import it keep working; these tests fail if a refactor drops a command or
moves the entry point out from under them.
"""
from __future__ import annotations

import argparse

from cli.main import build_parser
from cli.parsers import build_parser as composed_build_parser

TOP_LEVEL_COMMANDS = [
    "series",
    "character",
    "background",
    "episode",
    "pilot",
    "trailer",
    "script",
    "story",
    "render",
    "blender",
    "rig",
    "preproduction",
    "keyframe",
]

CHARACTER_COMMANDS = [
    "show",
    "init",
    "lock-narrative",
    "create",
    "import-image",
    "benchmark-validate",
    "turnaround-tournament",
    "benchmark-run",
    "view-consistency-report",
    "drift-report",
    "qc-calibration-create",
    "qc-calibration-summarize",
    "approve-design",
    "turnaround",
    "pose-pack",
    "reject-view-pack",
    "approve-view-pack",
    "plan",
    "anchor",
    "references",
    "approve-pilot",
    "approve-references",
    "dataset",
    "audit-dataset",
    "review-template",
    "train",
]


def _subcommands(parser: argparse.ArgumentParser) -> list[str]:
    action = next(
        item
        for item in parser._actions  # noqa: SLF001 - introspection is the point
        if isinstance(item, argparse._SubParsersAction)  # noqa: SLF001
    )
    return list(action.choices)


def test_main_reexports_the_composed_parser() -> None:
    assert build_parser is composed_build_parser


def test_top_level_commands_are_all_registered_in_listing_order() -> None:
    assert _subcommands(build_parser()) == TOP_LEVEL_COMMANDS


def test_character_commands_are_all_registered_in_listing_order() -> None:
    character = next(
        item
        for item in build_parser()._actions  # noqa: SLF001
        if isinstance(item, argparse._SubParsersAction)  # noqa: SLF001
    ).choices["character"]
    assert _subcommands(character) == CHARACTER_COMMANDS
