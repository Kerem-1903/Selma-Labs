from __future__ import annotations

import json
from pathlib import Path

import httpx
from dotenv import dotenv_values


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "motion" / "public" / "earth-stop" / "footage"
MANIFEST = OUT / "manifest.json"

QUERIES = {
    "earth": "planet earth from space",
    "city": "city skyline traffic aerial",
    "storm": "storm clouds over city",
    "ocean": "powerful ocean waves aerial",
    "polar": "arctic ice aerial",
    "satellite": "satellite orbit earth space",
    "tunnel": "underground tunnel bunker",
    "flood": "flooded city street",
    "rubble": "earthquake rubble city",
}


def select_file(files: list[dict]) -> dict:
    mp4s = [f for f in files if f.get("file_type") == "video/mp4"]
    landscape = [f for f in mp4s if (f.get("width") or 0) > (f.get("height") or 0)]
    candidates = landscape or mp4s
    if not candidates:
        raise RuntimeError("No MP4 file found")
    # Prefer Full HD without downloading unnecessarily huge 4K files.
    return min(
        candidates,
        key=lambda f: (
            abs((f.get("width") or 0) - 1920),
            abs((f.get("height") or 0) - 1080),
            f.get("file_size") or 0,
        ),
    )


def score(video: dict, used_ids: set[int]) -> tuple:
    width = video.get("width") or 0
    height = video.get("height") or 0
    duration = video.get("duration") or 0
    return (
        video.get("id") in used_ids,
        not (width > height),
        duration < 6,
        abs(duration - 16),
        -(width * height),
    )


def main() -> None:
    api_key = dotenv_values(ROOT / ".env").get("PEXELS_API_KEY")
    if not api_key:
        raise RuntimeError("PEXELS_API_KEY is missing")
    OUT.mkdir(parents=True, exist_ok=True)
    used_ids: set[int] = set()
    manifest: dict[str, dict] = {}
    headers = {"Authorization": str(api_key)}

    with httpx.Client(timeout=120, follow_redirects=True) as client:
        for scene, query in QUERIES.items():
            response = client.get(
                "https://api.pexels.com/videos/search",
                headers=headers,
                params={
                    "query": query,
                    "per_page": 12,
                    "orientation": "landscape",
                    "size": "large",
                },
            )
            response.raise_for_status()
            videos = response.json().get("videos", [])
            if not videos:
                raise RuntimeError(f"No results for {query}")
            video = min(videos, key=lambda v: score(v, used_ids))
            used_ids.add(video["id"])
            selected = select_file(video.get("video_files") or [])
            target = OUT / f"{scene}.mp4"
            if not target.exists():
                with client.stream("GET", selected["link"]) as download:
                    download.raise_for_status()
                    with target.open("wb") as handle:
                        for chunk in download.iter_bytes():
                            handle.write(chunk)
            user = video.get("user") or {}
            manifest[scene] = {
                "query": query,
                "pexelsId": video["id"],
                "page": video.get("url"),
                "creator": user.get("name"),
                "creatorUrl": user.get("url"),
                "license": "Pexels License — https://www.pexels.com/license/",
                "durationSeconds": video.get("duration"),
                "width": selected.get("width"),
                "height": selected.get("height"),
                "file": target.name,
            }
            print(f"{scene}: {video['id']} by {user.get('name')} -> {target.name}")

    MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
