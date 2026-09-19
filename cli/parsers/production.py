"""Argument-parser construction for the render, Blender, rig, preproduction
and keyframe commands."""

from __future__ import annotations

import argparse


def add_render_commands(commands: argparse._SubParsersAction) -> None:
    render = commands.add_parser("render", help="Render approved anime shots")
    render_commands = render.add_subparsers(dest="render_command", required=True)
    shot = render_commands.add_parser("shot")
    shot.add_argument("--plan", required=True, help="Shot JSON or breakdown JSON")
    shot.add_argument("--shot-id", help="Required when --plan contains multiple shots")
    shot.add_argument("--background-key", required=True)
    shot.add_argument("--audio-key", required=True)
    shot.add_argument("--output-key", required=True)

def add_blender_commands(commands: argparse._SubParsersAction) -> None:
    blender = commands.add_parser("blender", help="Blender Integration and A8.2 tools")
    blender_commands = blender.add_subparsers(dest="blender_command", required=True)
    register = blender_commands.add_parser("register-views")
    register.add_argument(
        "--input", required=True, help="Path to multiview reference image"
    )
    turntable = blender_commands.add_parser("turntable")
    turntable.add_argument("--model", required=True, help="Path to 3D model")
    turntable.add_argument(
        "--output-dir", default="output/blender", help="Directory for output"
    )
    turntable.add_argument(
        "--quality", default="preview", help="Render quality (preview, high)"
    )
    benchmark = blender_commands.add_parser("benchmark")
    benchmark.add_argument("--model", required=True, help="Path to 3D model")

def add_rig_commands(commands: argparse._SubParsersAction) -> None:
    rig = commands.add_parser("rig", help="A9 Rig and Acting Validation Tools")
    rig_commands = rig.add_subparsers(dest="rig_command", required=True)
    validate = rig_commands.add_parser("validate")
    validate.add_argument("--model", required=True, help="Path to blender model")
    preview = rig_commands.add_parser("preview")
    preview.add_argument("--model", required=True, help="Path to blender model")
    preview.add_argument("--action", required=True, help="Action name to preview")
    preview.add_argument(
        "--output", default="output/blender/preview.mp4", help="Output video path"
    )

def add_preproduction_commands(commands: argparse._SubParsersAction) -> None:
    preproduction = commands.add_parser(
        "preproduction", help="Run the locked P1-P8 anime pre-production workflow"
    )
    preproduction_commands = preproduction.add_subparsers(
        dest="preproduction_command", required=True
    )
    preproduction_commands.add_parser("status", help="Validate active canon locks")
    golden_set = preproduction_commands.add_parser(
        "golden-set", help="Generate a character's ten-image consistency set"
    )
    golden_set.add_argument("--character-id", default="akira")
    golden_set.add_argument("--model-id", required=True)
    golden_set.add_argument("--model-revision", required=True)
    golden_set.add_argument(
        "--output", help="Defaults to output/preproduction/<character>-golden-set.json"
    )
    production_plan = preproduction_commands.add_parser(
        "plan", help="Convert an approved EpisodeScript JSON into a shot hierarchy"
    )
    production_plan.add_argument("--input", required=True)
    production_plan.add_argument(
        "--character-id",
        required=True,
        help=(
            "Locked Character Bible that conditions the breakdown. Required on "
            "purpose: a defaulted identity would silently label every shot with "
            "the wrong character state."
        ),
    )
    production_plan.add_argument("--output", required=True)

def add_keyframe_commands(commands: argparse._SubParsersAction) -> None:
    keyframe = commands.add_parser("keyframe", help="Keyframe generation tools")
    keyframe_commands = keyframe.add_subparsers(dest="keyframe_command", required=True)
    pair = keyframe_commands.add_parser(
        "pair", help="Generate unapproved start/end frames with OpenPose"
    )
    pair.add_argument("--shot-id", required=True)
    pair.add_argument("--character-id", default="akira")
    pair.add_argument("--outfit-id", default="akira-default")
    pair.add_argument("--prompt-start", required=True)
    pair.add_argument("--prompt-end", required=True)
    pair.add_argument("--start-pose", required=True)
    pair.add_argument("--end-pose", required=True)
    pair_approve = keyframe_commands.add_parser(
        "approve-pair", help="Human-approve a generated start/end pair"
    )
    pair_approve.add_argument("--shot-id", required=True)
    pair_approve.add_argument("--manifest", required=True)
    pair_approve.add_argument("--approved-by", required=True)
    pair_approve.add_argument(
        "--check", action="append", dest="checks", default=[],
        help="Confirm one pair check; repeat for all five required checks",
    )
