from dataclasses import dataclass, field
from typing import Any

from core.domain.value_objects.character_identity import (
    IdentityConstraints,
    ReferenceView,
)
from core.domain.value_objects.character_narrative_profile import (
    CharacterNarrativeProfile,
)
from core.domain.value_objects.character_reference import CharacterReference
from core.domain.value_objects.outfit import Outfit
from core.domain.value_objects.style_profile import StyleProfile


@dataclass
class CharacterBible:
    character_id: str
    identity_constraints: IdentityConstraints
    style_profile: StyleProfile
    reference_pack: dict[ReferenceView, CharacterReference] = field(default_factory=dict)
    outfit_catalog: list[Outfit] = field(default_factory=list)
    narrative_profile: CharacterNarrativeProfile | None = None

    def __post_init__(self) -> None:
        if not self.character_id.strip():
            raise ValueError("CharacterBible character_id must not be empty.")
        for view, reference in self.reference_pack.items():
            if view != reference.view:
                raise ValueError("CharacterBible reference view does not match its pack key.")
            if reference.character_id != self.character_id:
                raise ValueError("CharacterBible references must belong to the same character.")
        if any(outfit.character_id != self.character_id for outfit in self.outfit_catalog):
            raise ValueError("CharacterBible outfits must belong to the same character.")

    @classmethod
    def akira(cls) -> "CharacterBible":
        """Return SELMA's canonical Akira identity without filesystem coupling."""
        return cls(
            character_id="akira",
            identity_constraints=IdentityConstraints(
                eye_color="amber",
                hair="black hair with one controlled deep-red front streak",
                facial_geometry="angular anime face, defined jaw, straight nose",
                body_proportions="athletic adult woman, consistent limb proportions",
                silhouette="cropped combat jacket, tapered combat trousers, single katana",
                trigger_prompt="akira_girl",
                immutable_marks=[
                    "single deep-red front hair streak",
                    "amber eyes",
                    "one katana only",
                ],
            ),
            style_profile=StyleProfile(
                base_style="cinematic cyberpunk anime",
                lighting_preferences=["controlled rim light", "high-contrast practical light"],
                color_palette=["charcoal", "black", "muted gray", "deep red", "amber"],
                negative_prompts=[
                    "identity drift",
                    "different face",
                    "extra person",
                    "extra limbs",
                    "extra sword",
                    "red ribbon",
                    "red energy trail",
                ],
            ),
            outfit_catalog=[
                Outfit(
                    id="akira-default",
                    character_id="akira",
                    description=(
                        "cropped charcoal combat jacket with deep-red inner lining, "
                        "black combat trousers, knee pads, and black combat boots"
                    ),
                    reference_image_keys=[],
                )
            ],
            narrative_profile=CharacterNarrativeProfile(
                canonical_names=("Akira",),
                motivation="Protect civilians without becoming a weapon of the memory regime.",
                backstory=(
                    "A disciplined swordswoman hunting the source of altered memories "
                    "inside a rain-soaked controlled city."
                ),
                voice_traits=("concise", "restrained", "observant"),
                allowed_abilities=("Crimson Arc",),
                forbidden_behaviors=("abandons civilians",),
                forbidden_voice_phrases=("I give up",),
                locked=True,
            ),
        )

    @property
    def trigger_prompt(self) -> str:
        return self.identity_constraints.trigger_prompt.strip()

    def prompt_fragments(self) -> tuple[str, ...]:
        """Provider-neutral, deterministic identity fragments for prompt builders."""
        fragments = (
            self.trigger_prompt,
            self.identity_constraints.hair,
            f"{self.identity_constraints.eye_color} eyes",
            self.identity_constraints.facial_geometry,
            self.identity_constraints.body_proportions,
            self.identity_constraints.silhouette,
            self.outfit_catalog[0].description if self.outfit_catalog else "",
            self.style_profile.base_style,
        )
        return tuple(dict.fromkeys(value.strip() for value in fragments if value.strip()))

    def to_dict(self) -> dict[str, Any]:
        return {
            "character_id": self.character_id,
            "identity_constraints": self.identity_constraints.to_dict(),
            "style_profile": self.style_profile.to_dict(),
            "reference_pack": {
                view.value: ref.to_dict()
                for view, ref in self.reference_pack.items()
            },
            "outfit_catalog": [outfit.to_dict() for outfit in self.outfit_catalog],
            "narrative_profile": (
                self.narrative_profile.to_dict() if self.narrative_profile else None
            ),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CharacterBible":
        refs = {
            ReferenceView(view_str): CharacterReference.from_dict(ref_data)
            for view_str, ref_data in data.get("reference_pack", {}).items()
        }
        outfits = [
            Outfit.from_dict(o_data)
            for o_data in data.get("outfit_catalog", [])
        ]
        return cls(
            character_id=data["character_id"],
            identity_constraints=IdentityConstraints.from_dict(data.get("identity_constraints", {})),
            style_profile=StyleProfile.from_dict(data.get("style_profile", {})),
            reference_pack=refs,
            outfit_catalog=outfits,
            narrative_profile=(
                CharacterNarrativeProfile.from_dict(dict(data["narrative_profile"]))
                if data.get("narrative_profile")
                else None
            ),
        )
