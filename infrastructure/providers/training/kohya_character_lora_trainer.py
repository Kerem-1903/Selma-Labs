from __future__ import annotations

import asyncio
import json
import subprocess
from pathlib import Path

from core.domain.ports.character_lora_trainer_port import CharacterLoraTrainerPort
from core.domain.value_objects.character_lora_training import (
    CharacterLoraTrainingRequest,
    CharacterLoraTrainingResult,
)


class KohyaCharacterLoraTrainer(CharacterLoraTrainerPort):
    """Run the official sd-scripts SDXL LoRA trainer with an 8 GB profile."""

    def __init__(self, sd_scripts_dir: str | Path) -> None:
        self._sd_scripts_dir = Path(sd_scripts_dir).resolve()

    async def train(
        self, request: CharacterLoraTrainingRequest
    ) -> CharacterLoraTrainingResult:
        self._validate_inputs(request)
        request.output_dir.mkdir(parents=True, exist_ok=True)
        dataset_config = request.dataset_dir / "dataset.toml"
        dataset_config.write_text(self._dataset_toml(request), encoding="utf-8")
        log_path = request.output_dir / f"{request.model_name}.training.log"
        command = self._command(request, dataset_config)
        return_code = await asyncio.to_thread(
            self._run, command, self._sd_scripts_dir, log_path
        )
        if return_code != 0:
            raise RuntimeError(
                f"LoRA training failed with exit code {return_code}; see {log_path}."
            )
        model_path = request.output_dir / f"{request.model_name}.safetensors"
        if not model_path.is_file() or model_path.stat().st_size == 0:
            raise RuntimeError("LoRA training completed without a model artifact.")
        return CharacterLoraTrainingResult(
            character_id=request.character_id,
            model_path=model_path.resolve(),
            log_path=log_path.resolve(),
            max_train_steps=request.max_train_steps,
            command_name="sd-scripts/sdxl_train_network.py",
        )

    def _validate_inputs(self, request: CharacterLoraTrainingRequest) -> None:
        manifest_path = request.dataset_dir / "manifest.json"
        if not manifest_path.is_file():
            raise FileNotFoundError(f"LoRA dataset manifest not found: {manifest_path}")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest.get("character_id") != request.character_id:
            raise ValueError(
                "LoRA dataset character does not match the training request."
            )
        if int(manifest.get("schema_version", 0)) < 2:
            raise ValueError(
                "Legacy LoRA dataset manifests cannot pass the V2 quality gate."
            )
        if (
            manifest.get("is_ready") is not True
            or manifest.get("training_approved") is not True
        ):
            raise ValueError("LoRA dataset has not passed its V2 quality gate.")
        if not (request.dataset_dir / "train").is_dir():
            raise FileNotFoundError("LoRA dataset train directory was not found.")
        if not request.base_model_path.is_file():
            raise FileNotFoundError(f"Base model not found: {request.base_model_path}")
        for required in (
            self._sd_scripts_dir / "venv" / "Scripts" / "accelerate.exe",
            self._sd_scripts_dir / "sdxl_train_network.py",
        ):
            if not required.is_file():
                raise FileNotFoundError(
                    f"sd-scripts training dependency not found: {required}"
                )

    def _command(
        self, request: CharacterLoraTrainingRequest, dataset_config: Path
    ) -> list[str]:
        accelerate = self._sd_scripts_dir / "venv" / "Scripts" / "accelerate.exe"
        return [
            str(accelerate),
            "launch",
            "--num_cpu_threads_per_process=2",
            str(self._sd_scripts_dir / "sdxl_train_network.py"),
            f"--pretrained_model_name_or_path={request.base_model_path.resolve()}",
            f"--dataset_config={dataset_config.resolve()}",
            f"--output_dir={request.output_dir.resolve()}",
            f"--output_name={request.model_name}",
            "--save_model_as=safetensors",
            "--network_module=networks.lora",
            f"--network_dim={request.network_dim}",
            f"--network_alpha={request.network_alpha}",
            "--network_train_unet_only",
            "--learning_rate=0.0001",
            "--optimizer_type=AdamW8bit",
            "--lr_scheduler=cosine",
            f"--max_train_steps={request.max_train_steps}",
            "--mixed_precision=fp16",
            "--save_precision=fp16",
            "--cache_latents",
            "--cache_latents_to_disk",
            "--cache_text_encoder_outputs",
            "--cache_text_encoder_outputs_to_disk",
            "--gradient_checkpointing",
            "--save_every_n_steps=80",
            f"--seed={request.seed}",
        ]

    @staticmethod
    def _dataset_toml(request: CharacterLoraTrainingRequest) -> str:
        image_dir = (request.dataset_dir / "train").resolve().as_posix()
        return (
            '[general]\ncaption_extension = ".txt"\nshuffle_caption = false\n'
            "keep_tokens = 1\n\n[[datasets]]\nresolution = 1024\nbatch_size = 1\n"
            "enable_bucket = true\nbucket_no_upscale = true\nbucket_reso_steps = 32\n\n"
            f'  [[datasets.subsets]]\n  image_dir = "{image_dir}"\n  num_repeats = 10\n'
        )

    @staticmethod
    def _run(command: list[str], cwd: Path, log_path: Path) -> int:
        with log_path.open("w", encoding="utf-8") as log_file:
            completed = subprocess.run(
                command,
                cwd=cwd,
                stdin=subprocess.DEVNULL,
                stdout=log_file,
                stderr=subprocess.STDOUT,
                check=False,
                text=True,
            )
        return completed.returncode
