from __future__ import annotations

import json
from pathlib import Path
from typing import get_args

import pytest

from config.provider_registry import (
    get_keyframe_generation_provider,
    load_keyframe_provider_profile,
    resolve_keyframe_provider_name,
)
from config.settings import Settings
from core.application.services.model_lock_service import load_model_lock
from core.domain.exceptions import PreProductionValidationError
from core.domain.value_objects.generation_capability import (
    SUPPORTED_KEYFRAME_PROVIDERS,
    GenerationCapability,
    KeyframeProviderProfile,
)
from infrastructure.providers.keyframe.comfyui_flux2_edit_provider import (
    ComfyUIFlux2EditProvider,
)
from infrastructure.providers.keyframe.comfyui_keyframe_provider import (
    ComfyUIKeyframeProvider,
)
from infrastructure.providers.keyframe.fake_keyframe_generation_provider import (
    FakeKeyframeGenerationProvider,
)

ROOT = Path(__file__).parents[2]
PROFILE_PATH = ROOT / "config" / "keyframe_provider_profile.json"


class MemoryStorage:
    async def save(self, key, data, content_type):
        raise NotImplementedError

    async def load(self, key):
        raise NotImplementedError

    async def exists(self, key):
        return False


def _settings(provider: str, profile: str | None = None) -> Settings:
    return Settings(
        _env_file=None,
        keyframe_generation_provider=provider,
        keyframe_provider_profile_path=(
            str(PROFILE_PATH) if profile is None else profile
        ),
    )


def test_shipped_profile_only_refines_the_turnaround_capability():
    profile = load_keyframe_provider_profile(PROFILE_PATH)

    assert profile.schema_version == 1
    assert profile.default_provider == ""
    assert profile.capabilities == {
        GenerationCapability.CHARACTER_TURNAROUND.value: "comfyui-flux2-edit"
    }


def test_supported_providers_match_the_settings_literal():
    literal = get_args(
        Settings.model_fields["keyframe_generation_provider"].annotation
    )

    assert set(literal) == set(SUPPORTED_KEYFRAME_PROVIDERS)


def test_turnaround_can_move_to_flux_while_storyboard_stays_on_the_pose_dialect():
    settings = _settings("comfyui")

    assert (
        resolve_keyframe_provider_name(
            settings, GenerationCapability.CHARACTER_TURNAROUND
        )
        == "comfyui-flux2-edit"
    )
    assert (
        resolve_keyframe_provider_name(
            settings, GenerationCapability.STORYBOARD_KEYFRAME
        )
        == "comfyui"
    )
    assert (
        resolve_keyframe_provider_name(settings, GenerationCapability.CHARACTER_DESIGN)
        == "comfyui"
    )


def test_an_override_can_never_switch_on_gpu_work():
    settings = _settings("fake")

    for capability in GenerationCapability:
        assert resolve_keyframe_provider_name(settings, capability) == "fake"


def test_explicit_global_selection_still_wins(monkeypatch):
    settings = _settings("comfyui-flux2-edit")

    for capability in GenerationCapability:
        assert (
            resolve_keyframe_provider_name(settings, capability)
            == "comfyui-flux2-edit"
        )


def test_legacy_call_without_a_capability_is_unchanged():
    assert resolve_keyframe_provider_name(_settings("comfyui"), None) == "comfyui"
    assert resolve_keyframe_provider_name(_settings("fake"), None) == "fake"


def test_a_missing_profile_file_means_no_overrides(tmp_path):
    profile = load_keyframe_provider_profile(tmp_path / "absent.json")

    assert profile.capabilities == {}
    assert (
        resolve_keyframe_provider_name(
            _settings("comfyui", str(tmp_path / "absent.json")),
            GenerationCapability.CHARACTER_TURNAROUND,
        )
        == "comfyui"
    )


def test_a_malformed_profile_raises_instead_of_silently_falling_back(tmp_path):
    broken = tmp_path / "broken.json"
    broken.write_text("{not json", encoding="utf-8")

    with pytest.raises(ValueError, match="not readable JSON"):
        load_keyframe_provider_profile(broken)


def test_profile_rejects_unknown_capabilities_and_providers(tmp_path):
    unknown_capability = tmp_path / "cap.json"
    unknown_capability.write_text(
        json.dumps(
            {"schema_version": 1, "capabilities": {"character.voice": "comfyui"}}
        ),
        encoding="utf-8",
    )
    with pytest.raises(PreProductionValidationError, match="Unknown generation capability"):
        load_keyframe_provider_profile(unknown_capability)

    unknown_provider = tmp_path / "prov.json"
    unknown_provider.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "capabilities": {"character.turnaround": "midjourney"},
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(PreProductionValidationError, match="Unknown keyframe provider"):
        load_keyframe_provider_profile(unknown_provider)

    with pytest.raises(PreProductionValidationError, match="schema_version"):
        KeyframeProviderProfile.from_dict({"schema_version": 2, "capabilities": {}})


def test_profile_falls_back_to_its_own_default_before_the_global_setting():
    profile = KeyframeProviderProfile.from_dict(
        {"schema_version": 1, "default_provider": "comfyui", "capabilities": {}}
    )

    assert (
        profile.provider_for(GenerationCapability.CHARACTER_DESIGN, fallback="fake")
        == "comfyui"
    )


def test_capability_resolution_reaches_concrete_providers():
    storage = MemoryStorage()
    turnaround = get_keyframe_generation_provider(
        _settings("comfyui"),
        capability=GenerationCapability.CHARACTER_TURNAROUND,
        storage=storage,
    )
    storyboard = get_keyframe_generation_provider(
        _settings("comfyui"),
        capability=GenerationCapability.STORYBOARD_KEYFRAME,
        storage=storage,
    )
    offline = get_keyframe_generation_provider(
        _settings("fake"), capability=GenerationCapability.CHARACTER_TURNAROUND
    )

    assert isinstance(turnaround, ComfyUIFlux2EditProvider)
    assert isinstance(storyboard, ComfyUIKeyframeProvider)
    assert not isinstance(storyboard, ComfyUIFlux2EditProvider)
    assert isinstance(offline, FakeKeyframeGenerationProvider)


def test_only_the_edit_dialect_declares_an_edit_contract():
    edit_provider = ComfyUIFlux2EditProvider(
        api_url="http://127.0.0.1:8188",
        workflow_path=ROOT / "assets" / "comfyui_flux2_klein_edit_workflow.json",
        storage=MemoryStorage(),
        model_lock=load_model_lock(ROOT / "models-flux2.lock.json"),
    )
    pose_provider = ComfyUIKeyframeProvider(
        api_url="http://127.0.0.1:8188",
        workflow_path=ROOT / "assets" / "comfyui_keyframe_workflow.json",
        storage=MemoryStorage(),
    )

    assert edit_provider.edit_contract == "source-led-delta-edit-v1"
    assert pose_provider.edit_contract == ""


def test_the_shipped_flux_lock_hashes_are_real():
    lock = load_model_lock(ROOT / "models-flux2.lock.json")

    for role in ("diffusion_model", "text_encoder", "vae"):
        entry = lock.entry(role)
        assert len(entry.sha256) == 64
        assert entry.sha256 != "0" * 64
        assert entry.size_bytes > 0
