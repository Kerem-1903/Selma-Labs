from __future__ import annotations

import json
from pathlib import Path

import pytest

from cli.main import build_parser
from core.application.services.character_quality_benchmark_service import (
    CharacterQualityBenchmarkService,
)
from core.domain.exceptions import PreProductionValidationError
from core.domain.value_objects.character_quality_benchmark import (
    CharacterQualityBenchmark,
)

ROOT = Path(__file__).parents[2]
BENCHMARK = ROOT / "config" / "character_benchmarks" / "akira-quality-v1.json"


def test_akira_quality_benchmark_is_hash_and_dimension_locked():
    benchmark = CharacterQualityBenchmarkService(ROOT).validate(BENCHMARK)

    assert benchmark.benchmark_id == "akira-quality-v1"
    assert benchmark.usage == "quality_and_style_evaluation_only"
    assert benchmark.width == 1024
    assert benchmark.height == 1024
    assert len(benchmark.human_criteria) == 5
    assert sum(item.weight for item in benchmark.human_criteria) == pytest.approx(1.0)
    assert any("identity reference" in item for item in benchmark.prohibited_transfer)


def test_character_cli_accepts_benchmark_validation_command():
    arguments = build_parser().parse_args(
        ["character", "benchmark-validate", "--benchmark", str(BENCHMARK)]
    )

    assert arguments.character_command == "benchmark-validate"
    assert Path(arguments.benchmark) == BENCHMARK


def test_character_cli_accepts_text_only_model_tournament():
    arguments = build_parser().parse_args(
        [
            "character",
            "benchmark-run",
            "--benchmark",
            str(BENCHMARK),
            "--brief",
            "assets/character_creation_briefs/kaito.json",
            "--model-lock",
            "models.lock.json",
            "--model-lock",
            "config/model_profiles/illustrious-xl-v2.lock.json",
            "--output",
            "output/production/review/tournament.json",
        ]
    )

    assert arguments.character_command == "benchmark-run"
    assert arguments.count == 3
    assert arguments.model_locks == [
        "models.lock.json",
        "config/model_profiles/illustrious-xl-v2.lock.json",
    ]


def test_benchmark_rejects_weights_that_do_not_total_one():
    payload = json.loads(BENCHMARK.read_text(encoding="utf-8"))
    payload["human_criteria"][0]["weight"] = 0.10

    with pytest.raises(PreProductionValidationError, match="total 1.0"):
        CharacterQualityBenchmark.from_dict(payload)


def test_benchmark_service_rejects_tampered_reference(tmp_path):
    benchmark_dir = tmp_path / "config" / "character_benchmarks"
    asset_dir = tmp_path / "assets" / "quality_benchmarks" / "akira-v1"
    benchmark_dir.mkdir(parents=True)
    asset_dir.mkdir(parents=True)
    payload = json.loads(BENCHMARK.read_text(encoding="utf-8"))
    (benchmark_dir / "benchmark.json").write_text(
        json.dumps(payload), encoding="utf-8"
    )
    (asset_dir / "akira-quality-reference.png").write_bytes(b"changed")

    with pytest.raises(ValueError, match="hash mismatch"):
        CharacterQualityBenchmarkService(tmp_path).validate(
            benchmark_dir / "benchmark.json"
        )
