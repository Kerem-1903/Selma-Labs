from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Any, Optional
import datetime
import uuid

class CandidateStatus(Enum):
    PENDING = "PENDING"
    ACCEPTED = "ACCEPTED"
    REVISED = "REVISED"
    REJECTED = "REJECTED"
    PUBLISHED = "PUBLISHED"

class CandidateGroup(Enum):
    TRAIN = "TRAIN"
    VALIDATION = "VALIDATION"
    HOLDOUT = "HOLDOUT"

@dataclass
class CandidateScores:
    hook: float = 0.0
    accuracy: float = 0.0
    flow: float = 0.0
    originality: float = 0.0
    duration: float = 0.0

    def to_dict(self) -> Dict[str, float]:
        return {
            "hook": self.hook,
            "accuracy": self.accuracy,
            "flow": self.flow,
            "originality": self.originality,
            "duration": self.duration,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CandidateScores":
        if not data:
            return cls()
        return cls(
            hook=float(data.get("hook", 0.0)),
            accuracy=float(data.get("accuracy", 0.0)),
            flow=float(data.get("flow", 0.0)),
            originality=float(data.get("originality", 0.0)),
            duration=float(data.get("duration", 0.0)),
        )

@dataclass
class ScriptCandidate:
    id: str
    topic: str
    language: str
    target_duration_seconds: int
    target_audience: str
    raw_sources: str
    verified_claims: str
    model_info: str
    prompt_version: str
    initial_script: str
    revised_script: Optional[str] = None
    status: CandidateStatus = CandidateStatus.PENDING
    reasoning: str = ""
    scores: CandidateScores = field(default_factory=CandidateScores)
    content_hash: str = ""
    group: CandidateGroup = CandidateGroup.TRAIN
    retention_score: Optional[float] = None
    view_count: Optional[int] = None
    created_at: str = field(default_factory=lambda: datetime.datetime.now(datetime.timezone.utc).isoformat())

    @classmethod
    def create(
        cls,
        topic: str,
        language: str,
        target_duration_seconds: int,
        target_audience: str,
        raw_sources: str,
        verified_claims: str,
        model_info: str,
        prompt_version: str,
        initial_script: str,
        content_hash: str,
        group: CandidateGroup = CandidateGroup.TRAIN,
    ) -> "ScriptCandidate":
        return cls(
            id=str(uuid.uuid4()),
            topic=topic,
            language=language,
            target_duration_seconds=target_duration_seconds,
            target_audience=target_audience,
            raw_sources=raw_sources,
            verified_claims=verified_claims,
            model_info=model_info,
            prompt_version=prompt_version,
            initial_script=initial_script,
            content_hash=content_hash,
            group=group
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "topic": self.topic,
            "language": self.language,
            "target_duration_seconds": self.target_duration_seconds,
            "target_audience": self.target_audience,
            "raw_sources": self.raw_sources,
            "verified_claims": self.verified_claims,
            "model_info": self.model_info,
            "prompt_version": self.prompt_version,
            "initial_script": self.initial_script,
            "revised_script": self.revised_script,
            "status": self.status.value,
            "reasoning": self.reasoning,
            "scores": self.scores.to_dict(),
            "content_hash": self.content_hash,
            "group": self.group.value,
            "retention_score": self.retention_score,
            "view_count": self.view_count,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ScriptCandidate":
        return cls(
            id=data["id"],
            topic=data["topic"],
            language=data.get("language", "en"),
            target_duration_seconds=data.get("target_duration_seconds", 0),
            target_audience=data.get("target_audience", ""),
            raw_sources=data.get("raw_sources", ""),
            verified_claims=data.get("verified_claims", ""),
            model_info=data.get("model_info", ""),
            prompt_version=data.get("prompt_version", ""),
            initial_script=data.get("initial_script", ""),
            revised_script=data.get("revised_script"),
            status=CandidateStatus(data.get("status", CandidateStatus.PENDING.value)),
            reasoning=data.get("reasoning", ""),
            scores=CandidateScores.from_dict(data.get("scores", {})),
            content_hash=data.get("content_hash", ""),
            group=CandidateGroup(data.get("group", CandidateGroup.TRAIN.value)),
            retention_score=data.get("retention_score"),
            view_count=data.get("view_count"),
            created_at=data.get("created_at", datetime.datetime.now(datetime.timezone.utc).isoformat()),
        )
