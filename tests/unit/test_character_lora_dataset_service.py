from __future__ import annotations

import hashlib
import json

from PIL import Image

from core.application.services.character_lora_dataset_service import (
    CharacterLoraDatasetService,
)
from core.domain.entities.character_bible import CharacterBible


def _image(path, *, size=(1024, 1024), color="black"):
    Image.new("RGB", size, color).save(path)


def _approval(source, filenames, tmp_path):
    anchor = tmp_path / "anchor.png"
    _image(anchor, color="white")
    reviews = {
        filename: {
            "identity_score": 0.95,
            "anatomy_score": 0.90,
            "caption_matches": True,
            "human_approved": True,
            "reviewer": "test-reviewer",
            "content_hash": hashlib.sha256(
                (source / filename).read_bytes()
            ).hexdigest(),
        }
        for filename in filenames
    }
    manifest = tmp_path / "reviews.json"
    manifest.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "character_id": "akira",
                "approved_by": "test-reviewer",
                "canonical_anchor_sha256": hashlib.sha256(
                    anchor.read_bytes()
                ).hexdigest(),
                "reviews": reviews,
            }
        ),
        encoding="utf-8",
    )
    return anchor, manifest


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
    filenames = [path.name for path in source.iterdir()]
    anchor, reviews = _approval(source, filenames, tmp_path)

    report = service.build(
        source_dir=source,
        output_dir=output,
        character_id="akira",
        trigger_token="selma_akira_v1",
        review_manifest=reviews,
        canonical_anchor=anchor,
    )

    assert report.is_ready is True
    assert report.training_count == 3
    assert report.holdout_count == 1
    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["schema_version"] == 2
    assert manifest["training_approved"] is True
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


def test_service_captions_canonical_akira_identity_and_action_pose(tmp_path):
    source = tmp_path / "source"
    output = tmp_path / "dataset"
    source.mkdir()
    _image(source / "action-katana-ready-v1.png")
    service = CharacterLoraDatasetService(
        required_training_images=1,
        required_holdout_images=1,
    )

    report = service.build(
        source_dir=source,
        output_dir=output,
        character_id="akira",
        trigger_token="selma_akira_v1",
        character_bible=CharacterBible.akira(),
    )

    caption = report.samples[0].caption
    assert report.samples[0].view == "ACTION_KATANA_READY"
    assert "long straight black hair" in caption
    assert "single deep-red hair streak on the left-front section" in caption
    assert "two-handed katana ready stance" in caption
    assert "scar" not in caption


def test_service_fails_closed_without_per_image_review_and_anchor(tmp_path):
    source = tmp_path / "source"
    output = tmp_path / "dataset"
    source.mkdir()
    _image(source / "front-v1.png")
    service = CharacterLoraDatasetService(
        required_training_images=1, required_holdout_images=1
    )

    report = service.build(
        source_dir=source,
        output_dir=output,
        character_id="akira",
        trigger_token="selma_akira_v2",
    )

    assert report.dataset_complete is False
    assert report.training_approved is False
    assert "canonical_anchor_missing" in report.blockers
    assert "sample_reviews_missing" in report.blockers


def test_service_uses_specific_compound_view_captions(tmp_path):
    source = tmp_path / "source"
    output = tmp_path / "dataset"
    source.mkdir()
    _image(source / "full-body-profile-left.png")
    _image(source / "profile-right-full-body.png", color="blue")
    service = CharacterLoraDatasetService(
        required_training_images=1, required_holdout_images=1
    )

    report = service.build(
        source_dir=source,
        output_dir=output,
        character_id="akira",
        trigger_token="selma_akira_v2",
    )

    assert report.samples[0].view == "FULL_BODY_PROFILE_LEFT"
    assert "strict left profile" in report.samples[0].caption
    assert report.samples[1].view == "PROFILE_RIGHT_FULL_BODY"
    assert report.samples[1].split == "holdout"


def test_service_pads_portrait_images_without_cropping_character(tmp_path):
    source = tmp_path / "source"
    output = tmp_path / "dataset"
    source.mkdir()
    portrait = Image.new("RGB", (768, 1536), "white")
    portrait.putpixel((384, 0), (255, 0, 0))
    portrait.putpixel((384, 1535), (0, 0, 255))
    portrait.save(source / "full-body-v1.png")
    service = CharacterLoraDatasetService(
        output_size=1024,
        required_training_images=1,
        required_holdout_images=1,
    )

    report = service.build(
        source_dir=source,
        output_dir=output,
        character_id="akira",
        trigger_token="selma_akira_v1",
    )

    with Image.open(output / report.samples[0].image_path) as normalized:
        assert normalized.size == (1024, 1024)
        assert normalized.getpixel((512, 0))[0] > 200
        assert normalized.getpixel((512, 1023))[2] > 200
