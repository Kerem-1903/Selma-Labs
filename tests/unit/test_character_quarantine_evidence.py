from __future__ import annotations

import asyncio
import json
from pathlib import Path

from core.application.services.character_design_service import CharacterDesignService
from core.domain.value_objects.character_creation_brief import CharacterCreationBrief
from core.domain.value_objects.character_view_qc import (
    CharacterViewObservation,
    CharacterViewQcReport,
)
from infrastructure.providers.keyframe.fake_keyframe_generation_provider import (
    FakeKeyframeGenerationProvider,
)
from infrastructure.storage.local_fs_storage import LocalFsStorage


class RejectOnceGate:
    def __init__(self) -> None:
        self.calls = 0

    async def evaluate_design_candidate(self, *, image_bytes, seed, signature_marks=(), face_priority=False):
        del image_bytes, signature_marks, face_priority
        self.calls += 1
        rejected = self.calls == 1
        return CharacterViewQcReport(
            view="DESIGN_CANDIDATE",
            seed=seed,
            passed=not rejected,
            reasons=("person_count_2", "head_outside_frame") if rejected else (),
            observation=CharacterViewObservation(
                person_count=2 if rejected else 1,
                face_count=1,
                head_inside_frame=not rejected,
                feet_inside_frame=not rejected,
                orientation="front",
                confidence=0.8,
                provider="test-detector",
                person_bboxes=((0.1, 0.0, 0.5, 0.9), (0.5, 0.1, 0.9, 0.9)) if rejected else ((0.1, 0.1, 0.9, 0.9),),
            ),
            framing_metrics={},
            checks={"exactly_one_person": not rejected},
        )


def test_rejected_design_quarantine_preserves_forensic_evidence(tmp_path):
    brief = CharacterCreationBrief.from_dict({
        "schema_version": 1,
        "name": "Forensic Kaito",
        "concept": "A courier",
        "gender_presentation": "masculine adult man",
        "hair": "short black hair",
        "outfit": "charcoal jacket",
    })
    storage = LocalFsStorage(str(tmp_path))
    provider = FakeKeyframeGenerationProvider()
    service = CharacterDesignService(provider, storage, quality_gate=RejectOnceGate(), max_view_attempts=2)

    asyncio.run(service.generate_candidates(brief, count=1, run_id="forensic"))

    reports = list((tmp_path / "characters/forensic-kaito/designs").rglob("quarantine/*.json"))
    assert len(reports) == 1
    payload = json.loads(reports[0].read_text(encoding="utf-8"))
    assert payload["brief_hash"] == brief.content_hash
    assert payload["brief"]["name"] == brief.name
    assert payload["prompt"]
    assert payload["request"]["seed"] == payload["seed"]
    assert payload["state_reason_codes"] == payload["reasons"]
    assert payload["person_bboxes"] == [[0.1, 0.0, 0.5, 0.9], [0.5, 0.1, 0.9, 0.9]]
    assert (reports[0].with_suffix(".png")).is_file()
