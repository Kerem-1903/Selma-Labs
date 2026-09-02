"""Fail-closed orchestration for story drafting, review, and human approval."""

from __future__ import annotations

import asyncio

from core.application.services.canon_validation_service import CanonValidationService
from core.domain.entities.direction_bible import BibleStatus
from core.domain.entities.episode_script import (
    EpisodeScript,
    EpisodeScriptStatus,
    StoryBrief,
)
from core.domain.exceptions import StoryApprovalError, StoryDevelopmentError
from core.domain.ports.approval_repository_port import ApprovalRepositoryPort
from core.domain.ports.canon_repository_port import CanonRepositoryPort
from core.domain.ports.dialogue_generator_port import DialogueGeneratorPort
from core.domain.ports.story_generator_port import StoryGeneratorPort
from core.domain.ports.story_reviewer_port import StoryReviewerPort
from core.domain.value_objects.story_review import StoryDevelopmentResult


class StoryEngineService:
    def __init__(
        self,
        *,
        story_generator: StoryGeneratorPort,
        dialogue_generator: DialogueGeneratorPort,
        reviewers: tuple[StoryReviewerPort, ...],
        canon_repository: CanonRepositoryPort,
        approval_repository: ApprovalRepositoryPort,
        canon_validator: CanonValidationService | None = None,
    ) -> None:
        if not reviewers:
            raise StoryDevelopmentError(
                "StoryEngineService requires at least one reviewer."
            )
        self._story_generator = story_generator
        self._dialogue_generator = dialogue_generator
        self._reviewers = reviewers
        self._canon_repository = canon_repository
        self._approval_repository = approval_repository
        self._canon_validator = canon_validator or CanonValidationService()

    async def develop(self, brief: StoryBrief) -> StoryDevelopmentResult:
        direction = await self._canon_repository.get_creative_direction()
        world = await self._canon_repository.get_world_bible()
        characters = await self._canon_repository.get_character_bibles()
        if (
            direction.status is not BibleStatus.LOCKED
            or world.status is not BibleStatus.LOCKED
        ):
            raise StoryDevelopmentError(
                "Story development requires locked direction and world canon."
            )
        if not characters or any(
            not character.narrative_profile or not character.narrative_profile.locked
            for character in characters
        ):
            raise StoryDevelopmentError(
                "Story development requires locked character canon."
            )
        script = await self._story_generator.generate_episode(
            brief, direction, world, characters
        )
        script = await self._dialogue_generator.refine_dialogue(script, characters)
        if script.status is EpisodeScriptStatus.LOCKED:
            raise StoryDevelopmentError(
                "Providers must not return an already locked script."
            )
        canon_report = self._canon_validator.validate(
            script, direction, world, characters
        )
        reviews = tuple(
            await asyncio.gather(
                *(
                    reviewer.review(script, direction, world, characters)
                    for reviewer in self._reviewers
                )
            )
        )
        status = (
            EpisodeScriptStatus.READY_FOR_APPROVAL
            if canon_report.passed and all(review.passed for review in reviews)
            else EpisodeScriptStatus.CHANGES_REQUIRED
        )
        return StoryDevelopmentResult(script.with_status(status), canon_report, reviews)

    async def approve(
        self, result: StoryDevelopmentResult, *, approved_by: str
    ) -> EpisodeScript:
        if not result.ready_for_approval:
            raise StoryApprovalError(
                "A story with blocking review or canon issues cannot be approved."
            )
        locked = result.script.lock(approved_by)
        await self._approval_repository.record_story_approval(locked)
        return locked
