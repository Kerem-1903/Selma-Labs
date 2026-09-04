import re
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
from core.domain.value_objects.structured_mark import MarkAnchor, StructuredMark
from core.domain.value_objects.style_profile import StyleProfile


@dataclass
class CharacterBible:
    _PROP_WORDS = frozenset(
        {"bow", "gun", "katana", "knife", "rifle", "spear", "sword", "weapon"}
    )
    _LOWER_BODY_WORDS = frozenset(
        {"boot", "boots", "knee", "kneepad", "kneepads", "trouser", "trousers"}
    )
    _FACE_ONLY_VIEWS = frozenset(
        {
            "FACE_CLOSEUP",
            "PROFILE_LEFT",
            "PROFILE_RIGHT",
            "PROFILE_RIGHT_FACE_CLOSEUP",
            "THREE_QUARTER_LEFT",
            "THREE_QUARTER_RIGHT",
        }
    )
    character_id: str
    identity_constraints: IdentityConstraints
    style_profile: StyleProfile
    reference_pack: dict[ReferenceView, CharacterReference] = field(
        default_factory=dict
    )
    outfit_catalog: list[Outfit] = field(default_factory=list)
    narrative_profile: CharacterNarrativeProfile | None = None

    def __post_init__(self) -> None:
        if not self.character_id.strip():
            raise ValueError("CharacterBible character_id must not be empty.")
        for view, reference in self.reference_pack.items():
            if view != reference.view:
                raise ValueError(
                    "CharacterBible reference view does not match its pack key."
                )
            if reference.character_id != self.character_id:
                raise ValueError(
                    "CharacterBible references must belong to the same character."
                )
        if any(
            outfit.character_id != self.character_id for outfit in self.outfit_catalog
        ):
            raise ValueError(
                "CharacterBible outfits must belong to the same character."
            )

    @classmethod
    def akira(cls) -> "CharacterBible":
        """Return SELMA's canonical Akira identity without filesystem coupling."""
        return cls(
            character_id="akira",
            identity_constraints=IdentityConstraints(
                eye_color="amber",
                hair=(
                    "long straight black hair, otherwise entirely black, with exactly "
                    "one narrow deep-red front streak on character left (viewer right)"
                ),
                facial_geometry="angular anime face, defined jaw, straight nose",
                body_proportions="athletic adult woman, consistent limb proportions",
                silhouette="cropped combat jacket, tapered combat trousers, single katana",
                trigger_prompt="akira_girl",
                immutable_marks=[
                    "single deep-red hair streak on the left-front section",
                    "amber eyes",
                    "one katana only",
                ],
                structured_marks=[
                    StructuredMark(
                        id="akira-red-streak",
                        label="single deep-red front hair streak",
                        color_hex="#C04838",
                        viewer_side="viewer_right",
                        count=1,
                        color_tolerance_delta_e=18.0,
                        anchor=MarkAnchor(
                            region="front-hairline",
                            x_center=0.73,
                            y_root=0.11,
                            extent=0.12,
                            sweep_deg=-18.0,
                        ),
                        # Calibrated head zone of the locked 1024px anchor
                        # (318, 171, 663, 609) as normalized frame fractions.
                        head_bbox=(0.3105, 0.1670, 0.6475, 0.5947),
                        mirror_side="viewer_left",
                        shape_grammar="single narrow lock, full length, matte, no gradient",
                        enforcement="both",
                    ),
                ],
            ),
            style_profile=StyleProfile(
                base_style="cinematic cyberpunk anime",
                lighting_preferences=[
                    "controlled rim light",
                    "high-contrast practical light",
                ],
                color_palette=["charcoal", "black", "muted gray", "deep red", "amber"],
                negative_prompts=[
                    "identity drift",
                    "different face",
                    "extra person",
                    "extra limbs",
                    "extra sword",
                    "red ribbon",
                    "red energy trail",
                    "red hair on both sides",
                    "red hair on character right (viewer left)",
                    "multiple red hair streaks",
                    "red hair tips",
                    "red hair clip",
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
        return self._dedupe_fragments(
            (
                *self.identity_core_fragments(),
                *self.costume_fragments(),
                *self.prop_fragments(),
            )
        )

    def identity_core_fragments(self) -> tuple[str, ...]:
        """Return identity details that remain visible in every camera scope."""
        identity = self.identity_constraints
        fragments = [
            self.trigger_prompt,
            identity.hair,
            f"{identity.eye_color} eyes",
            identity.facial_geometry,
            identity.body_proportions,
            self.style_profile.base_style,
        ]
        fragments.extend(
            mark
            for mark in identity.immutable_marks
            if not self._contains_prop_word(mark)
        )
        return self._dedupe_fragments(fragments)

    def costume_fragments(self) -> tuple[str, ...]:
        """Return silhouette and outfit details, excluding held props."""
        fragments = [
            clause
            for clause in self._silhouette_clauses()
            if not self._contains_prop_word(clause)
        ]
        fragments.extend(self._outfit_clauses())
        return self._dedupe_fragments(fragments)

    def upper_body_costume_fragments(self) -> tuple[str, ...]:
        """Return costume clauses that can truthfully appear above the waist."""
        return self._dedupe_fragments(
            clause
            for clause in self.costume_fragments()
            if not self._contains_lower_body_word(clause)
        )

    def prop_fragments(self) -> tuple[str, ...]:
        """Return held-object constraints separately from identity and costume."""
        fragments = [
            clause
            for clause in self._silhouette_clauses()
            if self._contains_prop_word(clause)
        ]
        fragments.extend(
            mark
            for mark in self.identity_constraints.immutable_marks
            if self._contains_prop_word(mark)
        )
        return self._dedupe_fragments(fragments)

    def prompt_fragments_for_view(self, view: str | ReferenceView) -> tuple[str, ...]:
        """Return truthful prompt fragments for the visible camera scope."""
        view_name = view.value if isinstance(view, ReferenceView) else str(view)
        fragments = list(self.identity_core_fragments())
        if view_name not in self._FACE_ONLY_VIEWS:
            costume = (
                self.upper_body_costume_fragments()
                if "UPPER_BODY" in view_name or view_name == "FRONT"
                else self.costume_fragments()
            )
            fragments.extend(costume)
        if view_name.startswith("ACTION_"):
            fragments.extend(self.prop_fragments())
        return self._dedupe_fragments(fragments)

    @classmethod
    def is_face_only_view(cls, view: str | ReferenceView) -> bool:
        view_name = view.value if isinstance(view, ReferenceView) else str(view)
        return view_name in cls._FACE_ONLY_VIEWS

    @classmethod
    def is_prop_fragment(cls, value: str) -> bool:
        return cls._contains_prop_word(value)

    def _silhouette_clauses(self) -> tuple[str, ...]:
        return tuple(
            value.strip()
            for value in re.split(
                r",|\band\b", self.identity_constraints.silhouette, flags=re.IGNORECASE
            )
            if value.strip()
        )

    def _outfit_clauses(self) -> tuple[str, ...]:
        return tuple(
            clause.strip()
            for outfit in self.outfit_catalog
            for clause in re.split(
                r",|\band\b", outfit.description, flags=re.IGNORECASE
            )
            if clause.strip()
        )

    @classmethod
    def _contains_prop_word(cls, value: str) -> bool:
        words = set(re.findall(r"[a-z0-9]+", value.casefold()))
        return bool(words & cls._PROP_WORDS)

    @classmethod
    def _contains_lower_body_word(cls, value: str) -> bool:
        words = set(re.findall(r"[a-z0-9]+", value.casefold()))
        return bool(words & cls._LOWER_BODY_WORDS)

    @staticmethod
    def _dedupe_fragments(values: Any) -> tuple[str, ...]:
        result: list[str] = []
        token_sets: list[set[str]] = []
        stopwords = {"a", "an", "and", "on", "only", "section", "the", "with"}

        def tokens(value: str) -> set[str]:
            normalized = re.sub(
                r"\b(?:exactly\s+one|a\s+single|single)\b",
                "one",
                value.casefold(),
            )
            return {
                token.rstrip("s")
                for token in re.findall(r"[a-z0-9]+", normalized)
                if token not in stopwords
            }

        for raw in values:
            value = str(raw).strip()
            if not value:
                continue
            current = tokens(value)
            if any(
                current == existing
                or (
                    current
                    and existing
                    and len(current & existing) / min(len(current), len(existing)) >= 0.8
                )
                for existing in token_sets
            ):
                continue
            result.append(value)
            token_sets.append(current)
        return tuple(result)

    def to_dict(self) -> dict[str, Any]:
        return {
            "character_id": self.character_id,
            "identity_constraints": self.identity_constraints.to_dict(),
            "style_profile": self.style_profile.to_dict(),
            "reference_pack": {
                view.value: ref.to_dict() for view, ref in self.reference_pack.items()
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
            Outfit.from_dict(o_data) for o_data in data.get("outfit_catalog", [])
        ]
        return cls(
            character_id=data["character_id"],
            identity_constraints=IdentityConstraints.from_dict(
                data.get("identity_constraints", {})
            ),
            style_profile=StyleProfile.from_dict(data.get("style_profile", {})),
            reference_pack=refs,
            outfit_catalog=outfits,
            narrative_profile=(
                CharacterNarrativeProfile.from_dict(dict(data["narrative_profile"]))
                if data.get("narrative_profile")
                else None
            ),
        )
