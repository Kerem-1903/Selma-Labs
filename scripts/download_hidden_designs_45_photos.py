from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

import httpx
from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "motion" / "public" / "hidden-designs-45"
OUTPUT = ROOT / "output" / "hidden-designs-45"

QUERIES = [
    "blue bristle toothbrush close up",
    "supermarket shopping cart close up",
    "soda can tab straw close up",
    "retractable tape measure metal hook close up",
    "glass bottle cap opener close up",
    "scissors cutting aluminum foil",
    "stack of coins side edges macro",
    "car tire tread close up",
    "clothing fabric swatch close up",
    "canvas sneaker side eyelets close up",
    "notebook paper margin close up",
    "red blue eraser close up",
    "empty paper condiment cup fast food close up",
    "chinese takeout box open",
    "utility knife snap blade close up",
    "ballpoint pen caps close up",
    "shirt back collar loop close up",
    "office stapler open close up",
    "plastic takeaway coffee cup lid",
    "frying pan handle close up",
    "spaghetti server spoon pasta close up",
    "refrigerator door kitchen close up",
    "car seat headrest close up",
    "smartphone rear camera microphone macro",
    "padlock bottom hole close up",
    "car fuel gauge dashboard close up",
    "military metal jerry can close up",
    "plastic fuel can pouring liquid",
    "cedar wooden clothes hangers",
    "shirt buttons close up",
    "computer keyboard F J keys close up",
    "classic glass ketchup bottle close up",
    "single serve ketchup sachets packets close up",
    "toothpaste tube crimp bottom close up",
    "triangular chocolate bar close up",
    "striped toothpaste close up",
    "polishing silverware close up",
    "child holding small juice box close up",
    "open oven lower warming drawer close up",
    "small plastic mint candy box lid close up",
    "British coins close up",
    "kitchen tongs lemon close up",
    "bobby pins hair close up",
    "thick plastic ice cream spoon handle close up",
    "tape measure metal hook moving close up",
]

REDOWNLOAD_ONLY = {4, 7, 13, 18, 20, 21, 27, 32, 33, 34, 38, 39, 40, 42, 44, 45}

OVERRIDES = {
    15: ROOT / "motion" / "public" / "hidden-designs" / "knife.jpg",
    16: ROOT / "motion" / "public" / "hidden-designs" / "pen-holes-v3.png",
    25: ROOT / "motion" / "public" / "hidden-designs" / "padlock.jpg",
    26: ROOT / "motion" / "public" / "hidden-designs" / "fuel-gauge.jpg",
    31: ROOT / "motion" / "public" / "hidden-designs" / "keyboard-fj-v4.png",
}


def main() -> None:
    load_dotenv(ROOT / ".env")
    key = os.environ.get("PEXELS_API_KEY", "")
    if not key:
        raise RuntimeError("PEXELS_API_KEY is missing")
    TARGET.mkdir(parents=True, exist_ok=True)
    OUTPUT.mkdir(parents=True, exist_ok=True)
    credits = []
    headers = {"Authorization": key}
    with httpx.Client(timeout=60, follow_redirects=True) as client:
        for index, query in enumerate(QUERIES, 1):
            destination = TARGET / f"item-{index:02d}.jpg"
            if destination.exists() and index not in REDOWNLOAD_ONLY and index not in OVERRIDES:
                continue
            if index in OVERRIDES:
                shutil.copy2(OVERRIDES[index], destination)
                credits.append({"item": index, "query": query, "source": "project verified asset", "photographer": "Strange Things Lab asset library"})
                print(f"{index:02d}/45 verified")
                continue
            response = client.get(
                "https://api.pexels.com/v1/search",
                headers=headers,
                params={"query": query, "per_page": 8, "orientation": "landscape", "size": "large"},
            )
            response.raise_for_status()
            photos = response.json().get("photos", [])
            if not photos:
                raise RuntimeError(f"No Pexels result for {index}: {query}")
            photo = photos[0]
            source_url = photo["src"].get("large2x") or photo["src"]["large"]
            image = client.get(source_url)
            image.raise_for_status()
            destination.write_bytes(image.content)
            credits.append({
                "item": index,
                "query": query,
                "source": photo["url"],
                "photographer": photo["photographer"],
                "photographer_url": photo["photographer_url"],
                "license": "Pexels License",
            })
            print(f"{index:02d}/45 {photo['photographer']}")
    (OUTPUT / "stock_credits.json").write_text(json.dumps(credits, ensure_ascii=False, indent=2), encoding="utf-8")
    (OUTPUT / "stock_credits.txt").write_text("\n".join(f"{row['item']:02d}. {row['photographer']} — {row['source']}" for row in credits), encoding="utf-8")


if __name__ == "__main__":
    main()
