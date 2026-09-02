import os

# Create mock SFX files
sfx_types = ["whoosh", "impact", "riser", "glitch", "ambient"]
for sfx in sfx_types:
    path = f"assets/sfx/{sfx}.mp3"
    with open(path, "wb") as f:
        f.write(b"mock audio content")
print("Mock SFX files created.")
