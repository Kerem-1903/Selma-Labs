"""
RenderResult — what a RenderPort implementation returns immediately after
encoding, before StoragePort has persisted anything.

Deliberately mirrors StorageReference's role for VideoSearchService: a Port
implementation hands back just enough to locate and describe what it
produced, without itself deciding where that output ends up living
long-term. StoragePort.save() is what actually persists bytes in this
codebase (LocalFsStorage today, a future S3/MinIO adapter later); a render
engine's job ends at "here is a finished file on local disk," not "here is
where it's permanently stored."

``output_path`` points at a temporary file on local disk (FFmpeg always
writes to a file — a video is not naturally an in-memory byte stream the
way a downloaded image or a generated audio clip is, and encoded video can
be large enough that holding it as `bytes` on the RenderResult itself would
be wasteful for anything beyond a short clip). RenderService is the one
place that reads that file's bytes and hands them to StoragePort.save() --
this VO does not touch StoragePort itself and never will, keeping the
render/persist responsibilities cleanly separated the way VideoSearchService
already separates "download" from "save."

Not an entity: a RenderResult has no identity and no independent lifecycle
-- it exists only to carry one render engine invocation's output from
RenderPort to RenderService, the same relationship TimelineClip has to
Timeline. Once RenderService has read and persisted the file, the
RenderResult itself is discarded; RenderedVideo (the durable domain record)
is what survives.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RenderResult:
    # Path to the finished video file on local disk, written by the render
    # engine. Not guaranteed to exist after RenderService has read and
    # persisted it -- callers should not hold onto a RenderResult past that
    # point.
    output_path: str
    duration_seconds: float
    width: int
    height: int
    fps: float
