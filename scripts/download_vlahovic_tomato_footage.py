from __future__ import annotations

import json
from pathlib import Path

import httpx
from dotenv import dotenv_values


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "motion" / "public" / "vlahovic-tomato" / "footage"
QUERIES = {
    "tomatoes": "ripe red tomatoes close up",
    "restaurant": "friends dinner restaurant table",
    "airport_luggage": "airport luggage trolley terminal",
}


def choose_video(videos: list[dict], used: set[int]) -> dict:
    candidates = [
        video
        for video in videos
        if video.get("id") not in used
        and (video.get("height") or 0) > (video.get("width") or 0)
        and (video.get("duration") or 0) >= 6
    ] or [video for video in videos if video.get("id") not in used]
    return min(
        candidates,
        key=lambda video: (
            abs((video.get("duration") or 10) - 10),
            -((video.get("width") or 0) * (video.get("height") or 0)),
        ),
    )


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
    used: set[int] = set()
    manifest: dict[str, dict] = {}
    with httpx.Client(timeout=180, follow_redirects=True) as client:
        for name, query in QUERIES.items():
            response = client.get(
                "https://api.pexels.com/videos/search",
                headers={"Authorization": str(api_key)},
                params={"query": query, "per_page": 24, "orientation": "portrait", "size": "large"},
            )
            response.raise_for_status()
            video = choose_video(response.json().get("videos") or [], used)
            used.add(video["id"])
            selected = choose_file(video.get("video_files") or [])
            target = OUT / f"{name}.mp4"
            with client.stream("GET", selected["link"]) as download:
                download.raise_for_status()
                with target.open("wb") as handle:
                    for chunk in download.iter_bytes():
                        handle.write(chunk)
            creator = video.get("user") or {}
            manifest[name] = {
                "query": query,
                "pexelsId": video["id"],
                "page": video.get("url"),
                "creator": creator.get("name"),
                "creatorUrl": creator.get("url"),
                "license": "Pexels License — https://www.pexels.com/license/",
                "durationSeconds": video.get("duration"),
                "width": selected.get("width"),
                "height": selected.get("height"),
                "file": target.name,
            }
            print(f"{name}: {video['id']} by {creator.get('name')} ({video.get('duration')}s)")
    (OUT / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )


if __name__ == "__main__":
    main()
