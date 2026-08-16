"""
ScenePlanningService — application-layer orchestration for scene planning.

Same division of responsibility as ScriptService/VoiceService/
VideoSearchService: the provider adapter's job is "read narration text and
produce a semantic breakdown into scenes," this service's job is "decide
whether that breakdown is usable, and compute each scene's timing." It
depends only on ScenePlanningPort — never on a concrete provider.

Timing is deliberately NOT asked of the provider. An LLM has no reliable
sense of elapsed seconds; VoiceTrack.duration_seconds is a real, measured
value (VoiceService already validates it's > 0 before a VoiceTrack ever
exists). So this service estimates each scene's start/end time by
allocating VoiceTrack.duration_seconds proportionally to each scene's share
of the total narration word count — "estimating scene timing from
narration," exactly as the sprint brief asks for, using the one number in
this pipeline that IS trustworthy (measured audio duration) rather than a
number the provider would otherwise have to guess. This also means Scene
Planning works whether or not VoiceTrack.segments (per-word timing) is
populated — today no voice provider in this codebase populates it, so
relying on it would make this service unusable right now.

Scope, per Sprint 4's brief: this service only produces a plan. It does not
search Pexels, select assets, or rank anything — that's VideoSearchService
and later sprints, composed on top of this service's output without
changing its public contract.
"""
from __future__ import annotations

import logging
import re
from collections.abc import Sequence

from core.domain.entities.scene_plan import ScenePlan
from core.domain.entities.script import Script
from core.domain.entities.voice_track import VoiceTrack
from core.domain.exceptions import ScenePlanningError
from core.domain.ports.scene_planning_port import ScenePlanningPort
from core.domain.value_objects.scene import Scene
from core.domain.value_objects.narrative_contract import NarrativeBeat
from core.domain.value_objects.selected_highlight import SelectedHighlight
from core.domain.value_objects.subtitle_cue import SubtitleCue
from core.domain.value_objects.visual_intent import VisualIntent

logger = logging.getLogger("selma.scene_planning_service")


class ScenePlanningService:
    """Plans visual scenes for a Script/VoiceTrack pair via an injected
    provider."""

    def __init__(
        self,
        provider: ScenePlanningPort,
        minimum_scenes: int = 1,
        maximum_scene_seconds: float | None = None,
        maximum_visual_intent_duration_ms: int = 2_800,
    ) -> None:
        if minimum_scenes <= 0:
            raise ValueError("minimum_scenes must be positive.")
        if maximum_scene_seconds is not None and maximum_scene_seconds <= 0:
            raise ValueError("maximum_scene_seconds must be positive.")
        if maximum_visual_intent_duration_ms <= 0:
            raise ValueError("maximum_visual_intent_duration_ms must be positive.")
        self._provider = provider
        self._minimum_scenes = minimum_scenes
        self._maximum_scene_seconds = maximum_scene_seconds
        self._maximum_visual_intent_duration_ms = maximum_visual_intent_duration_ms

    async def plan(self, script: Script, voice_track: VoiceTrack) -> ScenePlan:
        """Produce a validated, timed ScenePlan for ``script``/``voice_track``.

        Args:
            script: The Script whose narration text will be segmented.
            voice_track: The narrated VoiceTrack for ``script`` — its
                ``duration_seconds`` is the authoritative total duration
                used to compute each scene's timing.

        Raises:
            ScenePlanningError: Input was invalid (no narration text, or
                an invalid voice track duration), or the provider's output
                failed validation (empty scene list, or a scene missing
                narration/search_keywords).
            ProviderError (and subclasses): Propagated unchanged from the
                adapter for auth/timeout/connection/quota failures —
                callers need the typed subclass to decide whether to
                retry.
        """
        narration_text = (script.full_text or "").strip()
        if not narration_text:
            raise ScenePlanningError("Script has no narration text to plan scenes for.")

        if voice_track.duration_seconds <= 0:
            raise ScenePlanningError(
                f"VoiceTrack has an invalid duration_seconds: "
                f"{voice_track.duration_seconds}."
            )

        logger.info(
            "scene_planning_started",
            extra={"script_id": script.id, "voice_track_id": voice_track.audio_id},
        )

        raw_scenes = await self._provider.plan_scenes(narration_text=narration_text)

        self._validate_raw_scenes(raw_scenes)
        raw_scenes = self._ensure_visual_density(
            raw_scenes,
            voice_track.duration_seconds,
        )

        timed_scenes = self._assign_timing(raw_scenes, voice_track.duration_seconds)

        scene_plan = ScenePlan.create(
            script_id=script.id,
            voice_track_id=voice_track.audio_id,
            total_duration_seconds=voice_track.duration_seconds,
            provider_used=self._provider.provider_identity,
            scenes=timed_scenes,
        )

        logger.info(
            "scene_planning_completed",
            extra={"script_id": script.id, "scene_count": len(timed_scenes)},
        )
        return scene_plan

    def plan_visual_intents(
        self,
        highlight: SelectedHighlight,
        subtitle_cues: list[SubtitleCue],
        *,
        narrative_beats: Sequence[NarrativeBeat] = (),
        visual_anchor: str | None = None,
    ) -> list[VisualIntent]:
        """Create one provider-neutral visual brief for every karaoke cue.

        ``SelectedHighlight.score`` is currently produced by the Librosa
        energy/onset selector, so it is a useful provisional energy signal.
        When a later selector exposes a dedicated energy feature, only this
        policy method needs changing; search and vision adapters remain
        isolated behind ``VisualIntent``.

        Raises:
            ScenePlanningError: No timed captions are available to anchor a
                visual plan to the selected music hook.
        """
        if not subtitle_cues:
            raise ScenePlanningError(
                "Cannot create visual intents without subtitle cues for the hook."
            )

        mood, motion_type = self._energy_profile(highlight.confidence_score)
        editorial_beats = self._partition_visual_beats(subtitle_cues, highlight)
        intents: list[VisualIntent] = []
        beat_count = len(editorial_beats)
        for index, (start_ms, end_ms, beat_cues) in enumerate(editorial_beats):
            keywords = self._keywords_for_cues(beat_cues)
            narrative_beat = self._match_narrative_beat(
                beat_cues,
                narrative_beats,
                index,
                beat_count,
            )
            narration_text = (
                narrative_beat.text
                if narrative_beat is not None
                else " ".join(cue.text for cue in beat_cues).strip()
            )
            narrative_role = (
                narrative_beat.role
                if narrative_beat is not None
                else self._narrative_role(index, beat_count)
            )
            semantic = self._semantic_visual_spec(
                narration_text,
                narrative_role,
                visual_anchor=visual_anchor,
            )
            intents.append(
                VisualIntent(
                    primary_keyword=keywords[0],
                    mood=mood,
                    motion_type=motion_type,
                    forbidden_concepts=("text", "logo", "watermark", "face"),
                    secondary_keywords=tuple(keywords[1:3]),
                    start_ms=start_ms,
                    end_ms=end_ms,
                    narrative_role=narrative_role,
                    shot_type=self._shot_type(index),
                    narration_text=narration_text,
                    visual_job=semantic["visual_job"],
                    required_subjects=semantic["required_subjects"],
                    required_actions=semantic["required_actions"],
                    required_relations=semantic["required_relations"],
                    forbidden_dominant_subjects=semantic[
                        "forbidden_dominant_subjects"
                    ],
                    explanation_mode=semantic["explanation_mode"],
                    overlay_labels=semantic["overlay_labels"],
                    explanatory_required=semantic["explanatory_required"],
                )
            )
        if narrative_beats:
            self._validate_semantic_intents(intents)
        return intents

    @classmethod
    def _match_narrative_beat(
        cls,
        cues: list[SubtitleCue],
        narrative_beats: Sequence[NarrativeBeat],
        visual_index: int,
        visual_count: int,
    ) -> NarrativeBeat | None:
        if not narrative_beats:
            return None
        cue_tokens = cls._semantic_tokens(" ".join(cue.text for cue in cues))
        ranked = sorted(
            narrative_beats,
            key=lambda beat: len(cue_tokens & cls._semantic_tokens(beat.text)),
            reverse=True,
        )
        if ranked and cue_tokens & cls._semantic_tokens(ranked[0].text):
            return ranked[0]
        proportional_index = min(
            len(narrative_beats) - 1,
            int(visual_index * len(narrative_beats) / max(visual_count, 1)),
        )
        return narrative_beats[proportional_index]

    @classmethod
    def _semantic_visual_spec(
        cls,
        narration_text: str,
        narrative_role: str,
        *,
        visual_anchor: str | None,
    ) -> dict[str, object]:
        normalized = narration_text.casefold()
        tokens = re.findall(r"[\w']+", normalized, flags=re.UNICODE)
        anatomy_stems = (
            "kalp", "kalb", "heart", "solungaç", "gill", "organ", "damar",
            "vücut", "body", "blood", "kan", "beyin", "brain", "akciğer", "lung",
            "material", "polymer", "crack", "damage", "fracture", "malzeme",
            "polimer", "çatlak", "hasar",
        )
        mechanism_stems = (
            "pomp", "gönder", "taşı", "dolaş", "akış", "pump", "send", "flow",
            "carry", "circul", "move", "besli", "supply", "heal", "repair",
            "seal", "reconnect", "bond", "close", "onar", "iyileş", "kapat",
            "birleştir", "bağlan",
        )
        comparison_markers = ("oysa", "ancak", "fark", "while", "whereas", "versus")
        consequence_markers = (
            "böylece", "bu yüzden", "sonuç", "sayesinde", "therefore", "so ",
            "which lets", "which allows", "as a result",
        )
        anatomy_terms = tuple(
            dict.fromkeys(
                token for token in tokens if any(token.startswith(stem) for stem in anatomy_stems)
            )
        )
        action_terms = tuple(
            dict.fromkeys(
                token for token in tokens if any(token.startswith(stem) for stem in mechanism_stems)
            )
        )
        if action_terms:
            visual_job = "demonstrate_mechanism"
        elif anatomy_terms:
            visual_job = "locate_part"
        elif any(marker in normalized for marker in comparison_markers):
            visual_job = "compare_states"
        elif narrative_role == "payoff" or any(
            marker in normalized for marker in consequence_markers
        ):
            visual_job = "deliver_payoff" if narrative_role == "payoff" else "show_consequence"
        elif narrative_role == "hook":
            visual_job = "establish_subject"
        else:
            visual_job = "support_context"

        explanatory_required = bool(
            anatomy_terms
            or action_terms
            or visual_job in {"compare_states", "show_consequence"}
        )
        anchor_subject = cls._anchor_subject(visual_anchor or "")
        required_subjects = tuple(
            dict.fromkeys(
                term for term in (anchor_subject, *anatomy_terms[:2]) if term
            )
        )
        forbidden_dominant_subjects = cls._subject_conflicts(anchor_subject)
        overlay_labels = (
            (cls._overlay_label(narration_text, anatomy_terms, action_terms),)
            if explanatory_required
            else ()
        )
        return {
            "visual_job": visual_job,
            "required_subjects": required_subjects,
            "required_actions": action_terms[:3],
            "required_relations": (
                ("part-to-function",) if anatomy_terms and action_terms else
                ("count-to-part",) if anatomy_terms and cls._contains_number(normalized) else ()
            ),
            "forbidden_dominant_subjects": forbidden_dominant_subjects,
            "explanation_mode": "hybrid" if explanatory_required else "stock",
            "overlay_labels": overlay_labels,
            "explanatory_required": explanatory_required,
        }

    @classmethod
    def _validate_semantic_intents(cls, intents: Sequence[VisualIntent]) -> None:
        if not intents:
            raise ScenePlanningError("Semantic storyboard produced no visual intents.")
        for index, intent in enumerate(intents):
            if not intent.narration_text:
                raise ScenePlanningError(
                    f"Semantic visual intent {index} has no narration evidence."
                )
            if not intent.required_subjects:
                raise ScenePlanningError(
                    f"Semantic visual intent {index} has no required subject."
                )
            if intent.explanatory_required and (
                intent.explanation_mode == "stock" or not intent.overlay_labels
            ):
                raise ScenePlanningError(
                    f"Semantic visual intent {index} requires a diagram or overlay."
                )

    @staticmethod
    def _anchor_subject(text: str) -> str:
        stop_words = {
            "neden", "nasıl", "niçin", "niye", "why", "how", "what", "do",
            "does", "have", "has", "the", "bir", "bu", "şu", "var", "vardır",
            "kalbi", "kalp", "hearts", "heart", "three", "üç",
        }
        tokens = re.findall(r"[\w']+", text.casefold(), flags=re.UNICODE)
        meaningful = [
            token for token in tokens if token not in stop_words and len(token) > 3
        ]
        return max(meaningful, key=len, default="")

    @staticmethod
    def _subject_conflicts(anchor_subject: str) -> tuple[str, ...]:
        if any(stem in anchor_subject for stem in ("ahtapot", "octopus")):
            return ("ray", "stingray", "shark", "fish", "human", "diver")
        return ("unrelated dominant subject",)

    @classmethod
    def _overlay_label(
        cls,
        narration_text: str,
        anatomy_terms: tuple[str, ...],
        action_terms: tuple[str, ...],
    ) -> str:
        normalized = narration_text.casefold()
        number_map = {
            "üç": "3", "iki": "2", "bir": "1", "three": "3", "two": "2", "one": "1",
        }
        number = next((digit for word, digit in number_map.items() if word in normalized), "")
        key_terms = [*anatomy_terms[:2], *action_terms[:1]]
        label = " ".join(term.upper() for term in key_terms)
        if number and label:
            label = f"{number} {label}"
        if not label:
            words = re.findall(r"[\w']+", narration_text, flags=re.UNICODE)[:5]
            label = " ".join(words).upper()
        return label[:36].rstrip()

    @staticmethod
    def _contains_number(text: str) -> bool:
        return bool(
            re.search(r"\d", text)
            or any(word in text for word in ("bir", "iki", "üç", "one", "two", "three"))
        )

    @staticmethod
    def _semantic_tokens(text: str) -> set[str]:
        stop_words = {
            "bir", "bu", "ve", "ile", "için", "the", "and", "with", "that", "this",
        }
        return {
            token
            for token in re.findall(r"[\w']+", text.casefold(), flags=re.UNICODE)
            if len(token) > 2 and token not in stop_words
        }

    def _partition_visual_beats(
        self,
        subtitle_cues: list[SubtitleCue],
        highlight: SelectedHighlight,
    ) -> list[tuple[int, int, list[SubtitleCue]]]:
        """Map captions onto a complete, time-coded editorial rhythm.

        The opening beat is deliberately short, the first six seconds stay
        dense, and later beats are allowed slightly more breathing room. The
        windows cover the selected audio without gaps, so the renderer can use
        them as an exact edit decision list rather than inventing cut points.
        """
        ordered_cues = sorted(subtitle_cues, key=lambda cue: cue.start_ms)
        beats: list[tuple[int, int, list[SubtitleCue]]] = []
        cursor = highlight.start_ms
        index = 0
        while cursor < highlight.end_ms:
            elapsed_ms = cursor - highlight.start_ms
            if index == 0:
                maximum_duration_ms = min(
                    1_300,
                    self._maximum_visual_intent_duration_ms,
                )
            elif elapsed_ms < 6_000:
                maximum_duration_ms = min(
                    2_200,
                    self._maximum_visual_intent_duration_ms,
                )
            else:
                maximum_duration_ms = min(
                    2_600,
                    self._maximum_visual_intent_duration_ms,
                )
            end_ms = min(cursor + maximum_duration_ms, highlight.end_ms)
            if end_ms < highlight.end_ms:
                end_ms = self._snap_to_caption_boundary(
                    end_ms,
                    cursor,
                    highlight.end_ms,
                    ordered_cues,
                )
            overlapping = [
                cue
                for cue in ordered_cues
                if cue.end_ms > cursor and cue.start_ms < end_ms
            ]
            if not overlapping:
                overlapping = [
                    min(
                        ordered_cues,
                        key=lambda cue: min(
                            abs(cue.start_ms - end_ms),
                            abs(cue.end_ms - cursor),
                        ),
                    )
                ]
            beats.append((cursor, end_ms, overlapping))
            cursor = end_ms
            index += 1
        return beats

    @staticmethod
    def _snap_to_caption_boundary(
        target_ms: int,
        cursor_ms: int,
        final_end_ms: int,
        cues: Sequence[SubtitleCue],
    ) -> int:
        """Move a planned cut onto a nearby spoken phrase/word boundary."""
        boundaries = {
            boundary
            for cue in cues
            for boundary in (
                cue.start_ms,
                cue.end_ms,
                *(word.end_ms for word in cue.words),
            )
            if cursor_ms + 300 <= boundary < final_end_ms
        }
        if not boundaries:
            return target_ms
        closest = min(boundaries, key=lambda boundary: abs(boundary - target_ms))
        return closest if abs(closest - target_ms) <= 450 else target_ms

    @staticmethod
    def _narrative_role(index: int, beat_count: int) -> str:
        if index == 0:
            return "hook"
        if index == beat_count - 1:
            return "payoff"
        if index == 1:
            return "context"
        return "evidence" if index % 2 == 0 else "development"

    @staticmethod
    def _shot_type(index: int) -> str:
        shot_grammar = (
            "macro-close-up",
            "wide-establishing",
            "tracking-medium",
            "detail-insert",
            "overhead-wide",
            "low-angle-medium",
        )
        return shot_grammar[index % len(shot_grammar)]

    @staticmethod
    def _energy_profile(energy_score: float) -> tuple[str, str]:
        """Map a normalized highlight-energy score to cinematic direction."""
        if energy_score >= 0.65:
            return "energetic", "fast-paced"
        if energy_score <= 0.40:
            return "melancholic", "slow-motion"
        return "reflective", "steady"

    @staticmethod
    def _primary_keyword(cue: SubtitleCue) -> str:
        """Extract a stable, searchable keyword without leaking punctuation."""
        stop_words = {
            "a", "an", "and", "are", "but", "for", "i", "in", "is", "it",
            "of", "or", "the", "to", "we", "with", "ya", "ve", "bir", "bu",
            "da", "de", "için", "ile", "mi", "mı", "ne", "o",
        }
        tokens = re.findall(r"[\w']+", cue.text.lower(), flags=re.UNICODE)
        meaningful = [token for token in tokens if token not in stop_words]
        # Longer content words are generally safer media-search terms than
        # pronouns or conjunctions. The fallback still keeps planning total.
        return max(meaningful, key=len, default="music")

    @classmethod
    def _primary_keyword_for_cues(cls, cues: list[SubtitleCue]) -> str:
        """Choose one searchable concept from an entire editorial beat."""
        words = [word for cue in cues for word in cue.words]
        if words:
            return cls._primary_keyword(SubtitleCue.from_words(words))
        return cls._primary_keyword(cues[0])

    @classmethod
    def _keywords_for_cues(cls, cues: list[SubtitleCue]) -> list[str]:
        """Return a stable primary concept plus supporting search anchors."""
        combined_text = " ".join(cue.text for cue in cues)
        tokens = re.findall(r"[\w']+", combined_text.lower(), flags=re.UNICODE)
        stop_words = {
            "a", "an", "and", "are", "but", "for", "i", "in", "is", "it",
            "of", "or", "the", "to", "we", "with", "ya", "ve", "bir", "bu",
            "da", "de", "için", "ile", "mi", "mı", "ne", "o",
        }
        meaningful = list(dict.fromkeys(token for token in tokens if token not in stop_words))
        ranked = sorted(meaningful, key=lambda token: (-len(token), meaningful.index(token)))
        return ranked[:3] or ["music"]

    def _ensure_visual_density(
        self,
        scenes: list[Scene],
        total_duration_seconds: float,
    ) -> list[Scene]:
        expanded = list(scenes)
        while True:
            total_words = sum(max(len(scene.narration.split()), 1) for scene in expanded)
            longest_estimated_seconds = max(
                (
                    total_duration_seconds
                    * max(len(scene.narration.split()), 1)
                    / total_words
                    for scene in expanded
                ),
                default=0.0,
            )
            needs_more_scenes = len(expanded) < self._minimum_scenes
            exceeds_duration = (
                self._maximum_scene_seconds is not None
                and longest_estimated_seconds > self._maximum_scene_seconds
            )
            if not needs_more_scenes and not exceeds_duration:
                break
            candidates = [
                (len(scene.narration.split()), index, scene)
                for index, scene in enumerate(expanded)
                if len(scene.narration.split()) >= 4
            ]
            if not candidates:
                break
            _, index, scene = max(candidates)
            split = self._split_scene(scene)
            if split is None:
                break
            expanded[index : index + 1] = split
        return expanded

    @staticmethod
    def _split_scene(scene: Scene) -> list[Scene] | None:
        clauses = [
            part.strip()
            for part in re.split(
                r"(?<=[.!?])\s+|(?<=,)\s+|\s+(?=(?:then|but|while|because)\b)",
                scene.narration,
                flags=re.IGNORECASE,
            )
            if part.strip()
        ]
        if len(clauses) >= 2:
            total_words = sum(len(clause.split()) for clause in clauses)
            running_words = 0
            split_index = 1
            for position, clause in enumerate(clauses[:-1], start=1):
                running_words += len(clause.split())
                split_index = position
                if running_words >= total_words / 2:
                    break
            narration_parts = [
                " ".join(clauses[:split_index]),
                " ".join(clauses[split_index:]),
            ]
        else:
            words = scene.narration.split()
            midpoint = len(words) // 2
            if midpoint < 2 or len(words) - midpoint < 2:
                return None
            narration_parts = [" ".join(words[:midpoint]), " ".join(words[midpoint:])]

        return [
            Scene(
                index=scene.index,
                narration=narration,
                search_keywords=list(scene.search_keywords),
                detected_objects=list(scene.detected_objects),
                location=scene.location,
                mood=scene.mood,
                visual_priority=scene.visual_priority,
                visual_job=scene.visual_job,
                required_subjects=list(scene.required_subjects),
                required_actions=list(scene.required_actions),
                required_relations=list(scene.required_relations),
                forbidden_dominant_subjects=list(scene.forbidden_dominant_subjects),
                explanation_mode=scene.explanation_mode,
                overlay_labels=list(scene.overlay_labels),
                explanatory_required=scene.explanatory_required,
            )
            for narration in narration_parts
            if narration
        ]

    @staticmethod
    def _validate_raw_scenes(scenes: list[Scene]) -> None:
        if not scenes:
            raise ScenePlanningError("Provider returned no scenes for this narration.")

        for position, scene in enumerate(scenes):
            if not scene.narration or not scene.narration.strip():
                raise ScenePlanningError(
                    f"Scene at position {position} is missing narration text."
                )
            if not scene.search_keywords:
                raise ScenePlanningError(
                    f"Scene at position {position} has no search_keywords — "
                    "every scene must be searchable by a later Asset Matching step."
                )
            if scene.visual_job not in {
                "establish_subject",
                "locate_part",
                "demonstrate_mechanism",
                "compare_states",
                "show_consequence",
                "deliver_payoff",
                "support_context",
            }:
                raise ScenePlanningError(
                    f"Scene at position {position} has unsupported visual_job "
                    f"{scene.visual_job!r}."
                )
            if scene.explanation_mode not in {"stock", "overlay", "diagram", "hybrid"}:
                raise ScenePlanningError(
                    f"Scene at position {position} has unsupported explanation_mode "
                    f"{scene.explanation_mode!r}."
                )
            if scene.explanatory_required and (
                scene.explanation_mode == "stock" or not scene.overlay_labels
            ):
                raise ScenePlanningError(
                    f"Scene at position {position} requires an explanatory overlay or diagram."
                )

    @staticmethod
    def _assign_timing(scenes: list[Scene], total_duration_seconds: float) -> list[Scene]:
        # Proportional allocation by word count. Simple on purpose: this
        # service has no acoustic information (pauses, pacing) to do
        # better than "more words -> more seconds," and that's a
        # reasonable approximation until per-word timing (VoiceTrack.
        # segments) is populated by a future voice provider — see this
        # module's docstring and the README's Future Enhancements section.
        word_counts = [max(len(scene.narration.split()), 1) for scene in scenes]
        total_words = sum(word_counts)
        last_position = len(scenes) - 1

        timed_scenes = []
        cursor = 0.0
        for position, (scene, words) in enumerate(zip(scenes, word_counts)):
            start_time = cursor
            if position == last_position:
                # Snap the final scene's end exactly to the measured total
                # duration, rather than letting proportional rounding drift
                # short or long of it across many scenes.
                end_time = total_duration_seconds
            else:
                end_time = start_time + (total_duration_seconds * words / total_words)

            timed_scenes.append(
                scene.finalize(
                    index=position,
                    start_time=round(start_time, 2),
                    end_time=round(end_time, 2),
                )
            )
            cursor = end_time

        return timed_scenes
