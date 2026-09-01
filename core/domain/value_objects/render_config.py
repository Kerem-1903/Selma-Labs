from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from dataclasses import dataclass


@dataclass(frozen=True)
class RenderConfig:
    """Immutable settings for deterministic two-pass anime motion."""

    width: int
    height: int
    fps: int
    seed: int
    sampler_name: str
    pass1_denoise: float
    pass2_denoise: float
    sampling_steps: int = 16
    guidance_scale: float = 4.5

    def __post_init__(self) -> None:
        if self.width <= 0 or self.height <= 0:
            raise ValueError("Render dimensions must be greater than zero.")
        if not 1 <= self.fps <= 120:
            raise ValueError("Render fps must be between 1 and 120.")
        if self.seed < 0:
            raise ValueError("Render seed must not be negative.")
        if not self.sampler_name.strip():
            raise ValueError("Render sampler_name must not be empty.")
        if not 0.0 < self.pass2_denoise <= self.pass1_denoise <= 1.0:
            raise ValueError(
                "Two-pass denoise must satisfy 0 < pass2 <= pass1 <= 1."
            )
        if not 1 <= self.sampling_steps <= 150:
            raise ValueError("Render sampling_steps must be between 1 and 150.")
        if not 0.0 < self.guidance_scale <= 30.0:
            raise ValueError("Render guidance_scale must be between 0 and 30.")

    def compute_hash(
        self,
        prompt: str,
        character_tags: Iterable[str],
        *,
        source_key: str = "",
        frame_count: int | None = None,
    ) -> str:
        normalized_prompt = " ".join(prompt.split())
        if not normalized_prompt:
            raise ValueError("A render hash requires a non-empty prompt.")
        if frame_count is not None and frame_count <= 0:
            raise ValueError("Render hash frame_count must be greater than zero.")
        payload = {
            "character_tags": list(dict.fromkeys(tag.strip() for tag in character_tags if tag.strip())),
            "config": {
                "width": self.width,
                "height": self.height,
                "fps": self.fps,
                "seed": self.seed,
                "sampler_name": self.sampler_name,
                "pass1_denoise": self.pass1_denoise,
                "pass2_denoise": self.pass2_denoise,
                "sampling_steps": self.sampling_steps,
                "guidance_scale": self.guidance_scale,
            },
            "frame_count": frame_count,
            "prompt": normalized_prompt,
            "source_key": source_key,
        }
        serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()
