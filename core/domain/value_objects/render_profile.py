from enum import Enum

class RenderProfile(str, Enum):
    """
    Defines the quality and cost profile for video generation and rendering.

    - DRAFT: Low resolution, fast generation, meant for quick storyboard previews.
    - BALANCED: Medium resolution/quality, standard fps, good for internal reviews.
    - FINAL: High resolution, best quality, full mastering applied.
    """
    DRAFT = "DRAFT"
    BALANCED = "BALANCED"
    FINAL = "FINAL"
