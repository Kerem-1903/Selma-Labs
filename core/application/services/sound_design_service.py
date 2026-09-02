import logging
import random
from typing import Optional
from core.domain.entities.timeline import Timeline
from core.domain.value_objects.timeline_sfx import TimelineSfx
from core.domain.entities.script import Script

logger = logging.getLogger(__name__)

class SoundDesignService:
    """
    Automatically analyzes the scene breaks and script content to inject
    sound effects (SFX) like swooshes and impacts into the timeline.
    """

    def __init__(self, sfx_library_path: str = "assets/sfx"):
        self.sfx_library_path = sfx_library_path

    def inject_sfx(self, timeline: Timeline, script: Optional[Script] = None) -> Timeline:
        logger.info(f"Applying Auto Sound Design to timeline {timeline.id}")
        sfx_tracks = []

        # Simple heuristic: add a 'whoosh' at every scene transition
        # Add an 'impact' if the scene narration contains strong keywords

        if not timeline.clips:
            return timeline

        impact_keywords = ["boom", "sudden", "discover", "reveal", "secret", "explosion", "magic"]

        for i, clip in enumerate(timeline.clips):
            scene = clip.scene

            # Transition whoosh (except first scene)
            if i > 0:
                sfx_tracks.append(
                    TimelineSfx(
                        sfx_type="whoosh",
                        start_time=scene.start_time,
                        volume=0.4,
                        asset_path=f"{self.sfx_library_path}/whoosh.mp3"
                    )
                )

            # Impact detection based on text
            text = scene.narration.lower()
            if any(k in text for k in impact_keywords):
                # Place impact 0.5s after scene starts
                impact_time = min(scene.start_time + 0.5, scene.end_time)
                sfx_tracks.append(
                    TimelineSfx(
                        sfx_type="impact",
                        start_time=impact_time,
                        volume=0.7,
                        asset_path=f"{self.sfx_library_path}/impact.mp3"
                    )
                )

        logger.info(f"Injected {len(sfx_tracks)} SFX tracks into timeline.")

        # Create a new timeline with the added tracks
        return Timeline.create(
            asset_match_plan_id=timeline.asset_match_plan_id,
            clips=timeline.clips,
            sfx_tracks=sfx_tracks
        )
