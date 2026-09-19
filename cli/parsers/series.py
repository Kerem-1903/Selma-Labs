"""Argument-parser construction for the ``series`` command."""

from __future__ import annotations

import argparse


def add_series_commands(commands: argparse._SubParsersAction) -> None:
    series = commands.add_parser("series", help="Inspect a multi-character anime series")
    series_commands = series.add_subparsers(dest="series_command", required=True)
    series_status = series_commands.add_parser(
        "status", help="Validate the series style lock and character registry"
    )
    series_status.add_argument(
        "--project", default="config/series/selma-anime-v1.json"
    )
    series_style_approve = series_commands.add_parser(
        "approve-style", help="Create a human creative Style Approval Receipt"
    )
    series_style_approve.add_argument(
        "--project", default="config/series/selma-anime-v1.json"
    )
    series_style_approve.add_argument("--approved-by", required=True)
    series_style_approve.add_argument(
        "--check", action="append", dest="checks", default=[],
        help="Confirm one creative style criterion; repeat as needed",
    )
    series_style_promote = series_commands.add_parser(
        "promote-style", help="Promote the persisted creative style receipt"
    )
    series_style_promote.add_argument(
        "--project", default="config/series/selma-anime-v1.json"
    )
    series_lock_create = series_commands.add_parser(
        "create-production-lock", help="Create a pending technical production style lock"
    )
    series_lock_create.add_argument(
        "--project", default="config/series/selma-anime-v1.json"
    )
    series_lock_create.add_argument(
        "--workflow", default="assets/comfyui_keyframe_workflow.json"
    )
    series_lock_create.add_argument("--receipt-sha256", required=True)
    series_lock_create.add_argument("--width", type=int, default=768)
    series_lock_create.add_argument("--height", type=int, default=1152)
    series_lock_create.add_argument("--sampler", default="euler")
    series_lock_create.add_argument("--steps", type=int, default=24)
    series_lock_create.add_argument("--cfg", type=float, default=5.0)
    series_lock_create.add_argument("--denoise", type=float, default=0.65)
    series_lock_create.add_argument("--lock-version", type=int, default=1)
    series_lock_smoke = series_commands.add_parser(
        "smoke-production-lock",
        help=(
            "Render one frame through the pending production lock and write its "
            "smoke-test receipt"
        ),
    )
    series_lock_smoke.add_argument(
        "--project", default="config/series/selma-anime-v1.json"
    )
    series_lock_smoke.add_argument(
        "--workflow", default="assets/comfyui_keyframe_workflow.json"
    )
    series_lock_smoke.add_argument(
        "--receipt", required=True, help="Where to write the smoke-test receipt JSON"
    )
    series_lock_smoke.add_argument(
        "--image", help="Smoke frame path; defaults beside the receipt"
    )
    series_lock_smoke.add_argument(
        "--seed", type=int, help="Override the deterministic smoke seed"
    )
    series_lock_smoke.add_argument(
        "--full-model-hash",
        action="store_true",
        help="Hash every locked weight instead of checking size only",
    )
    series_lock_compatible = series_commands.add_parser(
        "mark-production-compatible",
        help="Attach a real smoke-test receipt and enable production",
    )
    series_lock_compatible.add_argument(
        "--project", default="config/series/selma-anime-v1.json"
    )
    series_lock_compatible.add_argument("--smoke-receipt", required=True)
    series_register = series_commands.add_parser(
        "register-character", help="Add one Character Bible to the series cast"
    )
    series_register.add_argument(
        "--project", default="config/series/selma-anime-v1.json"
    )
    series_register.add_argument("--bible", required=True)
    series_register.add_argument("--role", required=True)
    series_register.add_argument("--version", type=int, default=1)
    series_register.add_argument(
        "--status", choices=("DRAFT", "CANONICAL", "RETIRED"), default="DRAFT"
    )
