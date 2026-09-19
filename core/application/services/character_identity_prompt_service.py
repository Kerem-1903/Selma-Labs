"""Provider-request factory for the shared character identity contract.

This service deliberately has no storage, provider, QC, or approval concerns. It
turns the immutable character identity and a view-specific recipe into a
provider-neutral ``KeyframeGenerationRequest``. Keeping this boundary small
prevents canonical, turnaround, and pose-pack flows from inventing different
prompt contracts.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, ClassVar

from core.domain.value_objects.character_creation_brief import CharacterCreationBrief
from core.domain.value_objects.character_identity_contract import (
    CharacterIdentityContract,
)
from core.domain.value_objects.keyframe_generation_request import (
    KeyframeGenerationRequest,
)

ConditioningReference = tuple[str, str, str, float]

#: Fixed turnaround canvas used by the pose-driven dialect. The IP-Adapter
#: recipe was calibrated on this portrait shape, so it stays the default.
_DEFAULT_REFERENCE_CANVAS = (768, 1152)

#: Target pixel budget for a source-aspect edit canvas. Matches the default
#: ``image_edit_megapixels`` the FLUX.2 edit provider injects, so the canvas and
#: the resolution-scaling node agree instead of fighting each other.
_EDIT_CANVAS_MEGAPIXELS = 1.0

#: Diffusion transformers need both dimensions divisible by the patch/VAE
#: stride. 16 is the safe common multiple for the FLUX.2 family.
_EDIT_CANVAS_STRIDE = 16


def edit_canvas_for(width: int, height: int) -> tuple[int, int]:
    """Return a ~1 MP edit canvas that preserves the source aspect ratio.

    The source-led dialect treats Picture 1 as the visual truth and permits only
    one change: the viewpoint. Rendering a square source onto a fixed portrait
    canvas silently adds a second change, re-framing, and re-framing moves the
    subject box, the palette histogram and the backdrop gradient together. That
    is exactly the drift the turnaround was supposed to avoid, and no prompt can
    remove it while the canvas disagrees with the picture. Matching the source
    aspect leaves rotation as the only thing the model has to decide.
    """
    if width <= 0 or height <= 0:
        raise ValueError("Source dimensions must be positive.")
    scale = (_EDIT_CANVAS_MEGAPIXELS * 1_000_000.0 / (width * height)) ** 0.5
    stride = _EDIT_CANVAS_STRIDE
    columns = max(stride * 16, int(round(width * scale / stride)) * stride)
    rows = max(stride * 16, int(round(height * scale / stride)) * stride)
    return columns, rows


class CharacterIdentityPromptService:
    """Build deterministic generation requests from one character contract."""

    _IMAGE_EDIT_VIEW_INSTRUCTIONS: ClassVar[dict[str, str]] = {
        "FRONT": "keep the current strict front view",
        "PROFILE_LEFT": (
            "show a strict left side profile, nose pointing to image left, "
            "with only one eye visible"
        ),
        "PROFILE_RIGHT": (
            "show a strict right side profile, nose pointing to image right, "
            "with only one eye visible"
        ),
        "THREE_QUARTER_LEFT": (
            "rotate the face and torso about 45 degrees toward image left into a true "
            "left three-quarter view, with both eyes and both sides of the torso visible; "
            "do not make a side profile"
        ),
        "THREE_QUARTER_RIGHT": (
            "rotate the face and torso about 45 degrees toward image right into a true "
            "right three-quarter view, with both eyes and both sides of the torso visible; "
            "do not make a side profile"
        ),
        "BACK": "show a strict rear view, with the face and facial features fully hidden",
    }

    # Viewpoint is the only thing that may change. These clauses restate the
    # *invariants* a text-only model otherwise drifts on (prop size/colour,
    # signature markings mirroring away, invented hidden surfaces) without
    # dumping the brief's descriptive identity text into the prompt.
    _IMAGE_EDIT_ACCESSORY_INVARIANT = (
        "Every depicted prop keeps the same count, the same side of the body, "
        "the same scale and the same colour."
    )
    _IMAGE_EDIT_MARK_INVARIANT = (
        "Any depicted signature hair marking keeps its exact count, side, "
        "width and colour; it never mirrors onto the visible side, never "
        "multiplies and never disappears."
    )
    _IMAGE_EDIT_HIDDEN_SURFACE_INVARIANT = (
        "Infer only surfaces hidden in Picture 1 and keep them minimal: no new "
        "strap, pocket, seam, panel, accessory or colour field may appear."
    )
    _IMAGE_EDIT_FRONT_FACING_SIDE: ClassVar[dict[str, str]] = {
        "FRONT": "",
        "PROFILE_LEFT": "left",
        "THREE_QUARTER_LEFT": "left",
        "PROFILE_RIGHT": "right",
        "THREE_QUARTER_RIGHT": "right",
        "BACK": "",
    }
    # A character's left is the viewer's right in a front view and the viewer's
    # left in a back view.
    _IMAGE_EDIT_MARK_IMAGE_SIDE: ClassVar[dict[tuple[str, str], str]] = {
        ("FRONT", "left"): "image right",
        ("FRONT", "right"): "image left",
        ("BACK", "left"): "image left",
        ("BACK", "right"): "image right",
    }

    _NEGATIVES: ClassVar[tuple[str, ...]] = (
        "multiple characters",
        "duplicate character",
        "duplicate person",
        "2boys",
        "3boys",
        "2girls",
        "3girls",
        "4girls",
        "5girls",
        "group",
        "lineup",
        "collage",
        "multiple views",
        "multiple poses",
        "character sheet",
        "split panel",
        "background figure",
        "giant silhouette",
        "oversized shadow",
        "cast shadow shaped like a person",
        "dynamic pose",
        "action pose",
        "crouching",
        "wide stance",
        "cropped head",
        "cropped feet",
        "extra limbs",
        "bad hands",
        "text",
        "watermark",
    )
    _TURNAROUND_NEGATIVES: ClassVar[tuple[str, ...]] = (
        "cinematic street scene",
        "city street",
        "buildings",
        "architecture",
        "rainy background",
        "dramatic background",
        "neon lights",
        "neon glow",
        "strong rim light",
        "volumetric lighting",
        "spotlight",
        "scenery",
        "landscape",
        "props not in the locked outfit",
        "different costume",
        "different clothing",
        "different hairstyle",
        "style drift",
        "photorealistic",
        "3d render",
        "chibi proportions",
    )
    _ANCHOR_WORKFLOW_VERSION = "dual-anchor-v2-deterministic"
    _POSE_NEGATIVES: ClassVar[tuple[str, ...]] = (
        "multiple characters",
        "duplicate person",
        "character sheet",
        "collage",
        "split panel",
        "text",
        "watermark",
        "cropped head",
        "cropped feet",
        "extra limbs",
        "bad hands",
    )

    def build_design_request(
        self,
        brief: CharacterCreationBrief,
        *,
        seed: int,
        variant: int,
        style_reference: tuple[str, str, float] | None = None,
    ) -> KeyframeGenerationRequest:
        contract = CharacterIdentityContract.from_brief(brief)
        subject_tag = self.subject_tag(contract.gender_presentation)
        identity = contract.identity_description
        palette = ", ".join(contract.palette)
        personality = ", ".join(brief.personality)
        is_face_design = contract.style_preset.casefold() == "selma-anime-v3-face"
        composition = (
            (
                "one isolated figure only, portrait from chest and shoulders upward, "
                "large readable head occupying at least one third of the canvas, "
                "face centered and fully visible, hairline and both eyes clearly visible"
            )
            if is_face_design
            else (
                "one isolated figure only, strict neutral front standing pose, "
                "arms relaxed at sides, feet shoulder-width apart, full body, "
                "entire head and both feet visible, centered and occupying about "
                "seventy percent of the canvas"
            )
        )
        prompt = ", ".join(
            value
            for value in (
                (
                    "masterpiece, best quality, professional anime character "
                    f"concept art, {subject_tag}, solo"
                ),
                contract.concept,
                identity,
                personality,
                f"character palette: {palette}" if palette else "",
                self.style_prompt(contract.style_preset),
                composition,
                "clean softly graded studio background",
                f"design variation {variant}",
                contract.additional_notes,
            )
            if value
        )
        visual_constraints: dict[str, object] = {
            "prompt": prompt,
            "composition_contract": (
                "one centered portrait; head and shoulders clearly visible"
                if is_face_design
                else "one centered character; full silhouette visible"
            ),
            "environment_style": "soft gradient studio background",
            "latent_mode": "empty",
            "extra_tags": f"{subject_tag}, solo, one person",
            "identity_contract_hash": contract.content_hash,
        }
        conditioning: tuple[dict[str, object], ...] = ()
        reference_asset_ids: tuple[str, ...] = ()
        reference_storage_keys: tuple[str, ...] = ()
        if style_reference is not None:
            storage_key, content_hash, weight = style_reference
            style_id = f"style:{content_hash[:12]}"
            visual_constraints["identity_reference_weights"] = [weight]
            visual_constraints["style_seed_weight"] = weight
            visual_constraints["identity_mode"] = "style_only"
            conditioning = (
                {
                    "character_id": contract.character_id,
                    "identity_constraints": {
                        "contract_hash": contract.content_hash,
                        "description": identity,
                    },
                    "active_outfit": {"description": contract.outfit},
                    "references": [
                        {
                            "view": "STYLE_SEED",
                            "asset_id": style_id,
                            "storage_key": storage_key,
                        }
                    ],
                },
            )
            reference_asset_ids = (style_id,)
            reference_storage_keys = (storage_key,)
        return KeyframeGenerationRequest(
            shot_contract_id=f"character-design-{contract.character_id}-{seed}",
            camera_constraints={
                "angle": "front-facing head and shoulders portrait"
                if is_face_design
                else "full body front view",
                "lens": "50mm",
                "movement": "locked",
            },
            action_constraints={"primary_action": "neutral standing pose"},
            visual_constraints=visual_constraints,
            character_conditioning=conditioning,
            reference_asset_ids=reference_asset_ids,
            reference_storage_keys=reference_storage_keys,
            negative_prompts=tuple(
                dict.fromkeys(
                    (
                        *contract.avoid,
                        *self._NEGATIVES,
                        *self.subject_exclusions(contract.gender_presentation),
                    )
                )
            ),
            width=768 if is_face_design else 1024,
            height=1024,
            seed=seed,
        )

    def build_anchor_request(
        self,
        brief: CharacterCreationBrief,
        *,
        canonical_source_key: str,
        canonical_source_hash: str,
        role: str,
        seed: int,
        width: int,
        height: int,
    ) -> KeyframeGenerationRequest:
        contract = CharacterIdentityContract.from_brief(brief)
        subject_tag = self.subject_tag(contract.gender_presentation)
        identity = contract.identity_description
        if role == "FACE":
            direction = (
                "front-facing close-up portrait, neutral expression, complete hair and "
                "hairline visible, preserve eye shape and facial marks"
            )
            negatives = ("full body", "long shot", "feet", "distant subject")
            latent_mode = "reference"
            strength = 0.85
        elif role == "FULL_BODY":
            direction = (
                "strict front view, neutral standing pose, full body from head to feet, "
                "preserve body proportions, outfit layers and palette"
            )
            negatives = ("close-up", "portrait crop", "cropped head", "cropped feet")
            latent_mode = "empty"
            strength = 0.65
        else:
            raise ValueError(f"Unknown anchor role: {role}")
        reference = {
            "view": "FRONT",
            "asset_id": canonical_source_hash,
            "storage_key": canonical_source_key,
        }
        return KeyframeGenerationRequest(
            shot_contract_id=(
                f"character-anchor-{contract.character_id}-{role.casefold()}-{seed}"
            ),
            camera_constraints={
                "angle": direction,
                "lens": "50mm",
                "movement": "locked",
            },
            action_constraints={"primary_action": "neutral character reference"},
            visual_constraints={
                "prompt": ", ".join(
                    (
                        f"masterpiece, {subject_tag}, solo, one person only",
                        contract.concept,
                        identity,
                        direction,
                        contract.style_preset,
                        "plain softly graded studio background",
                    )
                ),
                "composition_contract": direction,
                "environment_style": "plain softly graded studio background",
                "latent_mode": latent_mode,
                "identity_mode": "identity_only",
                "identity_strength": strength,
                "identity_end_at": 0.85,
                "identity_contract_hash": contract.content_hash,
                "extra_tags": f"{subject_tag}, solo, one person, single image",
                "workflow_version": self._ANCHOR_WORKFLOW_VERSION,
            },
            character_conditioning=(
                {
                    "character_id": contract.character_id,
                    "identity_constraints": {
                        "contract_hash": contract.content_hash,
                        "description": identity,
                    },
                    "active_outfit": {"description": contract.outfit},
                    "references": [reference],
                },
            ),
            reference_asset_ids=(canonical_source_hash,),
            reference_storage_keys=(canonical_source_key,),
            negative_prompts=tuple(
                dict.fromkeys((*contract.avoid, *self._NEGATIVES, *negatives))
            ),
            width=width,
            height=height,
            seed=seed,
        )

    def build_reference_request(
        self,
        brief: CharacterCreationBrief,
        *,
        view: str,
        direction: str,
        seed: int,
        references: tuple[ConditioningReference, ...],
        pose_storage_key: str = "",
        canvas: tuple[int, int] | None = None,
    ) -> KeyframeGenerationRequest:
        width, height = canvas or _DEFAULT_REFERENCE_CANVAS
        canvas_policy = "source_aspect" if canvas else "fixed_portrait"
        contract = CharacterIdentityContract.from_brief(brief)
        identity = contract.identity_description
        subject_tag = self.subject_tag(contract.gender_presentation)
        style_contract = self.style_prompt(contract.style_preset)
        consistency_contract = contract.consistency_contract(style=style_contract)
        # Keep the model-facing prompt compact. The full contract remains in
        # ``visual_constraints`` and the request manifest for provenance, but
        # repeating every brief field in natural language makes view changes
        # compete with identity preservation.
        prompt = ", ".join(
            value
            for value in (
                "anime character reference",
                self.view_positive_tags(view),
                f"{subject_tag}, solo, one person only",
                self._compact_identity(contract),
                self._compact_style(contract.style_preset),
                "full body, head and feet visible"
                if view != "FACE_CLOSEUP"
                else "close-up portrait, complete hair and face visible",
                "plain light-gray studio background",
            )
            if value
        )
        weights = tuple(item[3] for item in references)
        reference_ids = tuple(
            f"{reference_view.casefold()}:{content_hash}"
            for reference_view, _storage_key, content_hash, _weight in references
        )
        return KeyframeGenerationRequest(
            shot_contract_id=f"character-reference-{contract.character_id}-{view.casefold()}",
            camera_constraints={
                "angle": direction,
                "lens": "50mm",
                "movement": "locked",
            },
            action_constraints={"primary_action": "neutral reference pose"},
            visual_constraints={
                "prompt": prompt,
                "composition_contract": direction,
                "environment_style": "plain softly graded studio background",
                "latent_mode": "empty",
                "identity_mode": "identity_only",
                "identity_strength": max(weights),
                "identity_reference_weights": list(weights),
                "identity_contract": {
                    "contract_hash": contract.content_hash,
                    "face": contract.face,
                    "hair": contract.hair,
                    "signature_marks": list(contract.signature_mark_labels),
                    "costume": contract.outfit,
                    "props": list(contract.props),
                    "palette": list(contract.palette),
                    "style": style_contract,
                    "background": "plain light-gray studio background",
                },
                "consistency_contract": consistency_contract,
                "reference_views": [item[0] for item in references],
                "identity_contract_hash": contract.content_hash,
                "prompt_mode": "compact-turnaround",
                "view": view,
                "image_edit_prompt": self.build_flux2_edit_prompt(brief, view=view),
                "image_edit_negative_prompts": list(
                    self.image_edit_negative_prompts(view)
                ),
                "image_edit_provider": "flux2-klein",
                "identity_end_at": (
                    0.65
                    if view in {"PROFILE_LEFT", "PROFILE_RIGHT"}
                    else 0.55
                    if view == "BACK"
                    else 0.78
                    if view in {"THREE_QUARTER_LEFT", "THREE_QUARTER_RIGHT"}
                    else 0.85
                ),
                "extra_tags": (
                    f"{subject_tag}, solo, one person, single image, "
                    "turnaround consistency locked"
                ),
                **({"pose_storage_key": pose_storage_key} if pose_storage_key else {}),
                # Recorded so a reviewer can tell a source-aspect edit from the
                # fixed portrait canvas that was calibrated for the pose dialect.
                "canvas_policy": canvas_policy,
                **(
                    {
                        "pose_strength": (
                            1.0
                            if view in {"PROFILE_LEFT", "PROFILE_RIGHT", "BACK"}
                            else 0.90
                        )
                    }
                    if pose_storage_key
                    else {}
                ),
            },
            character_conditioning=tuple(
                {
                    "character_id": contract.character_id,
                    "identity_constraints": {
                        "contract_hash": contract.content_hash,
                        "description": identity,
                        "immutable_marks": list(contract.signature_mark_labels),
                        "face": contract.face,
                        "hair": contract.hair,
                        "palette": list(contract.palette),
                        "style": style_contract,
                    },
                    "active_outfit": {
                        "description": contract.outfit,
                        "props": list(contract.props),
                        "palette": list(contract.palette),
                    },
                    "style_profile": {
                        "base_style": style_contract,
                        "background": "plain light-gray studio background",
                    },
                    "references": [
                        {
                            "view": reference_view,
                            "asset_id": asset_id,
                            "storage_key": storage_key,
                        }
                    ],
                }
                for (
                    reference_view,
                    storage_key,
                    _content_hash,
                    _weight,
                ), asset_id in zip(references, reference_ids)
            ),
            reference_asset_ids=reference_ids,
            reference_storage_keys=tuple(item[1] for item in references),
            negative_prompts=tuple(
                dict.fromkeys(
                    (
                        *contract.avoid,
                        *self._NEGATIVES,
                        *self._TURNAROUND_NEGATIVES,
                        *self.view_negatives(view),
                    )
                )
            ),
            width=width,
            height=height,
            seed=seed,
        )

    def build_flux2_edit_prompt(
        self,
        brief: CharacterCreationBrief,
        *,
        view: str,
        task: str | None = None,
    ) -> str:
        """Build a source-led FLUX.2 turnaround edit instruction.

        The source image is the visual truth. The brief's descriptive identity
        text is intentionally not restated because it can conflict with the
        depicted details; only structural invariants that a text-only model
        cannot read off the picture are added (mark side, prop continuity).
        """
        view_instruction = self._IMAGE_EDIT_VIEW_INSTRUCTIONS.get(
            view, self._IMAGE_EDIT_VIEW_INSTRUCTIONS["FRONT"]
        )
        change = task or f"Change only the viewpoint: {view_instruction}."
        return " ".join(
            part
            for part in (
                "Edit Picture 1.",
                change,
                "Keep the exact same character and treat this as a turnaround, not a redesign.",
                "Preserve the depicted silhouette, proportions, hairstyle, every visible color boundary and asymmetry, garment panel, accessory count, scale and placement, line art, cel shading, and studio background.",
                self._IMAGE_EDIT_ACCESSORY_INVARIANT,
                self._IMAGE_EDIT_MARK_INVARIANT,
                self._mark_side_clause(brief, view),
                self._hidden_surface_clause(view),
                "Do not add, remove, enlarge, simplify, recolor, restyle, or replace anything.",
                "Keep one centered full-body character with the complete head and both boots visible.",
            )
            if part
        )

    def _mark_side_clause(
        self, brief: CharacterCreationBrief, view: str
    ) -> str:
        """State which way a side-bound signature mark must read in this view.

        This is the one piece of brief data the prompt may use: the *side* of a
        marking is a semantic fact the image alone cannot disambiguate, and it
        is exactly what drifts when the character turns.
        """
        sides = [
            mark.character_side
            for mark in brief.signature_marks
            if mark.character_side in {"left", "right"}
        ]
        if not sides or view not in self._IMAGE_EDIT_FRONT_FACING_SIDE:
            return ""
        facing_side = self._IMAGE_EDIT_FRONT_FACING_SIDE[view]
        clauses: list[str] = []
        for side in dict.fromkeys(sides):
            if facing_side == side:
                clauses.append(
                    f"The {side}-side hair marking faces the camera in this "
                    "view and must stay visible at the same width and colour."
                )
            elif facing_side:
                clauses.append(
                    f"The {side}-side hair marking is on the far side in this "
                    "view: keep it hidden and do not mirror it onto the visible side."
                )
            else:
                image_side = self._IMAGE_EDIT_MARK_IMAGE_SIDE.get(
                    (view, side), "same side as Picture 1"
                )
                clauses.append(
                    f"The {side}-side hair marking stays on the {image_side} in "
                    "this view."
                )
        return " ".join(clauses)

    @classmethod
    def _hidden_surface_clause(cls, view: str) -> str:
        clause = cls._IMAGE_EDIT_HIDDEN_SURFACE_INVARIANT
        if view == "BACK" or view.startswith("THREE_QUARTER"):
            clause += (
                " Any strap, bag or layered garment already depicted continues "
                "over the same shoulder and hip without resizing or recolouring."
            )
        return clause

    def build_qwen_edit_prompt(
        self,
        brief: CharacterCreationBrief,
        *,
        view: str,
        task: str | None = None,
    ) -> str:
        """Compatibility alias for stored manifests created before FLUX.2."""
        return self.build_flux2_edit_prompt(brief, view=view, task=task)

    def image_edit_negative_prompts(self, view: str) -> tuple[str, ...]:
        """Return only edit-specific negatives; identity is supplied by the image."""
        return tuple(
            dict.fromkeys(
                (
                    "second person",
                    "character redesign",
                    "costume change",
                    "hair change",
                    "style change",
                    *(() if view == "FRONT" else ("front view",)),
                    *self.view_negatives(view),
                    "cropped head",
                    "cropped feet",
                    "text",
                    "watermark",
                )
            )
        )

    def qwen_edit_negative_prompts(self, view: str) -> tuple[str, ...]:
        """Compatibility alias for stored manifests created before FLUX.2."""
        return self.image_edit_negative_prompts(view)

    @staticmethod
    def _compact_identity(contract: CharacterIdentityContract) -> str:
        """Summarize immutable visual anchors without duplicating the brief."""
        mark = ", ".join(contract.signature_mark_labels)
        prop = ", ".join(contract.props)
        return ", ".join(
            value
            for value in (
                contract.age_band,
                contract.gender_presentation,
                contract.hair,
                mark,
                contract.outfit,
                prop,
            )
            if value
        )

    @staticmethod
    def _compact_style(style_preset: str) -> str:
        normalized = style_preset.casefold()
        if normalized.startswith("selma-anime"):
            return                "anime line art, cel shading, adult proportions"

        return style_preset

    def build_pose_request(
        self,
        brief: CharacterCreationBrief,
        *,
        style_key: str,
        style_hash: str,
        pose_id: str,
        expected_view: str,
        seed: int,
        face_anchor_key: str,
        face_anchor_hash: str,
        fullbody_anchor_key: str,
        fullbody_anchor_hash: str,
        pose_template_key: str,
        style_lock_snapshot: Mapping[str, Any] | None = None,
        references: tuple[tuple[str, str, str, float], ...] | None = None,
        width: int = 768,
        height: int = 1152,
    ) -> KeyframeGenerationRequest:
        contract = CharacterIdentityContract.from_brief(brief)
        identity = contract.identity_description
        style_prompt = self.style_prompt(contract.style_preset)
        pose_prompts = {
            "FRONT_NEUTRAL": "front-facing neutral standing pose, full body, relaxed arms",
            "PROFILE_LEFT": "strict left side profile standing pose, full body, neutral posture",
            "BACK_FULL_BODY": "strict back-facing standing pose, full body, complete back silhouette",
        }
        try:
            pose_prompt = pose_prompts[pose_id]
        except KeyError as error:
            raise ValueError(f"Unknown pose id: {pose_id}") from error
        prompt = ", ".join(
            value for value in (
                "masterpiece, best quality, solo, one person only",
                contract.concept,
                identity,
                pose_prompt,
                style_prompt,
                f"series style lock {style_hash[:12]}",
                "neutral studio background, complete silhouette, head and both feet visible",
            ) if value
        )
        # The pose dialect chains at most two references. It deliberately does
        # not add the style reference as a third slot: the SDXL production
        # workflow owns exactly two identity adapters, and a third reference is
        # unreachable -- the provider would raise before rendering anything.
        # Style still reaches the render through the style-locked prompt and the
        # ``style_reference_hash`` recorded below.
        #
        # Which two references those are is a caller decision, because it is a
        # continuity question rather than a prompt question: the anchor pair
        # always depicts the front view, so a caller that needs a profile or a
        # back pose can pass the approved view that matches that orientation.
        default_refs = (
            ("FACE", face_anchor_key, face_anchor_hash, 0.75),
            ("FULL_BODY", fullbody_anchor_key, fullbody_anchor_hash, 0.50),
        )
        refs = tuple(references) if references else default_refs
        snapshot = style_lock_snapshot or {}
        return KeyframeGenerationRequest(
            shot_contract_id=f"character-pose-pack-{contract.character_id}-{pose_id.casefold()}",
            camera_constraints={"angle": pose_prompt, "lens": "50mm", "movement": "locked"},
            action_constraints={"primary_action": f"character pose pack {pose_id}"},
            visual_constraints={
                "prompt": prompt,
                "composition_contract": "one complete centered character; full silhouette inside frame",
                "environment_style": "plain softly graded studio background",
                "latent_mode": "empty",
                "identity_mode": "identity_only",
                "identity_strength": 0.75,
                "identity_reference_weights": [0.75, 0.50],
                # Name the chain explicitly: the provider selects one reference
                # per conditioning entry, so without this the two declared
                # weights would be read against a single selected reference and
                # the request would be rejected.
                "reference_views": [item[0] for item in refs],
                "identity_contract_hash": contract.content_hash,
                "style_reference_hash": style_hash,
                "consistency_contract": contract.consistency_contract(style=style_prompt),
                "pose_storage_key": pose_template_key,
                "pose_strength": 0.88,
                "workflow_version": "character-pose-pack-v1",
                "expected_view": expected_view,
                "style_lock_digest": snapshot.get("production_lock_digest", ""),
                "series_id": snapshot.get("series_id", ""),
                "style_id": snapshot.get("style_id", ""),
                "style_version": snapshot.get("style_version", 0),
            },
            character_conditioning=(
                {
                    "character_id": contract.character_id,
                    "identity_constraints": {
                        "contract_hash": contract.content_hash,
                        "description": identity,
                        "immutable_marks": list(contract.signature_mark_labels),
                    },
                    "active_outfit": {
                        "description": contract.outfit,
                        "props": list(contract.props),
                        "palette": list(contract.palette),
                    },
                    "style_profile": {
                        "base_style": style_prompt,
                        "background": "plain light-gray studio background",
                    },
                    # The conditioning references must carry the same identity
                    # the request declares in ``reference_asset_ids``: the
                    # provider resolves a named view by looking its asset id up
                    # in that map, so a raw content hash here would match
                    # nothing and the view would read as unavailable.
                    "references": [
                        {
                            "view": view,
                            "asset_id": f"{view.casefold()}:{content_hash}",
                            "storage_key": storage_key,
                        }
                        for view, storage_key, content_hash, _weight in refs
                    ],
                },
            ),
            reference_asset_ids=tuple(
                f"{view.casefold()}:{content_hash}" for view, _key, content_hash, _weight in refs
            ),
            reference_storage_keys=tuple(storage_key for _view, storage_key, _hash, _weight in refs),
            negative_prompts=tuple(dict.fromkeys((*contract.avoid, *self._POSE_NEGATIVES))),
            width=width,
            height=height,
            seed=seed,
        )
    @staticmethod
    def style_prompt(style_preset: str) -> str:
        normalized = style_preset.casefold()
        if normalized in {"selma-anime-v1", "selma-anime-v2-balanced"}:
            return (
                "clean precise anime line art, thin controlled outlines, restrained two-step "
                "cel shading, natural adult proportions, soft readable facial planes, "
                "clear garment construction, matte charcoal and muted gray materials, "
                "limited cobalt-blue accent colour, simplified animation-friendly silhouette, "
                "polished professional character design, plain light-gray studio background, "
                "no heavy black shadow blocks, no neon glow, no excessive straps or armor layers"
            )
        if normalized == "selma-anime-v3-face":
            return (
                "clean precise anime line art, thin controlled outlines, restrained two-step "
                "cel shading, natural adult facial proportions, softly modeled cheeks and jaw, "
                "clear expressive steel-blue eyes, short black hair with one narrow cobalt accent, "
                "matte charcoal clothing only at the shoulder edge, plain light-gray studio "
                "background, no heavy black shadow blocks, no neon glow, no cyberpunk armor"
            )
        return style_preset

    @staticmethod
    def view_negatives(view: str) -> tuple[str, ...]:
        if view == "FACE_CLOSEUP":
            return ("full body", "long shot", "feet", "distant subject")
        if view == "PROFILE_LEFT":
            return (
                "front view", "right profile", "three-quarter view", "looking at viewer",
                "both eyes visible", "symmetrical shoulders",
            )
        if view == "PROFILE_RIGHT":
            return (
                "front view", "left profile", "left-facing", "nose pointing left",
                "three-quarter view", "looking at viewer", "both eyes visible",
                "symmetrical shoulders",
            )
        if view == "THREE_QUARTER_LEFT":
            return ("front view", "right three-quarter view", "back view")
        if view == "THREE_QUARTER_RIGHT":
            return (
                "front view", "left-facing", "left three-quarter view", "nose pointing left",
                "back view",
            )
        if view == "BACK":
            return (
                "front view", "face", "eyes", "nose", "mouth", "facial features",
                "face visible", "looking at viewer", "looking back", "three-quarter view",
                "profile view",
            )
        return ()

    @staticmethod
    def view_positive_tags(view: str) -> str:
        return {
            "PROFILE_LEFT": "strict left profile, nose points to image left, one visible eye",
            "PROFILE_RIGHT": "strict right profile, nose points to image right, one visible eye",
            "THREE_QUARTER_LEFT": "left three-quarter view, facing image left",
            "THREE_QUARTER_RIGHT": "right three-quarter view, facing image right",
            "BACK": "strict rear view, face fully hidden, back silhouette visible",
        }.get(view, "front view")

    @staticmethod
    def subject_tag(gender_presentation: str) -> str:
        presentation = gender_presentation.casefold()
        if any(token in presentation for token in ("feminine", "female", "woman", "girl")):
            return "1girl"
        if any(token in presentation for token in ("masculine", "male", "man", "boy")):
            return "1boy"
        return "one person"

    @staticmethod
    def subject_exclusions(gender_presentation: str) -> tuple[str, ...]:
        presentation = gender_presentation.casefold()
        if any(token in presentation for token in ("feminine", "female", "woman", "girl")):
            return ("1boy", "male", "man", "masculine face")
        if any(token in presentation for token in ("masculine", "male", "man", "boy")):
            return ("1girl", "female", "woman", "feminine face")
        return ()

    def consistency_contract(self, brief: CharacterCreationBrief) -> dict[str, Any]:
        contract = CharacterIdentityContract.from_brief(brief)
        return contract.consistency_contract(style=self.style_prompt(contract.style_preset))
