from __future__ import annotations

from core.domain.value_objects.character_identity import ReferenceView


class ReferenceViewRoutingService:
    """Map provider-neutral camera language to ordered character references."""

    @staticmethod
    def preferred_views(camera_angle: str) -> tuple[ReferenceView, ...]:
        normalized = " ".join(camera_angle.casefold().replace("_", "-").split())
        if "close" in normalized or "portrait" in normalized:
            return (
                ReferenceView.FACE_CLOSEUP,
                ReferenceView.THREE_QUARTER_LEFT,
                ReferenceView.FRONT,
            )
        if "back" in normalized or "rear" in normalized:
            return (
                ReferenceView.BACK,
                ReferenceView.THREE_QUARTER_LEFT,
                ReferenceView.FRONT,
            )
        if "profile" in normalized or "side" in normalized:
            if "right" in normalized:
                return (
                    ReferenceView.PROFILE_RIGHT,
                    ReferenceView.THREE_QUARTER_RIGHT,
                    ReferenceView.PROFILE_LEFT,
                )
            return (
                ReferenceView.PROFILE_LEFT,
                ReferenceView.THREE_QUARTER_LEFT,
                ReferenceView.PROFILE_RIGHT,
            )
        if "wide" in normalized or "full" in normalized:
            return (
                ReferenceView.FULL_BODY,
                ReferenceView.FRONT,
                ReferenceView.THREE_QUARTER_LEFT,
            )
        if "front" in normalized:
            return (
                ReferenceView.FRONT,
                ReferenceView.THREE_QUARTER_LEFT,
                ReferenceView.FACE_CLOSEUP,
            )
        return (
            ReferenceView.THREE_QUARTER_LEFT,
            ReferenceView.FRONT,
            ReferenceView.FACE_CLOSEUP,
            ReferenceView.FULL_BODY,
        )
