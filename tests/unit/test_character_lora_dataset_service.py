from __future__ import annotations

import json

from PIL import Image

from core.application.services.character_lora_dataset_service import (
    CharacterLoraDatasetService,
)


def _image(path, *, size=(1024, 1024), color="black"):
    Image.new("RGB", size, color).save(path)


def test_service_builds_versioned_dataset_and_keeps_holdout_separate(tmp_path):
    source = tmp_path / "source"
    output = tmp_path / "dataset"
    source.mkdir()
    _image(source / "front-v1.png", color="black")
    _image(source / "face-closeup-v1.png", color="red")
    _image(source / "profile-left-v1.png", color="green")
    _image(source / "profile-right-v1.png", color="blue")
    service = CharacterLoraDatasetService(
        required_training_images=3,
        required_holdout_images=1,
    )

    report = service.build(
        source_dir=source,
        output_dir=output,
        character_id="akira",
        trigger_token="selma_akira_v1",
    )

    assert report.is_ready is True
    assert report.training_count == 3
    assert report.holdout_count == 1
    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["schema_version"] == 1
    assert manifest["rights_status"] == "original_character"
    assert "selma_akira_v1" in (output / "train/akira-0001.txt").read_text()
    assert (output / "holdout/akira-0004.png").is_file()


def test_service_rejects_small_unknown_and_duplicate_images(tmp_path):
    source = tmp_path / "source"
    output = tmp_path / "dataset"
    source.mkdir()
    _image(source / "front-v1.png", color="black")
    (source / "front-v2.png").write_bytes((source / "front-v1.png").read_bytes())
    _image(source / "profile-left-v1.png", size=(256, 256), color="red")
    _image(source / "akira-master-sheet-v1.png", color="green")
    _image(source / "mystery-v1.png", color="yellow")
    service = CharacterLoraDatasetService()

    report = service.build(
        source_dir=source,
        output_dir=output,
        character_id="akira",
        trigger_token="selma_akira_v1",
    )

    assert report.is_ready is False
    assert report.duplicate_files == ("front-v2.png",)
    assert {item["reason"] for item in report.rejected_files} == {
        "resolution_too_small",
        "unknown_view",
    }
