from __future__ import annotations

import json
import sys
from pathlib import Path

import httpx
from dotenv import dotenv_values


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "motion" / "public" / "internet-outage" / "footage"
MANIFEST = OUT / "manifest.json"

QUERIES = {
    "istanbul_morning": "Istanbul city morning aerial traffic",
    "phone_problem": "frustrated man smartphone error close up",
    "office_network": "modern office computers teamwork",
    "data_center": "modern server room blue lights technician",
    "payment": "customer credit card payment terminal shop",
    "atm": "ATM cash withdrawal close up",
    "traffic": "Istanbul heavy traffic aerial",
    "airport": "airport departure board close up passengers",
    "cell_tower": "telecommunications tower city",
    "emergency": "emergency call center operator headset dispatch",
    "radio": "radio host studio microphone",
    "warehouse": "logistics warehouse workers packages",
    "fuel": "person fuel pump car close up",
    "hospital": "hospital corridor doctors working",
    "evening_home": "family home television evening",
    "network_repair": "fiber optic cable technician repair",
    "cash_market": "customer paying cash grocery store",
}


def select_file(files: list[dict]) -> dict:
    mp4s = [f for f in files if f.get("file_type") == "video/mp4"]
    candidates = [f for f in mp4s if (f.get("width") or 0) > (f.get("height") or 0)] or mp4s
    if not candidates:
        raise RuntimeError("No MP4 file found")
    return min(candidates, key=lambda f: (abs((f.get("width") or 0) - 1920), abs((f.get("height") or 0) - 1080), f.get("file_size") or 0))


def score(video: dict, used_ids: set[int]) -> tuple:
    width = video.get("width") or 0
    height = video.get("height") or 0
    duration = video.get("duration") or 0
    return (video.get("id") in used_ids, not width > height, duration < 7, abs(duration - 14), -(width * height))


def main() -> None:
    api_key = dotenv_values(ROOT / ".env").get("PEXELS_API_KEY")
    if not api_key:
        raise RuntimeError("PEXELS_API_KEY is missing")
    OUT.mkdir(parents=True, exist_ok=True)
    used_ids: set[int] = set()
    manifest: dict[str, dict] = {}
    with httpx.Client(timeout=180, follow_redirects=True) as client:
        selected_scenes = set(sys.argv[1:])
        for scene, query in QUERIES.items():
            if selected_scenes and scene not in selected_scenes:
                continue
            response = client.get("https://api.pexels.com/videos/search", headers={"Authorization": str(api_key)}, params={"query": query, "per_page": 18, "orientation": "landscape", "size": "large"})
            response.raise_for_status()
            videos = response.json().get("videos", [])
            if not videos:
                raise RuntimeError(f"No results for {query}")
            video = min(videos, key=lambda item: score(item, used_ids))
            used_ids.add(video["id"])
            selected = select_file(video.get("video_files") or [])
            target = OUT / f"{scene}.mp4"
            with client.stream("GET", selected["link"]) as download:
                download.raise_for_status()
                with target.open("wb") as handle:
                    for chunk in download.iter_bytes():
                        handle.write(chunk)
            user = video.get("user") or {}
            manifest[scene] = {"query": query, "pexelsId": video["id"], "page": video.get("url"), "creator": user.get("name"), "creatorUrl": user.get("url"), "license": "Pexels License — https://www.pexels.com/license/", "durationSeconds": video.get("duration"), "width": selected.get("width"), "height": selected.get("height"), "file": target.name}
            print(f"{scene}: {video['id']} by {user.get('name')} ({video.get('duration')}s)")
    existing = json.loads(MANIFEST.read_text(encoding="utf-8")) if MANIFEST.exists() else {}
    existing.update(manifest)
    MANIFEST.write_text(json.dumps(existing, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
