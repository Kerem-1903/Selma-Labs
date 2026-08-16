from __future__ import annotations

import json
from pathlib import Path

import httpx
from dotenv import dotenv_values


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "motion" / "public" / "perseid-short" / "footage"
QUERIES = {
    "meteor": "shooting star night sky timelapse",
    "stars": "milky way stars night sky timelapse",
    "stargazer": "person watching stars night sky",
    "comet": "asteroid space animation",
}


def select_video(videos: list[dict], used: set[int]) -> dict:
    vertical = [v for v in videos if (v.get("height") or 0) > (v.get("width") or 0) and v.get("id") not in used]
    candidates = vertical or [v for v in videos if v.get("id") not in used] or videos
    return max(candidates, key=lambda v: ((v.get("height") or 0) > (v.get("width") or 0), v.get("duration") or 0, (v.get("width") or 0) * (v.get("height") or 0)))


def select_file(files: list[dict]) -> dict:
    mp4s = [f for f in files if f.get("file_type") == "video/mp4"]
    vertical = [f for f in mp4s if (f.get("height") or 0) > (f.get("width") or 0)]
    candidates = vertical or mp4s
    return min(candidates, key=lambda f: (abs((f.get("width") or 0) - 1080), abs((f.get("height") or 0) - 1920), f.get("file_size") or 0))


def main() -> None:
    key = dotenv_values(ROOT / ".env").get("PEXELS_API_KEY")
    if not key:
        raise RuntimeError("PEXELS_API_KEY missing")
    OUT.mkdir(parents=True, exist_ok=True)
    manifest: dict[str, dict] = {}
    used: set[int] = set()
    with httpx.Client(timeout=120, follow_redirects=True) as client:
        for name, query in QUERIES.items():
            response = client.get("https://api.pexels.com/videos/search", headers={"Authorization": str(key)}, params={"query": query, "per_page": 15, "orientation": "portrait", "size": "large"})
            response.raise_for_status()
            video = select_video(response.json().get("videos") or [], used)
            used.add(video["id"])
            selected = select_file(video.get("video_files") or [])
            target = OUT / f"{name}.mp4"
            with client.stream("GET", selected["link"]) as download:
                download.raise_for_status()
                with target.open("wb") as handle:
                    for chunk in download.iter_bytes():
                        handle.write(chunk)
            creator = video.get("user") or {}
            manifest[name] = {"query": query, "pexelsId": video["id"], "page": video.get("url"), "creator": creator.get("name"), "creatorUrl": creator.get("url"), "license": "Pexels License — https://www.pexels.com/license/", "file": target.name}
            print(name, video["id"], creator.get("name"))
    (OUT / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
