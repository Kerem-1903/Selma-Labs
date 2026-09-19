"""Build a six-view FLUX.2 Klein turnaround from one approved source image.

DEPRECATED: this script exists only to reproduce the first FLUX.2 diagnostic
run byte-for-byte. It duplicates the ComfyUI graph that now lives in
``assets/comfyui_flux2_klein_edit_workflow.json`` and is driven by the
``comfyui:flux2-edit`` provider, so it bypasses the model lock, preflight,
watchdog, QC gate, production manifest, drift report, and view-pack approval.

Use the product path instead:

    python -m cli.main character turnaround \
        --brief assets/character_creation_briefs/kaito-quality-benchmark-v1.json \
        --approval output/production/characters/kaito/v5/canonical-approval.json \
        --manifest output/production/characters/kaito/v5/view-pack.json \
        --seeds 3

with ``keyframe_generation_provider = "comfyui-flux2-edit"``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path

from core.application.services.character_identity_prompt_service import (
    CharacterIdentityPromptService,
)
from core.domain.value_objects.character_creation_brief import CharacterCreationBrief
from scripts.run_flux2_klein_edit import request_json, wait_for_output, workflow

GENERATED_VIEWS = (
    "THREE_QUARTER_LEFT",
    "PROFILE_LEFT",
    "BACK",
    "PROFILE_RIGHT",
    "THREE_QUARTER_RIGHT",
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("config", type=Path)
    parser.add_argument("--server", default="http://127.0.0.1:8188")
    args = parser.parse_args()

    config = json.loads(args.config.read_text(encoding="utf-8"))
    brief = CharacterCreationBrief.from_dict(
        json.loads(Path(config["brief_path"]).read_text(encoding="utf-8"))
    )
    prompt_service = CharacterIdentityPromptService()
    destination = Path(config["destination"])
    destination.mkdir(parents=True, exist_ok=True)
    source = Path(config["source_path"])

    front_target = destination / "front.png"
    shutil.copy2(source, front_target)
    assets: list[dict[str, object]] = [
        {
            "view": "FRONT",
            "generated": False,
            "seed": None,
            "prompt": None,
            "output": str(front_target.resolve()),
            "sha256": sha256(front_target),
        }
    ]

    for view in GENERATED_VIEWS:
        prompt = prompt_service.build_flux2_edit_prompt(brief, view=view)
        slug = view.casefold().replace("_", "-")
        target = destination / f"{slug}.png"
        run_config = {
            **config,
            "prompt": prompt,
            "view": view,
            "destination": str(target),
            "output_prefix": f"flux2_kaito_turnaround_{slug}",
        }
        queued = request_json(
            f"{args.server}/prompt", {"prompt": workflow(run_config)}
        )
        prompt_id = str(queued["prompt_id"])
        print(f"queued {view}: {prompt_id}", flush=True)
        record = wait_for_output(args.server, prompt_id)
        image_info = record["outputs"]["save"]["images"][0]
        rendered = (
            Path(config["comfy_output"])
            / str(image_info.get("subfolder", ""))
            / str(image_info["filename"])
        )
        shutil.copy2(rendered, target)
        asset = {
            "view": view,
            "generated": True,
            "seed": int(config["seed"]),
            "prompt": prompt,
            "prompt_id": prompt_id,
            "output": str(target.resolve()),
            "sha256": sha256(target),
        }
        target.with_suffix(".json").write_text(
            json.dumps({**run_config, **asset}, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        assets.append(asset)
        print(f"saved {view}: {target}", flush=True)

    manifest = {
        "schema_version": 1,
        "workflow": "flux2-klein-single-source-turnaround-v1",
        "prompt_contract": "source-led-delta-edit-v1",
        "brief_path": str(Path(config["brief_path"]).resolve()),
        "source_path": str(source.resolve()),
        "source_sha256": sha256(source),
        "model": config["model"],
        "text_encoder": config["text_encoder"],
        "vae": config["vae"],
        "seed": config["seed"],
        "steps": config["steps"],
        "cfg": config["cfg"],
        "megapixels": config["megapixels"],
        "assets": assets,
    }
    (destination / "pack-manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"pack saved: {destination}", flush=True)


if __name__ == "__main__":
    main()
