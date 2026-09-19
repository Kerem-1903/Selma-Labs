"""Argument-parser construction for the ``character`` command.

The character surface is the widest in the CLI, so it is registered by
two builders -- lifecycle and asset/quality -- that share one subparser."""

from __future__ import annotations

import argparse


def add_character_commands(commands: argparse._SubParsersAction) -> None:
    character = commands.add_parser("character", help="Inspect canonical characters")
    character_commands = character.add_subparsers(
        dest="character_command", required=True
    )
    add_character_lifecycle_commands(character_commands)
    add_character_asset_commands(character_commands)

def add_character_lifecycle_commands(character_commands: argparse._SubParsersAction) -> None:
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

def add_character_asset_commands(character_commands: argparse._SubParsersAction) -> None:
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
        "pose-pack", help="Generate or approve the three-pose pre-animation character pack"
    )
    pose_pack_commands = pose_pack.add_subparsers(
        dest="pose_pack_command", required=True
    )
    pose_pack_generate = pose_pack_commands.add_parser(
        "generate", help="Generate a resumable three-pose pack from a canonical approval"
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
        "approve", help="Human-approve a complete three-pose character pack"
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
