from __future__ import annotations

import json
from pathlib import Path

import httpx
from dotenv import dotenv_values


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "motion" / "public" / "airplane-lavatory" / "footage"
STILLS = ROOT / "motion" / "public" / "airplane-lavatory" / "stills"
QUERIES = {
    "airplane_flying": "passenger airplane flying close up",
    "airplane_cabin": "passenger airplane cabin aisle",
    "airplane_lavatory": "airplane toilet lavatory interior",
    "airport_ground_crew": "airport ground crew service vehicle airplane",
    "toilet_flush": "toilet flushing close up",
    "airport_ground_close": "airport ground crew servicing airplane",
}
COMMONS_FILES = {
    "aircraft_lavatory": "File:Aircraft Lavatory.JPG",
    "aircraft_toilet_blue_water": "File:Airplane-toilet-with-blue-water.jpg",
    "lavatory_service": "File:Fleet service 130311-F-VV898-019.jpg",
    "service_hose_connection": "File:Connecting waste suction hose to the lavatory service outlet.jpg",
}
FIXED_VIDEOS = {
    "toilet_flush_hand": 7593981,
    "toilet_flush_bowl": 854680,
    "ground_crew_working": 9512141,
}


def choose_video(videos: list[dict], used: set[int]) -> dict:
    candidates = [
        video
        for video in videos
        if video.get("id") not in used
        and (video.get("height") or 0) > (video.get("width") or 0)
        and (video.get("duration") or 0) >= 7
    ] or [video for video in videos if video.get("id") not in used]
    if not candidates:
        raise RuntimeError("No suitable Pexels footage found")
    return min(
        candidates,
        key=lambda video: (
            abs((video.get("duration") or 11) - 11),
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
    STILLS.mkdir(parents=True, exist_ok=True)
    used: set[int] = set()
    manifest_path = OUT / "manifest.json"
    manifest: dict[str, dict] = (
        json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}
    )
    with httpx.Client(
        timeout=180,
        follow_redirects=True,
        headers={"User-Agent": "StrangeThingsLab/1.0 (educational video production)"},
    ) as client:
        for name, query in QUERIES.items():
            target = OUT / f"{name}.mp4"
            if target.exists():
                print(f"{name}: already downloaded")
                continue
            response = client.get(
                "https://api.pexels.com/videos/search",
                headers={"Authorization": str(api_key)},
                params={"query": query, "per_page": 30, "orientation": "portrait", "size": "large"},
            )
            response.raise_for_status()
            video = choose_video(response.json().get("videos") or [], used)
            used.add(video["id"])
            selected = choose_file(video.get("video_files") or [])
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
            creator_name = str(creator.get("name") or "unknown").encode("ascii", "replace").decode()
            print(f"{name}: {video['id']} by {creator_name} ({video.get('duration')}s)")
        for name, video_id in FIXED_VIDEOS.items():
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
                "query": f"fixed Pexels ID {video_id}",
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
            creator_name = str(creator.get("name") or "unknown").encode("ascii", "replace").decode()
            print(f"{name}: {video_id} by {creator_name} ({video.get('duration')}s)")
        commons_manifest_path = STILLS / "manifest.json"
        commons_manifest: dict[str, dict] = (
            json.loads(commons_manifest_path.read_text(encoding="utf-8"))
            if commons_manifest_path.exists()
            else {}
        )
        for name, title in COMMONS_FILES.items():
            target = STILLS / f"{name}.jpg"
            if target.exists():
                print(f"{name}: already downloaded")
                continue
            response = client.get(
                "https://commons.wikimedia.org/w/api.php",
                params={
                    "action": "query",
                    "format": "json",
                    "prop": "imageinfo",
                    "iiprop": "url|extmetadata",
                    "iiurlwidth": 1920,
                    "titles": title,
                },
            )
            response.raise_for_status()
            page = next(iter(response.json()["query"]["pages"].values()))
            info = page["imageinfo"][0]
            metadata = info.get("extmetadata") or {}
            url = info.get("thumburl") or info["url"]
            with client.stream("GET", url) as download:
                download.raise_for_status()
                with target.open("wb") as handle:
                    for chunk in download.iter_bytes():
                        handle.write(chunk)
            commons_manifest[name] = {
                "title": title,
                "descriptionUrl": info["descriptionurl"],
                "author": (metadata.get("Artist") or {}).get("value"),
                "license": (metadata.get("LicenseShortName") or {}).get("value"),
                "licenseUrl": (metadata.get("LicenseUrl") or {}).get("value"),
                "file": target.name,
            }
            print(f"{name}: {title}")
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    commons_manifest_path.write_text(
        json.dumps(commons_manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )


if __name__ == "__main__":
    main()
