from __future__ import annotations

import math
import re

from core.domain.entities.character_bible import CharacterBible
from core.domain.entities.character_state import CharacterState
from core.domain.entities.episode_script import EpisodeScript, EpisodeScriptStatus
from core.domain.entities.shot_animation import ShotPlan
from core.domain.exceptions import StoryApprovalError


class ScriptBreakdownService:
    """Turn dialogue/action lines into deterministic, unapproved anime shots."""

    _SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
    _DIALOGUE = re.compile(r"^([A-ZÇĞİÖŞÜ][A-ZÇĞİÖŞÜ0-9 _-]{1,39}):\s*(.+)$")
    _SCENE = re.compile(r"^(?:SCENE\s*:|INT\.|EXT\.)\s*(.+)$", re.IGNORECASE)

    def __init__(self, character_bible: CharacterBible | None = None) -> None:
        self._bible = character_bible or CharacterBible.akira()
        if not self._bible.trigger_prompt:
            raise ValueError("Script breakdown requires a character trigger prompt.")

    def parse_script(self, script_text: str, script_id: str) -> list[ShotPlan]:
        if not script_text.strip():
            raise ValueError("Script text must not be empty.")
        if not self._SAFE_ID.fullmatch(script_id):
            raise ValueError("script_id must be a storage-safe identifier.")
        scene_number = 1
        scene_id = f"{script_id}-scene-{scene_number:03d}"
        shots: list[ShotPlan] = []
        negative_prompt = ", ".join(self._bible.style_profile.negative_prompts)
        identity_prompt = ", ".join(self._bible.prompt_fragments())

        for source_line, raw_line in enumerate(script_text.splitlines(), start=1):
            line = " ".join(raw_line.strip().split())
            if not line or line.startswith("#"):
                continue
            scene_match = self._SCENE.match(line)
            if scene_match:
                scene_number += 1 if shots else 0
                scene_id = f"{script_id}-scene-{scene_number:03d}"
                continue

            dialogue_match = self._DIALOGUE.match(line)
            dialogue = dialogue_match.group(2).strip() if dialogue_match else ""
            speaker = dialogue_match.group(1).strip().casefold() if dialogue_match else ""
            if dialogue_match and speaker == self._bible.character_id:
                visual_action = f"speaking with restrained natural facial motion: {dialogue}"
                line_type = "dialogue"
            elif dialogue_match:
                visual_action = f"reaction shot while listening to off-screen dialogue: {dialogue}"
                line_type = "offscreen_dialogue"
            else:
                visual_action = line
                line_type = "action"

            ordinal = len(shots) + 1
            words = len((dialogue or line).split())
            duration = self._duration_seconds(words, dialogue=bool(dialogue_match))
            shots.append(
                ShotPlan(
                    id=f"{script_id}-shot-{ordinal:03d}",
                    script_id=script_id,
                    scene_plan_id=scene_id,
                    prompt=f"{identity_prompt}, {visual_action}",
                    negative_prompt=negative_prompt,
                    duration_seconds=duration,
                    character_state=CharacterState(
                        character_id=self._bible.character_id,
                        active_outfit_id=(
                            self._bible.outfit_catalog[0].id
                            if self._bible.outfit_catalog
                            else "akira-default"
                        ),
                        injuries=[],
                        held_objects=[],
                    ),
                    dialogue=dialogue,
                    keyframe_approved=False,
                    metadata={"source_line": source_line, "line_type": line_type},
                )
            )
        if not shots:
            raise ValueError("Script did not contain any executable dialogue or action lines.")
        return shots

    def parse_episode(self, script: EpisodeScript) -> list[ShotPlan]:
        """Break down only a reviewed and explicitly human-approved screenplay."""
        if script.status is not EpisodeScriptStatus.LOCKED:
            raise StoryApprovalError(
                "Script breakdown requires a human-approved locked episode script."
            )
        lines: list[str] = []
        for scene in script.scenes:
            lines.append(f"SCENE: {scene.location}")
            lines.append(scene.summary)
            lines.extend(f"{line.speaker.upper()}: {line.text}" for line in scene.dialogue)
        return self.parse_script("\n".join(lines), script.id)

    @staticmethod
    def _duration_seconds(word_count: int, *, dialogue: bool) -> float:
        if dialogue:
            return float(max(2, min(8, math.ceil(word_count / 2.5))))
        return float(max(2, min(6, math.ceil(word_count / 4))))
