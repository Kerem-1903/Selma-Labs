from pathlib import Path

from PIL import Image, ImageDraw


ROOT = Path(__file__).resolve().parents[1]
FOOTAGE = ROOT / "motion" / "public" / "internet-outage" / "footage"
review_dir = ROOT / "output" / "internet-mid-review"
files = sorted(review_dir.glob("*.jpg"))
thumbs: list[Image.Image] = []
for path in files:
    image = Image.open(path).convert("RGB")
    image.thumbnail((480, 240))
    canvas = Image.new("RGB", (480, 270), "#07101c")
    canvas.paste(image, ((480 - image.width) // 2, 0))
    ImageDraw.Draw(canvas).text((12, 246), path.stem, fill="white")
    thumbs.append(canvas)

sheet = Image.new("RGB", (4 * 496, 5 * 286), "#02060c")
for index, image in enumerate(thumbs):
    sheet.paste(image, (8 + (index % 4) * 496, 8 + (index // 4) * 286))
sheet.save(ROOT / "output" / "internet-mid-review-sheet.jpg", quality=92)
