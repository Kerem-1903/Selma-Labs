from __future__ import annotations

import asyncio
import json

import pytest

from core.domain.value_objects.character_lora_training import (
    CharacterLoraTrainingRequest,
)
from infrastructure.providers.training.kohya_character_lora_trainer import (
    KohyaCharacterLoraTrainer,
)


def _layout(tmp_path, *, ready=True):
    scripts = tmp_path / "sd-scripts"
    (scripts / "venv/Scripts").mkdir(parents=True)
    (scripts / "venv/Scripts/accelerate.exe").write_bytes(b"fake")
    (scripts / "sdxl_train_network.py").write_text("", encoding="utf-8")
    dataset = tmp_path / "dataset"
    (dataset / "train").mkdir(parents=True)
    (dataset / "manifest.json").write_text(
        json.dumps({"character_id": "nova", "is_ready": ready}),
        encoding="utf-8",
    )
    base_model = tmp_path / "base.safetensors"
    base_model.write_bytes(b"base")
    output = tmp_path / "model"
    return scripts, dataset, base_model, output


def test_trainer_builds_safe_8gb_command_and_returns_model(tmp_path, monkeypatch):
    scripts, dataset, base_model, output = _layout(tmp_path)
    request = CharacterLoraTrainingRequest(
        character_id="nova",
        dataset_dir=dataset,
        base_model_path=base_model,
        output_dir=output,
        model_name="selma-nova-v1",
    )
    trainer = KohyaCharacterLoraTrainer(scripts)
    captured = {}

    def fake_run(command, cwd, log_path):
        captured["command"] = command
        captured["cwd"] = cwd
        log_path.write_text("complete", encoding="utf-8")
        (output / "selma-nova-v1.safetensors").write_bytes(b"trained")
        return 0

    monkeypatch.setattr(trainer, "_run", fake_run)
    result = asyncio.run(trainer.train(request))

    assert result.model_path.name == "selma-nova-v1.safetensors"
    assert "--network_train_unet_only" in captured["command"]
    assert "--gradient_checkpointing" in captured["command"]
    assert "--cache_latents_to_disk" in captured["command"]
    assert "--max_train_steps=240" in captured["command"]
    assert 'image_dir = "' in (dataset / "dataset.toml").read_text(encoding="utf-8")


def test_trainer_rejects_dataset_that_failed_readiness_gate(tmp_path):
    scripts, dataset, base_model, output = _layout(tmp_path, ready=False)
    trainer = KohyaCharacterLoraTrainer(scripts)
    request = CharacterLoraTrainingRequest(
        character_id="nova",
        dataset_dir=dataset,
        base_model_path=base_model,
        output_dir=output,
        model_name="selma-nova-v1",
    )

    with pytest.raises(ValueError, match="readiness gate"):
        asyncio.run(trainer.train(request))
