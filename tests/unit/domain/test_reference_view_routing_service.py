from core.domain.services.reference_view_routing_service import (
    ReferenceViewRoutingService,
)
from core.domain.value_objects.character_identity import ReferenceView


def test_reference_router_maps_camera_language_to_ordered_views():
    assert ReferenceViewRoutingService.preferred_views("face close-up")[0] is (
        ReferenceView.FACE_CLOSEUP
    )
    assert ReferenceViewRoutingService.preferred_views("left profile")[0] is (
        ReferenceView.PROFILE_LEFT
    )
    assert ReferenceViewRoutingService.preferred_views("right-side profile")[0] is (
        ReferenceView.PROFILE_RIGHT
    )
    assert ReferenceViewRoutingService.preferred_views("rear view")[0] is (
        ReferenceView.BACK
    )
    assert ReferenceViewRoutingService.preferred_views("full body wide")[0] is (
        ReferenceView.FULL_BODY
    )


def test_reference_router_uses_stable_three_quarter_fallback():
    assert ReferenceViewRoutingService.preferred_views("dutch angle")[0] is (
        ReferenceView.THREE_QUARTER_LEFT
    )
