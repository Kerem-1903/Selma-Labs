"""CLI handlers for character quality, dataset, benchmark, and training commands."""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
from typing import Any, Callable

JsonWriter = Callable[[str | Path, dict[str, Any]], Path]
CharacterLoader = Callable[[str | Path], Any]
BriefLoader = Callable[[str | Path], Any]


#: Turnaround file stems as written by the view-pack asset service.
#: Only drawn views are listed. ``front.png`` and ``face-closeup.png`` are
#: contract copies of approved artifacts rather than model output, so there is
#: no drift to measure: the front image is the source itself, and comparing a
#: head crop with a full-body source compares two different framings. Including
#: them flagged the approved face anchor against its own bytes.
_DRIFT_VIEW_STEMS: dict[str, str] = {
    "three-quarter-left": "THREE_QUARTER_LEFT",
    "profile-left": "PROFILE_LEFT",
    "three-quarter-right": "THREE_QUARTER_RIGHT",
    "profile-right": "PROFILE_RIGHT",
    "back": "BACK",
}

#: Where the view-pack asset service writes view images, relative to the pack
#: directory. Older packs kept them beside ``view-pack.json``.
_DRIFT_VIEW_SUBDIRS: tuple[str, ...] = ("", "views")


def _drift_views(arguments: argparse.Namespace) -> dict[str, Path]:
    """Resolve the views to measure from explicit entries or a pack directory."""
    entries = list(arguments.drift_views or [])
    if entries:
        views: dict[str, Path] = {}
        for entry in entries:
            name, separator, raw_path = entry.partition("=")
            if not separator or not raw_path.strip():
                raise ValueError(f"--view expects VIEW=path, received: {entry!r}")
            views[name.strip().upper()] = Path(raw_path.strip())
        return views
    if not arguments.pack:
        raise ValueError("Provide --pack or at least one --view VIEW=path entry.")
    pack = Path(arguments.pack)
    discovered: dict[str, Path] = {}
    for stem, view in _DRIFT_VIEW_STEMS.items():
        for subdir in _DRIFT_VIEW_SUBDIRS:
            candidate = pack / subdir / f"{stem}.png"
            if candidate.is_file():
                discovered[view] = candidate
                break
    if not discovered:
        searched = ", ".join(
            (pack / subdir / "<view>.png").as_posix()
            for subdir in _DRIFT_VIEW_SUBDIRS
        )
        raise ValueError(f"No drawn turnaround view images found; looked at {searched}")
    return discovered


def run_character_quality_command(
    arguments: argparse.Namespace,
    *,
    write_json: JsonWriter,
    load_character_bible: CharacterLoader,
    load_creation_brief: BriefLoader,
) -> int:
    """Handle non-generation character commands outside the CLI entrypoint."""
    if arguments.character_command == "dataset":
        from core.application.services.character_lora_dataset_service import (
            CharacterLoraDatasetService,
        )
        from core.application.services.character_onboarding_service import (
            CharacterOnboardingService,
        )

        character = load_character_bible(arguments.input)
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

    if arguments.character_command == "audit-dataset":
        from core.application.services.character_lora_dataset_audit_service import (
            CharacterLoraDatasetAuditService,
        )

        audit = CharacterLoraDatasetAuditService().audit(arguments.manifest)
        payload = audit.to_dict()
        if arguments.output:
            print(write_json(arguments.output, payload))
        else:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0 if audit.training_approved else 2

    if arguments.character_command == "review-template":
        from core.application.services.character_lora_dataset_audit_service import (
            CharacterLoraDatasetAuditService,
        )

        payload = CharacterLoraDatasetAuditService().create_review_template(
            manifest_path=arguments.manifest,
            canonical_anchor=arguments.canonical_anchor,
        )
        print(write_json(arguments.output, payload))
        return 0

    if arguments.character_command == "view-consistency-report":
        from core.application.services.character_view_consistency_report_service import (
            CharacterViewConsistencyReportService,
        )

        report = CharacterViewConsistencyReportService().build(
            pack_path=arguments.view_pack,
            brief_path=arguments.brief,
            manifest_path=arguments.manifest,
            human_review_path=arguments.human_review,
        )
        if arguments.output:
            print(write_json(arguments.output, report))
        else:
            print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if report["status"] == "HUMAN_REVIEW_REQUIRED" else 2

    if arguments.character_command == "drift-report":
        from core.application.services.character_turnaround_drift_service import (
            CharacterTurnaroundDriftService,
            load_drift_thresholds,
        )

        # Load the band through the same loader production uses, so a diagnostic
        # run and a rendered pack can never disagree about which band was used.
        from config.settings import get_settings

        defaults = get_settings()
        selected = arguments.thresholds or defaults.character_drift_thresholds_path or None
        thresholds = None
        threshold_source: dict[str, str] = {}
        if selected:
            thresholds, threshold_source = load_drift_thresholds(selected)
        # Fall back to the configured identity for the same reason: running the
        # mark metrics with an empty accent or side would report a clean pack
        # simply because the mark checks were skipped.
        service = CharacterTurnaroundDriftService(
            accent_colour=(
                defaults.character_drift_accent_colour
                if arguments.accent_colour is None
                else arguments.accent_colour
            ),
            mark_side=(
                defaults.character_drift_mark_side
                if arguments.mark_side is None
                else arguments.mark_side
            ),
            threshold_source=threshold_source,
        )
        views = _drift_views(arguments)
        if arguments.calibrate:
            print(
                write_json(
                    arguments.output,
                    service.calibrate_paths(
                        source_path=arguments.source,
                        views=views,
                        margin=arguments.margin,
                    ).to_dict(),
                )
            )
            return 0
        report = service.evaluate_paths(
            source_path=arguments.source, views=views, thresholds=thresholds
        )
        if arguments.output:
            print(write_json(arguments.output, report))
        else:
            print(json.dumps(report, ensure_ascii=False, indent=2))
        # Exit 2 means "needs human attention", never "rejected": the drift
        # report is advisory evidence, not an approval decision.
        return 0 if report["status"] == "WITHIN_TOLERANCE" else 2

    if arguments.character_command == "qc-calibration-create":
        from core.application.services.character_qc_calibration_service import (
            CharacterQcCalibrationService,
        )

        payload = CharacterQcCalibrationService().create_manifest(
            storage_root=arguments.storage_root,
            benchmark_prefix=arguments.benchmark_prefix,
            minimum_images=arguments.minimum_images,
            maximum_images=arguments.maximum_images,
        )
        print(write_json(arguments.output, payload))
        return 0

    if arguments.character_command == "qc-calibration-summarize":
        from core.application.services.character_qc_calibration_service import (
            CharacterQcCalibrationService,
        )

        payload = json.loads(Path(arguments.manifest).read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise TypeError("Calibration manifest must contain an object.")
        summary = CharacterQcCalibrationService().summarize(payload)
        if arguments.output:
            print(write_json(arguments.output, summary))
        else:
            print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0

    if arguments.character_command == "train":
        return asyncio.run(
            _train_character_lora(
                arguments,
                load_character_bible=load_character_bible,
            )
        )

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
                {"status": "VALID", "benchmark": benchmark.to_dict()},
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    raise ValueError(f"Unsupported character quality command: {arguments.character_command}")


async def _train_character_lora(
    arguments: argparse.Namespace,
    *,
    load_character_bible: CharacterLoader,
) -> int:
    from core.domain.value_objects.character_lora_training import (
        CharacterLoraTrainingRequest,
    )
    from infrastructure.providers.training.kohya_character_lora_trainer import (
        KohyaCharacterLoraTrainer,
    )

    character = load_character_bible(arguments.input)
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


__all__ = ["run_character_quality_command"]
