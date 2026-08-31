from dataclasses import dataclass
import hashlib
from typing import List

@dataclass
class RenderConfig:
    width: int
    height: int
    fps: int
    seed: int
    sampler_name: str
    pass1_denoise: float
    pass2_denoise: float

    def compute_hash(self, prompt: str, character_tags: List[str]) -> str:
        data = f"{self.width}x{self.height}@{self.fps}_{self.seed}_{self.sampler_name}_{self.pass1_denoise}_{self.pass2_denoise}_{prompt}_{'-'.join(character_tags)}"
        return hashlib.sha256(data.encode('utf-8')).hexdigest()
