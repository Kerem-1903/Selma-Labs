from __future__ import annotations

import hashlib
import io
import json
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image, ImageDraw

from core.application.services.structured_mark_validation_service import (
    StructuredMarkValidationService,
)
from core.domain.entities.character_bible import CharacterBible
from core.domain.entities.character_golden_set import (
    CharacterGoldenSet,
    GoldenCandidateResult,
    GoldenScenario,
    GoldenTestCase,
    default_akira_golden_cases,
)
from core.domain.entities.direction_bible import VisualStyleBible
from core.domain.exceptions import GoldenSetValidationError
from core.domain.ports.head_region_port import HeadRegionPort
from core.domain.ports.storage_port import StoragePort
from core.domain.value_objects.character_identity import ReferenceView
from core.domain.value_objects.head_region import HeadRegion
from infrastructure.providers.vision.guarded_golden_set_evaluator import (
    GuardedGoldenSetEvaluator,
)
from infrastructure.providers.vision.insightface_head_region_provider import (
    InsightFaceHeadRegionProvider,
)

HEAD = (100.0, 40.0, 200.0, 260.0)  # root = (173, 64.2)
APPROVED_ANCHOR = (
    Path(__file__).parents[1]
    / "assets"
    / "characters"
    / "akira"
    / "identity_lock"
    / "v2"
    / "akira-canonical-anchor-v2.png"
)
IDENTITY_LOCK = APPROVED_ANCHOR.with_name("identity-lock.json")


class _FakeHead(HeadRegionPort):
    def __init__(self, region):
        self._region = region

    async def detect(self, image_bytes):
        return self._region


class _FakeStorage(StoragePort):
    def __init__(self, data):
        self._data = data

    async def load(self, key):
        return self._data

    async def save(self, key, data, content_type):
        return None

    async def save_stream(self, key, chunks, content_type):
        return None

    async def exists(self, key):
        return True

    def upload_file(self, file_stream, destination_path, content_type):
        return destination_path

    def download_file(self, source_path, local_destination):
        return True

    def delete_file(self, file_path):
        return True


class _PassHuman:
    async def evaluate(self, *, character, style, test_case, storage_key):
        return GoldenCandidateResult(
            scenario=test_case.scenario,
            storage_key=storage_key,
            identity_score=0.95,
            style_score=0.90,
            anatomy_score=0.90,
            human_approved=True,
        )


def _img(root_x, root_y=64, collateral_red=False):
    img = Image.new("RGB", (300, 300), (20, 20, 20))
    d = ImageDraw.Draw(img)
    if root_x is not None:
        d.polygon(
            [
                (root_x - 4, root_y),
                (root_x + 4, root_y),
                (root_x + 2, root_y + 80),
                (root_x - 2, root_y + 80),
            ],
            fill=(192, 72, 56),
        )
    if collateral_red:
        d.rectangle([80, 270, 220, 295], fill=(192, 72, 56))
    b = io.BytesIO()
    img.save(b, format="PNG")
    return b.getvalue()


def _guard(data, head):
    return GuardedGoldenSetEvaluator(
        human_evaluator=_PassHuman(),
        storage=_FakeStorage(data),
        head_region_provider=_FakeHead(head),
        mark_validator=StructuredMarkValidationService(),
    )


def _tc(critical=True):
    return GoldenTestCase(
        scenario=GoldenScenario.FACE_FRONT,
        prompt="front face",
        seed=1,
        required_views=(ReferenceView.FACE_CLOSEUP,),
        critical=critical,
    )


def _style():
    return VisualStyleBible(
        id="s",
        name="s",
        version=1,
        palette=("b",),
        line_language="l",
        shading_language="s",
        camera_language="c",
    )


@pytest.mark.asyncio
async def test_correct_streak_passes():
    result = await _guard(_img(173), HeadRegion(bbox=HEAD, source="fake")).evaluate(
        character=CharacterBible.akira(),
        style=_style(),
        test_case=_tc(),
        storage_key="g.png",
    )
    assert result.marker_gate_passed is True
    assert result.structured_mark_reports[0].passed is True


@pytest.mark.asyncio
async def test_wrong_side_blocks():
    result = await _guard(_img(125), HeadRegion(bbox=HEAD, source="fake")).evaluate(
        character=CharacterBible.akira(),
        style=_style(),
        test_case=_tc(),
        storage_key="g.png",
    )
    assert result.marker_gate_passed is False and result.passed is False


@pytest.mark.asyncio
async def test_collateral_red_outside_head_ignored():
    result = await _guard(
        _img(173, collateral_red=True), HeadRegion(bbox=HEAD, source="fake")
    ).evaluate(
        character=CharacterBible.akira(),
        style=_style(),
        test_case=_tc(),
        storage_key="g.png",
    )
    assert result.marker_gate_passed is True
    assert result.structured_mark_reports[0].detected_count == 1


@pytest.mark.asyncio
async def test_no_head_fails_closed():
    with pytest.raises(GoldenSetValidationError):
        await _guard(_img(173), None).evaluate(
            character=CharacterBible.akira(),
            style=_style(),
            test_case=_tc(),
            storage_key="g.png",
        )


@pytest.mark.asyncio
async def test_anchor_distance_is_a_gate():
    # head (100..300), root=(216,53.2); draw streak far away at x=120
    head = (100.0, 40.0, 300.0, 260.0)
    result = await _guard(_img(120), HeadRegion(bbox=head, source="fake")).evaluate(
        character=CharacterBible.akira(),
        style=_style(),
        test_case=_tc(),
        storage_key="g.png",
    )
    assert result.marker_gate_passed is False
    assert ("anchor_distance", False) in result.structured_mark_reports[0].checks


def test_legacy_record_without_marker_gate_migrates_to_false():
    d = {
        "scenario": "FACE_FRONT",
        "storage_key": "g.png",
        "identity_score": 0.95,
        "style_score": 0.9,
        "anatomy_score": 0.9,
        "human_approved": True,
        "notes": "",
    }
    payload = {
        "id": "x",
        "character_id": "akira",
        "model_id": "m",
        "model_revision": "r",
        "results": [d],
        "created_at": "2026-01-01T00:00:00+00:00",
        "approved_by": None,
        "locked_at": None,
    }
    gs = CharacterGoldenSet.from_dict(payload)
    assert gs.results[0].marker_gate_passed is False


@pytest.mark.asyncio
async def test_unreliable_wide_shot_skips_marker_detection():
    test_case = replace(_tc(), marker_validation_required=False)
    result = await _guard(_img(173), None).evaluate(
        character=CharacterBible.akira(),
        style=_style(),
        test_case=test_case,
        storage_key="g.png",
    )

    assert result.marker_gate_passed is True
    assert result.structured_mark_reports == ()


@pytest.mark.asyncio
async def test_character_without_structured_marks_skips_marker_detection():
    character = CharacterBible.akira()
    character.identity_constraints.structured_marks.clear()
    result = await _guard(_img(173), None).evaluate(
        character=character,
        style=_style(),
        test_case=_tc(),
        storage_key="g.png",
    )

    assert result.marker_gate_passed is True
    assert result.structured_mark_reports == ()


@pytest.mark.asyncio
async def test_approved_akira_v2_anchor_passes_the_real_marker_gate():
    data = APPROVED_ANCHOR.read_bytes()
    calibrated_head = (
        318.43206787109375,
        171.85008697509767,
        663.5477905273438,
        609.806640625,
    )

    result = await _guard(
        data, HeadRegion(bbox=calibrated_head, source="approved-anchor-fixture")
    ).evaluate(
        character=CharacterBible.akira(),
        style=_style(),
        test_case=_tc(),
        storage_key="akira-canonical-anchor-v2.png",
    )

    assert result.marker_gate_passed is True
    assert result.structured_mark_reports[0].detected_count == 1


def test_akira_v2_identity_lock_hash_and_calibration_cannot_drift():
    lock = json.loads(IDENTITY_LOCK.read_text(encoding="utf-8"))
    mark = CharacterBible.akira().identity_constraints.structured_marks[0]

    assert lock["status"] == "LOCKED"
    assert lock["master_reference"]["sha256"] == hashlib.sha256(
        APPROVED_ANCHOR.read_bytes()
    ).hexdigest()
    assert lock["structured_mark_calibration"] == {
        "color_hex": mark.color_hex,
        "color_tolerance_delta_e": mark.color_tolerance_delta_e,
        "viewer_side": mark.viewer_side,
        "count": mark.count,
        "anchor": {
            "region": mark.anchor.region,
            "x_center": mark.anchor.x_center,
            "y_root": mark.anchor.y_root,
            "extent": mark.anchor.extent,
        },
    }
    assert lock["training_policy"]["dataset_approved"] is False


def test_akira_defaults_lock_critical_scenarios_and_action_poses():
    cases = {case.scenario: case for case in default_akira_golden_cases()}

    assert {scenario for scenario, case in cases.items() if case.critical} == {
        GoldenScenario.FACE_FRONT,
        GoldenScenario.PROFILE_LEFT,
        GoldenScenario.KATANA_GRIP,
        GoldenScenario.DETERMINED_EXPRESSION,
    }
    assert cases[GoldenScenario.RUNNING].pose_reference_key.endswith(
        "akira-running-openpose-v1.png"
    )
    assert cases[GoldenScenario.KATANA_GRIP].pose_reference_key.endswith(
        "akira-katana-ready-openpose-v1.png"
    )
    assert "raising one open hand" in cases[GoldenScenario.DETERMINED_EXPRESSION].prompt


@pytest.mark.asyncio
async def test_insightface_provider_uses_bgr_largest_face_and_clamped_roi():
    class _FaceApp:
        def get(self, image):
            assert image[0, 0].tolist() == [30, 20, 10]
            return [
                SimpleNamespace(bbox=(2.0, 2.0, 5.0, 5.0)),
                SimpleNamespace(bbox=(7.0, 2.0, 12.0, 9.0)),
            ]

    image = Image.new("RGB", (12, 10), (10, 20, 30))
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    provider = InsightFaceHeadRegionProvider()
    provider._app = _FaceApp()

    region = await provider.detect(buffer.getvalue())

    assert region is not None
    assert region.bbox[2] == 12.0
    assert region.bbox[3] == 9.0
