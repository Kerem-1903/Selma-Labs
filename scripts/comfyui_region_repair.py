"""Repair a user-supplied image region through the local ComfyUI API."""

from __future__ import annotations

import argparse
import asyncio
import time
from pathlib import Path
from typing import Any

import aiohttp


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Inpaint only the white area of a grayscale mask."
    )
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--mask", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--prompt", required=True)
    parser.add_argument("--negative", default="red hair, colored hair, artifacts")
    parser.add_argument("--checkpoint", required=True)
    parser.add_argument("--api-url", default="http://127.0.0.1:8188")
    parser.add_argument("--seed", type=int, default=1903)
    parser.add_argument("--steps", type=int, default=24)
    parser.add_argument("--cfg", type=float, default=5.0)
    parser.add_argument("--denoise", type=float, default=0.4)
    parser.add_argument("--timeout", type=float, default=300.0)
    return parser


def _workflow(arguments: argparse.Namespace, image: str, mask: str) -> dict[str, Any]:
    return {
        "1": {
            "class_type": "CheckpointLoaderSimple",
            "inputs": {"ckpt_name": arguments.checkpoint},
        },
        "2": {"class_type": "LoadImage", "inputs": {"image": image}},
        "3": {
            "class_type": "LoadImageMask",
            "inputs": {"image": mask, "channel": "red"},
        },
        "4": {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": arguments.prompt, "clip": ["1", 1]},
        },
        "5": {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": arguments.negative, "clip": ["1", 1]},
        },
        "6": {
            "class_type": "InpaintModelConditioning",
            "inputs": {
                "positive": ["4", 0],
                "negative": ["5", 0],
                "vae": ["1", 2],
                "pixels": ["2", 0],
                "mask": ["3", 0],
                "noise_mask": True,
            },
        },
        "7": {
            "class_type": "KSampler",
            "inputs": {
                "seed": arguments.seed,
                "steps": arguments.steps,
                "cfg": arguments.cfg,
                "sampler_name": "euler_ancestral",
                "scheduler": "normal",
                "denoise": arguments.denoise,
                "model": ["1", 0],
                "positive": ["6", 0],
                "negative": ["6", 1],
                "latent_image": ["6", 2],
            },
        },
        "8": {
            "class_type": "VAEDecode",
            "inputs": {"samples": ["7", 0], "vae": ["1", 2]},
        },
        "9": {
            "class_type": "SaveImage",
            "inputs": {"filename_prefix": "SELMA-Region-Repair", "images": ["8", 0]},
        },
    }


async def _upload(session: aiohttp.ClientSession, api_url: str, path: Path) -> str:
    form = aiohttp.FormData()
    form.add_field("image", path.read_bytes(), filename=path.name, content_type="image/png")
    form.add_field("type", "input")
    form.add_field("overwrite", "true")
    async with session.post(f"{api_url}/upload/image", data=form) as response:
        response.raise_for_status()
        payload = await response.json()
    subfolder = str(payload.get("subfolder", "")).strip("/")
    return f"{subfolder}/{payload['name']}" if subfolder else str(payload["name"])


async def _run(arguments: argparse.Namespace) -> None:
    for path in (arguments.input, arguments.mask):
        if not path.is_file():
            raise FileNotFoundError(path)
    if not 0.0 < arguments.denoise <= 1.0:
        raise ValueError("denoise must satisfy 0 < denoise <= 1")
    api_url = arguments.api_url.rstrip("/")
    timeout = aiohttp.ClientTimeout(total=arguments.timeout)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        image = await _upload(session, api_url, arguments.input)
        mask = await _upload(session, api_url, arguments.mask)
        async with session.post(
            f"{api_url}/prompt",
            json={"prompt": _workflow(arguments, image, mask)},
        ) as response:
            response.raise_for_status()
            prompt_id = str((await response.json())["prompt_id"])

        deadline = time.monotonic() + arguments.timeout
        image_info: dict[str, str] | None = None
        while time.monotonic() < deadline:
            async with session.get(f"{api_url}/history/{prompt_id}") as response:
                response.raise_for_status()
                history = await response.json()
            item = history.get(prompt_id)
            if item:
                status = item.get("status", {})
                if status.get("status_str") == "error":
                    raise RuntimeError(f"ComfyUI repair failed: {status}")
                images = item.get("outputs", {}).get("9", {}).get("images", [])
                if images:
                    image_info = images[0]
                    break
            await asyncio.sleep(1)
        if image_info is None:
            raise TimeoutError("ComfyUI region repair timed out")
        params = {
            "filename": image_info["filename"],
            "subfolder": image_info.get("subfolder", ""),
            "type": image_info.get("type", "output"),
        }
        async with session.get(f"{api_url}/view", params=params) as response:
            response.raise_for_status()
            content = await response.read()

    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_bytes(content)
    print(arguments.output.resolve())


def main() -> None:
    asyncio.run(_run(_parser().parse_args()))


if __name__ == "__main__":
    main()
