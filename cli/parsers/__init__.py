"""Compose the SELMA Labs command-line parser from per-family builders.

Each builder owns one top-level command and keeps its arguments beside the
rest of that command's family, so ``cli/main.py`` stays a dispatcher.
"""

from __future__ import annotations

import argparse

from cli.parsers.character import add_character_commands
from cli.parsers.episode import (
    add_background_commands,
    add_episode_commands,
    add_pilot_commands,
    add_script_commands,
    add_story_commands,
    add_trailer_commands,
)
from cli.parsers.production import (
    add_blender_commands,
    add_keyframe_commands,
    add_preproduction_commands,
    add_render_commands,
    add_rig_commands,
)
from cli.parsers.series import add_series_commands


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="SELMA Labs anime production CLI")
    commands = parser.add_subparsers(dest="command", required=True)

    add_series_commands(commands)
    add_character_commands(commands)
    add_background_commands(commands)
    add_episode_commands(commands)
    add_pilot_commands(commands)
    add_trailer_commands(commands)
    add_script_commands(commands)
    add_story_commands(commands)
    add_render_commands(commands)
    add_blender_commands(commands)
    add_rig_commands(commands)
    add_preproduction_commands(commands)
    add_keyframe_commands(commands)

    return parser
