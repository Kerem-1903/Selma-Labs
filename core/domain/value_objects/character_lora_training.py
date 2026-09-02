from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class CharacterLoraTrainingRequest:
    character_id: str
    dataset_dir: Path
    base_model_path: Path
    output_dir: Path
    model_name: str
    max_train_steps: int = 240
    network_dim: int = 16
    network_alpha: int = 8
    seed: int = 1903

    def __post_init__(self) -> None:
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", self.character_id):
            raise ValueError("LoRA training requires a portable character ID.")
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", self.model_name):
            raise ValueError("LoRA model name must be a portable filename stem.")
        if (
            self.max_train_steps <= 0
            or self.network_dim <= 0
            or self.network_alpha <= 0
        ):
            raise ValueError("LoRA training numeric settings must be positive.")
        if self.network_alpha > self.network_dim:
            raise ValueError("LoRA network_alpha cannot exceed network_dim.")


@dataclass(frozen=True)
class CharacterLoraTrainingResult:
    character_id: str
    model_path: Path
    log_path: Path
    max_train_steps: int
    command_name: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "character_id": self.character_id,
            "model_path": str(self.model_path),
            "log_path": str(self.log_path),
            "max_train_steps": self.max_train_steps,
            "command_name": self.command_name,
        }
