"""
SubtitleTrack entity.

The result of splitting a ScenePlan's per-scene narration into readable,
timed on-screen caption cues -- a new, parallel branch off ScenePlan
(Sprint 4's output), independent of AssetMatchPlan/Timeline/RenderedVideo.
Plain dataclass, no framework dependency, same pattern as every prior
entity in this codebase.

References only ``scene_plan_id`` (its one direct parent), same ancestry
convention AssetMatchPlan/Timeline/RenderedVideo already established -- a
consumer that needs the full chain follows
SubtitleTrack -> ScenePlan -> Script/VoiceTrack rather than this entity
duplicating ancestor ids it doesn't itself depend on.

Deliberately does NOT reference Timeline or RenderedVideo, even though in
practice a SubtitleTrack is usually delivered *alongside* a specific
RenderedVideo. SubtitleTrack's actual computational input is ScenePlan --
it can be generated the moment Sprint 4 finishes, with no dependency on
whether asset matching, timeline creation, or rendering ever happen at
all. Coupling this entity's identity to a sibling branch it does not
depend on would repeat the same mistake AssetMatchPlan's own docstring
already rejected for script_id/voice_track_id. Where a SubtitleTrack's
exported files are stored *alongside* a specific RenderedVideo is a
composition-root/storage-key naming concern (see scripts/render_video.py's
``--subtitle`` flag and scripts/generate_subtitles.py's
``--rendered-video-id`` flag), not a domain-model concern -- this entity
never needs to know a RenderedVideo id exists.

**Deliberately exposes only domain data -- no ``to_srt()``/``to_vtt()``
methods live here**, unlike the ``to_dict()`` convention every prior
entity in this codebase carries for JSON export. This is a real deviation
from that convention, not an oversight, and it deserves the same scrutiny
given to any deviation:

``to_dict()`` exports this entity's own data in its own terms (a plain
Python dict) -- it doesn't encode this entity's knowledge of a *foreign*
text syntax invented by someone else (the SubtitleRip/WebVTT specs).
SRT and WebVTT are serialization formats with their own timecode
punctuation, header conventions, and (in WebVTT's case) an entire cue
settings mini-language -- concerns a domain entity has no business
knowing about, the same way Script does not know it will eventually be
handed to an LLM API as a JSON payload. Formatting logic for those two
external syntaxes lives in ``SubtitleFormatter``
(``core/application/services/subtitle_formatter.py``), a pure,
dependency-free application-layer class -- keeping SubtitleTrack itself
format-agnostic, exactly as domain entities are required to remain.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field as dataclass_field
from datetime import datetime, timezone
from typing import Optional

from core.domain.value_objects.subtitle_cue import SubtitleCue


@dataclass(frozen=True)
class SubtitleTrack:
    id: str
    scene_plan_id: Optional[str]
    cues: list[SubtitleCue]
    total_duration_seconds: float
    created_at: datetime = dataclass_field(default_factory=lambda: datetime.now(timezone.utc))

    @staticmethod
    def create(
        *,
        scene_plan_id: Optional[str],
        cues: list[SubtitleCue],
    ) -> "SubtitleTrack":
        total_duration_seconds = (
            max(cue.end_time for cue in cues) if cues else 0.0
        )
        return SubtitleTrack(
            id=str(uuid.uuid4()),
            scene_plan_id=scene_plan_id,
            cues=cues,
            total_duration_seconds=total_duration_seconds,
            created_at=datetime.now(timezone.utc),
        )

    def to_dict(self) -> dict:
        """Export a plain-dict shape for CLI/JSON output. Mirrors
        Timeline.to_dict()/AssetMatchPlan.to_dict(). Not a caption-file
        format -- see this module's docstring for why SRT/VTT formatting
        lives in SubtitleFormatter instead."""
        return {
            "id": self.id,
            "scene_plan_id": self.scene_plan_id,
            "total_duration_seconds": self.total_duration_seconds,
            "created_at": self.created_at.isoformat(),
            "cues": [
                {
                    "index": cue.index,
                    "scene_index": cue.scene_index,
                    "start_time": cue.start_time,
                    "end_time": cue.end_time,
                    "text": cue.text,
                }
                for cue in self.cues
            ],
        }
