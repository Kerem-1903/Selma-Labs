from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import sys
import tempfile
from collections.abc import Callable, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config.container import AnimationContainer, create_container
from core.application.services.hierarchical_shot_planning_service import (
    HierarchicalShotPlanningService,
)
from core.application.services.script_breakdown_service import ScriptBreakdownService
from core.domain.entities.character_bible import CharacterBible
from core.domain.entities.episode_script import EpisodeScript
from core.domain.entities.shot_animation import ShotPlan
from core.domain.value_objects.story_review import StoryDevelopmentResult


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="SELMA Labs anime production CLI")
    commands = parser.add_subparsers(dest="command", required=True)

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

    character = commands.add_parser("character", help="Inspect canonical characters")
    character_commands = character.add_subparsers(
        dest="character_command", required=True
    )
    character_show = character_commands.add_parser(
        "show", help="Show an explicitly selected Character Bible"
    )
    character_show.add_argument("--input", required=True, help="Character Bible JSON")
    character_init = character_commands.add_parser(
        "init", help="Create a Character Bible from a descriptive brief"
    )
    character_init.add_argument("--brief", required=True)
    character_init.add_argument("--output", required=True)
    character_lock_narrative = character_commands.add_parser(
        "lock-narrative",
        help=(
            "Lock a character's narrative canon on its own, without "
            "producing or claiming any visual asset"
        ),
    )
    character_lock_narrative.add_argument(
        "--input", required=True, help="Character Bible JSON"
    )
    character_lock_narrative.add_argument(
        "--approved-by", required=True, help="Named human locking this narrative canon"
    )
    character_lock_narrative.add_argument(
        "--output", required=True, help="Character Bible JSON to write back"
    )
    character_lock_narrative.add_argument(
        "--receipt",
        help=(
            "Approval receipt path; defaults to "
            "output/preproduction/narrative-locks/<character_id>.json"
        ),
    )
    character_create = character_commands.add_parser(
        "create", help="Generate canonical design choices from a character brief"
    )
    character_create.add_argument("--brief", required=True)
    character_create.add_argument("--manifest", required=True)
    character_create.add_argument("--output-prefix", default="characters")
    character_create.add_argument("--count", type=int, default=5)
    character_create.add_argument(
        "--run-id",
        help="Optional unique run label; generated automatically when omitted",
    )
    character_create.add_argument(
        "--style-reference",
        help=(
            "Optional local image (e.g. an approved Akira frame) used ONLY as a "
            "low-weight visual style seed; the new character's identity comes "
            "from the brief text"
        ),
    )
    character_create.add_argument(
        "--style-weight",
        type=float,
        default=0.35,
        help="IP-Adapter weight for the style seed (0 < weight <= 1; default 0.35)",
    )
    character_import = character_commands.add_parser(
        "import-image", help="Register a supplied front-view image as an unapproved canonical candidate"
    )
    character_import.add_argument("--brief", required=True)
    character_import.add_argument("--image", required=True)
    character_import.add_argument("--manifest", required=True)
    character_import.add_argument("--output-prefix", default="characters")
    character_import.add_argument("--run-id")
    character_benchmark = character_commands.add_parser(
        "benchmark-validate",
        help="Validate a versioned character quality benchmark and its image",
    )
    character_benchmark.add_argument("--benchmark", required=True)
    character_tournament = character_commands.add_parser(
        "turnaround-tournament",
        help=(
            "Render one approved source through several model locks and "
            "compare drift to decide local vs rented compute"
        ),
    )
    character_tournament.add_argument("--benchmark", required=True)
    character_tournament.add_argument("--brief", required=True)
    character_tournament.add_argument(
        "--source-storage-key",
        required=True,
        help="Approved canonical image inside the keyframe storage root",
    )
    character_tournament.add_argument(
        "--model-lock",
        action="append",
        dest="model_locks",
        required=True,
        help="Model lock to test; repeat for each checkpoint",
    )
    character_tournament.add_argument("--output", required=True)
    character_tournament.add_argument(
        "--seeds",
        type=int,
        default=3,
        help="Seeds rendered per view (1-6); each variant sees the identical set",
    )
    character_tournament.add_argument("--seed-base", type=int, default=42)
    character_tournament.add_argument("--run-id")
    character_tournament.add_argument(
        "--output-prefix", default="benchmarks/turnaround"
    )
    character_tournament.add_argument("--thresholds")
    character_benchmark_run = character_commands.add_parser(
        "benchmark-run",
        help="Run a fair text-only character quality tournament across model locks",
    )
    character_benchmark_run.add_argument("--benchmark", required=True)
    character_benchmark_run.add_argument("--brief", required=True)
    character_benchmark_run.add_argument(
        "--model-lock",
        action="append",
        dest="model_locks",
        required=True,
        help="Model lock to test; repeat for each checkpoint",
    )
    character_benchmark_run.add_argument("--output", required=True)
    character_benchmark_run.add_argument("--count", type=int, default=3)
    character_benchmark_run.add_argument(
        "--run-id",
        help="Stable tournament run id; generated automatically when omitted",
    )
    character_consistency = character_commands.add_parser(
        "view-consistency-report",
        help="Audit existing character view-pack consistency evidence",
    )
    character_consistency.add_argument("--view-pack", required=True)
    character_consistency.add_argument("--brief", required=True)
    character_consistency.add_argument("--manifest")
    character_consistency.add_argument("--human-review")
    character_consistency.add_argument("--output")
    character_drift = character_commands.add_parser(
        "drift-report",
        help=(
            "Measure advisory pixel drift between an approved source and a "
            "generated turnaround pack"
        ),
    )
    character_drift.add_argument("--source", required=True)
    character_drift.add_argument(
        "--pack",
        help="Turnaround directory to read VIEW.png files from",
    )
    character_drift.add_argument(
        "--view",
        action="append",
        dest="drift_views",
        help="Explicit VIEW=path entry; repeat per view",
    )
    character_drift.add_argument(
        "--accent-colour",
        default=None,
        help=(
            "#RRGGBB accent used for signature-mark and accent-fraction "
            "metrics; defaults to the configured accent, pass an empty value "
            "to disable those metrics"
        ),
    )
    character_drift.add_argument(
        "--mark-side",
        default=None,
        choices=["", "left", "right"],
        help=(
            "Body side the signature mark is bound to, for mirror detection; "
            "defaults to the configured side, pass an empty value to disable "
            "the mark checks"
        ),
    )
    character_drift.add_argument(
        "--thresholds", help="Previously calibrated thresholds JSON"
    )
    character_drift.add_argument(
        "--calibrate",
        action="store_true",
        help="Derive thresholds from an already accepted pack instead of reporting",
    )
    character_drift.add_argument("--margin", type=float, default=1.35)
    character_drift.add_argument("--output")
    character_qc_calibration = character_commands.add_parser(
        "qc-calibration-create",
        help="Create a human-labelled character QC calibration manifest",
    )
    character_qc_calibration.add_argument("--storage-root", default="output/production")
    character_qc_calibration.add_argument(
        "--benchmark-prefix", default="benchmarks/akira-quality-v1"
    )
    character_qc_calibration.add_argument("--output", required=True)
    character_qc_calibration.add_argument("--minimum-images", type=int, default=50)
    character_qc_calibration.add_argument("--maximum-images", type=int, default=100)
    character_qc_summary = character_commands.add_parser(
        "qc-calibration-summarize",
        help="Summarize completed human labels in a QC calibration manifest",
    )
    character_qc_summary.add_argument("--manifest", required=True)
    character_qc_summary.add_argument("--output")
    character_approve_design = character_commands.add_parser(
        "approve-design", help="Lock one generated design as the canonical character"
    )
    character_approve_design.add_argument("--brief", required=True)
    character_approve_design.add_argument("--manifest", required=True)
    character_approve_design.add_argument("--candidate-key", required=True)
    character_approve_design.add_argument("--approved-by", required=True)
    character_approve_design.add_argument("--output", required=True)
    character_approve_design.add_argument("--output-prefix", default="characters")
    character_approve_design.add_argument("--version", type=int, default=1)
    character_approve_design.add_argument(
        "--confirm-brief-consistency",
        action="store_true",
        help="Explicitly confirm that a supplied image does not conflict with the brief",
    )
    character_turnaround = character_commands.add_parser(
        "turnaround",
        help="Generate the seven neutral reference drafts from an approved design",
    )
    character_turnaround.add_argument("--brief", required=True)
    character_turnaround.add_argument("--approval", required=True)
    character_turnaround.add_argument("--manifest", required=True)
    character_turnaround.add_argument("--output-prefix", default="characters")
    character_turnaround.add_argument(
        "--seeds",
        type=int,
        default=1,
        help=(
            "Render this many seeds per view and keep the least-drifted one "
            "(1-6; only meaningful for the source-led edit dialect)"
        ),
    )
    character_turnaround.add_argument(
        "--view",
        action="append",
        dest="rerender_views",
        default=[],
        help=(
            "Re-render only this view inside an existing pack and keep every "
            "other view byte-identical; repeat per view. The replaced render is "
            "archived as quarantine evidence, and the new attempt uses a seed "
            "block that has never been drawn"
        ),
    )
    character_turnaround.add_argument(
        "--restore-superseded",
        action="store_true",
        help=(
            "Undo a targeted re-render for the named --view entries: put the "
            "archived render back and file the render it displaces. Nothing is "
            "drawn"
        ),
    )
    character_turnaround.add_argument(
        "--restored-by",
        help="Human whose verdict restores the archived renders (required with --restore-superseded)",
    )
    character_turnaround.add_argument(
        "--reason",
        default="",
        help="Why the archived render is preferred; recorded in the restore receipt",
    )
    pose_pack = character_commands.add_parser(
        "pose-pack", help="Generate or approve the five-pose pre-animation character pack"
    )
    pose_pack_commands = pose_pack.add_subparsers(
        dest="pose_pack_command", required=True
    )
    pose_pack_generate = pose_pack_commands.add_parser(
        "generate", help="Generate a resumable five-pose pack from a canonical approval"
    )
    pose_pack_generate.add_argument("--brief", required=True)
    pose_pack_generate.add_argument("--approval", required=True)
    pose_pack_generate.add_argument(
        "--active-series",
        default="config/series/selma-anime-v1.json",
        help="Active series manifest; Production resolves style only from this file",
    )
    pose_pack_generate.add_argument("--manifest", required=True)
    pose_pack_generate.add_argument("--output-prefix", default="characters")
    pose_pack_generate.add_argument("--run-id")
    pose_pack_approve = pose_pack_commands.add_parser(
        "approve", help="Human-approve a complete five-pose character pack"
    )
    pose_pack_approve.add_argument("--manifest", required=True)
    pose_pack_approve.add_argument("--approved-by", required=True)
    pose_pack_approve.add_argument(
        "--check", action="append", dest="checks", default=[],
        help="Confirm one pose-pack check; repeat for all five checks",
    )
    pose_pack_reject = pose_pack_commands.add_parser(
        "reject",
        help=(
            "Record a human refusal of a pose pack; a rejected pack can never "
            "be approved afterwards"
        ),
    )
    pose_pack_reject.add_argument("--manifest", required=True)
    pose_pack_reject.add_argument("--rejected-by", required=True)
    pose_pack_reject.add_argument(
        "--reason", required=True, help="Why the pack was refused; stored verbatim"
    )
    pose_pack_reject.add_argument(
        "--superseded-by-version",
        type=int,
        help="Character version that replaces this one, when already known",
    )
    pose_pack_rerender = pose_pack_commands.add_parser(
        "rerender",
        help=(
            "Redraw only the poses whose pose guide changed, in place, and file "
            "the displaced bytes as quarantine evidence"
        ),
    )
    pose_pack_rerender.add_argument("--brief", required=True)
    pose_pack_rerender.add_argument("--approval", required=True)
    pose_pack_rerender.add_argument(
        "--manifest",
        required=True,
        help="Storage key of the pose-pack manifest, as recorded in the pack",
    )
    pose_pack_rerender.add_argument("--authorized-by", required=True)
    pose_pack_rerender.add_argument(
        "--reason", required=True, help="Why the redraw is allowed; stored verbatim"
    )
    pose_pack_rerender.add_argument(
        "--output",
        help="Optional path to write the redrawn manifest receipt to",
    )
    pose_pack_batch = pose_pack_commands.add_parser(
        "batch", help="Run resumable pose-pack generation for a JSON job list"
    )
    pose_pack_batch.add_argument("--jobs", required=True)
    pose_pack_batch.add_argument("--manifest", required=True)
    pose_pack_batch.add_argument(
        "--active-series",
        default="config/series/selma-anime-v1.json",
        help="Active series whose production style lock is pinned at batch start",
    )
    pose_pack_batch.add_argument(
        "--workflow",
        default="assets/comfyui_keyframe_workflow.json",
        help="Workflow whose hash is verified against the production style lock",
    )
    pose_pack_batch.add_argument("--stop-on-error", action="store_true")
    character_reject_views = character_commands.add_parser(
        "reject-view-pack",
        help=(
            "Record a human refusal of a view pack; a rejected pack can never "
            "be approved afterwards"
        ),
    )
    character_reject_views.add_argument("--character", required=True)
    character_reject_views.add_argument("--version", default="v1")
    character_reject_views.add_argument("--rejected-by", required=True)
    character_reject_views.add_argument(
        "--reason", required=True, help="Why the pack was refused; stored verbatim"
    )
    character_reject_views.add_argument("--output")
    character_reject_views.add_argument("--output-prefix", default="characters")
    character_reject_views.add_argument(
        "--superseded-by-version",
        type=int,
        help="Character version that replaces this one, when already known",
    )
    character_approve_views = character_commands.add_parser(
        "approve-view-pack",
        help="Human-approve a complete QC-passed seven-view pack",
    )
    character_approve_views.add_argument("--character", required=True)
    character_approve_views.add_argument("--version", default="v1")
    character_approve_views.add_argument("--approved-by", default="local-operator")
    character_approve_views.add_argument("--output")
    character_approve_views.add_argument("--output-prefix", default="characters")
    character_approve_views.add_argument(
        "--acceptance",
        help=(
            "Path to the character acceptance list JSON; defaults to "
            "config/character_acceptance/<character>-v<version>.json"
        ),
    )
    character_approve_views.add_argument(
        "--check",
        action="append",
        dest="checks",
        default=[],
        help=(
            "Confirm one human acceptance check id; repeat for every item "
            "in the acceptance list"
        ),
    )
    character_plan = character_commands.add_parser(
        "plan", help="Create a reusable 20+3 character reference recipe"
    )
    character_plan.add_argument("--input", required=True, help="Character Bible JSON")
    character_plan.add_argument("--output", required=True, help="Onboarding plan JSON")
    character_anchor = character_commands.add_parser(
        "anchor", help="Generate one unapproved identity anchor"
    )
    character_anchor.add_argument("--input", required=True, help="Character Bible JSON")
    character_anchor.add_argument("--output-prefix", default="character-candidates")
    character_anchor.add_argument(
        "--count", type=int, default=3, help="Number of unapproved anchor candidates"
    )
    character_anchor.add_argument(
        "--source-reference-key",
        help="Optional storage key used to bootstrap a reference-locked anchor",
    )
    character_references = character_commands.add_parser(
        "references", help="Generate the 20+3 candidate pack from an approved anchor"
    )
    character_references.add_argument(
        "--input", required=True, help="Character Bible JSON"
    )
    character_references.add_argument("--approved-anchor-key", required=True)
    character_references.add_argument("--output-prefix", default="character-candidates")
    character_references.add_argument("--manifest", required=True)
    character_references.add_argument(
        "--limit", type=int, help="Generate only the first N recipes for a pilot run"
    )
    character_references.add_argument(
        "--recipe-offset",
        type=int,
        default=0,
        help="Zero-based recipe index to start from; lets staged runs skip already-covered views",
    )
    character_references.add_argument(
        "--defer-visual-review",
        action="store_true",
        help="Keep candidates pending when no trustworthy vision model is available",
    )
    character_references.add_argument(
        "--pilot-approval",
        help="Human pilot-approval receipt required for more than one recipe",
    )
    character_references.add_argument(
        "--seed-offset",
        type=int,
        default=0,
        help="Deterministic pilot variation; use 0, 10000, 20000, ...",
    )
    character_references.add_argument(
        "--pose-references",
        help=(
            "JSON file mapping every selected ACTION_* view to an OpenPose "
            "PNG storage key"
        ),
    )
    character_pilot_approve = character_commands.add_parser(
        "approve-pilot", help="Approve the identity/framing pilot after visual review"
    )
    character_pilot_approve.add_argument("--input", required=True)
    character_pilot_approve.add_argument("--approved-anchor-key", required=True)
    character_pilot_approve.add_argument("--pilot-key", required=True)
    character_pilot_approve.add_argument("--approved-by", required=True)
    character_pilot_approve.add_argument("--output", required=True)
    for check in (
        "face-match",
        "hair-match",
        "immutable-marks-match",
        "outfit-match",
        "framing-match",
        "anatomy-pass",
    ):
        character_pilot_approve.add_argument(f"--{check}", action="store_true")
    character_approve = character_commands.add_parser(
        "approve-references",
        help="Register human-selected reference candidates in a Character Bible",
    )
    character_approve.add_argument(
        "--input", required=True, help="Character Bible JSON"
    )
    character_approve.add_argument("--selections", required=True)
    character_approve.add_argument("--approved-by", required=True)
    character_approve.add_argument("--output", required=True)
    character_approve.add_argument(
        "--lock-narrative",
        action="store_true",
        help="Also confirm and lock the narrative profile",
    )
    character_dataset = character_commands.add_parser(
        "dataset", help="Build a LoRA dataset with character-specific captions"
    )
    character_dataset.add_argument(
        "--input", required=True, help="Character Bible JSON"
    )
    character_dataset.add_argument("--source", required=True)
    character_dataset.add_argument("--output", required=True)
    character_dataset.add_argument(
        "--trigger-token",
        help="Defaults to the character-specific schema-v2 trigger token",
    )
    character_dataset.add_argument(
        "--review-manifest", help="Human review JSON for every source image"
    )
    character_dataset.add_argument(
        "--canonical-anchor", help="Approved identity anchor used to verify lineage"
    )
    character_audit = character_commands.add_parser(
        "audit-dataset", help="Audit an existing LoRA dataset without training"
    )
    character_audit.add_argument("--manifest", required=True)
    character_audit.add_argument("--output")
    character_review_template = character_commands.add_parser(
        "review-template", help="Create a fail-closed per-image review form"
    )
    character_review_template.add_argument("--manifest", required=True)
    character_review_template.add_argument("--canonical-anchor", required=True)
    character_review_template.add_argument("--output", required=True)
    character_train = character_commands.add_parser(
        "train", help="Train a validated character LoRA with the 8 GB profile"
    )
    character_train.add_argument("--input", required=True, help="Character Bible JSON")
    character_train.add_argument("--dataset", required=True)
    character_train.add_argument("--base-model", required=True)
    character_train.add_argument("--sd-scripts-dir", required=True)
    character_train.add_argument("--output", required=True)
    character_train.add_argument("--model-name", required=True)
    character_train.add_argument("--steps", type=int, default=240)

    background = commands.add_parser(
        "background", help="Create consistent, character-free anime locations"
    )
    background_commands = background.add_subparsers(
        dest="background_command", required=True
    )
    background_init = background_commands.add_parser(
        "init", help="Create a Location Bible from a descriptive brief"
    )
    background_init.add_argument("--brief", required=True)
    background_init.add_argument("--output", required=True)
    background_plan = background_commands.add_parser(
        "plan", help="Create the reusable 12-shot coverage plan"
    )
    background_plan.add_argument("--input", required=True)
    background_plan.add_argument("--output", required=True)
    background_generate = background_commands.add_parser(
        "generate", help="Generate automatically reviewed clean background plates"
    )
    background_generate.add_argument("--input", required=True)
    background_generate.add_argument("--output-prefix", default="background-candidates")
    background_generate.add_argument("--manifest", required=True)
    background_approve = background_commands.add_parser(
        "approve", help="Human-approve a complete background pack and lock the location"
    )
    background_approve.add_argument("--input", required=True)
    background_approve.add_argument("--manifest", required=True)
    background_approve.add_argument("--approved-by", required=True)
    background_approve.add_argument("--output", required=True)

    episode = commands.add_parser(
        "episode", help="Create an executable screenplay-to-timeline visual plan"
    )
    episode_commands = episode.add_subparsers(
        dest="episode_command", required=True
    )
    episode_plan = episode_commands.add_parser(
        "plan", help="Plan scene purpose, character poses, backgrounds, and a 24 FPS timeline"
    )
    episode_plan.add_argument("--input", required=True, help="Screenplay text or EpisodeScript JSON")
    episode_plan.add_argument("--output", help="Optional JSON output path")
    episode_plan.add_argument("--episode-id", default="episode-001")
    episode_plan.add_argument("--title", default="Untitled episode")
    episode_plan.add_argument("--director-provider", choices=("rules", "claude"), default="rules", help="Optional structured Episode Director provider")
    episode_plan.add_argument("--director-model", default="claude-sonnet-4-5")
    episode_plan.add_argument(
        "--character-bible", action="append", dest="character_bibles", default=[],
        help="Character Bible JSON; repeat for every available character",
    )
    episode_plan.add_argument(
        "--location-bible", action="append", dest="location_bibles", default=[],
        help="Location Bible JSON; repeat for every available location",
    )
    episode_plan.add_argument(
        "--world-bible",
        help=(
            "World Bible JSON; its non-cast voices speak without joining the "
            "cast, so they never order a pose pack"
        ),
    )
    episode_plan.add_argument(
        "--pose-pack", action="append", dest="pose_packs", default=[],
        help="Generated five-pose manifest JSON; repeat for every available character",
    )
    episode_plan.add_argument(
        "--background-pack", action="append", dest="background_packs", default=[],
        help="Generated background candidate pack JSON; repeat for every location",
    )
    episode_prepare = episode_commands.add_parser(
        "prepare", help="Prepare an episode plan and enumerate missing pose/background jobs"
    )
    episode_prepare.add_argument("--input", required=True, help="Screenplay text or EpisodeScript JSON")
    episode_prepare.add_argument("--output", required=True, help="Preparation manifest and plan output path")
    episode_prepare.add_argument("--episode-id", default="episode-001")
    episode_prepare.add_argument("--title", default="Untitled episode")
    episode_prepare.add_argument("--director-provider", choices=("rules", "claude"), default="rules", help="Optional structured Episode Director provider")
    episode_prepare.add_argument("--director-model", default="claude-sonnet-4-5")
    episode_prepare.add_argument(
        "--character-bible", action="append", dest="character_bibles", default=[],
        help="Character Bible JSON; repeat for every available character",
    )
    episode_prepare.add_argument(
        "--location-bible", action="append", dest="location_bibles", default=[],
        help="Location Bible JSON; repeat for every available location",
    )
    episode_prepare.add_argument(
        "--world-bible",
        help=(
            "World Bible JSON; its non-cast voices speak without joining the "
            "cast, so they never order a pose pack"
        ),
    )
    episode_prepare.add_argument(
        "--pose-pack", action="append", dest="pose_packs", default=[],
        help="Generated five-pose manifest JSON; repeat for every available character",
    )
    episode_prepare.add_argument(
        "--background-pack", action="append", dest="background_packs", default=[],
        help="Generated background candidate pack JSON; repeat for every location",
    )
    episode_prepare.add_argument(
        "--pose-job", action="append", dest="pose_jobs", default=[],
        help="Pose-pack generation job JSON; repeat for each character",
    )
    episode_prepare.add_argument(
        "--generate-assets", action="store_true",
        help="Dispatch supplied pose jobs and required backgrounds before writing the plan",
    )
    episode_prepare.add_argument(
        "--asset-mode", choices=("DISCOVERY", "PRODUCTION"), default="DISCOVERY",
        help="Use deterministic fake providers or the configured production provider",
    )
    episode_prepare.add_argument(
        "--asset-output-root",
        help="Directory for generated asset manifests; defaults beside --output",
    )
    episode_prepare.add_argument(
        "--active-series",
        default="config/series/selma-anime-v1.json",
        help="Production style-lock source used when dispatching pose generation",
    )
    episode_prepare.add_argument(
        "--workflow",
        default="assets/comfyui_keyframe_workflow.json",
        help="ComfyUI workflow whose lock is used for production generation",
    )
    episode_prepare.add_argument("--resume", help="Previous preparation manifest to resume")
    episode_prepare.add_argument(
        "--retry-job", action="append", dest="retry_jobs", default=[],
        help="Retry one failed preparation job; repeat for multiple jobs",
    )
    episode_inspect = episode_commands.add_parser(
        "inspect", help="Inspect a previously generated Episode Director plan"
    )
    episode_inspect.add_argument("--input", required=True)
    episode_inspect.add_argument(
        "--full", action="store_true", help="Print the complete plan instead of a summary"
    )
    episode_animatic = episode_commands.add_parser(
        "animatic", help="Build a reviewable 24 FPS animatic from an episode plan"
    )
    episode_animatic.add_argument("--input", required=True, help="Episode plan or preparation JSON")
    episode_animatic.add_argument("--output", required=True, help="Animatic result JSON")
    episode_animatic.add_argument(
        "--mode", choices=("STRICT", "PLACEHOLDER"), default="STRICT",
        help="Block on missing assets or render visible placeholders for review",
    )
    episode_animatic.add_argument(
        "--storage-root", default="output/production",
        help="Storage root containing resolved pose/background assets",
    )
    episode_animatic.add_argument(
        "--audio-map", help="JSON mapping shot IDs to dialogue audio storage keys"
    )
    episode_animatic.add_argument(
        "--motion-public-dir", default="motion/public",
        help="Remotion public directory used when --export is enabled",
    )
    episode_animatic.add_argument(
        "--export", action="store_true",
        help="Copy resolved clips and write Remotion props.json",
    )
    episode_animatic.add_argument(
        "--render", action="store_true",
        help="Render the exported Remotion composition to MP4 and verify it with ffprobe",
    )
    episode_animatic.add_argument(
        "--render-output", help="MP4 output path used with --render",
    )

    pilot = commands.add_parser(
        "pilot", help="Run the narrow Akira/Kaito anime pilot golden path"
    )
    pilot_commands = pilot.add_subparsers(dest="pilot_command", required=True)
    pilot_init = pilot_commands.add_parser(
        "init", help="Create the editable 30–60 second pilot screenplay template"
    )
    pilot_init.add_argument("--output", required=True, help="Output .fountain screenplay")
    pilot_init.add_argument("--pilot-id", default="kirik-kayit-pilot-v1")
    pilot_init.add_argument("--title", default="Kırık Kayıt — Pilot")
    pilot_check = pilot_commands.add_parser(
        "check", help="Validate pilot duration, characters, location and 24 FPS constraints"
    )
    pilot_check.add_argument("--input", required=True, help="Pilot .fountain screenplay")
    pilot_check.add_argument("--output", help="Optional readiness report JSON")
    pilot_plan = pilot_commands.add_parser(
        "plan", help="Convert a validated pilot screenplay into a 24 FPS shot plan"
    )
    pilot_plan.add_argument("--input", required=True, help="Pilot .fountain screenplay")
    pilot_plan.add_argument("--output", required=True, help="Episode director plan JSON")
    pilot_smoke = pilot_commands.add_parser(
        "smoke", help="Render a five-second canonical-anchor media smoke test"
    )
    pilot_smoke.add_argument(
        "--akira-image",
        default="characters/akira/v5/canonical_source.png",
        help="Canonical Akira anchor key under --storage-root",
    )
    pilot_smoke.add_argument(
        "--kaito-image",
        default="characters/kaito/v5/canonical_source.png",
        help="Canonical Kaito anchor key under --storage-root",
    )
    pilot_smoke.add_argument(
        "--storage-root", default="output/production",
        help="Storage root containing canonical anchor files",
    )
    pilot_smoke.add_argument(
        "--output", required=True, help="Smoke result JSON path"
    )
    pilot_smoke.add_argument(
        "--motion-public-dir", default="motion/public",
        help="Remotion public directory used for exported props",
    )
    pilot_smoke.add_argument(
        "--render", action="store_true",
        help="Render and ffprobe the five-second MP4",
    )
    pilot_smoke.add_argument(
        "--browser-executable",
        default="C:/Program Files/Google/Chrome/Application/chrome.exe",
        help="Chrome/Chromium executable used by Remotion render",
    )
    pilot_smoke.add_argument(
        "--render-output", default="output/pilot-anchor-smoke-5s.mp4",
        help="MP4 output path used with --render",
    )

    trailer = commands.add_parser("trailer", help="Plan and inspect a locked 180-second trailer")
    trailer_commands = trailer.add_subparsers(dest="trailer_command", required=True)
    trailer_init = trailer_commands.add_parser("init", help="Write the locked EŞİK//80 trailer brief")
    trailer_init.add_argument("--trailer-id", default="esik80-trailer-v1")
    trailer_init.add_argument("--output", required=True)
    trailer_plan = trailer_commands.add_parser("plan", help="Plan a traceable four-beat trailer from an episode plan")
    trailer_plan.add_argument("--input", required=True, help="Episode plan or preparation JSON")
    trailer_plan.add_argument("--output", required=True)
    trailer_plan.add_argument("--brief", help="TrailerBrief JSON; defaults to the locked v1 brief")
    trailer_inspect = trailer_commands.add_parser("inspect", help="Inspect a trailer plan")
    trailer_inspect.add_argument("--input", required=True)
    trailer_inspect.add_argument("--full", action="store_true")
    trailer_package = trailer_commands.add_parser("package", help="Create auditable Wan2.2 shot packages")
    trailer_package.add_argument("--input", required=True, help="Trailer plan JSON")
    trailer_package.add_argument("--sources", required=True, help="JSON mapping shot IDs to source image and motion metadata")
    trailer_package.add_argument("--output", required=True)
    trailer_animatic = trailer_commands.add_parser("animatic", help="Build and optionally render a trailer animatic")
    trailer_animatic.add_argument("--input", required=True, help="Trailer plan JSON")
    trailer_animatic.add_argument("--output", required=True, help="Animatic result JSON")
    trailer_animatic.add_argument("--assets", help="JSON mapping trailer shot IDs to asset keys")
    trailer_animatic.add_argument("--audio-cues", help="JSON list of timeline-bound MUSIC/SFX cues")
    trailer_animatic.add_argument("--shot-id", action="append", dest="shot_ids", default=[])
    trailer_animatic.add_argument("--mode", choices=("STRICT", "PLACEHOLDER"), default="STRICT")
    trailer_animatic.add_argument("--storage-root", default="output/production")
    trailer_animatic.add_argument("--motion-public-dir", default="motion/public")
    trailer_animatic.add_argument("--render", action="store_true")
    trailer_animatic.add_argument("--render-output")
    trailer_preflight = trailer_commands.add_parser("preflight", help="Check rented Wan2.2 worker configuration")
    trailer_preflight.add_argument("--worker", required=True)

    script = commands.add_parser("script", help="Break a script into executable shots")
    script_commands = script.add_subparsers(dest="script_command", required=True)
    breakdown = script_commands.add_parser("breakdown")
    breakdown.add_argument("--input", required=True, help="UTF-8 text script")
    breakdown.add_argument("--character-bible", required=True)
    breakdown.add_argument("--script-id", required=True)
    breakdown.add_argument("--output", help="Optional JSON output file")

    story = commands.add_parser(
        "story",
        help="Review a screenplay against locked canon and record human approval",
    )
    story_commands = story.add_subparsers(dest="story_command", required=True)
    for name, help_text in (
        ("review", "Gate an existing screenplay through canon and story reviewers"),
        ("approve", "Lock a review-ready screenplay under a named human approver"),
    ):
        story_command = story_commands.add_parser(name, help=help_text)
        story_command.add_argument(
            "--input", required=True, help="EpisodeScript JSON or Fountain screenplay"
        )
        story_command.add_argument(
            "--episode-id",
            default="episode-001",
            help="Script id used when normalizing a Fountain screenplay",
        )
        story_command.add_argument(
            "--title",
            default="Untitled episode",
            help="Episode title used when normalizing a Fountain screenplay",
        )
    story_commands.choices["approve"].add_argument(
        "--approved-by", required=True, help="Named human approving the locked script"
    )
    story_commands.choices["review"].add_argument(
        "--output", help="Optional JSON review report path; prints to stdout otherwise"
    )
    story_commands.choices["approve"].add_argument(
        "--output",
        help=(
            "Optional locked-screenplay path, written only when the gate "
            "passes; prints to stdout otherwise"
        ),
    )

    render = commands.add_parser("render", help="Render approved anime shots")
    render_commands = render.add_subparsers(dest="render_command", required=True)
    shot = render_commands.add_parser("shot")
    shot.add_argument("--plan", required=True, help="Shot JSON or breakdown JSON")
    shot.add_argument("--shot-id", help="Required when --plan contains multiple shots")
    shot.add_argument("--background-key", required=True)
    shot.add_argument("--audio-key", required=True)
    shot.add_argument("--output-key", required=True)

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

    return parser


def main(
    argv: Sequence[str] | None = None,
    *,
    container_factory: Callable[[], AnimationContainer] = create_container,
) -> int:
    arguments = build_parser().parse_args(argv)
    from config.settings import get_settings, warn_if_offline_test_profile

    warn_if_offline_test_profile(get_settings())
    try:
        if arguments.command == "series":
            from cli.series_commands import run_series_command

            return run_series_command(arguments)
        if arguments.command == "character":
            if arguments.character_command == "show":
                _show_character(_load_character_bible(arguments.input))
            elif arguments.character_command == "init":
                _initialize_character(arguments)
            elif arguments.character_command == "lock-narrative":
                _lock_character_narrative(arguments)
            elif arguments.character_command == "plan":
                _plan_character(arguments)
            elif arguments.character_command in {
                "dataset",
                "audit-dataset",
                "review-template",
                "view-consistency-report",
                "drift-report",
                "qc-calibration-create",
                "qc-calibration-summarize",
                "train",
                "benchmark-validate",
            }:
                from cli.character_quality_commands import (
                    run_character_quality_command,
                )

                return run_character_quality_command(
                    arguments,
                    write_json=_write_json,
                    load_character_bible=_load_character_bible,
                    load_creation_brief=_load_character_creation_brief,
                )
            else:
                from cli.character_asset_commands import (
                    run_character_asset_command,
                )

                return asyncio.run(
                    run_character_asset_command(
                        arguments,
                        container_factory(),
                        write_json=_write_json,
                        load_character_bible=_load_character_bible,
                        load_creation_brief=_load_character_creation_brief,
                        container_factory=container_factory,
                    )
                )
        elif arguments.command == "background":
            from cli.background_commands import run_background_command

            return run_background_command(
                arguments,
                write_json=_write_json,
                container_factory=container_factory,
            )
        elif arguments.command == "episode":
            return _run_episode_command(arguments, container_factory=container_factory)
        elif arguments.command == "pilot":
            from cli.pilot_commands import run_pilot_command

            return run_pilot_command(
                arguments,
                write_json=_write_json,
                awaitable_run=awaitable_run,
            )
        elif arguments.command == "trailer":
            return _run_trailer_command(arguments)
        elif arguments.command == "script":
            _break_down_script(arguments)
        elif arguments.command == "story":
            return asyncio.run(
                _run_story_commands(arguments, container_factory())
            )
        elif arguments.command == "render":
            asyncio.run(_render_shot(arguments, container_factory()))
        elif arguments.command == "blender":
            asyncio.run(_run_blender_commands(arguments, container_factory()))
        elif arguments.command == "rig":
            return asyncio.run(_run_rig_commands(arguments))
        elif arguments.command == "preproduction":
            return asyncio.run(
                _run_preproduction_commands(arguments, container_factory())
            )
        elif arguments.command == "keyframe":
            return asyncio.run(_run_keyframe_commands(arguments, container_factory()))
        return 0
    except Exception as error:  # noqa: BLE001 - CLI boundary
        print(f"SELMA command failed: {error}", file=sys.stderr)
        return 1


def _show_character(bible: CharacterBible) -> None:
    payload = bible.to_dict()
    payload["prompt_fragments"] = list(bible.prompt_fragments())
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def _initialize_character(arguments: argparse.Namespace) -> None:
    from core.application.services.character_bible_factory_service import (
        CharacterBibleFactoryService,
    )

    brief = json.loads(Path(arguments.brief).read_text(encoding="utf-8"))
    if not isinstance(brief, dict):
        raise TypeError("Character brief JSON must contain an object.")
    bible = CharacterBibleFactoryService().create(brief)
    print(
        _write_json(
            arguments.output,
            {"schema_version": 1, "character_bible": bible.to_dict()},
        )
    )


def _lock_character_narrative(arguments: argparse.Namespace) -> None:
    """Lock narrative canon alone; a visual reference pack is a separate claim.

    The story gate needs narrative canon, not rendered assets. Requiring a
    reference pack to lock a profile would force artwork before the screenplay
    is approved, so this records the human signature on its own.
    """
    from dataclasses import replace

    bible = _load_character_bible(arguments.input)
    profile = bible.narrative_profile
    if profile is None:
        raise ValueError("Character has no narrative profile to lock.")
    if profile.locked:
        raise ValueError(
            "Character narrative profile is already locked. Changing locked "
            "canon needs an explicit revision, not a silent re-lock."
        )
    approver = arguments.approved_by.strip()
    if not approver:
        raise ValueError("approved_by must not be empty.")

    locked_bible = replace(bible, narrative_profile=replace(profile, locked=True))
    _write_json(
        arguments.output,
        {"schema_version": 1, "character_bible": locked_bible.to_dict()},
    )

    canon_payload = {**profile.to_dict(), "locked": False}
    receipt = _write_json(
        arguments.receipt
        or Path("output/preproduction/narrative-locks")
        / f"{bible.character_id}.json",
        {
            "schema_version": 1,
            "character_id": bible.character_id,
            "approved_by": approver,
            "approved_at": datetime.now(timezone.utc).isoformat(),
            "narrative_locked": True,
            "narrative_hash": hashlib.sha256(
                json.dumps(canon_payload, ensure_ascii=False, sort_keys=True).encode(
                    "utf-8"
                )
            ).hexdigest(),
            "visual_readiness_claimed": False,
        },
    )
    print(str(receipt))


def _load_character_bible(path: str | Path) -> CharacterBible:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise TypeError("Character Bible JSON must contain an object.")
    bible_payload = payload.get("character_bible", payload)
    if not isinstance(bible_payload, dict):
        raise TypeError("character_bible must contain an object.")
    return CharacterBible.from_dict(bible_payload)


def _load_character_creation_brief(path: str | Path):
    from core.domain.value_objects.character_creation_brief import (
        CharacterCreationBrief,
    )

    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise TypeError("Character creation brief JSON must contain an object.")
    brief_payload = payload.get("character_creation_brief", payload)
    if not isinstance(brief_payload, dict):
        raise TypeError("character_creation_brief must contain an object.")
    brief = CharacterCreationBrief.from_dict(brief_payload)
    source = Path(path)
    lock_path = source.with_name(f"{source.stem}.lock.json")
    if lock_path.is_file():
        lock = json.loads(lock_path.read_text(encoding="utf-8"))
        if not isinstance(lock, dict) or lock.get("status") != "LOCKED":
            raise ValueError(f"Character brief lock is malformed: {lock_path}")
        if lock.get("brief_hash") != brief.content_hash:
            raise ValueError(
                "Character brief changed after approval; review and refresh its lock."
            )
    return brief


def _write_json(path: str | Path, payload: dict[str, Any]) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    descriptor, temporary_name = tempfile.mkstemp(
        dir=target.parent, prefix=f".{target.name}.", suffix=".tmp"
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(serialized)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, target)
    except BaseException:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass
        raise
    return target.resolve()

def _plan_character(arguments: argparse.Namespace) -> None:

    from core.application.services.character_onboarding_service import (
        CharacterOnboardingService,
    )

    character = _load_character_bible(arguments.input)
    plan = CharacterOnboardingService.plan(character)
    print(_write_json(arguments.output, plan.to_dict()))


def _build_character_dataset(arguments: argparse.Namespace) -> int:
    from core.application.services.character_lora_dataset_service import (
        CharacterLoraDatasetService,
    )
    from core.application.services.character_onboarding_service import (
        CharacterOnboardingService,
    )

    character = _load_character_bible(arguments.input)
    planned_token = CharacterOnboardingService.plan(character).trigger_token
    trigger_token = arguments.trigger_token or f"{planned_token.rsplit('_v', 1)[0]}_v2"
    report = CharacterLoraDatasetService().build(
        source_dir=arguments.source,
        output_dir=arguments.output,
        character_id=character.character_id,
        trigger_token=trigger_token,
        character_bible=character,
        review_manifest=arguments.review_manifest,
        canonical_anchor=arguments.canonical_anchor,
    )
    print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
    return 0 if report.is_ready else 2


def _audit_character_dataset(arguments: argparse.Namespace) -> int:
    from core.application.services.character_lora_dataset_audit_service import (
        CharacterLoraDatasetAuditService,
    )

    audit = CharacterLoraDatasetAuditService().audit(arguments.manifest)
    payload = audit.to_dict()
    if arguments.output:
        print(_write_json(arguments.output, payload))
    else:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if audit.training_approved else 2


def _create_character_review_template(arguments: argparse.Namespace) -> int:
    from core.application.services.character_lora_dataset_audit_service import (
        CharacterLoraDatasetAuditService,
    )

    payload = CharacterLoraDatasetAuditService().create_review_template(
        manifest_path=arguments.manifest,
        canonical_anchor=arguments.canonical_anchor,
    )
    print(_write_json(arguments.output, payload))
    return 0


async def _train_character_lora(arguments: argparse.Namespace) -> int:
    from core.domain.value_objects.character_lora_training import (
        CharacterLoraTrainingRequest,
    )
    from infrastructure.providers.training.kohya_character_lora_trainer import (
        KohyaCharacterLoraTrainer,
    )

    character = _load_character_bible(arguments.input)
    request = CharacterLoraTrainingRequest(
        character_id=character.character_id,
        dataset_dir=Path(arguments.dataset),
        base_model_path=Path(arguments.base_model),
        output_dir=Path(arguments.output),
        model_name=arguments.model_name,
        max_train_steps=arguments.steps,
    )
    result = await KohyaCharacterLoraTrainer(arguments.sd_scripts_dir).train(request)
    print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
    return 0


async def _run_character_generation(
    arguments: argparse.Namespace,
    container: AnimationContainer,
) -> int:
    if arguments.character_command == "pose-pack":
        from core.application.services.character_pose_pack_batch_service import (
            CharacterPosePackBatchService,
        )
        from core.domain.value_objects.character_design import (
            CharacterCanonicalApproval,
        )

        if arguments.pose_pack_command == "generate":
            brief = _load_character_creation_brief(arguments.brief)
            raw_approval = json.loads(Path(arguments.approval).read_text(encoding="utf-8"))
            if not isinstance(raw_approval, dict):
                raise TypeError("Canonical approval receipt must contain an object.")
            manifest = await container.character_pose_pack_service.generate_pack(
                brief,
                CharacterCanonicalApproval.from_dict(raw_approval),
                active_series_path=arguments.active_series,
                mode="PRODUCTION",
                output_prefix=arguments.output_prefix,
                run_id=arguments.run_id,
            )
            print(_write_json(arguments.manifest, manifest.to_dict()))
            return 0
        if arguments.pose_pack_command == "approve":
            approval = await container.character_pose_pack_service.approve_pack(
                manifest_storage_key=arguments.manifest,
                approved_by=arguments.approved_by,
                confirmed_checks=list(arguments.checks or []),
            )
            print(json.dumps(approval.to_dict(), ensure_ascii=False, indent=2))
            return 0
        raw_jobs = json.loads(Path(arguments.jobs).read_text(encoding="utf-8"))
        if not isinstance(raw_jobs, list) or not all(isinstance(item, dict) for item in raw_jobs):
            raise TypeError("Pose-pack batch jobs must be a JSON list of objects.")
        payload = await CharacterPosePackBatchService(
            container.character_pose_pack_service,
            style_lock_resolver=container.style_lock_service,
        ).run(
            raw_jobs,
            output_manifest=arguments.manifest,
            continue_on_error=not arguments.stop_on_error,
            active_series_path=arguments.active_series,
            workflow_path=arguments.workflow,
        )
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0
    if arguments.character_command == "benchmark-run":
        from config.settings import get_settings
        from core.application.services.character_model_tournament_service import (
            CharacterModelTournamentService,
        )
        from infrastructure.providers.keyframe.comfyui_memory_releaser import (
            ComfyUiMemoryReleaser,
        )

        workspace_root = Path(__file__).resolve().parents[1]
        base_settings = get_settings()
        brief = _load_character_creation_brief(arguments.brief)
        run_id = arguments.run_id or datetime.now(timezone.utc).strftime(
            "%Y%m%dT%H%M%SZ"
        )
        def generator_factory(model_lock_path: Path):
            settings = base_settings.model_copy(
                update={
                    "keyframe_generation_provider": "comfyui",
                    "comfyui_model_lock_path": str(model_lock_path),
                    "comfyui_keyframe_checkpoint": "",
                }
            )
            return create_container(settings=settings).character_design_service

        report = await CharacterModelTournamentService(
            workspace_root,
            generator_factory,
            ComfyUiMemoryReleaser(base_settings.comfyui_api_url).release,
        ).run(
            benchmark_path=arguments.benchmark,
            brief=brief,
            model_lock_paths=arguments.model_locks,
            count=arguments.count,
            run_id=run_id,
        )
        print(_write_json(arguments.output, report))
        return 0
    if arguments.character_command == "benchmark-validate":
        from core.application.services.character_quality_benchmark_service import (
            CharacterQualityBenchmarkService,
        )

        workspace_root = Path(__file__).resolve().parents[1]
        benchmark = CharacterQualityBenchmarkService(workspace_root).validate(
            arguments.benchmark
        )
        print(
            json.dumps(
                {
                    "status": "VALID",
                    "benchmark": benchmark.to_dict(),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
    if arguments.character_command == "create":
        brief = _load_character_creation_brief(arguments.brief)
        pack = await container.character_design_service.generate_candidates(
            brief,
            count=arguments.count,
            output_prefix=arguments.output_prefix,
            run_id=arguments.run_id,
            style_reference_path=arguments.style_reference,
            style_weight=arguments.style_weight,
        )
        print(_write_json(arguments.manifest, pack.to_dict()))
        return 0
    if arguments.character_command == "approve-design":
        from core.domain.value_objects.character_design import CharacterDesignCandidate

        brief = _load_character_creation_brief(arguments.brief)
        manifest = json.loads(Path(arguments.manifest).read_text(encoding="utf-8"))
        if not isinstance(manifest, dict):
            raise TypeError("Character design manifest must contain an object.")
        if (
            manifest.get("character_id") != brief.character_id
            or manifest.get("brief_hash") != brief.content_hash
        ):
            raise ValueError("Character design manifest belongs to another brief.")
        raw_candidates = manifest.get("candidates")
        if not isinstance(raw_candidates, list):
            raise TypeError("Character design manifest must contain candidates.")
        selected = next(
            (
                item
                for item in raw_candidates
                if isinstance(item, dict)
                and item.get("storage_key") == arguments.candidate_key
            ),
            None,
        )
        if selected is None:
            raise ValueError(
                "Selected design candidate is not present in the manifest."
            )
        approval = await container.character_canonical_approval_service.approve_candidate(
            brief,
            CharacterDesignCandidate.from_dict(selected),
            approved_by=arguments.approved_by,
            character_version=arguments.version,
            output_prefix=arguments.output_prefix,
            brief_consistency_confirmed=bool(arguments.confirm_brief_consistency),
        )
        print(_write_json(arguments.output, approval.to_dict()))
        return 0
    if arguments.character_command == "turnaround":
        from core.domain.value_objects.character_design import (
            CharacterCanonicalApproval,
        )

        brief = _load_character_creation_brief(arguments.brief)
        raw_approval = json.loads(Path(arguments.approval).read_text(encoding="utf-8"))
        if not isinstance(raw_approval, dict):
            raise TypeError("Canonical approval receipt must contain an object.")
        pack = await container.character_view_pack_generation_service.generate_canonical_views(
            brief,
            CharacterCanonicalApproval.from_dict(raw_approval),
            output_prefix=arguments.output_prefix,
            # Without this the --seeds flag was accepted and then ignored, so a
            # requested sweep silently rendered a single seed per view.
            view_candidate_count=arguments.seeds,
        )
        print(_write_json(arguments.manifest, pack.to_dict()))
        return 0
    if arguments.character_command == "approve-view-pack":
        raw_version = str(arguments.version).strip().casefold().removeprefix("v")
        approval = await container.character_view_pack_generation_service.approve_view_pack(
            character_id=arguments.character,
            character_version=int(raw_version),
            approved_by=arguments.approved_by,
            output_prefix=arguments.output_prefix,
            acceptance_path=arguments.acceptance,
            confirmed_checks=list(arguments.checks or []),
        )
        payload = approval.to_dict()
        if arguments.output:
            print(_write_json(arguments.output, payload))
        else:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0
    character = _load_character_bible(arguments.input)
    service = container.character_onboarding_service
    if arguments.character_command == "anchor":
        if not 1 <= arguments.count <= 8:
            raise ValueError("Anchor candidate count must be between 1 and 8.")
        candidates = [
            await service.generate_anchor(
                character,
                output_prefix=arguments.output_prefix,
                seed_offset=index * 10_000,
                source_reference_storage_key=arguments.source_reference_key,
            )
            for index in range(arguments.count)
        ]
        print(
            json.dumps(
                {
                    "character_id": character.character_id,
                    "candidates": [candidate.to_dict() for candidate in candidates],
                    "human_approved": False,
                    "next_gate": "HUMAN_ANCHOR_APPROVAL",
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
    if arguments.character_command == "references":
        from core.domain.value_objects.character_onboarding import (
            CharacterPilotApproval,
        )

        pilot_approval = None
        if arguments.pilot_approval:
            raw_approval = json.loads(
                Path(arguments.pilot_approval).read_text(encoding="utf-8")
            )
            if not isinstance(raw_approval, dict):
                raise TypeError("Pilot approval receipt must contain an object.")
            pilot_approval = CharacterPilotApproval.from_dict(raw_approval)
        pose_references = None
        if arguments.pose_references:
            raw_pose_references = json.loads(
                Path(arguments.pose_references).read_text(encoding="utf-8")
            )
            if not isinstance(raw_pose_references, dict) or not all(
                isinstance(view, str) and isinstance(storage_key, str)
                for view, storage_key in raw_pose_references.items()
            ):
                raise TypeError(
                    "Pose references must be a JSON object of view-to-storage-key strings."
                )
            pose_references = raw_pose_references
        pack = await service.generate_reference_pack(
            character,
            anchor_storage_key=arguments.approved_anchor_key,
            output_prefix=arguments.output_prefix,
            recipe_limit=arguments.limit,
            recipe_offset=arguments.recipe_offset,
            automatic_review=not arguments.defer_visual_review,
            pilot_approval=pilot_approval,
            seed_offset=arguments.seed_offset,
            pose_references=pose_references,
        )
        payload = {
            **pack.to_dict(),
            "automatic_review_deferred": arguments.defer_visual_review,
            "pack_complete": len(pack.candidates) == 23,
            "seed_offset": arguments.seed_offset,
        }
        print(_write_json(arguments.manifest, payload))
        return 0
    if arguments.character_command == "approve-pilot":
        checks = {
            name: bool(getattr(arguments, name))
            for name in (
                "face_match",
                "hair_match",
                "immutable_marks_match",
                "outfit_match",
                "framing_match",
                "anatomy_pass",
            )
        }
        approval = await service.approve_pilot(
            character,
            anchor_storage_key=arguments.approved_anchor_key,
            pilot_storage_key=arguments.pilot_key,
            approved_by=arguments.approved_by,
            checks=checks,
        )
        print(_write_json(arguments.output, approval.to_dict()))
        return 0
    if arguments.character_command == "approve-references":
        from dataclasses import replace

        from core.domain.services.character_bible_validation_service import (
            CharacterBibleValidationService,
        )
        from core.domain.value_objects.character_identity import ReferenceView

        approval = json.loads(Path(arguments.selections).read_text(encoding="utf-8"))
        if not isinstance(approval, dict) or not isinstance(
            approval.get("views"), dict
        ):
            raise TypeError("Reference selections must contain a views object.")
        selected = {
            ReferenceView(str(view)): str(storage_key)
            for view, storage_key in approval["views"].items()
        }
        character = await service.approve_reference_pack(character, selected)
        if arguments.lock_narrative:
            if character.narrative_profile is None:
                raise ValueError("Character has no narrative profile to lock.")
            character.narrative_profile = replace(
                character.narrative_profile, locked=True
            )
        report = CharacterBibleValidationService().validate(character)
        if not report.is_complete:
            raise ValueError("Approved references unexpectedly became invalid.")
        print(
            _write_json(
                arguments.output,
                {
                    "schema_version": 1,
                    "approval": {
                        "approved_by": arguments.approved_by,
                        "reference_pack_approved": True,
                        "narrative_locked": bool(
                            character.narrative_profile
                            and character.narrative_profile.locked
                        ),
                    },
                    "character_bible": character.to_dict(),
                },
            )
        )
        return 0
    raise ValueError(f"Unsupported character command: {arguments.character_command}")


def _load_json_object(path: str | Path) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise TypeError(f"JSON file must contain an object: {path}")
    return payload


def _load_episode_plan_inputs(arguments: argparse.Namespace):
    from core.domain.value_objects.background_production import (
        BackgroundCandidate,
        BackgroundCandidatePack,
    )
    from core.application.services.asset_approval_service import AssetApprovalService
    from core.domain.value_objects.asset_approval import AssetApprovalReceipt
    from core.domain.value_objects.character_pose_pack import (
        CharacterPosePackApproval,
        CharacterPosePackManifest,
    )

    characters = [_load_character_bible(path) for path in arguments.character_bibles]
    from cli.background_commands import _load_location_bible

    locations = [_load_location_bible(path) for path in arguments.location_bibles]
    pose_packs = {}
    for path in arguments.pose_packs:
        payload = _load_json_object(path)
        manifest_payload = payload.get("manifest", payload)
        manifest = CharacterPosePackManifest.from_dict(manifest_payload)
        approval_path = Path(path).with_name("approval.json")
        if approval_path.is_file() and manifest_payload is payload:
            approval = CharacterPosePackApproval.from_dict(
                _load_json_object(approval_path)
            )
            import hashlib
            manifest_bytes = Path(path).read_bytes()
            expected_pose_hashes = {
                pose.pose_id: pose.content_hash for pose in manifest.poses
            }
            shared_receipt = _load_json_object(approval_path).get("asset_approval_receipt")
            shared_valid = False
            if isinstance(shared_receipt, dict):
                try:
                    shared_valid = AssetApprovalService.verify(
                        AssetApprovalReceipt.from_dict(shared_receipt),
                        asset_hash=AssetApprovalService.asset_set_digest(
                            [pose.content_hash for pose in manifest.poses]
                        ),
                        manifest_payload=manifest.to_dict(),
                    )
                except Exception:
                    shared_valid = False
            if (
                hashlib.sha256(manifest_bytes).hexdigest()
                == approval.manifest_content_hash
                and approval.character_id == manifest.character_id
                and approval.character_version == manifest.character_version
                and dict(approval.pose_hashes) == expected_pose_hashes
                and shared_valid
            ):
                from dataclasses import replace
                manifest = replace(
                    manifest,
                    human_approved=True,
                    approval_receipt=shared_receipt,
                )
        pose_packs[manifest.character_id] = manifest
    background_packs = {}
    for path in arguments.background_packs:
        payload = _load_json_object(path)
        raw_candidates = payload.get("candidates", [])
        if not isinstance(raw_candidates, list):
            raise TypeError("Background candidate pack candidates must be a list.")
        candidates = tuple(
            BackgroundCandidate(
                recipe_id=str(item.get("recipe_id", "")),
                storage_key=str(item.get("storage_key", "")),
                width=int(item.get("width", 0)),
                height=int(item.get("height", 0)),
                attempt=int(item.get("attempt", 1)),
                content_hash=str(item.get("content_hash", "")),
            )
            for item in raw_candidates
            if isinstance(item, dict)
        )
        approval = payload.get("approval", {})
        raw_receipt = payload.get("approval_receipt")
        pack = BackgroundCandidatePack(
            location_id=str(payload.get("location_id", "")),
            candidates=candidates,
            human_approved=False,
            approval_receipt=(dict(raw_receipt) if isinstance(raw_receipt, dict) else None),
        )
        if isinstance(raw_receipt, dict):
            try:
                pack = BackgroundCandidatePack(
                    location_id=pack.location_id,
                    candidates=pack.candidates,
                    human_approved=AssetApprovalService.verify(
                        AssetApprovalReceipt.from_dict(raw_receipt),
                        asset_hash=AssetApprovalService.asset_set_digest(
                            [candidate.content_hash for candidate in candidates]
                        ),
                        manifest_payload=pack.to_dict(),
                    ),
                    approval_receipt=raw_receipt,
                )
            except Exception:
                pass
        background_packs[pack.location_id] = pack
    non_cast_voices: tuple[Any, ...] = ()
    if getattr(arguments, "world_bible", None):
        from core.domain.entities.direction_bible import WorldBible

        world_payload = _load_json_object(arguments.world_bible)
        world = WorldBible.from_dict(
            dict(world_payload.get("world_bible", world_payload))
        )
        non_cast_voices = world.non_cast_voices
    return characters, locations, pose_packs, background_packs, non_cast_voices


def _episode_director_provider(arguments: argparse.Namespace):
    if getattr(arguments, "director_provider", "rules") == "rules":
        return None
    if arguments.director_provider == "claude":
        from config.settings import get_settings
        from infrastructure.providers.episode_director.claude_episode_director_provider import (
            ClaudeEpisodeDirectorProvider,
        )

        settings = get_settings()
        return ClaudeEpisodeDirectorProvider(
            api_key=settings.anthropic_api_key,
            model=arguments.director_model,
        )
    raise ValueError(f"Unsupported Episode Director provider: {arguments.director_provider}")


def _run_trailer_command(arguments: argparse.Namespace) -> int:
    from core.application.services.trailer_cli_service import TrailerCliService

    service = TrailerCliService()
    if arguments.trailer_command == "init":
        payload = service.init(arguments.trailer_id)
        print(_write_json(arguments.output, payload))
        return 0
    if arguments.trailer_command == "plan":
        episode = service.load(arguments.input)
        brief = service.load(arguments.brief) if arguments.brief else None
        payload = service.plan(episode, brief)
        print(_write_json(arguments.output, payload))
        return 0
    if arguments.trailer_command == "package":
        from core.application.services.wan22_package_service import Wan22PackageService
        from core.domain.value_objects.trailer_plan import TrailerPlan
        plan = TrailerPlan.from_dict(service.load(arguments.input))
        sources = service.load(arguments.sources)
        packages = Wan22PackageService().build(plan, sources)
        print(_write_json(arguments.output, {"schema_version": 1, "trailer_id": plan.timeline.trailer_id, "packages": [item.to_dict() for item in packages]}))
        return 0
    if arguments.trailer_command == "animatic":
        from core.application.services.trailer_animatic_service import TrailerAnimaticService
        from infrastructure.storage.local_fs_storage import LocalFsStorage
        from core.domain.value_objects.trailer_audio_cue import TrailerAudioCue
        from core.domain.value_objects.trailer_plan import TrailerPlan
        plan = TrailerPlan.from_dict(service.load(arguments.input))
        assets = service.load(arguments.assets) if arguments.assets else {}
        raw_cues = service.load(arguments.audio_cues) if arguments.audio_cues else []
        if isinstance(raw_cues, dict):
            raw_cues = raw_cues.get("audio_cues", [])
        if not isinstance(raw_cues, list):
            raise TypeError("Audio cues must contain a JSON list.")
        audio_cues = tuple(
            TrailerAudioCue.from_dict(item)
            for item in raw_cues
            if isinstance(item, dict)
        )
        storage = LocalFsStorage(arguments.storage_root)
        animatic_service = TrailerAnimaticService(storage)

        async def build_trailer_animatic():
            normalized_assets, audio_diagnostics = await animatic_service.prepare_audio_assets(
                plan, assets, shot_ids=arguments.shot_ids or None
            )
            built_project = await animatic_service.build(
                plan,
                assets=normalized_assets,
                shot_ids=arguments.shot_ids or None,
                audio_cues=audio_cues,
                mode=arguments.mode,
            )
            return built_project, audio_diagnostics

        project, audio_diagnostics = asyncio.run(build_trailer_animatic())
        audio_blocked = arguments.mode == "STRICT" and any(
            item.get("status") != "OK" for item in audio_diagnostics
        )
        payload = {
            "status": "BLOCKED" if audio_blocked else ("READY_FOR_REVIEW" if project else "BLOCKED"),
            "mode": arguments.mode,
            "project_kind": "TRAILER",
            "animatic_project": project.to_dict() if project and not audio_blocked else None,
            "audio_diagnostics": list(audio_diagnostics),
        }
        if audio_blocked:
            print(_write_json(arguments.output, payload))
            return 2
        if project is not None and arguments.render:
            from core.application.services.animatic_render_service import (
                AnimaticRenderService,
            )
            from infrastructure.providers.render.ffprobe_media_inspection_provider import (
                FfprobeMediaInspectionProvider,
            )
            from infrastructure.providers.render.remotion_animatic_exporter import (
                RemotionAnimaticExporter,
            )
            props_path = asyncio.run(RemotionAnimaticExporter(storage, arguments.motion_public_dir).export(project))
            render_result = asyncio.run(AnimaticRenderService(
                motion_directory="motion",
                inspector=FfprobeMediaInspectionProvider(),
            ).render(
                project, props_path=props_path,
                output_path=arguments.render_output or str(Path(arguments.output).with_suffix(".mp4")),
            ))
            payload["render"] = render_result.to_dict()
            if render_result.status != "READY_FOR_REVIEW":
                print(_write_json(arguments.output, payload))
                return 3
        print(_write_json(arguments.output, payload))
        return 0
    if arguments.trailer_command == "preflight":
        from core.application.services.wan22_package_service import Wan22PackageService
        print(json.dumps(Wan22PackageService.preflight(arguments.worker), ensure_ascii=False, indent=2))
        return 0
    if arguments.trailer_command == "inspect":
        payload = service.load(arguments.input)
        plan = payload
        shots = plan.get("shots", [])
        timeline = plan.get("timeline", {})
        summary = {
            "trailer_id": plan.get("timeline", {}).get("trailer_id", ""),
            "fps": timeline.get("fps"),
            "duration_frames": timeline.get("duration_frames"),
            "shot_count": len(shots) if isinstance(shots, list) else 0,
            "beat_count": len(timeline.get("beats", [])) if isinstance(timeline, dict) else 0,
            "warnings": plan.get("warnings", []),
        }
        print(json.dumps(plan if arguments.full else summary, ensure_ascii=False, indent=2))
        return 0
    raise ValueError(f"Unsupported trailer command: {arguments.trailer_command}")


def _run_episode_command(
    arguments: argparse.Namespace,
    *,
    container_factory: Callable[[], AnimationContainer] = create_container,
) -> int:
    from core.domain.value_objects.episode_director_plan import EpisodeDirectorPlan

    if arguments.episode_command == "animatic":
        from cli.episode_commands import run_episode_animatic_command

        return run_episode_animatic_command(
            arguments,
            load_json_object=_load_json_object,
            write_json=_write_json,
            awaitable_run=awaitable_run,
        )

    if arguments.episode_command == "inspect":
        payload = _load_json_object(arguments.input)
        plan = EpisodeDirectorPlan.from_dict(payload.get("episode_director_plan", payload))
        summary = {
            "episode_id": plan.episode_id,
            "title": plan.title,
            "decision_mode": plan.decision_mode,
            "provider": plan.provider,
            "fps": plan.fps,
            "total_duration_seconds": plan.total_duration_seconds,
            "duration_frames": plan.duration_frames,
            "scene_count": len(plan.scenes),
            "shot_count": sum(len(scene.shots) for scene in plan.scenes),
            "character_requirements": [item.to_dict() for item in plan.character_requirements],
            "background_requirements": [item.to_dict() for item in plan.background_requirements],
            "warnings": list(plan.warnings),
        }
        print(json.dumps(plan.to_dict() if arguments.full else summary, ensure_ascii=False, indent=2))
        return 0

    if arguments.episode_command not in {"plan", "prepare"}:
        raise ValueError(f"Unsupported episode command: {arguments.episode_command}")

    is_prepare = arguments.episode_command == "prepare"
    from core.application.services.episode_director_service import EpisodeDirectorService

    (
        characters,
        locations,
        pose_packs,
        background_packs,
        non_cast_voices,
    ) = _load_episode_plan_inputs(arguments)
    source = Path(arguments.input)
    raw = _load_json_object(source) if source.suffix.lower() == ".json" else None
    director = EpisodeDirectorService()
    provider = _episode_director_provider(arguments)
    if isinstance(raw, dict) and ("sequences" in raw or "episode_script" in raw):
        script_payload = raw.get("episode_script", raw)
        script = EpisodeScript.from_dict(dict(script_payload))
        planning_input: EpisodeScript | str = script
        plan_kwargs = {
            "character_bibles": characters,
            "locations": locations,
            "pose_packs": pose_packs,
            "background_packs": background_packs,
            "non_cast_voices": non_cast_voices,
            "episode_id": arguments.episode_id if arguments.episode_id != "episode-001" else None,
        }
        plan = awaitable_run(director.plan_with_provider(script, provider, **plan_kwargs)) if provider else director.plan_episode(script, **plan_kwargs)
    else:
        plan_kwargs = {
            "character_bibles": characters,
            "locations": locations,
            "pose_packs": pose_packs,
            "background_packs": background_packs,
            "non_cast_voices": non_cast_voices,
        }
        if source.suffix.lower() == ".fountain":
            from core.application.services.screenplay_normalization_service import (
                ScreenplayNormalizationService,
            )

            script = ScreenplayNormalizationService().from_fountain(
                source.read_text(encoding="utf-8"),
                script_id=arguments.episode_id,
                title=arguments.title,
            )
            planning_input = script
            plan_kwargs["episode_id"] = arguments.episode_id
            plan = (
                awaitable_run(director.plan_with_provider(script, provider, **plan_kwargs))
                if provider
                else director.plan_episode(script, **plan_kwargs)
            )
        else:
            screenplay_text = raw.get("script_text", "") if isinstance(raw, dict) else source.read_text(encoding="utf-8")
            planning_input = screenplay_text
            plan_kwargs.update({"episode_id": arguments.episode_id, "title": arguments.title})
            plan = (
                awaitable_run(director.plan_with_provider(screenplay_text, provider, **plan_kwargs))
                if provider
                else director.plan_text(screenplay_text, **plan_kwargs)
            )

    if is_prepare:
        from core.application.services.episode_preparation_service import (
            EpisodePreparationResult,
            EpisodePreparationService,
        )

        previous = None
        if arguments.resume:
            previous = EpisodePreparationResult.from_dict(
                _load_json_object(arguments.resume)
            )
        asset_generation = None
        generation_failures: dict[str, str] = {}
        if arguments.generate_assets:
            from core.application.services.episode_asset_generation_service import (
                EpisodeAssetGenerationService,
            )

            pose_jobs: list[dict[str, Any]] = []
            for path in arguments.pose_jobs:
                raw_job = _load_json_object(path)
                raw_jobs = raw_job.get("jobs", raw_job.get("pose_jobs", raw_job))
                if isinstance(raw_jobs, list):
                    pose_jobs.extend(
                        item for item in raw_jobs if isinstance(item, dict)
                    )
                elif isinstance(raw_jobs, dict):
                    pose_jobs.append(raw_jobs)
                else:
                    raise TypeError("Pose generation job JSON must contain an object or list.")
            if arguments.asset_mode == "DISCOVERY":
                from core.application.services.background_factory_service import (
                    BackgroundFactoryService,
                )
                from core.application.services.character_pose_pack_service import (
                    CharacterPosePackService,
                )
                from infrastructure.providers.keyframe.fake_keyframe_generation_provider import (
                    FakeKeyframeGenerationProvider,
                )
                from infrastructure.storage.local_fs_storage import LocalFsStorage

                discovery_storage = LocalFsStorage(
                    str(
                        Path(arguments.asset_output_root or Path(arguments.output).parent / "assets")
                        / "storage"
                    )
                )
                discovery_generator = FakeKeyframeGenerationProvider(sized_output=True)
                discovery_pose_service = CharacterPosePackService(
                    discovery_generator,
                    discovery_storage,
                    require_real_provenance=False,
                    default_mode="DISCOVERY",
                )
                discovery_background_service = BackgroundFactoryService(
                    discovery_generator,
                    discovery_storage,
                )
                from core.application.services.episode_asset_generation_service import (
                    EpisodeAssetGenerationService,
                )

                asset_service = EpisodeAssetGenerationService(
                    discovery_pose_service,
                    discovery_background_service,
                    discovery_storage,
                )
            else:
                container = container_factory()
                asset_service = container.episode_asset_generation_service
            generated = awaitable_run(
                asset_service.generate(
                    plan,
                    locations=tuple(locations),
                    pose_jobs=pose_jobs,
                    asset_mode=arguments.asset_mode,
                    output_root=(
                        arguments.asset_output_root
                        or Path(arguments.output).parent / "assets"
                    ),
                    active_series_path=arguments.active_series,
                    workflow_path=arguments.workflow,
                )
            )
            asset_generation = generated
            generation_failures = dict(generated.failures)
            if generated.pose_packs or generated.background_packs:
                regenerated_kwargs = {
                    **plan_kwargs,
                    "character_bibles": characters,
                    "locations": locations,
                    "pose_packs": {**pose_packs, **generated.pose_packs},
                    "background_packs": {**background_packs, **generated.background_packs},
                }
                plan = (
                    awaitable_run(director.plan_with_provider(planning_input, provider, **regenerated_kwargs))
                    if provider
                    else director.plan(planning_input, **regenerated_kwargs)
                )

        result = EpisodePreparationService().prepare(
            plan,
            previous=previous,
            retry_job_ids=tuple(arguments.retry_jobs or ()),
            failed_jobs=generation_failures,
        )
        payload = result.to_dict()
        if asset_generation is not None:
            payload["asset_generation"] = asset_generation.to_dict()
    else:
        payload = {"schema_version": 1, "episode_director_plan": plan.to_dict()}
    if arguments.output:
        print(_write_json(arguments.output, payload))
    else:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def awaitable_run(awaitable):
    """Run one async asset dispatch from the synchronous CLI boundary."""
    return asyncio.run(awaitable)


def _break_down_script(arguments: argparse.Namespace) -> None:
    source = Path(arguments.input)
    script_text = source.read_text(encoding="utf-8")
    service = ScriptBreakdownService(_load_character_bible(arguments.character_bible))
    shots = service.parse_script(script_text, script_id=arguments.script_id)
    payload = {
        "schema_version": 1,
        "script_id": arguments.script_id,
        "shots": [shot.to_dict() for shot in shots],
    }
    serialized = json.dumps(payload, ensure_ascii=False, indent=2)
    if arguments.output:
        output = Path(arguments.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(f"{serialized}\n", encoding="utf-8")
        print(str(output.resolve()))
    else:
        print(serialized)


def _load_episode_script_input(
    path: str | Path, *, episode_id: str, title: str
) -> EpisodeScript:
    """Accept a normalized EpisodeScript JSON or a Fountain screenplay."""
    source = Path(path)
    if not source.is_file():
        raise FileNotFoundError(f"Screenplay input does not exist: {source}")
    suffix = source.suffix.lower()
    if suffix == ".json":
        payload = _load_json_object(source)
        script_payload = payload.get("episode_script", payload)
        if not isinstance(script_payload, dict):
            raise TypeError("episode_script must contain an object.")
        return EpisodeScript.from_dict(dict(script_payload))
    if suffix == ".fountain":
        from core.application.services.screenplay_normalization_service import (
            ScreenplayNormalizationService,
        )

        return ScreenplayNormalizationService().from_fountain(
            source.read_text(encoding="utf-8"),
            script_id=episode_id,
            title=title,
        )
    raise ValueError(
        f"Unsupported screenplay input '{source.suffix}'. Use .json or .fountain."
    )


def _story_review_report(
    script: EpisodeScript, result: StoryDevelopmentResult, *, source: str
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "input": source,
        "episode_script_id": script.id,
        "status": result.script.status.value,
        "ready_for_approval": result.ready_for_approval,
        "canon_report": {
            "passed": result.canon_report.passed,
            "violations": [
                {
                    "code": violation.code.value,
                    "message": violation.message,
                    "scene_id": violation.scene_id,
                    "evidence": violation.evidence,
                }
                for violation in result.canon_report.violations
            ],
        },
        "reviews": [
            {
                "reviewer": report.reviewer,
                "passed": report.passed,
                "issues": [
                    {
                        "code": issue.code,
                        "message": issue.message,
                        "severity": issue.severity.value,
                        "scene_id": issue.scene_id,
                    }
                    for issue in report.issues
                ],
            }
            for report in result.reviews
        ],
    }


async def _run_story_commands(
    arguments: argparse.Namespace,
    container: AnimationContainer,
) -> int:
    """Refuse to lock a screenplay that has not passed canon and story review."""
    script = _load_episode_script_input(
        arguments.input,
        episode_id=arguments.episode_id,
        title=arguments.title,
    )
    engine = container.story_engine_service
    result = await engine.review(script)
    report = _story_review_report(
        script, result, source=str(Path(arguments.input).resolve())
    )
    if arguments.story_command == "review":
        _emit_story_report(report, arguments.output)
        return 0 if result.ready_for_approval else 1

    if not result.ready_for_approval:
        report["locked"] = False
        report["blocked_reason"] = (
            "Blocking canon violations or reviewer findings must be resolved "
            "before a human can lock this screenplay."
        )
        # --output means the locked screenplay. A blocked run must never leave
        # a file where a caller expects to find one.
        _emit_story_report(report, None)
        return 1

    locked = await engine.approve(result, approved_by=arguments.approved_by)
    payload = {
        "schema_version": 1,
        "episode_script": locked.to_dict(),
        "story_review": {
            **report,
            "status": locked.status.value,
            "locked": True,
            "approved_by": locked.approved_by,
            "approved_at": locked.approved_at.isoformat()
            if locked.approved_at
            else None,
        },
    }
    if arguments.output:
        print(str(_write_json(arguments.output, payload)))
    else:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def _emit_story_report(report: dict[str, Any], output: str | None) -> None:
    if output:
        print(str(_write_json(output, report)))
    else:
        print(json.dumps(report, ensure_ascii=False, indent=2))


async def _render_shot(
    arguments: argparse.Namespace,
    container: AnimationContainer,
) -> None:
    payload = json.loads(Path(arguments.plan).read_text(encoding="utf-8"))
    shot_payload = _select_shot_payload(payload, arguments.shot_id)
    shot = ShotPlan.from_dict(shot_payload)
    output = await container.animation_orchestrator_service.orchestrate_shot(
        shot_plan=shot,
        background_image_path=arguments.background_key,
        audio_path=arguments.audio_key,
        output_path=arguments.output_key,
    )
    print(output)


async def _run_blender_commands(
    arguments: argparse.Namespace,
    container: AnimationContainer,
) -> None:
    if arguments.blender_command == "register-views":
        from core.application.services.multiview_asset_registration_service import (
            MultiviewAssetRegistrationService,
        )

        service = MultiviewAssetRegistrationService(container.storage)
        updated_bible = await service.register_multiview_asset(
            bible=container.character_bible, image_path=arguments.input
        )
        print("Successfully registered multiview assets.")
        _show_character(updated_bible)
    elif arguments.blender_command == "turntable":
        from config.settings import get_settings
        from infrastructure.providers.blender.blender_scene_adapter import (
            BlenderSceneAdapter,
        )

        adapter = BlenderSceneAdapter(blender_bin_path=get_settings().blender_bin_path)
        manifest = await adapter.render_turntable(
            model_path=arguments.model,
            output_dir=arguments.output_dir,
            resolution_profile=arguments.quality,
        )
        print(json.dumps(manifest.to_dict(), indent=2))
    elif arguments.blender_command == "benchmark":
        from config.settings import get_settings
        from infrastructure.providers.blender.blender_scene_adapter import (
            BlenderSceneAdapter,
        )

        adapter = BlenderSceneAdapter(blender_bin_path=get_settings().blender_bin_path)
        stats = await adapter.run_benchmark(model_path=arguments.model)
        print(json.dumps(stats, indent=2))


async def _run_rig_commands(arguments: argparse.Namespace) -> int:
    from dataclasses import asdict

    from config.settings import get_settings
    from core.application.services.rig_validation_service import RigValidationService
    from core.domain.exceptions import RigValidationError
    from infrastructure.providers.blender.blender_rig_adapter import BlenderRigAdapter

    adapter = BlenderRigAdapter(blender_bin_path=get_settings().blender_bin_path)
    service = RigValidationService(adapter)

    if arguments.rig_command == "validate":
        report = await service.validate_character_rig(arguments.model)

        # Convert frozensets to lists for JSON serialization
        spec_dict = asdict(report.specification)
        spec_dict["shape_keys"] = sorted(spec_dict["shape_keys"])
        spec_dict["available_actions"] = sorted(spec_dict["available_actions"])

        output = {
            "is_valid": report.is_valid,
            "errors": report.errors,
            "specification": spec_dict,
        }
        print(json.dumps(output, indent=2))
        return 0 if report.is_valid else 2
    elif arguments.rig_command == "preview":
        report = await service.validate_character_rig(arguments.model)
        if not report.is_valid:
            raise RigValidationError(" ".join(report.errors))
        output_path = await adapter.bake_action_preview(
            model_path=arguments.model,
            action_name=arguments.action,
            output_path=arguments.output,
        )
        print(f"Preview saved to: {output_path}")
        return 0
    raise ValueError(f"Unsupported rig command: {arguments.rig_command}")


async def _run_preproduction_commands(
    arguments: argparse.Namespace,
    container: AnimationContainer,
) -> int:
    if arguments.preproduction_command == "status":
        direction = await container.canon_repository.get_creative_direction()
        world = await container.canon_repository.get_world_bible()
        visual = await container.canon_repository.get_visual_style()
        characters = await container.canon_repository.get_character_bibles()
        payload = {
            "schema_version": 1,
            "story_canon_locked": direction.status.value == "LOCKED",
            "world_canon_locked": world.status.value == "LOCKED",
            "visual_style_locked": visual.status.value == "LOCKED",
            "characters": [
                {
                    "character_id": bible.character_id,
                    "narrative_locked": bool(
                        bible.narrative_profile and bible.narrative_profile.locked
                    ),
                    "reference_count": len(bible.reference_pack),
                }
                for bible in characters
            ],
            "next_gate": "GOLDEN_SET",
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0
    if arguments.preproduction_command == "plan":
        source = json.loads(Path(arguments.input).read_text(encoding="utf-8"))
        script_payload = source.get("episode_script", source)
        script = EpisodeScript.from_dict(dict(script_payload))
        # The breakdown service needs a concrete bible, and the container is
        # built once for every command, so the identity is selected here rather
        # than injected. Nothing else built a bible, which is why this command
        # used to be reachable only from tests.
        characters = await container.canon_repository.get_character_bibles()
        matches = [
            item for item in characters if item.character_id == arguments.character_id
        ]
        if len(matches) != 1:
            raise ValueError(
                f"The locked Character Bible '{arguments.character_id}' "
                "was not found exactly once."
            )
        plan = HierarchicalShotPlanningService(
            ScriptBreakdownService(matches[0])
        ).plan(script)
        target = Path(arguments.output)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps(
                {"schema_version": 1, "episode_production_plan": plan.to_dict()},
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        print(str(target.resolve()))
        return 0
    if arguments.preproduction_command == "golden-set":
        visual = await container.canon_repository.get_visual_style()
        characters = await container.canon_repository.get_character_bibles()
        matches = [
            item for item in characters if item.character_id == arguments.character_id
        ]
        if len(matches) != 1:
            raise ValueError(
                f"The locked Character Bible '{arguments.character_id}' "
                "was not found exactly once."
            )
        golden_set = await container.character_golden_set_service.run(
            character=matches[0],
            style=visual,
            model_id=arguments.model_id,
            model_revision=arguments.model_revision,
        )
        target = Path(
            arguments.output
            or f"output/preproduction/{arguments.character_id}-golden-set.json"
        )
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps(
                {"schema_version": 1, "golden_set": golden_set.to_dict()},
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        print(str(target.resolve()))
        return 0
    raise ValueError(
        f"Unsupported preproduction command: {arguments.preproduction_command}"
    )


def _select_shot_payload(payload: Any, shot_id: str | None) -> dict[str, Any]:
    if isinstance(payload, dict) and isinstance(payload.get("shots"), list):
        shots = [item for item in payload["shots"] if isinstance(item, dict)]
        if not shot_id:
            raise ValueError(
                "--shot-id is required for a breakdown containing multiple shots."
            )
        matches = [item for item in shots if str(item.get("id")) == shot_id]
        if len(matches) != 1:
            raise ValueError(
                f"Shot '{shot_id}' was not found exactly once in the plan."
            )
        return matches[0]
    if not isinstance(payload, dict):
        raise TypeError("Shot plan JSON must contain an object.")
    if shot_id and str(payload.get("id")) != shot_id:
        raise ValueError(f"Shot plan does not contain requested shot '{shot_id}'.")
    return payload


async def _run_keyframe_commands(
    arguments: argparse.Namespace,
    container: AnimationContainer,
) -> int:
    if arguments.keyframe_command == "approve-pair":
        approval = await container.keyframe_generation_service.approve_keyframe_pair(
            shot_id=arguments.shot_id,
            manifest_storage_key=arguments.manifest,
            approved_by=arguments.approved_by,
            confirmed_checks=list(arguments.checks or []),
        )
        print(json.dumps(approval.to_dict(), ensure_ascii=False, indent=2))
        return 0
    if arguments.keyframe_command != "pair":
        raise ValueError(f"Unsupported keyframe command: {arguments.keyframe_command}")

    from core.domain.entities.character_state import CharacterState
    from core.domain.entities.shot_animation import AnimationShotPlan

    shot = AnimationShotPlan(
        id=arguments.shot_id,
        script_id="keyframe-pair",
        scene_plan_id="keyframe-pair",
        prompt=arguments.prompt_start,
        prompt_end=arguments.prompt_end,
        duration_seconds=2.0,
        character_state=CharacterState(
            character_id=arguments.character_id,
            active_outfit_id=arguments.outfit_id,
            injuries=[],
            held_objects=[],
        ),
        start_pose_reference_key=arguments.start_pose,
        end_pose_reference_key=arguments.end_pose,
        controlnet_type="openpose",
    )
    pair = await container.keyframe_generation_service.generate_keyframe_pair(shot)
    print(
        json.dumps(
            {
                "shot_id": arguments.shot_id,
                "start_storage_key": pair.start_storage_key,
                "end_storage_key": pair.end_storage_key,
                "manifest_storage_key": pair.manifest_storage_key,
                "contact_sheet_storage_key": pair.contact_sheet_storage_key,
                "human_approved": pair.human_approved,
            },
            indent=2,
        )
    )
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
