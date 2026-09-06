"""Load and integrity-check character quality benchmarks."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from PIL import Image, UnidentifiedImageError

from core.domain.value_objects.character_quality_benchmark import (
    CharacterQualityBenchmark,
)


class CharacterQualityBenchmarkService:
    def __init__(self, workspace_root: str | Path) -> None:
        self._workspace_root = Path(workspace_root).resolve()

    def validate(self, benchmark_path: str | Path) -> CharacterQualityBenchmark:
        source = Path(benchmark_path).resolve()
        source.relative_to(self._workspace_root)
        raw = json.loads(source.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise TypeError("Character quality benchmark must contain an object.")
        benchmark = CharacterQualityBenchmark.from_dict(raw)
        asset = (self._workspace_root / benchmark.reference_asset).resolve()
        asset.relative_to(self._workspace_root)
        data = asset.read_bytes()
        if hashlib.sha256(data).hexdigest() != benchmark.reference_sha256:
            raise ValueError("Character quality benchmark reference hash mismatch.")
        try:
            with Image.open(asset) as image:
                dimensions = image.size
                image.verify()
        except (UnidentifiedImageError, OSError) as error:
            raise ValueError(
                "Character quality benchmark reference is not a valid image."
            ) from error
        if dimensions != (benchmark.width, benchmark.height):
            raise ValueError("Character quality benchmark dimensions mismatch.")
        return benchmark
