from dataclasses import dataclass


@dataclass(frozen=True)
class TimelineSfx:
    """Represents a Sound Effect placed on the timeline."""
    sfx_type: str # e.g., 'whoosh', 'impact'
    start_time: float
    volume: float = 1.0
    asset_path: str | None = None
