"""Argument-parser construction for the episode, background, pilot, trailer,
screenplay and story commands."""

from __future__ import annotations

import argparse


def add_background_commands(commands: argparse._SubParsersAction) -> None:
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

def add_episode_commands(commands: argparse._SubParsersAction) -> None:
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
        help="Generated three-pose manifest JSON; repeat for every available character",
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
        help="Generated three-pose manifest JSON; repeat for every available character",
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

def add_pilot_commands(commands: argparse._SubParsersAction) -> None:
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

def add_trailer_commands(commands: argparse._SubParsersAction) -> None:
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

def add_script_commands(commands: argparse._SubParsersAction) -> None:
    script = commands.add_parser("script", help="Break a script into executable shots")
    script_commands = script.add_subparsers(dest="script_command", required=True)
    breakdown = script_commands.add_parser("breakdown")
    breakdown.add_argument("--input", required=True, help="UTF-8 text script")
    breakdown.add_argument("--character-bible", required=True)
    breakdown.add_argument("--script-id", required=True)
    breakdown.add_argument("--output", help="Optional JSON output file")

def add_story_commands(commands: argparse._SubParsersAction) -> None:
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
