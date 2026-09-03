from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from core.domain.entities.episode_script import EpisodeScript
from core.domain.value_objects.canon_validation import CanonValidationReport


class ReviewSeverity(str, Enum):
    NOTE = "NOTE"
    WARNING = "WARNING"
    BLOCKING = "BLOCKING"


@dataclass(frozen=True)
class StoryReviewIssue:
    code: str
    message: str
    severity: ReviewSeverity
    scene_id: str | None = None


@dataclass(frozen=True)
class StoryReviewReport:
    reviewer: str
    issues: tuple[StoryReviewIssue, ...] = ()

    @property
    def passed(self) -> bool:
        return all(
            issue.severity is not ReviewSeverity.BLOCKING for issue in self.issues
        )


@dataclass(frozen=True)
class StoryDevelopmentResult:
    script: EpisodeScript
    canon_report: CanonValidationReport
    reviews: tuple[StoryReviewReport, ...]

    @property
    def ready_for_approval(self) -> bool:
        return self.canon_report.passed and all(
            review.passed for review in self.reviews
        )
