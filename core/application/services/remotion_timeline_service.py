"""Translate verified editorial artifacts into a Remotion composition contract."""
from __future__ import annotations

import math
from pathlib import Path
from typing import Any, Sequence

from core.domain.value_objects.subtitle_cue import SubtitleCue
from core.domain.value_objects.visual_edit_plan import VisualEditBeat, VisualEditPlan
from core.domain.value_objects.visual_intent import VisualIntent


class RemotionTimelineService:
    """Build a deterministic, frame-accurate creative timeline for Remotion."""

    def __init__(
        self,
        *,
        fps: int = 30,
        brand_signature: str = "STRANGE THINGS",
    ) -> None:
        if fps <= 0:
            raise ValueError("Remotion timeline fps must be greater than zero.")
        if not brand_signature.strip():
            raise ValueError("Remotion brand signature must not be empty.")
        self._fps = fps
        self._brand_signature = " ".join(brand_signature.split()).strip()

    def build(
        self,
        *,
        title: str,
        cues: Sequence[SubtitleCue],
        visual_intents: Sequence[VisualIntent],
        video_clips: Sequence[str],
        visual_edit_plan: VisualEditPlan | None = None,
    ) -> dict[str, Any]:
        if not cues:
            raise ValueError("Remotion timeline requires subtitle cues.")
        if not visual_intents:
            raise ValueError("Remotion timeline requires visual intents.")
        if len(visual_intents) != len(video_clips):
            raise ValueError("Remotion scenes and selected video clips must match.")
        if visual_edit_plan is not None and len(visual_edit_plan.beats) != len(visual_intents):
            raise ValueError("Remotion visual edit beats and scenes must match.")

        duration_ms = max(
            max(cue.end_ms for cue in cues),
            max(intent.end_ms for intent in visual_intents),
        )
        duration_in_frames = max(1, math.ceil(duration_ms * self._fps / 1_000))
        scenes = [
            self._scene_to_dict(
                intent,
                video_clips[index],
                index,
                visual_edit_plan.beats[index] if visual_edit_plan is not None else None,
            )
            for index, intent in enumerate(visual_intents)
        ]
        captions = [self._cue_to_dict(cue) for cue in cues]
        brand_start_frame, brand_duration_frames = self._brand_window(
            cues, duration_in_frames
        )
        cta_start_frame = max(
            brand_start_frame + brand_duration_frames,
            duration_in_frames - round(self._fps * 1.4),
        )
        return {
            "fps": self._fps,
            "durationInFrames": duration_in_frames,
            "title": title.strip(),
            "hookText": self._hook_text(cues[0]),
            "brandSignature": self._brand_signature,
            "brandStartFrame": brand_start_frame,
            "brandDurationFrames": brand_duration_frames,
            "ctaText": self._cta_text(title, cues),
            "ctaStartFrame": cta_start_frame,
            "scenes": scenes,
            "captions": captions,
        }

    def _scene_to_dict(
        self,
        intent: VisualIntent,
        video_clip: str,
        index: int,
        edit_beat: VisualEditBeat | None = None,
    ) -> dict[str, Any]:
        start_frame = self._frame(intent.start_ms)
        end_frame = max(start_frame + 1, self._frame(intent.end_ms))
        scene = {
            "startFrame": start_frame,
            "durationFrames": end_frame - start_frame,
            "source": Path(video_clip).resolve().as_uri(),
            "motion": edit_beat.motion_type if edit_beat is not None else intent.motion_type,
            "shotType": edit_beat.shot_type if edit_beat is not None else intent.shot_type,
            "visualJob": intent.visual_job,
            "labels": list(intent.overlay_labels[:3]),
            "transition": (
                edit_beat.transition
                if edit_beat is not None
                else self._transition_for(intent, index)
            ),
            "patternInterrupt": (
                edit_beat.pattern_interrupt if edit_beat is not None else "none"
            ),
            "safeZone": (
                edit_beat.safe_zone
                if edit_beat is not None
                else "center_subject_caption_clear"
            ),
        }
        diagram_kind = self._diagram_kind(intent)
        if diagram_kind is not None:
            scene["diagramKind"] = diagram_kind
        return scene

    def _cue_to_dict(self, cue: SubtitleCue) -> dict[str, Any]:
        start_frame = self._frame(cue.start_ms)
        end_frame = max(start_frame + 1, self._frame(cue.end_ms))
        return {
            "startFrame": start_frame,
            "endFrame": end_frame,
            "words": [
                {
                    "text": word.text,
                    "startFrame": self._frame(word.start_ms),
                    "endFrame": max(
                        self._frame(word.start_ms) + 1,
                        self._frame(word.end_ms),
                    ),
                }
                for word in cue.words
            ],
        }

    def _frame(self, milliseconds: int) -> int:
        return max(0, round(milliseconds * self._fps / 1_000))

    def _brand_window(
        self,
        cues: Sequence[SubtitleCue],
        duration_in_frames: int,
    ) -> tuple[int, int]:
        signature_words = self._brand_signature.casefold().split()
        signature_phrase = " ".join(signature_words)
        for cue in cues:
            cue_text = " ".join(word.text.strip(".,!?;:").casefold() for word in cue.words)
            if signature_phrase in cue_text:
                start = self._frame(cue.start_ms)
                end = max(start + 1, self._frame(cue.end_ms))
                return start, end - start
        fallback_duration = min(math.ceil(self._fps * 0.95), duration_in_frames)
        fallback_start = min(round(self._fps * 0.9), max(0, duration_in_frames - fallback_duration))
        return fallback_start, max(1, fallback_duration)

    @staticmethod
    def _hook_text(cue: SubtitleCue) -> str:
        words = [word.text for word in cue.words]
        numeric = next(
            (
                word
                for word in words
                if any(character.isdigit() for character in word)
                or word.casefold() in {"iki", "üç", "dört", "beş", "tek"}
            ),
            None,
        )
        if numeric is not None:
            anchor_index = words.index(numeric)
            compact = words[anchor_index : anchor_index + 3]
        else:
            compact = words[:4]
        return "".join(
            "İ" if character == "i" else "I" if character == "ı" else character.upper()
            for character in " ".join(compact)
        )

    @staticmethod
    def _cta_text(title: str, cues: Sequence[SubtitleCue] = ()) -> str:
        narration = " ".join(
            word.text for cue in cues for word in cue.words
        )
        normalized = f"{title} {narration}".casefold()
        turkish_language_markers = (
            "ç", "ğ", "ı", "ö", "ş", "ü", " neden ", " nasıl ",
            " çünkü ", " için ", " bir ", " bu ",
        )
        if any(marker in f" {normalized} " for marker in turkish_language_markers):
            return "DAHA GARİBİ İÇİN TAKİP ET"
        turkish_markers = (
            "malzeme", "teknoloji", "cihaz", "polimer", "batarya", "robot",
            "neden", "nasıl", "nedir", "gelecek", "kendini", "onaran",
        )
        if any(marker in normalized for marker in turkish_markers):
            return "DAHA GARİBİ İÇİN TAKİP ET"
        product_markers = (
            "material", "technology", "device", "polymer", "battery", "robot",
            "malzeme", "teknoloji", "cihaz", "polimer", "batarya", "robot",
        )
        if any(marker in normalized for marker in product_markers):
            return "WHERE SHOULD WE USE THIS FIRST?"
        return "WHAT SURPRISED YOU MOST?"

    @staticmethod
    def _diagram_kind(intent: VisualIntent) -> str | None:
        corpus = " ".join(
            (
                intent.primary_keyword,
                intent.narration_text,
                *intent.secondary_keywords,
                *intent.overlay_labels,
            )
        ).casefold()
        self_healing_markers = (
            "self-heal", "self heal", "healing agent", "kendini onar",
            "çatlak", "yeniden bağ", "crack", "repair polymer",
        )
        if any(marker in corpus for marker in self_healing_markers):
            return "self_healing"
        return None

    @staticmethod
    def _transition_for(intent: VisualIntent, index: int) -> str:
        if index == 0:
            return "hard"
        return {
            "locate_part": "push",
            "demonstrate_mechanism": "match_zoom",
            "compare_states": "mask_reveal",
            "show_consequence": "impact_flash",
            "deliver_payoff": "mask_reveal",
        }.get(intent.visual_job, "hard")
