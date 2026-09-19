"""Capability-scoped provider selection for still-image generation.

One global ``keyframe_generation_provider`` switch cannot serve every workload.
Text-only design candidates, source-led turnaround views, pose-conditioned
keyframes and golden-set evaluation need different engines, different prompt
contracts and different reference policies. When a single switch selects all of
them, turning on a new engine for one workload silently reroutes the others --
which is exactly why the source-led FLUX.2 dialect could not become the
turnaround default.

A profile refines the globally configured engine per capability. It is a
*refinement*, never a switch: an empty profile leaves every workload on
``keyframe_generation_provider``, and the registry refuses to let an override
promote the offline ``fake`` engine into real GPU work.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from typing import Any

from core.domain.exceptions import PreProductionValidationError

#: Providers a profile may name. ``config.settings`` mirrors this list in a
#: ``Literal`` for environment validation; a test keeps the two in step.
SUPPORTED_KEYFRAME_PROVIDERS: tuple[str, ...] = (
    "fake",
    "comfyui",
    "comfyui-flux2-edit",
)


class GenerationCapability(str, Enum):
    """A distinct still-image workload, named by what it produces."""

    CHARACTER_DESIGN = "character.design"
    CHARACTER_ONBOARDING = "character.onboarding"
    CHARACTER_TURNAROUND = "character.turnaround"
    CHARACTER_POSE_PACK = "character.pose_pack"
    STORYBOARD_KEYFRAME = "storyboard.keyframe"
    GOLDEN_SET = "golden_set"


def _text(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise PreProductionValidationError(f"{field_name} must be non-empty text.")
    return value.strip()


@dataclass(frozen=True)
class KeyframeProviderProfile:
    """Per-capability provider overrides layered over the global setting."""

    schema_version: int
    capabilities: Mapping[str, str]
    default_provider: str = ""
    notes: str = ""

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise PreProductionValidationError(
                "keyframe provider profile schema_version must be 1."
            )
        default = self.default_provider.strip()
        if default and default not in SUPPORTED_KEYFRAME_PROVIDERS:
            raise PreProductionValidationError(
                f"Unknown default keyframe provider: {default!r}."
            )
        object.__setattr__(self, "default_provider", default)
        object.__setattr__(self, "notes", self.notes.strip())
        normalized: dict[str, str] = {}
        known = {item.value for item in GenerationCapability}
        for raw_capability, raw_provider in dict(self.capabilities).items():
            capability = _text(raw_capability, "capability")
            if capability not in known:
                raise PreProductionValidationError(
                    f"Unknown generation capability: {capability!r}."
                )
            provider = _text(raw_provider, f"provider for {capability}")
            if provider not in SUPPORTED_KEYFRAME_PROVIDERS:
                raise PreProductionValidationError(
                    f"Unknown keyframe provider for {capability}: {provider!r}."
                )
            normalized[capability] = provider
        object.__setattr__(self, "capabilities", normalized)

    @classmethod
    def empty(cls) -> KeyframeProviderProfile:
        return cls(schema_version=1, capabilities={})

    def provider_for(
        self, capability: GenerationCapability, *, fallback: str
    ) -> str:
        """Return the provider for one capability, or ``fallback``.

        A domain-pure lookup: whether the override is *allowed* to apply is the
        registry's decision, not the profile's.
        """
        return self.capabilities.get(capability.value) or self.default_provider or fallback

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "default_provider": self.default_provider,
            "notes": self.notes,
            "capabilities": dict(sorted(self.capabilities.items())),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> KeyframeProviderProfile:
        raw_capabilities = data.get("capabilities", {})
        if not isinstance(raw_capabilities, Mapping):
            raise PreProductionValidationError(
                "keyframe provider profile capabilities must be an object."
            )
        return cls(
            schema_version=int(data.get("schema_version", 0)),
            capabilities={str(key): str(value) for key, value in raw_capabilities.items()},
            default_provider=str(data.get("default_provider", "")),
            notes=str(data.get("notes", "")),
        )


__all__ = [
    "GenerationCapability",
    "KeyframeProviderProfile",
    "SUPPORTED_KEYFRAME_PROVIDERS",
]
