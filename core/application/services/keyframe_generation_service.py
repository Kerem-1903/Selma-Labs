from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone

from core.domain.entities.character_bible import CharacterBible
from core.domain.entities.candidate.keyframe_candidate import CandidateStatus
from core.domain.entities.shot_contract import ShotContract
from core.domain.entities.shot_storyboard import ShotStoryboard
from core.domain.exceptions import KeyframeGenerationError, StorageError
from core.domain.ports.character_bible_repository_port import CharacterBibleRepositoryPort
from core.domain.ports.keyframe_generation_port import KeyframeGenerationPort
from core.domain.ports.shot_storyboard_repository_port import ShotStoryboardRepositoryPort
from core.domain.ports.storage_port import StoragePort
from core.domain.services.reference_conditioning_builder import ReferenceConditioningBuilder
from core.domain.value_objects.storyboard_frame import StoryboardFrame
from core.application.services.candidate.candidate_evaluation_service import (
    CandidateEvaluationService,
)


class KeyframeGenerationService:
    """Orchestrate reference loading, image generation, and durable metadata."""

    _CONTENT_TYPES = {"image/png": ".png", "image/jpeg": ".jpg", "image/webp": ".webp"}
    _SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")

    def __init__(
        self,
        *,
        generator: KeyframeGenerationPort,
        storage: StoragePort,
        character_bibles: CharacterBibleRepositoryPort,
        storyboards: ShotStoryboardRepositoryPort,
        candidate_evaluation: CandidateEvaluationService | None = None,
        human_review_required: bool = True,
        conditioning_builder: ReferenceConditioningBuilder | None = None,
    ) -> None:
        self._generator = generator
        self._storage = storage
        self._character_bibles = character_bibles
        self._storyboards = storyboards
        self._candidate_evaluation = candidate_evaluation
        self._human_review_required = human_review_required
        if human_review_required and candidate_evaluation is None:
            raise ValueError(
                "Candidate evaluation service is required when human review is enabled."
            )
        self._conditioning_builder = conditioning_builder or ReferenceConditioningBuilder()

    async def generate(
        self,
        *,
        shot_contract: ShotContract,
        sequence_index: int = 0,
        storyboard: ShotStoryboard | None = None,
        width: int = 1024,
        height: int = 1024,
        seed: int | None = None,
    ) -> ShotStoryboard:
        if sequence_index < 0:
            raise KeyframeGenerationError("sequence_index cannot be negative.")
        if not self._SAFE_ID.fullmatch(shot_contract.id):
            raise KeyframeGenerationError("Shot contract ID is not storage-key safe.")
        if storyboard is not None and storyboard.shot_contract_id != shot_contract.id:
            raise KeyframeGenerationError("Storyboard belongs to another shot contract.")
        if storyboard is not None and any(
            frame.sequence_index == sequence_index for frame in storyboard.frames
        ):
            raise KeyframeGenerationError(
                f"Storyboard already contains sequence index {sequence_index}."
            )

        bibles: list[CharacterBible] = []
        seen_character_ids: set[str] = set()
        for state in shot_contract.required_character_states:
            if state.character_id in seen_character_ids:
                continue
            seen_character_ids.add(state.character_id)
            bibles.append(await self._character_bibles.load(state.character_id))

        request = self._conditioning_builder.build(
            shot_contract=shot_contract,
            character_bibles=bibles,
            width=width,
            height=height,
            seed=seed,
        )
        for reference_key in request.reference_storage_keys:
            if not await self._storage.exists(reference_key):
                raise StorageError(
                    f"Character reference asset '{reference_key}' was not found."
                )
        generated = await self._generator.generate_keyframe(request)
        self._validate_generated_image(generated.image_bytes, generated.content_type)
        if generated.width <= 0 or generated.height <= 0:
            raise KeyframeGenerationError("Generator returned invalid image dimensions.")

        media_asset_id = str(uuid.uuid4())
        extension = self._CONTENT_TYPES[generated.content_type]
        storage_key = (
            f"storyboards/{shot_contract.id}/frames/"
            f"{sequence_index:04d}-{media_asset_id}{extension}"
        )
        stored = await self._storage.save(
            storage_key, generated.image_bytes, generated.content_type
        )
        if stored.key != storage_key:
            raise StorageError("Storage adapter returned a different key for the keyframe.")

        used_reference_asset_ids = generated.metadata.get("reference_asset_ids")
        if used_reference_asset_ids is None:
            frame_reference_asset_ids = request.reference_asset_ids
        elif isinstance(used_reference_asset_ids, list) and all(
            isinstance(asset_id, str) and asset_id in request.reference_asset_ids
            for asset_id in used_reference_asset_ids
        ):
            frame_reference_asset_ids = tuple(dict.fromkeys(used_reference_asset_ids))
        else:
            raise KeyframeGenerationError(
                "Generator reported reference asset IDs outside the request."
            )

        frame = StoryboardFrame(
            id=str(uuid.uuid4()),
            shot_contract_id=shot_contract.id,
            sequence_index=sequence_index,
            media_asset_id=media_asset_id,
            storage_key=storage_key,
            content_type=generated.content_type,
            provider=self._generator.name,
            provider_asset_id=generated.provider_asset_id,
            width=generated.width,
            height=generated.height,
            reference_asset_ids=frame_reference_asset_ids,
            created_at=datetime.now(timezone.utc),
        )
        # Explicit compatibility path for callers that intentionally retain A5 behavior.
        if not self._human_review_required:
            result = (storyboard or ShotStoryboard.create(shot_contract.id)).with_frame(frame)
            await self._storyboards.save(result)
            return result

        # A7 Candidate Generation Flow (single candidate)
        assert self._candidate_evaluation is not None
        await self._candidate_evaluation.register_candidate(
            shot_contract_id=shot_contract.id,
            storage_key=storage_key,
            generation_metadata={
                "sequence_index": sequence_index,
                "media_asset_id": media_asset_id,
                "content_type": generated.content_type,
                "provider": self._generator.name,
                "provider_asset_id": generated.provider_asset_id,
                "width": generated.width,
                "height": generated.height,
                "reference_asset_ids": list(frame_reference_asset_ids),
            }
        )
        return storyboard or ShotStoryboard.create(shot_contract.id)

    async def generate_candidates(
        self,
        *,
        shot_contract: ShotContract,
        sequence_index: int = 0,
        count: int = 3,
        width: int = 1024,
        height: int = 1024,
    ) -> None:
        """Generates multiple candidates for human review (A7 workflow)."""
        if not self._human_review_required or not self._candidate_evaluation:
            raise KeyframeGenerationError("Candidate evaluation service is required to generate candidates.")
        if not 1 <= count <= 10:
            raise KeyframeGenerationError("Candidate count must be between 1 and 10.")

        for _ in range(count):
            await self.generate(
                shot_contract=shot_contract,
                sequence_index=sequence_index,
                width=width,
                height=height,
            )

    async def commit_approved_candidate(self, shot_contract_id: str, storyboard: ShotStoryboard | None = None) -> ShotStoryboard:
        """
        Quality Gate: Commits the approved candidate into the ShotStoryboard.
        Fails if no approved candidate exists.
        """
        if not self._candidate_evaluation:
            raise KeyframeGenerationError("Candidate evaluation service is required to commit candidates.")

        candidate = await self._candidate_evaluation.get_approved_candidate_for_shot(shot_contract_id)
        if not candidate:
            raise KeyframeGenerationError(f"No approved candidate found for shot contract {shot_contract_id}")
        if candidate.status == CandidateStatus.COMMITTED:
            raise KeyframeGenerationError(
                f"Approved candidate for shot contract {shot_contract_id} was already committed."
            )
        if not await self._storage.exists(candidate.storage_key):
            raise StorageError(
                f"Approved candidate asset '{candidate.storage_key}' was not found."
            )

        meta = candidate.generation_metadata
        frame = StoryboardFrame(
            id=str(uuid.uuid4()),
            shot_contract_id=shot_contract_id,
            sequence_index=meta["sequence_index"],
            media_asset_id=meta["media_asset_id"],
            storage_key=candidate.storage_key,
            content_type=meta.get("content_type", "image/png"),
            provider=meta["provider"],
            provider_asset_id=meta["provider_asset_id"],
            width=meta["width"],
            height=meta["height"],
            reference_asset_ids=tuple(meta["reference_asset_ids"]),
            created_at=datetime.now(timezone.utc),
        )

        result = (storyboard or ShotStoryboard.create(shot_contract_id)).with_frame(frame)
        await self._storyboards.save(result)
        await self._candidate_evaluation.mark_candidate_committed(candidate.id)
        return result

    def _validate_generated_image(self, data: bytes, content_type: str) -> None:
        if not data:
            raise KeyframeGenerationError("Generator returned empty image bytes.")
        if content_type not in self._CONTENT_TYPES:
            raise KeyframeGenerationError(
                f"Generator returned unsupported content type: {content_type}"
            )
        signatures = {
            "image/png": data.startswith(b"\x89PNG\r\n\x1a\n"),
            "image/jpeg": data.startswith(b"\xff\xd8\xff"),
            "image/webp": data.startswith(b"RIFF") and data[8:12] == b"WEBP",
        }
        if not signatures[content_type]:
            raise KeyframeGenerationError(
                "Generator bytes do not match the declared image content type."
            )
