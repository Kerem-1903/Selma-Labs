"""The narrow, user-facing golden path for the anime pilot."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from core.application.services.episode_director_service import EpisodeDirectorService
from core.application.services.screenplay_normalization_service import (
    ScreenplayNormalizationService,
)
from core.domain.exceptions import PreProductionValidationError


@dataclass(frozen=True)
class PilotCheckResult:
    """A deterministic readiness report for the first pilot gate."""

    status: str
    pilot_id: str
    title: str
    fps: int
    scene_count: int
    shot_count: int
    duration_seconds: float
    characters: tuple[str, ...]
    locations: tuple[str, ...]
    checks: dict[str, bool]
    failures: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "status": self.status,
            "pilot_id": self.pilot_id,
            "title": self.title,
            "fps": self.fps,
            "scene_count": self.scene_count,
            "shot_count": self.shot_count,
            "duration_seconds": self.duration_seconds,
            "characters": list(self.characters),
            "locations": list(self.locations),
            "checks": dict(self.checks),
            "failures": list(self.failures),
            "next_step": (
                "episode plan / animatic"
                if self.status == "READY"
                else "revise pilot screenplay"
            ),
        }


class PilotGoldenPathService:
    """Keep the first product path small and explicit before GPU work begins."""

    PILOT_ID = "kirik-kayit-pilot-v1"
    DEFAULT_TITLE = "Kırık Kayıt — Pilot"
    FPS = 24
    MIN_SHOTS = 6
    MAX_SHOTS = 10
    MIN_SECONDS = 30.0
    MAX_SECONDS = 60.0
    REQUIRED_CHARACTERS = frozenset({"akira", "kaito"})
    _SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")

    DEFAULT_FOUNTAIN = """Title: Kırık Kayıt — Pilot
Episode: 1

INT. SESSIZ SİNYAL ODASI - NIGHT

AKIRA
The signal is inside the old relay, not in the city network.

KAITO
Then someone wanted it found, but only after the district went quiet.

AKIRA
Keep the door closed. If the receiver wakes, every camera will see us.

KAITO
I can hold the line for one minute. After that, we leave together.

AKIRA
Look at the waveform. That pulse is a recorded voice, not interference.

KAITO
Your voice?

AKIRA
No. It is mine from tomorrow, warning us not to trust the clean copy.

KAITO
Then we take the evidence and burn the route behind us.
"""

    def initialize(
        self,
        output: str | Path,
        *,
        pilot_id: str = PILOT_ID,
        title: str = DEFAULT_TITLE,
    ) -> Path:
        """Write the human-editable Fountain pilot brief without starting production."""
        safe_id = self._safe_id(pilot_id)
        target = Path(output)
        if target.suffix.casefold() != ".fountain":
            raise ValueError("Pilot screenplay output must use the .fountain extension.")
        target.parent.mkdir(parents=True, exist_ok=True)
        content = self.DEFAULT_FOUNTAIN.replace(
            "Title: Kırık Kayıt — Pilot", f"Title: {title.strip() or self.DEFAULT_TITLE}"
        )
        target.write_text(content, encoding="utf-8")
        # Parse immediately so an edited implementation cannot create an invalid
        # starter artifact while still reporting success.
        self.check_text(content, pilot_id=safe_id, title=title)
        return target

    def check_file(self, input_path: str | Path) -> PilotCheckResult:
        path = Path(input_path)
        if path.suffix.casefold() != ".fountain":
            raise ValueError("Pilot input must be a .fountain screenplay.")
        return self.check_text(
            path.read_text(encoding="utf-8"),
            pilot_id=path.stem,
            title=self.DEFAULT_TITLE,
        )

    def check_text(
        self,
        text: str,
        *,
        pilot_id: str = PILOT_ID,
        title: str = DEFAULT_TITLE,
    ) -> PilotCheckResult:
        safe_id = self._safe_id(pilot_id)
        script = ScreenplayNormalizationService().from_fountain(
            text,
            script_id=safe_id,
            title=title,
        )
        plan = EpisodeDirectorService().plan_episode(script)
        characters = tuple(
            sorted(
                {
                    character.strip().casefold()
                    for scene in script.scenes
                    for character in scene.characters
                    if character.strip()
                }
            )
        )
        locations = tuple(
            sorted({scene.location.strip().casefold() for scene in script.scenes})
        )
        shot_count = sum(len(scene.shots) for scene in plan.scenes)
        duration_seconds = plan.total_duration_seconds
        checks = {
            "fps_24": plan.fps == self.FPS,
            "one_location": len(locations) == 1,
            "akira_present": "akira" in characters,
            "kaito_present": "kaito" in characters,
            "no_unapproved_characters": set(characters) <= self.REQUIRED_CHARACTERS,
            "shot_count_6_to_10": self.MIN_SHOTS <= shot_count <= self.MAX_SHOTS,
            "duration_30_to_60_seconds": self.MIN_SECONDS <= duration_seconds <= self.MAX_SECONDS,
        }
        failures = tuple(name for name, passed in checks.items() if not passed)
        return PilotCheckResult(
            status="READY" if not failures else "BLOCKED",
            pilot_id=safe_id,
            title=script.title,
            fps=plan.fps,
            scene_count=len(script.scenes),
            shot_count=shot_count,
            duration_seconds=duration_seconds,
            characters=characters,
            locations=locations,
            checks=checks,
            failures=failures,
        )

    @classmethod
    def _safe_id(cls, value: str) -> str:
        normalized = str(value).strip()
        if not cls._SAFE_ID.fullmatch(normalized):
            raise PreProductionValidationError(
                "Pilot id must be a portable storage-safe identifier."
            )
        return normalized.casefold()
