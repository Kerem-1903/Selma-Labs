"""Model capability lock loading without provider side effects."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from core.domain.value_objects.model_capability import ModelCapability


def load_model_capabilities(path: str | Path) -> tuple[ModelCapability, ...]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("schema_version") != 1:
        raise ValueError("Model capability manifest must use schema version 1.")
    raw_models = payload.get("models")
    if not isinstance(raw_models, list) or not raw_models:
        raise ValueError("Model capability manifest must contain models.")
    models = tuple(
        ModelCapability.from_dict(item)
        for item in raw_models
        if isinstance(item, dict)
    )
    if len(models) != len(raw_models):
        raise ValueError("Model capability manifest contains an invalid model entry.")
    ids = [model.model_id for model in models]
    if len(ids) != len(set(ids)):
        raise ValueError("Model capability model IDs must be unique.")
    return models


def capabilities_for_task(models: tuple[ModelCapability, ...], task: str, *, target: str | None = None) -> tuple[ModelCapability, ...]:
    return tuple(
        model for model in models
        if task in model.allowed_tasks and (target is None or model.execution_target == target)
    )
