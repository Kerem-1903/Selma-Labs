from __future__ import annotations

import json
from pathlib import Path

import httpx
from dotenv import dotenv_values


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "motion" / "public" / "chip-bag" / "footage"
VIDEO_IDS = {
    "eating_chips": 6547782,
    "chips_bowl": 8751424,
    "snack_aisle": 28671127,
    "holding_chip_bag": 6547807,
}
PHOTO_IDS = {"open_chip_bag": 13060695}


def choose_file(files: list[dict]) -> dict:
    candidates = [
        item
        for item in files
        if item.get("file_type") == "video/mp4"
        and (item.get("height") or 0) > (item.get("width") or 0)
        and (item.get("height") or 0) >= 1280
    ]
    if not candidates:
        candidates = [item for item in files if item.get("file_type") == "video/mp4"]
    if not candidates:
        raise RuntimeError("No MP4 rendition found")
    return min(
        candidates,
        key=lambda item: (
            abs((item.get("width") or 0) - 1080),
            abs((item.get("height") or 0) - 1920),
            item.get("file_size") or 0,
        ),
    )


def main() -> None:
    api_key = dotenv_values(ROOT / ".env").get("PEXELS_API_KEY")
    if not api_key:
        raise RuntimeError("PEXELS_API_KEY is missing")
    OUT.mkdir(parents=True, exist_ok=True)
    manifest_path = OUT / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}
    with httpx.Client(
        timeout=180,
        follow_redirects=True,
        headers={"User-Agent": "StrangeThingsLab/1.0 (educational video production)"},
    ) as client:
        for name, video_id in VIDEO_IDS.items():
            target = OUT / f"{name}.mp4"
            if target.exists():
                print(f"{name}: already downloaded")
                continue
            response = client.get(
                f"https://api.pexels.com/videos/videos/{video_id}",
                headers={"Authorization": str(api_key)},
            )
            response.raise_for_status()
            video = response.json()
            selected = choose_file(video.get("video_files") or [])
            with client.stream("GET", selected["link"]) as download:
                download.raise_for_status()
                with target.open("wb") as handle:
                    for chunk in download.iter_bytes():
                        handle.write(chunk)
            creator = video.get("user") or {}
            manifest[name] = {
                "pexelsId": video_id,
                "page": video.get("url"),
                "creator": creator.get("name"),
                "creatorUrl": creator.get("url"),
                "license": "Pexels License — https://www.pexels.com/license/",
                "durationSeconds": video.get("duration"),
                "width": selected.get("width"),
                "height": selected.get("height"),
                "file": target.name,
            }
            print(f"{name}: {video_id} ({video.get('duration')}s)")
        for name, photo_id in PHOTO_IDS.items():
            target = OUT / f"{name}.jpg"
            if target.exists():
                print(f"{name}: already downloaded")
                continue
            response = client.get(
                f"https://api.pexels.com/v1/photos/{photo_id}",
                headers={"Authorization": str(api_key)},
            )
            response.raise_for_status()
            photo = response.json()
            source = photo["src"].get("large2x") or photo["src"]["original"]
            with client.stream("GET", source) as download:
                download.raise_for_status()
                with target.open("wb") as handle:
                    for chunk in download.iter_bytes():
                        handle.write(chunk)
            manifest[name] = {
                "pexelsId": photo_id,
                "page": photo.get("url"),
                "creator": photo.get("photographer"),
                "creatorUrl": photo.get("photographer_url"),
                "license": "Pexels License — https://www.pexels.com/license/",
                "file": target.name,
            }
            print(f"{name}: {photo_id}")
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
