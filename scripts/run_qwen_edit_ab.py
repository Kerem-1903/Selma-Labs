"""Run reproducible Qwen Image Edit prompt variants through ComfyUI."""

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
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def workflow(config: dict[str, object], prompt: str, output_prefix: str) -> dict[str, object]:
    source_name = str(config["source_name"])
    return {
        "load": {"class_type": "LoadImage", "inputs": {"image": source_name}},
        "scale": {
            "class_type": "FluxKontextImageScale",
            "inputs": {"image": ["load", 0]},
        },
        "unet": {
            "class_type": "UNETLoader",
            "inputs": {
                "unet_name": str(config["model"]),
                "weight_dtype": "default",
            },
        },
        "sampling": {
            "class_type": "ModelSamplingAuraFlow",
            "inputs": {"model": ["unet", 0], "shift": 3.1},
        },
        "cfg_norm": {
            "class_type": "CFGNorm",
            "inputs": {"model": ["sampling", 0], "strength": 1.0},
        },
        "clip": {
            "class_type": "CLIPLoader",
            "inputs": {
                "clip_name": str(config["text_encoder"]),
                "type": "qwen_image",
                "device": "default",
            },
        },
        "vae": {
            "class_type": "VAELoader",
            "inputs": {"vae_name": str(config["vae"])},
        },
        "positive": {
            "class_type": "TextEncodeQwenImageEditPlus",
            "inputs": {
                "clip": ["clip", 0],
                "vae": ["vae", 0],
                "image1": ["scale", 0],
                "prompt": prompt,
            },
        },
        "negative": {
            "class_type": "TextEncodeQwenImageEditPlus",
            "inputs": {
                "clip": ["clip", 0],
                "vae": ["vae", 0],
                "image1": ["scale", 0],
                "prompt": "",
            },
        },
        "positive_reference": {
            "class_type": "FluxKontextMultiReferenceLatentMethod",
            "inputs": {
                "conditioning": ["positive", 0],
                "reference_latents_method": "index_timestep_zero",
            },
        },
        "negative_reference": {
            "class_type": "FluxKontextMultiReferenceLatentMethod",
            "inputs": {
                "conditioning": ["negative", 0],
                "reference_latents_method": "index_timestep_zero",
            },
        },
        "encode": {
            "class_type": "VAEEncode",
            "inputs": {"pixels": ["scale", 0], "vae": ["vae", 0]},
        },
        "sample": {
            "class_type": "KSampler",
            "inputs": {
                "model": ["cfg_norm", 0],
                "positive": ["positive_reference", 0],
                "negative": ["negative_reference", 0],
                "latent_image": ["encode", 0],
                "seed": int(config["seed"]),
                "steps": int(config["steps"]),
                "cfg": float(config["cfg"]),
                "sampler_name": "euler",
                "scheduler": "simple",
                "denoise": 1.0,
            },
        },
        "decode": {
            "class_type": "VAEDecode",
            "inputs": {"samples": ["sample", 0], "vae": ["vae", 0]},
        },
        "save": {
            "class_type": "SaveImage",
            "inputs": {"images": ["decode", 0], "filename_prefix": output_prefix},
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
    parser.add_argument("--server", default="http://127.0.0.1:8190")
    parser.add_argument("--variant")
    args = parser.parse_args()
    config = json.loads(args.config.read_text(encoding="utf-8"))
    destination = Path(config["destination"])
    destination.mkdir(parents=True, exist_ok=True)

    for variant in config["variants"]:
        name = str(variant["name"])
        if args.variant and name != args.variant:
            continue
        graph = workflow(config, str(variant["prompt"]), f"qwen_kaito_clean_ab_{name}")
        queued = request_json(f"{args.server}/prompt", {"prompt": graph})
        prompt_id = str(queued["prompt_id"])
        print(f"queued {name}: {prompt_id}", flush=True)
        record = wait_for_output(args.server, prompt_id)
        image_info = record["outputs"]["save"]["images"][0]
        source = Path(config["comfy_output"]) / str(image_info.get("subfolder", "")) / str(
            image_info["filename"]
        )
        target = destination / f"qwen-kaito-clean-ab-{name}.png"
        shutil.copy2(source, target)
        manifest = {
            "prompt_id": prompt_id,
            "variant": name,
            "prompt": variant["prompt"],
            "negative_prompt": "",
            "source_name": config["source_name"],
            "source_sha256": config["source_sha256"],
            "model": config["model"],
            "text_encoder": config["text_encoder"],
            "vae": config["vae"],
            "seed": config["seed"],
            "steps": config["steps"],
            "cfg": config["cfg"],
            "sampler": "euler",
            "scheduler": "simple",
            "denoise": 1.0,
            "reference_latents_method": "index_timestep_zero",
            "output": str(target.resolve()),
        }
        target.with_suffix(".json").write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        print(f"saved {name}: {target}", flush=True)


if __name__ == "__main__":
    main()
