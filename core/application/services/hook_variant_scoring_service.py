"""Deterministically rank source-grounded hook candidates before production."""
from __future__ import annotations

import hashlib
import re
import unicodedata

from core.domain.exceptions import NarrativeQualityError
from core.domain.value_objects.hook_variant import HookExperiment, HookVariantScore


_STOPWORDS = {
    "a", "an", "and", "are", "can", "does", "for", "from", "how", "is",
    "of", "the", "this", "to", "what", "why", "ve", "bir", "bu", "için",
    "ile", "nasıl", "neden", "ne",
}
_CURIOSITY_MARKERS = (
    "?", "what if", "why", "how", "but", "yet", "never", "actually",
    "imagine", "secret", "neden", "nasıl", "ama", "oysa", "hiç",
)
_CLICKBAIT_PHRASES = (
    "you won't believe", "will shock you", "mind blowing", "insane truth",
    "inanamayacaksın", "şok olacaksın", "aklını başından alacak",
)


class HookVariantScoringService:
    maximum_score = 15
    minimum_publishable_score = 11

    def rank(self, *, topic: str, variants: list[str] | tuple[str, ...]) -> tuple[HookVariantScore, ...]:
        cleaned = list(dict.fromkeys(" ".join(text.split()) for text in variants if text.strip()))
        if len(cleaned) < 2:
            raise ValueError("At least two distinct hook variants are required.")
        scored = [self._score(topic, text) for text in cleaned]
        return tuple(sorted(scored, key=lambda item: (-item.score, len(item.text), item.text)))

    def prepare_experiment(
        self,
        *,
        topic: str,
        variants: list[str] | tuple[str, ...],
        control_index: int = 0,
    ) -> HookExperiment:
        if not 0 <= control_index < len(variants):
            raise ValueError("control_index is outside the supplied variants.")
        ranked = self.rank(topic=topic, variants=variants)
        control_text = " ".join(variants[control_index].split())
        control = next(item for item in ranked if item.text == control_text)
        selected = ranked[0]
        if selected.score < self.minimum_publishable_score:
            raise NarrativeQualityError(
                f"No hook variant reached {self.minimum_publishable_score}/{self.maximum_score}."
            )
        fingerprint = "\n".join([self._normalize(topic), *(self._normalize(v.text) for v in ranked)])
        return HookExperiment(
            experiment_id=f"hook-{hashlib.sha256(fingerprint.encode('utf-8')).hexdigest()[:12]}",
            topic=topic.strip(),
            principal_variable="opening_hook",
            control=control,
            selected=selected,
            ranked_variants=ranked,
        )

    def _score(self, topic: str, text: str) -> HookVariantScore:
        normalized = self._normalize(text)
        words = text.split()
        topic_tokens = self._tokens(topic)
        hook_tokens = self._tokens(text)
        overlap = len(topic_tokens & hook_tokens)
        strengths: list[str] = []
        issues: list[str] = []
        score = 0

        if overlap >= 2:
            score += 4
            strengths.append("specific_to_topic")
        elif overlap == 1:
            score += 2
            strengths.append("mentions_topic")
        else:
            issues.append("weak_topic_connection")

        curiosity = any(self._contains_marker(normalized, marker) for marker in _CURIOSITY_MARKERS)
        if curiosity:
            score += 3
            strengths.append("curiosity_gap")
        else:
            issues.append("no_curiosity_or_consequence")

        if 4 <= len(words) <= 12:
            score += 3
            strengths.append("mobile_brevity")
        elif 3 <= len(words) <= 18:
            score += 2
        elif len(words) <= 22:
            score += 1
        else:
            issues.append("too_long")

        concrete = bool(re.search(r"\d", text)) or overlap >= 1 or any(
            token in normalized for token in ("after", "before", "inside", "without", "sonra", "önce")
        )
        if concrete:
            score += 3
            strengths.append("concrete_promise")
        else:
            issues.append("abstract_promise")

        clickbait = any(phrase in normalized for phrase in _CLICKBAIT_PHRASES)
        if not clickbait and "..." not in text:
            score += 2
            strengths.append("integrity_safe")
        else:
            issues.append("clickbait_or_trailing_tease")

        hook_type = (
            "question" if "?" in text else
            "contrast" if any(
                self._contains_marker(normalized, marker)
                for marker in ("but", "yet", "ama", "oysa")
            ) else
            "number" if re.search(r"\d", text) else
            "consequence"
        )
        return HookVariantScore(
            text=text,
            hook_type=hook_type,
            score=score,
            maximum_score=self.maximum_score,
            strengths=tuple(strengths),
            issues=tuple(issues),
        )

    @staticmethod
    def _tokens(text: str) -> set[str]:
        return {
            HookVariantScoringService._stem(token)
            for token in re.findall(
                r"[a-z0-9çğıöşü]+",
                HookVariantScoringService._normalize(text),
            )
            if len(token) > 2 and token not in _STOPWORDS
        }

    @staticmethod
    def _stem(token: str) -> str:
        """Normalize only safe English inflections; this is not semantic rewriting."""
        if len(token) > 5 and token.endswith("ies"):
            return f"{token[:-3]}y"
        if len(token) > 4 and token.endswith("s") and not token.endswith("ss"):
            return token[:-1]
        return token

    @staticmethod
    def _contains_marker(text: str, marker: str) -> bool:
        if marker == "?":
            return marker in text
        return bool(re.search(rf"(?<!\w){re.escape(marker)}(?!\w)", text))

    @staticmethod
    def _normalize(text: str) -> str:
        return " ".join(unicodedata.normalize("NFKC", text or "").casefold().split())
