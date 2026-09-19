from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.application.services.character_view_pack_generation_service import (
    CharacterViewPackGenerationService,
)
from core.application.services.model_lock_service import (
    load_model_lock,
    verify_model_lock,
)
from core.domain.value_objects.character_design import (
    CharacterAnchorArtifact,
    CharacterCanonicalApproval,
    CharacterReferenceDraft,
)

ROOT = Path(__file__).parents[2]


def _draft(view: str, seed: int = 1) -> CharacterReferenceDraft:
    slug = view.casefold().replace("_", "-")
    return CharacterReferenceDraft(
        view=view,
        storage_key=f"characters/kaito/v5/views/{slug}.png",
        content_hash=(view[0].casefold() * 64),
        seed=seed,
        width=768,
        height=1152,
    )


def _brief():
    from core.domain.value_objects.character_creation_brief import (  # noqa: PLC0415
        CharacterCreationBrief,
    )

    return CharacterCreationBrief.from_dict(
        {
            "schema_version": 1,
            "name": "Kaito",
            "concept": "Disciplined courier",
            "gender_presentation": "masculine",
            "body_type": "athletic adult",
            "face": "angular anime face",
            "eyes": "steel blue eyes",
            "hair": "short black hair with one cobalt streak",
            "outfit": "charcoal courier jacket with blue trim",
            "props": ["messenger bag on character-right hip"],
            "palette": ["charcoal", "black", "cobalt blue"],
            "style_preset": "selma-anime-v1",
            "avoid": ["chibi proportions"],
        }
    )


def _anchor(role: str, seed: int = 7) -> CharacterAnchorArtifact:
    return CharacterAnchorArtifact(
        role=role,
        storage_key=f"characters/kaito/v5/{role.casefold()}_anchor.png",
        content_hash=("f" * 64),
        seed=seed,
        width=1024,
        height=1024,
        provider_asset_id=f"{role.lower()}-asset",
        model_checkpoint="animagine-xl-4.0-opt.safetensors",
    )


def _approval() -> CharacterCanonicalApproval:
    return CharacterCanonicalApproval(
        schema_version=1,
        character_id="kaito",
        character_version=5,
        brief_hash="b" * 64,
        source_candidate_key="characters/kaito/v5/candidates/c0.png",
        canonical_storage_key="characters/kaito/v5/canonical_source.png",
        canonical_content_hash="c" * 64,
        provider="comfyui:keyframe",
        provider_asset_id="canonical-asset",
        seed=42,
        approved_by="Selma",
        approved_at=__import__("datetime").datetime.now(
            __import__("datetime").timezone.utc
        ),
        anchor_provider="comfyui:keyframe",
        anchor_workflow_version="dual-anchor-v2-deterministic",
        face_anchor=_anchor("FACE"),
        fullbody_anchor=_anchor("FULL_BODY"),
    )


class _NoopGenerator:
    name = "fake:keyframe"

    async def generate_keyframe(self, request):  # pragma: no cover - unused
        raise AssertionError("generation is not exercised here")


class _NoopStorage:
    def __init__(self, assets: dict[str, bytes] | None = None) -> None:
        self.assets = assets or {}

    async def load(self, key: str) -> bytes:
        return self.assets.get(key, b"source")


def _service(
    *,
    edit_dialect: bool,
    drift_service=None,
    storage: _NoopStorage | None = None,
) -> CharacterViewPackGenerationService:
    return CharacterViewPackGenerationService(
        _NoopGenerator(),
        storage or _NoopStorage(),
        edit_dialect=edit_dialect,
        drift_service=drift_service,
    )


def test_edit_wings_derive_from_the_source_not_from_each_other():
    service = _service(edit_dialect=True)
    approval = _approval()
    produced = {
        view: _draft(view)
        for view in (
            "FRONT",
            "THREE_QUARTER_LEFT",
            "PROFILE_LEFT",
            "THREE_QUARTER_RIGHT",
            "PROFILE_RIGHT",
        )
    }

    left_wing = service._edit_conditioning_references(
        view="PROFILE_LEFT", approval=approval, face_anchor=approval.face_anchor, produced=produced
    )
    right_wing = service._edit_conditioning_references(
        view="PROFILE_RIGHT", approval=approval, face_anchor=approval.face_anchor, produced=produced
    )

    assert [item[0] for item in left_wing] == ["FRONT", "THREE_QUARTER_LEFT"]
    assert [item[0] for item in right_wing] == ["FRONT", "THREE_QUARTER_RIGHT"]


def test_back_view_sees_both_profiles_because_the_bag_only_reads_from_one_side():
    service = _service(edit_dialect=True)
    approval = _approval()
    produced = {
        view: _draft(view)
        for view in (
            "FRONT",
            "THREE_QUARTER_LEFT",
            "PROFILE_LEFT",
            "THREE_QUARTER_RIGHT",
            "PROFILE_RIGHT",
        )
    }

    references = service._edit_conditioning_references(
        view="BACK", approval=approval, face_anchor=approval.face_anchor, produced=produced
    )

    assert [item[0] for item in references] == [
        "FRONT",
        "PROFILE_LEFT",
        "PROFILE_RIGHT",
    ]
    # The graph has exactly three reference slots, so BACK is the only view that
    # may consume all of them.
    assert len(references) == 3


def test_three_quarter_views_start_from_the_source_only():
    service = _service(edit_dialect=True)
    approval = _approval()
    produced = {"FRONT": _draft("FRONT")}

    references = service._edit_conditioning_references(
        view="THREE_QUARTER_LEFT",
        approval=approval,
        face_anchor=approval.face_anchor,
        produced=produced,
    )

    assert [item[0] for item in references] == ["FRONT"]
    assert references[0][1] == produced["FRONT"].storage_key


def test_missing_dependency_is_reported_before_generation():
    service = _service(edit_dialect=True)

    with pytest.raises(ValueError, match="PROFILE_RIGHT"):
        service._edit_conditioning_references(
            view="BACK",
            approval=_approval(),
            face_anchor=_approval().face_anchor,
            produced={"FRONT": _draft("FRONT"), "PROFILE_LEFT": _draft("PROFILE_LEFT")},
        )


def test_edit_dialect_front_is_the_approved_canonical_image():
    service = _service(edit_dialect=True)
    approval = _approval()

    inherited = service._inherited_view(
        view="FRONT",
        approval=approval,
        face=approval.face_anchor,
        fullbody=approval.fullbody_anchor,
    )

    assert inherited is not None
    assert inherited.storage_key == approval.canonical_storage_key
    assert inherited.content_hash == approval.canonical_content_hash
    assert inherited.human_approved is True
    assert inherited.seed == approval.seed


def test_standard_dialect_still_inherits_the_generated_fullbody_anchor():
    service = _service(edit_dialect=False)
    approval = _approval()

    inherited = service._inherited_view(
        view="FRONT",
        approval=approval,
        face=approval.face_anchor,
        fullbody=approval.fullbody_anchor,
    )

    assert inherited is not None
    assert inherited.storage_key == approval.fullbody_anchor.storage_key
    assert inherited.human_approved is False


def test_only_fixed_views_are_inherited():
    service = _service(edit_dialect=True)
    approval = _approval()

    for view in ("PROFILE_LEFT", "BACK", "THREE_QUARTER_RIGHT"):
        assert (
            service._inherited_view(
                view=view,
                approval=approval,
                face=approval.face_anchor,
                fullbody=approval.fullbody_anchor,
            )
            is None
        )


# ----------------------------------------------------------------------
# Seed sweep selection
# ----------------------------------------------------------------------
def _candidate(slot: int, image: bytes):
    from core.application.services.character_view_pack_generation_service import (  # noqa: PLC0415
        _ViewCandidate,
    )
    from core.domain.value_objects.character_view_qc import (  # noqa: PLC0415
        CharacterViewObservation,
        CharacterViewQcReport,
    )

    return _ViewCandidate(
        slot=slot,
        seed=100 + slot,
        image_bytes=image,
        width=768,
        height=1152,
        digest=f"{slot:02d}" * 32,
        report=CharacterViewQcReport(
            view="PROFILE_LEFT",
            seed=100 + slot,
            passed=True,
            reasons=(),
            observation=CharacterViewObservation(
                person_count=1,
                face_count=1,
                head_inside_frame=True,
                feet_inside_frame=True,
                orientation="profile_left",
                confidence=1.0,
                provider="test",
            ),
            framing_metrics={},
            checks={},
        ),
        provider_asset_id=f"asset-{slot}",
        model_checkpoint="flux-2-klein-4b-fp8.safetensors",
        generation_metadata={},
    )


class _FakeDrift:
    """Scores by a marker byte so the test controls the ranking directly."""

    def evaluate(self, *, source_bytes, views):
        del source_bytes
        view, data = next(iter(views.items()))
        clean = b"clean" in data
        return {
            "views": [
                {
                    "view": view,
                    "status": "WITHIN_TOLERANCE" if clean else "DRIFT_FLAGGED",
                    "reasons": [] if clean else ["palette_drift"],
                    "metrics": {"palette_distance": 0.01 if clean else 0.5},
                }
            ]
        }


@pytest.mark.asyncio
async def test_candidate_sweep_keeps_the_least_drifted_seed():
    service = _service(edit_dialect=True, drift_service=_FakeDrift())
    noisy = _candidate(0, b"noisy")
    clean = _candidate(1, b"clean") 

    chosen, outranked = await service._select_view_candidate(
        view="PROFILE_LEFT", approval=_approval(), candidates=[noisy, clean]
    )

    assert chosen.slot == 1
    assert chosen.image_bytes == b"clean"
    assert [item.slot for item in outranked] == [0]
    assert chosen.drift_metrics is not None
    assert chosen.drift_metrics["status"] == "WITHIN_TOLERANCE"


@pytest.mark.asyncio
async def test_single_candidate_is_never_reordered_or_scored():
    service = _service(edit_dialect=True, drift_service=_FakeDrift())
    only = _candidate(0, b"noisy")

    chosen, outranked = await service._select_view_candidate(
        view="PROFILE_LEFT", approval=_approval(), candidates=[only]
    )

    assert chosen is only
    assert outranked == []
    assert chosen.drift_metrics is None


def test_candidate_count_is_bounded():
    with pytest.raises(ValueError, match="between 1 and 6"):
        CharacterViewPackGenerationService(
            _NoopGenerator(), _NoopStorage(), view_candidate_count=9
        )


def test_turnaround_cli_accepts_a_seed_sweep():
    from cli.main import build_parser  # noqa: PLC0415

    arguments = build_parser().parse_args(
        [
            "character",
            "turnaround",
            "--brief",
            "b.json",
            "--approval",
            "a.json",
            "--manifest",
            "m.json",
            "--seeds",
            "4",
        ]
    )

    assert arguments.seeds == 4


# ----------------------------------------------------------------------
# Drift evidence covers drawn views only
# ----------------------------------------------------------------------
class _RecordingDrift:
    """Records which views a drift report asked it to measure."""

    def __init__(self) -> None:
        self.measured: list[str] = []

    def evaluate(self, *, source_bytes, views, labels=None):
        del source_bytes, labels
        self.measured.extend(sorted(views))
        return {
            "schema_version": 1,
            "views": [
                {"view": view, "status": "WITHIN_TOLERANCE", "reasons": []}
                for view in sorted(views)
            ],
            "summary": {"flagged_views": []},
        }


class _MemoryStorage:
    def __init__(self, assets: dict[str, bytes] | None = None) -> None:
        self.assets = dict(assets or {})

    async def save(self, key, data, content_type):
        from core.domain.value_objects.storage_reference import (  # noqa: PLC0415
            StorageReference,
        )

        self.assets[key] = data
        return StorageReference(key=key, path=f"memory://{key}", size_bytes=len(data))

    async def save_stream(self, key, stream, content_type, **kwargs):
        del kwargs
        payload = b"".join([chunk async for chunk in stream])
        return await self.save(key, payload, content_type)

    async def load(self, key):
        return self.assets[key]

    async def exists(self, key):
        return key in self.assets

    def upload_file(self, file_stream, destination_path, content_type):
        del file_stream, content_type
        return f"memory://{destination_path}"

    def download_file(self, source_path, local_destination):
        del source_path, local_destination
        return False

    def delete_file(self, file_path):
        return self.assets.pop(file_path, None) is not None


def test_face_closeup_counts_as_inherited_so_it_is_not_measured():
    """The v6 report flagged the approved face anchor against itself.

    The front image and the face close-up are copied from approved artifacts by
    contract, so there is no render to measure. Measuring the face close-up
    compares a head crop with a full-body source and produced a
    ``signature_mark_missing_or_hidden`` alarm on byte-identical approved
    evidence.
    """
    service = _service(edit_dialect=True)
    approval = _approval()

    assert service._view_is_inherited("FRONT", approval) is True
    assert service._view_is_inherited("FACE_CLOSEUP", approval) is True
    for view in ("PROFILE_LEFT", "THREE_QUARTER_LEFT", "BACK"):
        assert service._view_is_inherited(view, approval) is False


@pytest.mark.asyncio
async def test_drift_report_only_measures_drawn_views():
    recorder = _RecordingDrift()
    approval = _approval()
    canonical = b"canonical-source-bytes"
    storage = _MemoryStorage(
        {
            approval.canonical_storage_key: canonical,
            _draft("PROFILE_LEFT", seed=11).storage_key: b"profile-bytes",
            _draft("BACK", seed=12).storage_key: b"back-bytes",
        }
    )
    service = _service(edit_dialect=True, drift_service=recorder, storage=storage)
    drafts = [
        _draft("FACE_CLOSEUP"),
        _draft("FRONT"),
        _draft("PROFILE_LEFT", seed=11),
        _draft("BACK", seed=12),
    ]

    await service._write_drift_report(
        root="characters/kaito/v6",
        brief=_brief(),
        approval=approval,
        drafts=drafts,
    )

    assert recorder.measured == ["BACK", "PROFILE_LEFT"]


@pytest.mark.asyncio
async def test_a_pack_of_only_copied_views_produces_no_drift_report():
    """A report over zero drawn views would claim a measurement that never """
    recorder = _RecordingDrift()
    approval = _approval()
    storage = _MemoryStorage({approval.canonical_storage_key: b"canonical"})
    service = _service(edit_dialect=True, drift_service=recorder, storage=storage)

    await service._write_drift_report(
        root="characters/kaito/v6",
        brief=_brief(),
        approval=approval,
        drafts=[_draft("FRONT"), _draft("FACE_CLOSEUP")],
    )

    assert recorder.measured == []
    assert await storage.exists("characters/kaito/v6/drift-report.json") is False


# ----------------------------------------------------------------------
# The edit canvas follows the source instead of re-framing it
# ----------------------------------------------------------------------
def test_edit_canvas_preserves_the_source_aspect_ratio():
    from core.application.services.character_identity_prompt_service import (  # noqa: PLC0415
        edit_canvas_for,
    )

    square = edit_canvas_for(1024, 1024)
    portrait = edit_canvas_for(1024, 1536)

    # A square source must stay square: rendering it onto the fixed 768x1152
    # portrait canvas made the model re-frame as well as rotate, which is how
    # the palette and subject-box metrics collapsed in the v6 run.
    assert square[0] == square[1]
    assert abs(portrait[0] / portrait[1] - 1024 / 1536) < 0.02
    for columns, rows in (square, portrait):
        assert columns % 16 == 0 and rows % 16 == 0
        assert 0.5e6 <= columns * rows <= 1.6e6

    with pytest.raises(ValueError, match="positive"):
        edit_canvas_for(0, 100)


def test_reference_request_keeps_the_calibrated_canvas_by_default():
    from core.application.services.character_identity_prompt_service import (  # noqa: PLC0415
        CharacterIdentityPromptService,
    )

    service = CharacterIdentityPromptService()
    brief = _brief()
    references = (("FRONT", "characters/kaito/v6/canonical_source.png", "c" * 64, 1.0),)

    default = service.build_reference_request(
        brief,
        view="PROFILE_LEFT",
        direction="strict left side profile",
        seed=1,
        references=references,
    )
    derived = service.build_reference_request(
        brief,
        view="PROFILE_LEFT",
        direction="strict left side profile",
        seed=1,
        references=references,
        canvas=(992, 992),
    )

    assert (default.width, default.height) == (768, 1152)
    assert default.visual_constraints["canvas_policy"] == "fixed_portrait"
    assert (derived.width, derived.height) == (992, 992)
    assert derived.visual_constraints["canvas_policy"] == "source_aspect"


# ----------------------------------------------------------------------
# Rejected-approach hygiene
# ----------------------------------------------------------------------
REJECTED_ROOT = ROOT / "output" / "diagnostics" / "rejected-approaches"


def test_rejected_approaches_directory_is_documented_evidence():
    readme = REJECTED_ROOT / "README.md"
    assert readme.is_file()
    text = readme.read_text(encoding="utf-8")
    assert "kanıt" in text
    assert "LoRA" in text


def test_no_acceptance_or_benchmark_config_sources_a_rejected_approach():
    offenders: list[str] = []
    for path in list((ROOT / "config").rglob("*.json")) + list(
        (ROOT / "assets" / "quality_benchmarks").rglob("*.json")
    ):
        if "rejected-approaches" in path.read_text(encoding="utf-8"):
            offenders.append(path.relative_to(ROOT).as_posix())
    assert offenders == []


def test_kaito_acceptance_requires_the_drift_report():
    acceptance = json.loads(
        (ROOT / "config" / "character_acceptance" / "kaito-v1.json").read_text(
            encoding="utf-8"
        )
    )
    assert "drift-report.json" in acceptance["required_evidence"]


def test_flux_evidence_never_lands_in_the_rejected_folder():
    rejected = {path.name for path in REJECTED_ROOT.iterdir()}
    assert not any(name.startswith("flux2-") for name in rejected)


# ----------------------------------------------------------------------
# Weight removal (2026-09-13): raw weights are gone, evidence stays
# ----------------------------------------------------------------------
REMOVED_WEIGHTS = (
    "qwen_image_edit_2511_int8_convrot.safetensors",
    "qwen_2.5_vl_7b_fp8_scaled.safetensors",
    "qwen_image_vae.safetensors",
    "ip-adapter-faceid-plusv2_sdxl.bin",
    "ip-adapter-faceid-plusv2_sdxl_lora.safetensors",
    "Illustrious-XL-v2.0.safetensors",
    "sdpose_wholebody_fp16.safetensors",
)
DELETION_RECORD = ROOT / "docs" / "REJECTED_APPROACHES.md"
RETIRED_PROFILE = ROOT / "config" / "model_profiles" / "illustrious-xl-v2.lock.json"


def test_removed_weights_are_recorded_with_sizes_and_sources():
    """Deleting bytes is only safe because the record says what and how to restore."""
    text = DELETION_RECORD.read_text(encoding="utf-8")
    for name in REMOVED_WEIGHTS:
        assert name in text, name
    for size in ("20499083824", "9384670680", "6938040674", "1916645792"):
        assert size in text, size
    for source in (
        "Qwen/Qwen-Image-Edit-2511",
        "h94/IP-Adapter-FaceID",
        "OnomaAIResearch/Illustrious-XL-v2.0",
    ):
        assert source in text, source


def test_qwen_text_encoder_name_collision_is_documented():
    """FLUX.2's encoder is a qwen file; "delete qwen" must not take it out."""
    assert "qwen_3_4b.safetensors" in DELETION_RECORD.read_text(encoding="utf-8")
    flux_lock = json.loads(
        (ROOT / "models-flux2.lock.json").read_text(encoding="utf-8")
    )
    encoders = [
        entry["filename"]
        for entry in flux_lock["models"]
        if entry["role"] == "text_encoder"
    ]
    assert encoders == ["qwen_3_4b.safetensors"]
    assert not any(name.startswith("qwen_3_4b") for name in REMOVED_WEIGHTS)


def test_no_live_config_still_requires_a_removed_weight():
    """A removed weight may only survive in an explicitly retired profile."""
    offenders: list[str] = []
    candidates = [
        ROOT / "models.lock.json",
        ROOT / "models-flux2.lock.json",
        RETIRED_PROFILE,
        *sorted((ROOT / "config").rglob("*.json")),
    ]
    for path in candidates:
        text = path.read_text(encoding="utf-8")
        if not any(name in text for name in REMOVED_WEIGHTS):
            continue
        if json.loads(text).get("retired") is True:
            continue
        offenders.append(path.relative_to(ROOT).as_posix())
    assert offenders == []


def test_retired_model_profile_fails_preflight_loudly():
    """A stale pointer must abort, not quietly resolve to an abandoned path."""
    lock = load_model_lock(RETIRED_PROFILE)
    assert lock.retired is True
    assert "Illustrious" in lock.retired_reason
    checks = verify_model_lock(lock, full_hash=False)
    retired = [check for check in checks if check.name == "model_lock:retired"]
    assert len(retired) == 1
    assert retired[0].passed is False
    assert retired[0].warning is False


def test_kept_fallback_stack_still_verifies_on_disk():
    """FLUX is an editor; the text-driven SDXL stack must keep working."""
    for name in ("models.lock.json", "models-flux2.lock.json"):
        lock = load_model_lock(ROOT / name)
        assert lock.retired is False
        if not Path(lock.comfyui_root).is_dir():
            # Offline CI has no ComfyUI install; the record above still guards it.
            pytest.skip(f"comfyui root not installed here: {lock.comfyui_root}")
        failed = [
            check
            for check in verify_model_lock(lock, full_hash=False)
            if not check.passed
        ]
        assert failed == [], (name, [check.name for check in failed])
