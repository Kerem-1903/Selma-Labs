"""Fast screenplay-to-visual-plan orchestration for the internal anime tool."""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from core.application.services.canon_validation_service import normalize_canon_name
from core.domain.entities.direction_bible import NonCastVoice
from core.domain.entities.episode_script import EpisodeScript
from core.domain.entities.location_bible import LocationBible
from core.domain.exceptions import PreProductionValidationError, ProviderError, ScenePlanningError
from core.domain.ports.episode_director_decision_port import EpisodeDirectorDecisionPort
from core.domain.value_objects.background_production import (
    BackgroundCandidatePack,
    BackgroundProductionPlan,
)
from core.domain.value_objects.character_pose_pack import (
    POSE_PACK_POSE_IDS,
    CharacterPosePackManifest,
)
from core.domain.value_objects.episode_director_decision import (
    EpisodeSceneDecision,
)
from core.domain.value_objects.episode_director_plan import (
    DirectorBackgroundRequirement,
    DirectorCharacterRequirement,
    DirectorScene,
    DirectorShot,
    EpisodeDirectorPlan,
    EpisodeTimelineClip,
)


@dataclass(frozen=True)
class _DirectorInputScene:
    scene_id: str
    title: str
    location_id: str
    summary: str
    characters: tuple[str, ...]
    dialogue: tuple[tuple[str, str], ...]
    time_of_day: str = "day"
    weather: str = "clear"


class EpisodeDirectorService:
    """Turn an episode screenplay into an executable 24 FPS visual plan.

    The rule director is intentionally deterministic: it makes useful camera,
    pose, background and timing decisions without requiring Ollama. A later
    provider can replace the decision layer while keeping this plan contract.
    """

    _SCENE_RE = re.compile(r"^(?:SCENE\s*:\s*|(?:INT\.|EXT\.)\s*)(.+)$", re.I)
    _DIALOGUE_RE = re.compile(r"^([\wÇĞİÖŞÜçğıöşü][\wÇĞİÖŞÜçğıöşü .'-]{0,63}):\s*(.+)$")
    _SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")

    def plan(
        self,
        screenplay: EpisodeScript | str,
        **kwargs: Any,
    ) -> EpisodeDirectorPlan:
        """Plan either a structured EpisodeScript or raw screenplay text."""
        if isinstance(screenplay, EpisodeScript):
            return self.plan_episode(screenplay, **kwargs)
        return self.plan_text(str(screenplay), **kwargs)

    async def plan_with_provider(
        self,
        screenplay: EpisodeScript | str,
        provider: EpisodeDirectorDecisionPort,
        **kwargs: Any,
    ) -> EpisodeDirectorPlan:
        """Use a structured provider when it returns a traceable decision set.

        Asset resolution, pose validity and 24 FPS timing remain deterministic
        and local. A provider outage or malformed response falls back to the
        rules director rather than making offline planning unusable.
        """
        if isinstance(screenplay, EpisodeScript):
            provider_input = self._structured_decision_input(screenplay)
            expected_ids = tuple(scene.id for scene in screenplay.scenes)
        else:
            text = str(screenplay)
            parsed = self._parse_text(text, kwargs.get("episode_id", "episode-001"), kwargs.get("locations", ()))
            provider_input = self._text_decision_input(text, parsed)
            expected_ids = tuple(scene.scene_id for scene in parsed)
        try:
            decision = await provider.decide(provider_input)
            decision_by_id = {item.scene_id: item for item in decision.decisions}
            if set(decision_by_id) != set(expected_ids):
                raise ScenePlanningError("Episode Director provider did not return exactly one decision per scene.")
            kwargs["decisions"] = tuple(decision_by_id[scene_id] for scene_id in expected_ids)
            kwargs["decision_mode"] = "LLM"
            kwargs["decision_provider"] = provider.provider_identity
            return self.plan(screenplay, **kwargs)
        except (ProviderError, ScenePlanningError, PreProductionValidationError) as exc:
            kwargs.pop("decisions", None)
            kwargs["decision_mode"] = "RULE_FALLBACK"
            kwargs["decision_provider"] = "rules:episode-director-v1"
            plan = self.plan(screenplay, **kwargs)
            return self._with_warning(plan, f"Director provider unavailable; deterministic fallback used: {exc}")

    @staticmethod
    def _with_warning(plan: EpisodeDirectorPlan, warning: str) -> EpisodeDirectorPlan:
        return EpisodeDirectorPlan(
            schema_version=plan.schema_version,
            episode_id=plan.episode_id,
            title=plan.title,
            decision_mode=plan.decision_mode,
            provider=plan.provider,
            fps=plan.fps,
            total_duration_seconds=plan.total_duration_seconds,
            scenes=plan.scenes,
            character_requirements=plan.character_requirements,
            background_requirements=plan.background_requirements,
            timeline=plan.timeline,
            warnings=(*plan.warnings, warning),
            metadata=plan.metadata,
        )

    @staticmethod
    def _structured_decision_input(script: EpisodeScript) -> str:
        return "\n\n".join(
            f"SCENE_ID: {scene.id}\nTITLE: {scene.title}\nLOCATION: {scene.location}\nSUMMARY: {scene.summary}\n"
            + "\n".join(f"{line.speaker}: {line.text}" for line in scene.dialogue)
            for scene in script.scenes
        )

    @staticmethod
    def _text_decision_input(text: str, scenes: Sequence[_DirectorInputScene]) -> str:
        return text + "\n\nDETERMINISTIC SCENE IDS:\n" + "\n".join(
            f"{scene.scene_id}: {scene.title}" for scene in scenes
        )

    def plan_episode(
        self,
        script: EpisodeScript,
        *,
        character_bibles: Sequence[Any] = (),
        locations: Sequence[LocationBible] = (),
        pose_packs: Mapping[str, CharacterPosePackManifest] | None = None,
        background_packs: Mapping[str, BackgroundCandidatePack] | None = None,
        episode_id: str | None = None,
        non_cast_voices: Sequence[NonCastVoice] = (),
        decisions: Sequence[EpisodeSceneDecision] = (),
        decision_mode: str = "RULE_FALLBACK",
        decision_provider: str | None = None,
    ) -> EpisodeDirectorPlan:
        scenes = tuple(
            _DirectorInputScene(
                scene_id=scene.id,
                title=scene.title,
                location_id=self._location_id(scene.location, locations),
                summary=scene.summary,
                characters=tuple(scene.characters),
                dialogue=tuple((line.speaker, line.text) for line in scene.dialogue),
            )
            for scene in script.scenes
        )
        return self._build_plan(
            scenes,
            episode_id=episode_id or self._safe_id(script.id, "episode"),
            title=script.title,
            character_bibles=character_bibles,
            locations=locations,
            pose_packs=pose_packs or {},
            background_packs=background_packs or {},
            non_cast_voices=non_cast_voices,
            provider=decision_provider or "rules:episode-director-v1",
            decisions=decisions,
            decision_mode=decision_mode,
        )

    def plan_text(
        self,
        script_text: str,
        *,
        episode_id: str = "episode-001",
        title: str = "Untitled episode",
        character_bibles: Sequence[Any] = (),
        locations: Sequence[LocationBible] = (),
        pose_packs: Mapping[str, CharacterPosePackManifest] | None = None,
        background_packs: Mapping[str, BackgroundCandidatePack] | None = None,
        non_cast_voices: Sequence[NonCastVoice] = (),
        decisions: Sequence[EpisodeSceneDecision] = (),
        decision_mode: str = "RULE_FALLBACK",
        decision_provider: str | None = None,
    ) -> EpisodeDirectorPlan:
        scenes = self._parse_text(script_text, episode_id, locations)
        return self._build_plan(
            scenes,
            episode_id=self._safe_id(episode_id, "episode_id"),
            title=title.strip() or "Untitled episode",
            character_bibles=character_bibles,
            locations=locations,
            pose_packs=pose_packs or {},
            background_packs=background_packs or {},
            non_cast_voices=non_cast_voices,
            provider=decision_provider or "rules:episode-director-v1",
            decisions=decisions,
            decision_mode=decision_mode,
        )

    def _build_plan(
        self,
        scenes: Sequence[_DirectorInputScene],
        *,
        episode_id: str,
        title: str,
        character_bibles: Sequence[Any],
        locations: Sequence[LocationBible],
        pose_packs: Mapping[str, CharacterPosePackManifest],
        background_packs: Mapping[str, BackgroundCandidatePack],
        non_cast_voices: Sequence[NonCastVoice] = (),
        provider: str,
        decisions: Sequence[EpisodeSceneDecision] = (),
        decision_mode: str = "RULE_FALLBACK",
    ) -> EpisodeDirectorPlan:
        if not scenes:
            raise PreProductionValidationError("Episode screenplay contains no scenes.")

        voice_names = self._non_cast_voice_names(non_cast_voices)
        character_lookup = self._character_lookup(character_bibles)
        location_lookup = {location.location_id.casefold(): location for location in locations}
        background_plans: dict[str, BackgroundProductionPlan] = {}
        character_names: set[str] = set()
        for scene in scenes:
            if not scene.characters:
                raise PreProductionValidationError(
                    f"Scene '{scene.scene_id}' needs at least one character."
                )
            for character in scene.characters:
                if normalize_canon_name(character) in voice_names:
                    continue
                character_names.add(self._character_id(character, character_lookup))
            if scene.location_id.casefold() in location_lookup:
                background_plans[scene.location_id] = self._background_plan(
                    location_lookup[scene.location_id.casefold()]
                )
        character_requirements = tuple(
            DirectorCharacterRequirement(
                character_id=character_id,
                pose_ids=POSE_PACK_POSE_IDS,
                status="READY" if self._pack_ready(character_id, pose_packs) else "PLANNED",
                pose_pack_manifest_ref=self._pack_manifest_ref(character_id, pose_packs),
                pose_asset_refs=self._pack_asset_refs(character_id, pose_packs),
            )
            for character_id in sorted(character_names)
        )

        cursor_frame = 0
        director_scenes: list[DirectorScene] = []
        background_requirements: dict[str, DirectorBackgroundRequirement] = {}
        timeline: list[EpisodeTimelineClip] = []
        warnings: list[str] = []
        previous_location = ""
        shot_number = 0
        decision_by_scene_id = {
            decision.scene_id: decision
            for decision in decisions
        }
        for scene_index, scene in enumerate(scenes, start=1):
            scene_shots: list[DirectorShot] = []
            decision = decision_by_scene_id.get(scene.scene_id)
            lines = self._visual_lines(scene)
            story_beat = decision.story_beat if decision else self._story_beat(scene_index, len(scenes), scene.summary)
            scene_purpose = decision.purpose if decision else self._purpose(story_beat, scene.summary)
            emotional_intent = decision.emotional_intent if decision else self._emotion(story_beat, scene.summary)
            for shot_index, line in enumerate(lines, start=1):
                character_id = self._character_id(self._visual_character(scene, shot_index), character_lookup)
                preferred_pose = decision.pose_preferences.get(character_id) if decision else None
                pose_id = preferred_pose or self._pose_for(story_beat, shot_index, len(lines))
                preferred_size = decision.shot_sizes[shot_index - 1] if decision and shot_index <= len(decision.shot_sizes) else None
                shot_size = preferred_size or self._shot_size(shot_index, len(lines), bool(line[1]))
                duration_frames = self._duration_frames(line[1] or line[0], bool(line[1]))
                duration_seconds = duration_frames / 24
                start_frame = cursor_frame
                end_frame = start_frame + duration_frames
                location = location_lookup.get(scene.location_id.casefold())
                background_id, background_prompt, background_asset_ref, recipe_id = self._select_background(
                    scene, shot_size, location, background_plans, background_packs
                )
                shot_number += 1
                shot_id = f"{episode_id}-shot-{shot_number:03d}"
                purpose = scene_purpose
                action = (decision.character_actions.get(character_id, line[0]) if decision else line[0])
                dialogue = line[1]
                angle = self._camera_angle(pose_id)
                movement = self._camera_movement(story_beat, shot_index)
                effects = self._effects(f"{scene.summary} {action} {dialogue}")
                shot = DirectorShot(
                    shot_id=shot_id,
                    scene_id=scene.scene_id,
                    purpose=purpose,
                    story_beat=story_beat,
                    source_script_lines=(action,) if not dialogue else (f"{line[2]}: {dialogue}",),
                    dialogue=dialogue,
                    duration_seconds=duration_seconds,
                    character_id=character_id,
                    character_pose_id=pose_id,
                    pose_reason=self._pose_reason(pose_id, story_beat, dialogue),
                    character_action=action,
                    expression=(emotional_intent if decision else self._expression(story_beat, dialogue)),
                    shot_size=shot_size,
                    camera_angle=angle,
                    camera_movement=movement,
                    background_recipe_id=background_id,
                    background_prompt=(
                        f"{background_prompt}; {decision.background_direction}"
                        if decision and decision.background_direction
                        else background_prompt
                    ),
                    foreground_effects=effects,
                    transition_in="dissolve" if previous_location and previous_location != scene.location_id else "cut",
                    transition_out="cut",
                    start_ms=start_frame * 1000 // 24,
                    end_ms=end_frame * 1000 // 24,
                    reasoning=(
                        f"{story_beat} beat: {purpose}; {pose_id} keeps the character readable "
                        f"while {shot_size} framing serves the scene."
                    ),
                    character_pose_asset_ref=self._pose_asset_ref(character_id, pose_id, pose_packs),
                    background_asset_ref=background_asset_ref,
                    start_frame=start_frame,
                    duration_frames=duration_frames,
                )
                scene_shots.append(shot)
                timeline.extend(self._clips_for_shot(shot, background_id))
                if background_id not in background_requirements:
                    background_requirements[background_id] = self._background_requirement(
                        scene, shot, recipe_id, background_prompt, location,
                        asset_ref=background_asset_ref,
                    )
                cursor_frame = end_frame
            director_scenes.append(
                DirectorScene(
                    scene_id=scene.scene_id,
                    title=scene.title,
                    location_id=scene.location_id,
                    scene_purpose=scene_purpose,
                    story_beat=story_beat,
                    emotional_intent=emotional_intent,
                    time_of_day=scene.time_of_day,
                    weather=scene.weather,
                    continuity_notes=(
                        (f"Hold continuity at {scene.location_id}.",)
                        if previous_location == scene.location_id
                        else (f"Establish {scene.location_id} before character action.",)
                    ),
                    shots=tuple(scene_shots),
                )
            )
            previous_location = scene.location_id

        if any(not pack.complete or pack.status != "PENDING_HUMAN_REVIEW" for pack in pose_packs.values()):
            warnings.append("One or more supplied pose packs are incomplete or unapproved; pose assets remain provisional.")
        if not locations:
            warnings.append("No Location Bible was supplied; background prompts are provisional recipes.")
        if not pose_packs:
            warnings.append("No pose-pack manifests were supplied; all three pose assets remain provisional references.")

        if not background_packs:
            warnings.append("No background candidate packs were supplied; background assets remain provisional recipes.")

        total_seconds = cursor_frame / 24
        return EpisodeDirectorPlan(
            schema_version=1,
            episode_id=episode_id,
            title=title,
            decision_mode=decision_mode,
            provider=provider,
            fps=24,
            total_duration_seconds=total_seconds,
            scenes=tuple(director_scenes),
            character_requirements=character_requirements,
            background_requirements=tuple(background_requirements.values()),
            timeline=tuple(timeline),
            warnings=tuple(warnings),
            metadata={"source": "screenplay", "timeline_policy": "24fps_contiguous"},
        )

    @classmethod
    def _parse_text(
        cls, script_text: str, episode_id: str, locations: Sequence[LocationBible]
    ) -> tuple[_DirectorInputScene, ...]:
        if not script_text.strip():
            raise PreProductionValidationError("Episode screenplay must not be empty.")
        scenes: list[_DirectorInputScene] = []
        current_location = "unknown-location"
        current_title = "Opening"
        current_lines: list[tuple[str, str, str]] = []
        scene_number = 0

        def flush() -> None:
            nonlocal current_lines, scene_number
            if not current_lines:
                return
            scene_number += 1
            summary = " ".join(item[0] for item in current_lines).strip()
            characters = tuple(dict.fromkeys(item[1] for item in current_lines if item[1]))
            if not characters:
                characters = ("protagonist",)
            scenes.append(
                _DirectorInputScene(
                    scene_id=f"{cls._safe_id(episode_id, 'episode')}-scene-{scene_number:03d}",
                    title=current_title,
                    location_id=cls._location_id(current_location, locations),
                    summary=summary,
                    characters=characters,
                    dialogue=tuple((speaker, text) for _action, speaker, text in current_lines if text),
                )
            )
            current_lines = []

        for raw in script_text.splitlines():
            line = " ".join(raw.strip().split())
            if not line or line.startswith("#"):
                continue
            match = cls._SCENE_RE.match(line)
            if match:
                flush()
                current_location = match.group(1).strip()
                current_title = current_location
                continue
            dialogue = cls._DIALOGUE_RE.match(line)
            if dialogue:
                speaker, text = dialogue.group(1).strip(), dialogue.group(2).strip()
                current_lines.append((f"{speaker} speaks", speaker, text))
            else:
                current_lines.append((line, "", ""))
        flush()
        return tuple(scenes)

    @staticmethod
    def _visual_lines(scene: _DirectorInputScene) -> list[tuple[str, str, str]]:
        # Dialogue gets its own close-up; actions remain their own visual beat.
        action_lines = [item for item in scene.dialogue]
        if not action_lines:
            return [(scene.summary, "", "")]
        result: list[tuple[str, str, str]] = [(scene.summary, "", "")]
        result.extend((f"{speaker} delivers the line", text, speaker) for speaker, text in action_lines)
        return result

    @staticmethod
    def _visual_character(scene: _DirectorInputScene, index: int) -> str:
        return scene.characters[(index - 1) % len(scene.characters)]

    @staticmethod
    def _character_lookup(bibles: Sequence[Any]) -> dict[str, str]:
        lookup: dict[str, str] = {}
        for bible in bibles:
            character_id = str(getattr(bible, "character_id", "")).strip()
            if not character_id:
                continue
            lookup[character_id.casefold()] = character_id
            narrative = getattr(bible, "narrative_profile", None)
            for name in getattr(narrative, "canonical_names", ()):
                lookup[str(name).casefold()] = character_id
        return lookup

    @classmethod
    def _character_id(cls, name: str, lookup: Mapping[str, str]) -> str:
        value = str(name).strip()
        return lookup.get(value.casefold(), cls._safe_id(value, "character"))

    @staticmethod
    def _non_cast_voice_names(voices: Sequence[NonCastVoice]) -> frozenset[str]:
        """Ambient voices canon accepts but never casts, so never renders."""
        return frozenset(
            normalize_canon_name(value) for voice in voices for value in voice.names()
        )

    @staticmethod
    def _location_id(value: str, locations: Sequence[LocationBible]) -> str:
        normalized = str(value).strip()
        for location in locations:
            if normalized.casefold() in {location.location_id.casefold(), location.name.casefold()}:
                return location.location_id
        return EpisodeDirectorService._safe_id(normalized or "unknown-location", "location")

    @staticmethod
    def _background_plan(location: LocationBible) -> BackgroundProductionPlan:
        from core.application.services.background_factory_service import BackgroundFactoryService

        return BackgroundFactoryService.plan(location)

    @staticmethod
    def _select_background(
        scene: _DirectorInputScene,
        shot_size: str,
        location: LocationBible | None,
        plans: Mapping[str, BackgroundProductionPlan],
        packs: Mapping[str, BackgroundCandidatePack],
    ) -> tuple[str, str, str, str]:
        if location is not None and location.location_id in plans:
            scale = {"wide": "wide establishing", "medium": "medium", "close_up": "close detail", "profile": "medium", "insert": "close detail"}[shot_size]
            angle = "reverse" if shot_size == "profile" else "front"
            recipe = next(
                (item for item in plans[location.location_id].recipes if item.shot_scale == scale and item.camera_angle == angle),
                plans[location.location_id].recipes[0],
            )
            requirement_id = f"{location.location_id}-{recipe.recipe_id}"
            asset_ref = EpisodeDirectorService._background_asset_ref(location.location_id, recipe.recipe_id, packs)
            return requirement_id, recipe.prompt, asset_ref, recipe.recipe_id
        location_id = scene.location_id
        return f"{location_id}-{shot_size}", f"anime background plate, {location_id}, {shot_size} framing, character-free environment", "", shot_size

    @staticmethod
    def _background_requirement(
        scene: _DirectorInputScene,
        shot: DirectorShot,
        recipe_id: str,
        prompt: str,
        location: LocationBible | None,
        *,
        asset_ref: str = "",
    ) -> DirectorBackgroundRequirement:
        return DirectorBackgroundRequirement(
            recipe_id=recipe_id,
            location_id=scene.location_id,
            shot_scale=shot.shot_size,
            camera_angle=shot.camera_angle,
            weather=location.weather_options[0] if location and location.weather_options else scene.weather,
            time_of_day=scene.time_of_day,
            prompt=prompt,
            scene_ids=(scene.scene_id,),
            shot_ids=(shot.shot_id,),
            status="READY" if asset_ref else "PLANNED",
            asset_ref=asset_ref,
        )

    def _clips_for_shot(self, shot: DirectorShot, background_id: str) -> tuple[EpisodeTimelineClip, ...]:
        if shot.start_frame is None or shot.duration_frames is None:
            # Compatibility for plans created by older callers. New plans always
            # carry explicit frame fields from the director cursor.
            start_frame = round(shot.start_ms / 1000 * 24)
            duration_frames = round(shot.duration_seconds * 24)
        else:
            start_frame = shot.start_frame
            duration_frames = shot.duration_frames
        clips = [
            EpisodeTimelineClip("SCRIPT", f"{shot.shot_id}-script", shot.shot_id, start_frame, duration_frames, shot.purpose, "script", shot.scene_id),
            EpisodeTimelineClip("CHARACTER", f"{shot.shot_id}-character", shot.shot_id, start_frame, duration_frames, shot.character_action, "pose", shot.character_pose_asset_ref or shot.character_pose_id),
            EpisodeTimelineClip("BACKGROUND", f"{shot.shot_id}-background", shot.shot_id, start_frame, duration_frames, background_id, "background_asset" if shot.background_asset_ref else "background_recipe", shot.background_asset_ref or background_id),
            EpisodeTimelineClip("CAMERA", f"{shot.shot_id}-camera", shot.shot_id, start_frame, duration_frames, shot.camera_movement, "camera", shot.camera_angle),
        ]
        if shot.dialogue:
            clips.append(EpisodeTimelineClip("DIALOGUE", f"{shot.shot_id}-dialogue", shot.shot_id, start_frame, duration_frames, shot.dialogue, "dialogue", shot.character_id))
        if shot.foreground_effects:
            clips.append(EpisodeTimelineClip("EFFECTS", f"{shot.shot_id}-effects", shot.shot_id, start_frame, duration_frames, ", ".join(shot.foreground_effects), "effects", ",".join(shot.foreground_effects)))
        return tuple(clips)

    @staticmethod
    def _pack_ready(character_id: str, packs: Mapping[str, CharacterPosePackManifest]) -> bool:
        pack = EpisodeDirectorService._pose_pack(character_id, packs)
        if not pack or not pack.complete or pack.status != "PENDING_HUMAN_REVIEW":
            return False
        from core.application.services.asset_approval_service import AssetApprovalService
        return AssetApprovalService.verify_asset_set(
            pack.approval_receipt,
            asset_id=pack.character_id,
            asset_hashes=[pose.content_hash for pose in pack.poses],
            manifest_payload=pack.to_dict(),
        ) and EpisodeDirectorService._pack_asset_refs(character_id, packs).keys() == set(POSE_PACK_POSE_IDS)

    @staticmethod
    def _pose_pack(character_id: str, packs: Mapping[str, CharacterPosePackManifest]) -> CharacterPosePackManifest | None:
        return packs.get(character_id) or packs.get(character_id.casefold())

    @staticmethod
    def _pack_manifest_ref(character_id: str, packs: Mapping[str, CharacterPosePackManifest]) -> str:
        pack = EpisodeDirectorService._pose_pack(character_id, packs)
        return pack.manifest_storage_key if pack else ""

    @staticmethod
    def _pack_asset_refs(character_id: str, packs: Mapping[str, CharacterPosePackManifest]) -> dict[str, str]:
        pack = EpisodeDirectorService._pose_pack(character_id, packs)
        if not pack or pack.status != "PENDING_HUMAN_REVIEW":
            return {}
        from core.application.services.asset_approval_service import AssetApprovalService
        if not AssetApprovalService.verify_asset_set(
            pack.approval_receipt,
            asset_id=pack.character_id,
            asset_hashes=[pose.content_hash for pose in pack.poses],
            manifest_payload=pack.to_dict(),
        ):
            return {}
        return {pose.pose_id: pose.storage_key for pose in pack.poses}

    @staticmethod
    def _pose_asset_ref(character_id: str, pose_id: str, packs: Mapping[str, CharacterPosePackManifest]) -> str:
        return EpisodeDirectorService._pack_asset_refs(character_id, packs).get(pose_id, "")

    @staticmethod
    def _background_asset_ref(location_id: str, recipe_id: str, packs: Mapping[str, BackgroundCandidatePack]) -> str:
        pack = packs.get(location_id) or packs.get(location_id.casefold())
        if not pack:
            return ""
        from core.application.services.asset_approval_service import AssetApprovalService
        if not AssetApprovalService.verify_asset_set(
            pack.approval_receipt,
            asset_id=pack.location_id,
            asset_hashes=[candidate.content_hash for candidate in pack.candidates],
            manifest_payload=pack.to_dict(),
        ):
            return ""
        for candidate in pack.candidates:
            if candidate.recipe_id == recipe_id:
                return candidate.storage_key
        return ""

    @staticmethod
    def _story_beat(index: int, total: int, text: str) -> str:
        normalized = text.casefold()
        if index == 1:
            return "setup"
        if index == total:
            return "payoff"
        if any(word in normalized for word in ("reveal", "discovers", "discovers", "truth", "sırrı", "ortaya")):
            return "reveal"
        if any(word in normalized for word in ("fight", "attack", "danger", "threat", "çatış", "saldır")):
            return "conflict"
        if any(word in normalized for word in ("react", "remembers", "hatır", "shock", "şaşk")):
            return "reaction"
        return "context"

    @staticmethod
    def _pose_for(beat: str, index: int, line_count: int) -> str:
        if beat == "setup":
            return "FRONT_NEUTRAL"
        if beat in {"conflict", "reveal"}:
            return "PROFILE_LEFT"
        if beat == "reaction":
            return "FRONT_NEUTRAL"
        if beat in {"transition", "payoff"} or index == line_count:
            return "BACK_FULL_BODY"
        return "FRONT_NEUTRAL"

    @staticmethod
    def _shot_size(index: int, line_count: int, dialogue: bool) -> str:
        if dialogue:
            return "close_up"
        if index == 1:
            return "wide"
        if index == line_count:
            return "profile"
        return "medium"

    @staticmethod
    def _duration_frames(text: str, dialogue: bool) -> int:
        words = max(len(text.split()), 1)
        seconds = max(2.0, min(8.0, words / 2.5 if dialogue else words / 4.0))
        return max(48, round(seconds * 24))

    @staticmethod
    def _purpose(beat: str, summary: str) -> str:
        purposes = {
            "setup": "establish the scene geography and character objective",
            "context": "make the current action understandable",
            "conflict": "make the threat and opposing force readable",
            "reveal": "direct attention to the new information",
            "reaction": "show the character processing the consequence",
            "transition": "carry location and emotional continuity forward",
            "payoff": "land the scene's dramatic result",
        }
        return purposes.get(beat, "visualize the screenplay action") + f": {summary[:120]}"

    @staticmethod
    def _emotion(beat: str, summary: str) -> str:
        return {"setup": "curious", "context": "focused", "conflict": "tense", "reveal": "alarmed", "reaction": "uncertain", "payoff": "resolved"}.get(beat, "neutral")

    @staticmethod
    def _expression(beat: str, dialogue: str) -> str:
        return {"setup": "watchful neutral", "context": "observant", "conflict": "determined", "reveal": "shocked restraint", "reaction": "processing", "payoff": "resolved focus"}.get(beat, "restrained")

    @staticmethod
    def _pose_reason(pose: str, beat: str, dialogue: str) -> str:
        if dialogue:
            return "A readable face-oriented pose gives the spoken line priority."
        return f"{pose} is selected because the {beat} beat needs a clear silhouette and readable orientation."

    @staticmethod
    def _camera_angle(pose: str) -> str:
        return {"FRONT_NEUTRAL": "front", "PROFILE_LEFT": "left profile", "BACK_FULL_BODY": "reverse"}[pose]

    @staticmethod
    def _camera_movement(beat: str, index: int) -> str:
        if beat == "conflict":
            return "slow_push_in"
        if beat == "reveal":
            return "snap_pan_then_hold"
        if beat == "payoff":
            return "locked_hold"
        return "subtle_parallax" if index % 2 else "slow_push_in"

    @staticmethod
    def _effects(text: str) -> tuple[str, ...]:
        normalized = text.casefold()
        return tuple(effect for keyword, effect in (("rain", "rain"), ("wind", "wind"), ("signal", "memory_signal"), ("light", "flicker")) if keyword in normalized)

    @staticmethod
    def _safe_id(value: str, field_name: str) -> str:
        # Accented letters must be transliterated, never deleted. Deleting them
        # turned "SAINT ORA KLINIGI - NOROLOJI IZOLASYON ODASI" into
        # "saint-ora-kl-n-n-roloj-zolasyon-odasi": the location name is lost, and
        # two locations that differ only by their accents collapse onto one
        # storage id. Mirrors the transliteration CharacterCreationBrief uses for
        # a character id.
        folded = str(value).translate(str.maketrans("ıİ", "iI"))
        folded = (
            unicodedata.normalize("NFKD", folded)
            .encode("ascii", "ignore")
            .decode("ascii")
        )
        normalized = re.sub(r"[^A-Za-z0-9._-]+", "-", folded.strip())
        normalized = re.sub(r"-+", "-", normalized).strip("-")
        if not normalized or not EpisodeDirectorService._SAFE_ID.fullmatch(normalized):
            raise PreProductionValidationError(f"{field_name} must be a storage-safe identifier.")
        return normalized.casefold()
