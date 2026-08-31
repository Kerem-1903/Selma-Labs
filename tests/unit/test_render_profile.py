from core.domain.value_objects.render_profile import RenderProfile


def test_render_profiles_map_to_increasing_real_cost_settings():
    draft = RenderProfile.DRAFT.settings
    balanced = RenderProfile.BALANCED.settings
    final = RenderProfile.FINAL.settings

    assert draft.width < balanced.width < final.width
    assert draft.height < balanced.height < final.height
    assert draft.fps < balanced.fps < final.fps
    assert draft.sampling_steps < balanced.sampling_steps < final.sampling_steps
