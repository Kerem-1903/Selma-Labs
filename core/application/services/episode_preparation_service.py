"""Prepare an episode plan and enumerate the asset work still required."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from core.domain.value_objects.episode_director_plan import EpisodeDirectorPlan


@dataclass(frozen=True)
class EpisodePreparationJob:
    job_id: str
    kind: str
    status: str
    target_id: str
    required_ids: tuple[str, ...]
    asset_refs: dict[str, str]
    shot_ids: tuple[str, ...]
    reason: str
    attempts: int = 0
    last_error: str = ""

    def __post_init__(self) -> None:
        if self.status not in {"READY", "PLANNED", "IN_PROGRESS", "FAILED"}:
            raise ValueError(f"Unknown preparation job status: {self.status}")
        if self.attempts < 0:
            raise ValueError("Preparation job attempts cannot be negative.")

    def to_dict(self) -> dict[str, Any]:
        return {
            "job_id": self.job_id,
            "kind": self.kind,
            "status": self.status,
            "target_id": self.target_id,
            "required_ids": list(self.required_ids),
            "asset_refs": dict(self.asset_refs),
            "shot_ids": list(self.shot_ids),
            "reason": self.reason,
            "attempts": self.attempts,
            "last_error": self.last_error,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> EpisodePreparationJob:
        return cls(
            job_id=str(data.get("job_id", "")),
            kind=str(data.get("kind", "")),
            status=str(data.get("status", "PLANNED")),
            target_id=str(data.get("target_id", "")),
            required_ids=tuple(str(item) for item in data.get("required_ids", ())),
            asset_refs={str(key): str(value) for key, value in data.get("asset_refs", {}).items()}
            if isinstance(data.get("asset_refs", {}), Mapping)
            else {},
            shot_ids=tuple(str(item) for item in data.get("shot_ids", ())),
            reason=str(data.get("reason", "")),
            attempts=int(data.get("attempts", 0)),
            last_error=str(data.get("last_error", "")),
        )


@dataclass(frozen=True)
class EpisodePreparationResult:
    plan: EpisodeDirectorPlan
    jobs: tuple[EpisodePreparationJob, ...]

    @property
    def status(self) -> str:
        if all(job.status == "READY" for job in self.jobs):
            return "READY"
        if any(job.status == "FAILED" for job in self.jobs):
            return "BLOCKED"
        return "PLANNED"

    def to_dict(self) -> dict[str, Any]:
        ready_jobs = sum(job.status == "READY" for job in self.jobs)
        failed_jobs = sum(job.status == "FAILED" for job in self.jobs)
        return {
            "schema_version": 1,
            "preparation_status": self.status,
            "episode_id": self.plan.episode_id,
            "title": self.plan.title,
            "episode_director_plan": self.plan.to_dict(),
            "jobs": [job.to_dict() for job in self.jobs],
            "summary": {
                "job_count": len(self.jobs),
                "ready_job_count": ready_jobs,
                "planned_job_count": len(self.jobs) - ready_jobs - failed_jobs,
                "failed_job_count": failed_jobs,
                "scene_count": len(self.plan.scenes),
                "shot_count": sum(len(scene.shots) for scene in self.plan.scenes),
                "duration_frames": self.plan.duration_frames,
            },
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> EpisodePreparationResult:
        raw_plan = data.get("episode_director_plan", data)
        if not isinstance(raw_plan, Mapping):
            raise TypeError("Preparation manifest must contain an episode director plan.")
        raw_jobs = data.get("jobs", ())
        if not isinstance(raw_jobs, list):
            raise TypeError("Preparation manifest jobs must be a list.")
        return cls(
            plan=EpisodeDirectorPlan.from_dict(raw_plan),
            jobs=tuple(
                EpisodePreparationJob.from_dict(item)
                for item in raw_jobs
                if isinstance(item, Mapping)
            ),
        )


class EpisodePreparationService:
    """Turn a resolved director plan into a resumable internal asset checklist."""

    def prepare(
        self,
        plan: EpisodeDirectorPlan,
        *,
        previous: EpisodePreparationResult | None = None,
        retry_job_ids: tuple[str, ...] = (),
        failed_jobs: Mapping[str, str] | None = None,
    ) -> EpisodePreparationResult:
        previous_jobs = {job.job_id: job for job in previous.jobs} if previous else {}
        retry_ids = set(retry_job_ids)
        jobs: list[EpisodePreparationJob] = []
        for requirement in plan.character_requirements:
            missing = tuple(
                pose_id
                for pose_id in requirement.pose_ids
                if pose_id not in requirement.pose_asset_refs
            )
            base = EpisodePreparationJob(
                job_id=f"pose-pack-{requirement.character_id}",
                kind="POSE_PACK",
                status=requirement.status,
                target_id=requirement.character_id,
                required_ids=requirement.pose_ids,
                asset_refs=dict(requirement.pose_asset_refs),
                shot_ids=tuple(
                    shot.shot_id
                    for scene in plan.scenes
                    for shot in scene.shots
                    if shot.character_id == requirement.character_id
                ),
                reason=(
                    "All three pose assets are resolved."
                    if not missing
                    else "Generate the missing three-pose character pack."
                ),
            )
            jobs.append(self._resume_job(base, previous_jobs, retry_ids))

        failed_jobs = failed_jobs or {}
        background_groups: dict[str, list[Any]] = defaultdict(list)
        for background_requirement in plan.background_requirements:
            background_groups[background_requirement.location_id].append(
                background_requirement
            )
        for location_id, requirements in sorted(background_groups.items()):
            required_ids = tuple(dict.fromkeys(item.recipe_id for item in requirements))
            asset_refs = {
                item.recipe_id: item.asset_ref
                for item in requirements
                if item.asset_ref
            }
            ready = all(item.status == "READY" for item in requirements)
            base = EpisodePreparationJob(
                job_id=f"background-pack-{location_id}",
                kind="BACKGROUND_PACK",
                status="READY" if ready else "PLANNED",
                target_id=location_id,
                required_ids=required_ids,
                asset_refs=asset_refs,
                shot_ids=tuple(
                    dict.fromkeys(
                        shot_id
                        for item in requirements
                        for shot_id in item.shot_ids
                    )
                ),
                reason=(
                    "All required background assets are resolved."
                    if ready
                    else "Generate the required background coverage recipes."
                ),
            )
            jobs.append(self._resume_job(base, previous_jobs, retry_ids))
        if failed_jobs:
            jobs = [
                EpisodePreparationJob(
                    **{
                        **job.__dict__,
                        "status": "FAILED",
                        "reason": "Asset generation failed; inspect the recorded error and retry the job.",
                        "last_error": str(failed_jobs[job.job_id]),
                    }
                )
                if job.job_id in failed_jobs
                else job
                for job in jobs
            ]
        return EpisodePreparationResult(plan=plan, jobs=tuple(jobs))

    @staticmethod
    def _resume_job(
        current: EpisodePreparationJob,
        previous_jobs: Mapping[str, EpisodePreparationJob],
        retry_ids: set[str],
    ) -> EpisodePreparationJob:
        previous = previous_jobs.get(current.job_id)
        if previous is None:
            return current
        if current.status == "READY":
            return EpisodePreparationJob(
                **{**current.__dict__, "attempts": previous.attempts, "last_error": ""}
            )
        if previous.status == "FAILED" and current.job_id not in retry_ids:
            return EpisodePreparationJob(
                **{
                    **current.__dict__,
                    "status": "FAILED",
                    "attempts": previous.attempts,
                    "last_error": previous.last_error,
                    "reason": "Previous attempt failed; use --retry-job to retry it.",
                }
            )
        if current.job_id in retry_ids:
            return EpisodePreparationJob(
                **{
                    **current.__dict__,
                    "attempts": previous.attempts + 1,
                    "reason": "Retry requested; asset generation is ready to be dispatched.",
                }
            )
        return EpisodePreparationJob(
            **{
                **current.__dict__,
                "attempts": previous.attempts,
                "last_error": previous.last_error,
            }
        )
