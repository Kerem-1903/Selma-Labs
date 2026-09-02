"""Ten-shot character consistency contract used before production images."""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from enum import Enum
from pathlib import PurePosixPath
from typing import Any

from core.domain.exceptions import GoldenSetValidationError
from core.domain.value_objects.character_identity import ReferenceView


class GoldenScenario(str, Enum):
    FACE_FRONT = "FACE_FRONT"
    PROFILE_LEFT = "PROFILE_LEFT"
    FULL_BODY = "FULL_BODY"
    RUNNING = "RUNNING"
    KATANA_GRIP = "KATANA_GRIP"
    TWO_CHARACTER_DIALOGUE = "TWO_CHARACTER_DIALOGUE"
    RAIN_ROOFTOP = "RAIN_ROOFTOP"
    IMPACT_ACTION = "IMPACT_ACTION"
    WIDE_STREET = "WIDE_STREET"
    DETERMINED_EXPRESSION = "DETERMINED_EXPRESSION"


@dataclass(frozen=True)
class GoldenTestCase:
    scenario: GoldenScenario
    prompt: str
    seed: int
    required_views: tuple[ReferenceView, ...]

    def __post_init__(self) -> None:
        if not self.prompt.strip() or self.seed < 0 or not self.required_views:
            raise GoldenSetValidationError("Golden test case is incomplete.")


@dataclass(frozen=True)
class GoldenCandidateResult:
    scenario: GoldenScenario
    storage_key: str
    identity_score: float
    style_score: float
    anatomy_score: float
    human_approved: bool
    notes: str = ""

    def __post_init__(self) -> None:
        path = PurePosixPath(self.storage_key.replace("\\", "/"))
        if (
            not self.storage_key.strip()
            or path.is_absolute()
            or any(part in {"", ".", ".."} for part in path.parts)
            or re.match(r"^[A-Za-z]:", self.storage_key)
        ):
            raise GoldenSetValidationError(
                "Golden candidate requires a portable storage key."
            )
        if any(
            not 0.0 <= score <= 1.0
            for score in (self.identity_score, self.style_score, self.anatomy_score)
        ):
            raise GoldenSetValidationError(
                "Golden candidate scores must be between 0 and 1."
            )

    @property
    def passed(self) -> bool:
        return (
            self.identity_score >= 0.90
            and self.style_score >= 0.85
            and self.anatomy_score >= 0.85
            and self.human_approved
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "scenario": self.scenario.value,
            "storage_key": self.storage_key,
            "identity_score": self.identity_score,
            "style_score": self.style_score,
            "anatomy_score": self.anatomy_score,
            "human_approved": self.human_approved,
            "notes": self.notes,
        }


@dataclass(frozen=True)
class CharacterGoldenSet:
    id: str
    character_id: str
    model_id: str
    model_revision: str
    results: tuple[GoldenCandidateResult, ...]
    created_at: datetime
    locked_at: datetime | None = None
    approved_by: str | None = None

    @classmethod
    def create(
        cls,
        *,
        character_id: str,
        model_id: str,
        model_revision: str,
        results: tuple[GoldenCandidateResult, ...],
    ) -> CharacterGoldenSet:
        expected = set(GoldenScenario)
        actual = [result.scenario for result in results]
        if set(actual) != expected or len(actual) != len(expected):
            raise GoldenSetValidationError(
                "Golden Set must contain every required scenario exactly once."
            )
        if (
            not character_id.strip()
            or not model_id.strip()
            or not model_revision.strip()
        ):
            raise GoldenSetValidationError("Golden Set model identity is incomplete.")
        return cls(
            str(uuid.uuid4()),
            character_id.strip(),
            model_id.strip(),
            model_revision.strip(),
            tuple(results),
            datetime.now(timezone.utc),
        )

    @property
    def passed(self) -> bool:
        return all(result.passed for result in self.results)

    @property
    def locked(self) -> bool:
        return self.locked_at is not None

    def lock(self, approved_by: str) -> CharacterGoldenSet:
        if not self.passed:
            raise GoldenSetValidationError("A failing Golden Set cannot be locked.")
        if not approved_by.strip():
            raise GoldenSetValidationError("Golden Set approver must not be empty.")
        return replace(
            self, approved_by=approved_by.strip(), locked_at=datetime.now(timezone.utc)
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "character_id": self.character_id,
            "model_id": self.model_id,
            "model_revision": self.model_revision,
            "results": [result.to_dict() for result in self.results],
            "created_at": self.created_at.isoformat(),
            "approved_by": self.approved_by,
            "locked_at": self.locked_at.isoformat() if self.locked_at else None,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CharacterGoldenSet:
        return cls(
            id=str(data["id"]),
            character_id=str(data["character_id"]),
            model_id=str(data["model_id"]),
            model_revision=str(data["model_revision"]),
            results=tuple(
                GoldenCandidateResult(
                    scenario=GoldenScenario(str(item["scenario"])),
                    storage_key=str(item["storage_key"]),
                    identity_score=float(item["identity_score"]),
                    style_score=float(item["style_score"]),
                    anatomy_score=float(item["anatomy_score"]),
                    human_approved=bool(item["human_approved"]),
                    notes=str(item.get("notes", "")),
                )
                for item in data["results"]
            ),
            created_at=datetime.fromisoformat(str(data["created_at"])),
            locked_at=(
                datetime.fromisoformat(str(data["locked_at"]))
                if data.get("locked_at")
                else None
            ),
            approved_by=str(data["approved_by"]) if data.get("approved_by") else None,
        )


def default_akira_golden_cases() -> tuple[GoldenTestCase, ...]:
    descriptions = (
        (
            GoldenScenario.FACE_FRONT,
            "masterpiece, best quality, anime screencap, solo, symmetrical front-facing head-and-shoulders portrait, entire head visible, neutral restrained expression, plain light background",
            ReferenceView.FACE_CLOSEUP,
        ),
        (
            GoldenScenario.PROFILE_LEFT,
            "masterpiece, best quality, anime screencap, solo, head-and-shoulders portrait, strict left-facing side profile, entire head and both shoulders visible, plain light background",
            ReferenceView.PROFILE_LEFT,
        ),
        (
            GoldenScenario.FULL_BODY,
            "masterpiece, best quality, anime character sheet, solo, full body, head-to-toe visible, centered standing turnaround pose, both boots visible, plain light background",
            ReferenceView.FRONT,
        ),
        (
            GoldenScenario.RUNNING,
            "masterpiece, best quality, cinematic anime action frame, solo, full body running from left to right, head-to-toe visible, strong readable sprint silhouette, arms and legs separated, urban street background",
            ReferenceView.THREE_QUARTER_LEFT,
        ),
        (
            GoldenScenario.KATANA_GRIP,
            "masterpiece, best quality, cinematic anime action frame, solo, medium full shot, exactly one katana held with both hands, both hands fully visible on one hilt, correct grip anatomy, guarded combat stance",
            ReferenceView.THREE_QUARTER_LEFT,
        ),
        (
            GoldenScenario.TWO_CHARACTER_DIALOGUE,
            "masterpiece, best quality, anime dialogue scene, medium two-shot, Akira on the left speaking with one adult male doctor on the right, both faces visible, clear eyelines, hospital room background",
            ReferenceView.FACE_CLOSEUP,
        ),
        (
            GoldenScenario.RAIN_ROOFTOP,
            "masterpiece, best quality, cinematic anime frame, medium-wide shot, Akira standing on a rainy night rooftop, complete upper body and hands visible, city skyline, controlled cool rim light, visible rain",
            ReferenceView.THREE_QUARTER_LEFT,
        ),
        (
            GoldenScenario.IMPACT_ACTION,
            "masterpiece, best quality, dynamic anime action frame, full body Akira delivering a single katana strike, exactly one katana, readable impact pose, strong silhouette, motion lines, ruined street background",
            ReferenceView.FRONT,
        ),
        (
            GoldenScenario.WIDE_STREET,
            "masterpiece, best quality, cinematic anime establishing shot, very wide old market street perspective, full body Akira small in frame walking away from camera, buildings and street dominate the composition, rainy evening",
            ReferenceView.BACK,
        ),
        (
            GoldenScenario.DETERMINED_EXPRESSION,
            "masterpiece, best quality, anime screencap, solo, head-and-shoulders close-up, entire head visible, restrained determined expression, amber eyes focused forward, subtle dramatic shadow",
            ReferenceView.FACE_CLOSEUP,
        ),
    )
    return tuple(
        GoldenTestCase(scenario, prompt, 190300 + index, (view,))
        for index, (scenario, prompt, view) in enumerate(descriptions)
    )
