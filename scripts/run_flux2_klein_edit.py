"""Run a reproducible FLUX.2 Klein 4B image-edit test through ComfyUI."""

from __future__ import annotations

import argparse
import json
import shutil
import time
import urllib.request
from pathlib import Path


def request_json(url: str, payload: dict[str, object] | None = None) -> dict[str, object]:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.load(response)


def workflow(config: dict[str, object]) -> dict[str, object]:
    return {
        "load": {
            "class_type": "LoadImage",
            "inputs": {"image": str(config["source_name"])},
        },
        "scale": {
            "class_type": "ImageScaleToTotalPixels",
            "inputs": {
                "image": ["load", 0],
                "upscale_method": "nearest-exact",
                "megapixels": float(config.get("megapixels", 1.0)),
                "resolution_steps": 1,
            },
        },
        "size": {
            "class_type": "GetImageSize",
            "inputs": {"image": ["scale", 0]},
        },
        "unet": {
            "class_type": "UNETLoader",
            "inputs": {
                "unet_name": str(config["model"]),
                "weight_dtype": "default",
            },
        },
        "clip": {
            "class_type": "CLIPLoader",
            "inputs": {
                "clip_name": str(config["text_encoder"]),
                "type": "flux2",
                "device": "default",
            },
        },
        "vae": {
            "class_type": "VAELoader",
            "inputs": {"vae_name": str(config["vae"])},
        },
        "positive": {
            "class_type": "CLIPTextEncode",
            "inputs": {"clip": ["clip", 0], "text": str(config["prompt"])},
        },
        "negative": {
            "class_type": "ConditioningZeroOut",
            "inputs": {"conditioning": ["positive", 0]},
        },
        "encode": {
            "class_type": "VAEEncode",
            "inputs": {"pixels": ["scale", 0], "vae": ["vae", 0]},
        },
        "positive_reference": {
            "class_type": "ReferenceLatent",
            "inputs": {"conditioning": ["positive", 0], "latent": ["encode", 0]},
        },
        "negative_reference": {
            "class_type": "ReferenceLatent",
            "inputs": {"conditioning": ["negative", 0], "latent": ["encode", 0]},
        },
        "latent": {
            "class_type": "EmptyFlux2LatentImage",
            "inputs": {
                "width": ["size", 0],
                "height": ["size", 1],
                "batch_size": 1,
            },
        },
        "noise": {
            "class_type": "RandomNoise",
            "inputs": {"noise_seed": int(config["seed"])},
        },
        "guider": {
            "class_type": "CFGGuider",
            "inputs": {
                "model": ["unet", 0],
                "positive": ["positive_reference", 0],
                "negative": ["negative_reference", 0],
                "cfg": float(config.get("cfg", 1.0)),
            },
        },
        "sampler": {
            "class_type": "KSamplerSelect",
            "inputs": {"sampler_name": "euler"},
        },
        "sigmas": {
            "class_type": "Flux2Scheduler",
            "inputs": {
                "steps": int(config.get("steps", 4)),
                "width": ["size", 0],
                "height": ["size", 1],
            },
        },
        "sample": {
            "class_type": "SamplerCustomAdvanced",
            "inputs": {
                "noise": ["noise", 0],
                "guider": ["guider", 0],
                "sampler": ["sampler", 0],
                "sigmas": ["sigmas", 0],
                "latent_image": ["latent", 0],
            },
        },
        "decode": {
            "class_type": "VAEDecode",
            "inputs": {"samples": ["sample", 0], "vae": ["vae", 0]},
        },
        "save": {
            "class_type": "SaveImage",
            "inputs": {
                "images": ["decode", 0],
                "filename_prefix": str(config.get("output_prefix", "flux2_kaito")),
            },
        },
    }


def wait_for_output(server: str, prompt_id: str) -> dict[str, object]:
    while True:
        history = request_json(f"{server}/history/{prompt_id}")
        if prompt_id in history:
            record = history[prompt_id]
            status = record.get("status", {})
            if status.get("status_str") == "error":
                raise RuntimeError(json.dumps(status, indent=2))
            return record
        time.sleep(5)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("config", type=Path)
    parser.add_argument("--server", default="http://127.0.0.1:8188")
    args = parser.parse_args()
    config = json.loads(args.config.read_text(encoding="utf-8"))

    queued = request_json(f"{args.server}/prompt", {"prompt": workflow(config)})
    prompt_id = str(queued["prompt_id"])
    print(f"queued: {prompt_id}", flush=True)
    record = wait_for_output(args.server, prompt_id)
    image_info = record["outputs"]["save"]["images"][0]
    source = Path(config["comfy_output"]) / str(image_info.get("subfolder", "")) / str(
        image_info["filename"]
    )
    target = Path(config["destination"])
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)

    manifest = {
        **config,
        "prompt_id": prompt_id,
        "sampler": "euler",
        "output": str(target.resolve()),
    }
    target.with_suffix(".json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"saved: {target}", flush=True)


if __name__ == "__main__":
    main()
