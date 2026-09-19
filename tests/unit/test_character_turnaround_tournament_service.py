from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from PIL import Image

from core.application.services.character_turnaround_drift_service import (
    CharacterTurnaroundDriftService,
)
from core.application.services.character_turnaround_tournament_service import (
    CharacterTurnaroundTournamentService,
)
from core.domain.value_objects.character_creation_brief import CharacterCreationBrief

BACKDROP = (240, 240, 240)
SUBJECT = (60, 60, 60)
COBALT = (0, 71, 171)

_WIDTH, _HEIGHT = 200, 300


def _png(*, accent: bool = True, tint: int = 0) -> bytes:
    array = np.full((_HEIGHT, _WIDTH, 3), BACKDROP, dtype=np.uint8)
    array[40:261, 60:141] = np.clip(
        np.array(SUBJECT, dtype=np.int16) + tint, 0, 255
    ).astype(np.uint8)
    if accent:
        array[45:70, 95:97] = COBALT
    buffer = io.BytesIO()
    Image.fromarray(array).save(buffer, format="PNG")
    return buffer.getvalue()


def _source_png() -> bytes:
    return _png()


def _drifted_png() -> bytes:
    return _png(accent=False, tint=90)


#: The views where a character-left front-hair streak must be hidden. A clean
#: render of those views legitimately omits the accent, exactly as the shipped
#: turnaround is expected to.
_HIDDEN_MARK_VIEWS = {"THREE_QUARTER_RIGHT", "PROFILE_RIGHT", "BACK"}


def _clean_view_png(view: str) -> bytes:
    return _png(accent=view not in _HIDDEN_MARK_VIEWS)


class CleanProvider:
    """Renders a view-correct turnaround: no invented mark, no palette drift."""

    def __init__(self, name="comfyui:flux2-edit", contract="source-led-delta-edit-v1"):
        self._name = name
        self._contract = contract
        self.requests = []

    @property
    def name(self):
        return self._name

    @property
    def edit_contract(self):
        return self._contract

    async def generate_keyframe(self, request):
        self.requests.append(request)
        return SimpleNamespace(
            image_bytes=_clean_view_png(request.visual_constraints["view"])
        )


class MemoryStorage:
    def __init__(self, assets=None):
        self.assets = dict(assets or {})

    async def load(self, key):
        return self.assets[key]

    async def save(self, key, data, content_type):
        del content_type
        self.assets[key] = data
        return SimpleNamespace(key=key, size_bytes=len(data))


class FakeProvider:
    def __init__(self, *, image: bytes, name="comfyui:flux2-edit", contract="source-led-delta-edit-v1"):
        self._image = image
        self._name = name
        self._contract = contract
        self.requests = []

    @property
    def name(self):
        return self._name

    @property
    def edit_contract(self):
        return self._contract

    async def generate_keyframe(self, request):
        self.requests.append(request)
        return SimpleNamespace(image_bytes=self._image)


def _brief() -> CharacterCreationBrief:
    return CharacterCreationBrief.from_dict(
        {
            "schema_version": 1,
            "name": "Kaito",
            "concept": "Disciplined courier",
            "gender_presentation": "masculine",
            "hair": "short black hair with one cobalt streak",
            "signature_marks": [
                {
                    "label": "single cobalt front hair streak",
                    "count": 1,
                    "character_side": "left",
                    "colour": "#0047AB",
                }
            ],
            "outfit": "charcoal courier jacket",
            "palette": ["charcoal", "cobalt blue"],
            "style_preset": "selma-anime-v1",
        }
    )


def _write_lock(path: Path, *, checkpoint: str, digest: str, size: int) -> Path:
    payload = {
        "schema_version": 1,
        "comfyui_root": "C:/ComfyUI",
        "models": [
            {
                "role": "diffusion_model",
                "filename": checkpoint,
                "relative_path": f"models/diffusion_models/{checkpoint}",
                "sha256": digest,
                "size_bytes": size,
            },
            {
                "role": "text_encoder",
                "filename": "qwen_3_4b.safetensors",
                "relative_path": "models/text_encoders/qwen_3_4b.safetensors",
                "sha256": "e" * 64,
                "size_bytes": 10,
            },
            {
                "role": "vae",
                "filename": "flux2-vae.safetensors",
                "relative_path": "models/vae/flux2-vae.safetensors",
                "sha256": "f" * 64,
                "size_bytes": 11,
            },
        ],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _benchmark(tmp_path: Path, source: bytes) -> Path:
    image = tmp_path / "reference.png"
    image.write_bytes(source)
    payload = {
        "schema_version": 1,
        "benchmark_id": "kaito-quality-v1",
        "reference_asset": "reference.png",
        "reference_sha256": hashlib.sha256(source).hexdigest(),
        "width": _WIDTH,
        "height": _HEIGHT,
        "usage": "quality_and_style_evaluation_only",
        "visual_targets": ["single centered full-body anime character head to boots"],
        "human_criteria": [{"id": "identity", "label": "same identity", "weight": 1.0}],
        "prohibited_transfer": ["using the benchmark reference as an identity reference"],
    }
    path = tmp_path / "benchmark.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _service(tmp_path: Path, providers: dict[str, FakeProvider]) -> CharacterTurnaroundTournamentService:
    return CharacterTurnaroundTournamentService(
        tmp_path,
        lambda lock: providers[lock.entry("diffusion_model").filename],
        drift_service=CharacterTurnaroundDriftService(
            accent_colour="#0047AB", mark_side="left"
        ),
    )


async def _run(tmp_path: Path, providers: dict[str, FakeProvider], **overrides):
    source = _source_png()
    locks = [
        _write_lock(tmp_path / f"{name}.lock.json", checkpoint=name, digest=digest, size=size)
        for name, digest, size in (
            ("small.safetensors", "a" * 64, 100),
            ("large.safetensors", "b" * 64, 9000),
        )
    ]
    arguments = {
        "benchmark_path": _benchmark(tmp_path, source),
        "brief": _brief(),
        "storage": MemoryStorage({"characters/kaito/v5/canonical_source.png": source}),
        "source_storage_key": "characters/kaito/v5/canonical_source.png",
        "model_lock_paths": locks,
        "seeds": [42],
        "run_id": "run-1",
    }
    arguments.update(overrides)
    return await _service(tmp_path, providers).run(**arguments)


@pytest.mark.asyncio
async def test_clean_variant_recommends_staying_local(tmp_path):
    report = await _run(
        tmp_path,
        {
            "small.safetensors": CleanProvider(),
            "large.safetensors": FakeProvider(image=_drifted_png()),
        },
    )

    comparison = report["comparison"]
    assert comparison["verdict"] == "LOCAL_SUFFICIENT"
    variant = next(item for item in report["variants"] if item["variant_id"] == "small")
    assert variant["flagged_view_count"] == 0
    assert comparison["recommended_variant"] == "small"
    assert comparison["human_review_required"] is True
    assert report["status"] == "PENDING_HUMAN_REVIEW"
    assert report["prompt_contract"] == "source-led-delta-edit-v1"


@pytest.mark.asyncio
async def test_a_view_that_drifts_in_every_variant_escalates(tmp_path):
    report = await _run(
        tmp_path,
        {
            "small.safetensors": FakeProvider(image=_drifted_png()),
            "large.safetensors": FakeProvider(image=_drifted_png()),
        },
    )

    comparison = report["comparison"]
    assert comparison["verdict"] == "ESCALATE_TO_LARGER_MODEL"
    assert set(comparison["universally_flagged_views"]) == {
        "THREE_QUARTER_LEFT",
        "PROFILE_LEFT",
        "THREE_QUARTER_RIGHT",
        "PROFILE_RIGHT",
        "BACK",
    }


@pytest.mark.asyncio
async def test_tournament_requires_two_distinct_checkpoints(tmp_path):
    source = _source_png()
    lock = _write_lock(
        tmp_path / "only.lock.json",
        checkpoint="only.safetensors",
        digest="a" * 64,
        size=1,
    )

    with pytest.raises(ValueError, match="at least two model locks"):
        await _run(
            tmp_path,
            {"only.safetensors": FakeProvider(image=source)},
            model_lock_paths=[lock],
        )


@pytest.mark.asyncio
async def test_tournament_rejects_a_duplicate_checkpoint(tmp_path):
    source = _source_png()
    first = _write_lock(
        tmp_path / "a.lock.json", checkpoint="same.safetensors", digest="a" * 64, size=1
    )
    second = _write_lock(
        tmp_path / "b.lock.json", checkpoint="same.safetensors", digest="a" * 64, size=1
    )

    with pytest.raises(ValueError, match="duplicate checkpoint"):
        await _run(
            tmp_path,
            {"same.safetensors": FakeProvider(image=source)},
            model_lock_paths=[first, second],
        )


@pytest.mark.asyncio
async def test_tournament_rejects_unaligned_dependencies(tmp_path):
    source = _source_png()
    first = _write_lock(
        tmp_path / "a.lock.json", checkpoint="small.safetensors", digest="a" * 64, size=1
    )
    second = _write_lock(
        tmp_path / "b.lock.json", checkpoint="large.safetensors", digest="b" * 64, size=1
    )
    payload = json.loads(second.read_text(encoding="utf-8"))
    payload["models"][1]["sha256"] = "9" * 64
    second.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="identical non-checkpoint dependencies"):
        await _run(
            tmp_path,
            {
                "small.safetensors": FakeProvider(image=source),
                "large.safetensors": FakeProvider(image=source),
            },
            model_lock_paths=[first, second],
        )


@pytest.mark.asyncio
async def test_tournament_rejects_a_source_that_is_not_the_benchmark_reference(tmp_path):
    source = _source_png()
    other = MemoryStorage(
        {"characters/kaito/v5/canonical_source.png": _drifted_png()}
    )

    with pytest.raises(ValueError, match="does not match the benchmark reference"):
        await _run(
            tmp_path,
            {
                "small.safetensors": FakeProvider(image=source),
                "large.safetensors": FakeProvider(image=source),
            },
            storage=other,
        )


@pytest.mark.asyncio
async def test_tournament_refuses_engines_without_the_edit_contract(tmp_path):
    source = _source_png()

    with pytest.raises(ValueError, match="does not declare a source-led edit contract"):
        await _run(
            tmp_path,
            {
                "small.safetensors": FakeProvider(image=source, contract=""),
                "large.safetensors": FakeProvider(image=source),
            },
        )


@pytest.mark.asyncio
async def test_tournament_rejects_duplicate_seeds(tmp_path):
    with pytest.raises(ValueError, match="unique"):
        await _run(
            tmp_path,
            {
                "small.safetensors": FakeProvider(image=_source_png()),
                "large.safetensors": FakeProvider(image=_source_png()),
            },
            seeds=[42, 42],
        )


@pytest.mark.asyncio
async def test_tournament_chains_views_through_the_shipped_request_shape(tmp_path):
    source = _source_png()
    left = FakeProvider(image=source)
    right = FakeProvider(image=source)

    await _run(
        tmp_path,
        {"small.safetensors": left, "large.safetensors": right},
    )

    by_view = {request.visual_constraints["view"]: request for request in left.requests}
    assert list(by_view) == [
        "THREE_QUARTER_LEFT",
        "PROFILE_LEFT",
        "THREE_QUARTER_RIGHT",
        "PROFILE_RIGHT",
        "BACK",
    ]
    assert by_view["PROFILE_LEFT"].visual_constraints["reference_views"] == [
        "FRONT",
        "THREE_QUARTER_LEFT",
    ]
    assert by_view["BACK"].visual_constraints["reference_views"] == [
        "FRONT",
        "PROFILE_LEFT",
        "PROFILE_RIGHT",
    ]
    assert by_view["THREE_QUARTER_RIGHT"].visual_constraints["reference_views"] == [
        "FRONT"
    ]


@pytest.mark.asyncio
async def test_tournament_keeps_the_least_drifted_seed_per_view(tmp_path):
    source = _source_png()

    class PerSeedProvider(CleanProvider):
        async def generate_keyframe(self, request):
            self.requests.append(request)
            image = (
                _clean_view_png(request.visual_constraints["view"])
                if request.seed == 143
                else _drifted_png()
            )
            return SimpleNamespace(image_bytes=image)

    provider = PerSeedProvider()
    report = await _run(
        tmp_path,
        {"small.safetensors": provider, "large.safetensors": CleanProvider()},
        seeds=[42, 143],
    )

    variant = next(item for item in report["variants"] if item["variant_id"] == "small")
    assert {view["seed"] for view in variant["views"]} == {143}
    assert variant["flagged_view_count"] == 0
    first_view = variant["views"][0]
    assert [candidate["seed"] for candidate in first_view["candidates"]] == [42, 143]


@pytest.mark.asyncio
async def test_tournament_records_every_candidate_and_accepted_view(tmp_path):
    report = await _run(
        tmp_path,
        {
            "small.safetensors": FakeProvider(image=_source_png()),
            "large.safetensors": FakeProvider(image=_source_png()),
        },
        seeds=[42, 143],
    )

    variant = report["variants"][0]
    assert variant["checkpoint"] in {"small.safetensors", "large.safetensors"}
    assert len(variant["views"]) == 5
    assert all(len(view["candidates"]) == 2 for view in variant["views"])
    assert variant["views"][0]["storage_key"].endswith("/three-quarter-left.png")
    assert variant["views"][0]["candidates"][0]["storage_key"].endswith(
        "/candidates/three-quarter-left-s42.png"
    )


def test_gate_policy_states_that_renting_needs_a_capacity_cause():
    from core.application.services.character_turnaround_tournament_service import (
        CharacterTurnaroundTournamentService,
    )

    comparison = CharacterTurnaroundTournamentService._compare(
        [
            {
                "variant_id": "a",
                "flagged_views": [],
                "flagged_view_count": 0,
                "views": [{"metrics": {"palette_distance": 0.01}}],
                "checkpoint_size_bytes": 10,
            },
            {
                "variant_id": "b",
                "flagged_views": ["BACK"],
                "flagged_view_count": 1,
                "views": [{"metrics": {"palette_distance": 0.05}}],
                "checkpoint_size_bytes": 99,
            },
        ],
        ("BACK",),
    )

    assert comparison["verdict"] == "LOCAL_SUFFICIENT"
    assert comparison["recommended_variant"] == "a"
    assert "GPU will not fix it" in comparison["gate_policy"]
