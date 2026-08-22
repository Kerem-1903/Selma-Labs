"""A provider-independent description of the desired background visual."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class VisualIntent:
    """Describes what an asset search and vision scorer should optimize for.

    The value object intentionally contains no Pexels, Storyblocks, or model
    specific fields.  Providers can turn it into a query or a vision prompt,
    while application services can use the same intent for deterministic
    quality policy.
    """

    primary_keyword: str
    mood: str
    motion_type: str
    forbidden_concepts: tuple[str, ...] = ()
    secondary_keywords: tuple[str, ...] = ()
    start_ms: int = 0
    end_ms: int = 0
    narrative_role: str = "development"
    shot_type: str = "medium"
    narration_text: str = ""
    visual_job: str = "support_context"
    generation_prompt: str | None = None
    required_subjects: tuple[str, ...] = ()
    required_actions: tuple[str, ...] = ()
    required_relations: tuple[str, ...] = ()
    forbidden_dominant_subjects: tuple[str, ...] = ()
    explanation_mode: str = "stock"
    overlay_labels: tuple[str, ...] = ()
    explanatory_required: bool = False

    def __post_init__(self) -> None:
        """Normalize immutable policy values and reject unusable intents."""
        primary_keyword = self.primary_keyword.strip()
        mood = self.mood.strip().lower()
        motion_type = self.motion_type.strip().lower()
        forbidden_concepts = tuple(
            concept.strip().lower()
            for concept in self.forbidden_concepts
            if concept and concept.strip()
        )
        secondary_keywords = tuple(
            keyword.strip().lower()
            for keyword in self.secondary_keywords
            if keyword and keyword.strip()
        )
        narrative_role = self.narrative_role.strip().lower()
        shot_type = self.shot_type.strip().lower()
        narration_text = self.narration_text.strip()
        visual_job = self.visual_job.strip().lower()
        required_subjects = self._normalized_terms(self.required_subjects)
        required_actions = self._normalized_terms(self.required_actions)
        required_relations = self._normalized_terms(self.required_relations)
        forbidden_dominant_subjects = self._normalized_terms(
            self.forbidden_dominant_subjects
        )
        explanation_mode = self.explanation_mode.strip().lower()
        overlay_labels = tuple(
            label.strip() for label in self.overlay_labels if label and label.strip()
        )

        if not primary_keyword:
            raise ValueError("VisualIntent primary_keyword must not be empty.")
        if not mood:
            raise ValueError("VisualIntent mood must not be empty.")
        if not motion_type:
            raise ValueError("VisualIntent motion_type must not be empty.")
        if self.start_ms < 0:
            raise ValueError("VisualIntent start_ms must not be negative.")
        if self.end_ms < self.start_ms:
            raise ValueError("VisualIntent end_ms must not precede start_ms.")
        if not narrative_role:
            raise ValueError("VisualIntent narrative_role must not be empty.")
        if not shot_type:
            raise ValueError("VisualIntent shot_type must not be empty.")
        if not visual_job:
            raise ValueError("VisualIntent visual_job must not be empty.")
        if explanation_mode not in {"stock", "overlay", "diagram", "hybrid"}:
            raise ValueError(
                "VisualIntent explanation_mode must be stock, overlay, diagram, or hybrid."
            )
        if self.explanatory_required and explanation_mode == "stock":
            raise ValueError(
                "An explanatory VisualIntent cannot rely on stock footage alone."
            )
        if self.explanatory_required and not overlay_labels:
            raise ValueError(
                "An explanatory VisualIntent requires at least one overlay label."
            )

        object.__setattr__(self, "primary_keyword", primary_keyword)
        object.__setattr__(self, "mood", mood)
        object.__setattr__(self, "motion_type", motion_type)
        object.__setattr__(self, "forbidden_concepts", forbidden_concepts)
        object.__setattr__(self, "secondary_keywords", secondary_keywords)
        object.__setattr__(self, "narrative_role", narrative_role)
        object.__setattr__(self, "shot_type", shot_type)
        object.__setattr__(self, "narration_text", narration_text)
        object.__setattr__(self, "visual_job", visual_job)
        object.__setattr__(self, "required_subjects", required_subjects)
        object.__setattr__(self, "required_actions", required_actions)
        object.__setattr__(self, "required_relations", required_relations)
        object.__setattr__(self, "forbidden_dominant_subjects", forbidden_dominant_subjects)
        object.__setattr__(self, "explanation_mode", explanation_mode)
        object.__setattr__(self, "overlay_labels", overlay_labels)

    @property
    def duration_ms(self) -> int:
        """Return this storyboard beat's exact editorial duration."""
        return self.end_ms - self.start_ms

    @property
    def search_query(self) -> str:
        """Build a stock-search query with concept and cinematography context."""
        terms = (
            self.primary_keyword,
            *self.secondary_keywords,
            *self.required_subjects[:1],
            *self.required_actions[:1],
            self.shot_type.replace("-", " "),
        )
        return " ".join(dict.fromkeys(term for term in terms if term)).strip()

    @staticmethod
    def _normalized_terms(values: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(
            dict.fromkeys(
                value.strip().lower()
                for value in values
                if value and value.strip()
            )
        )
