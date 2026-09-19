"""Shared view policy for a source-led character turnaround.

The production pipeline and the model tournament must chain views identically.
If they do not, a tournament compares methods that are not the one that ships --
the numbers look comparable and are not. Both therefore read this policy rather
than each keeping their own table.

Geometry this encodes:

* FRONT is the approved canonical image, copied rather than regenerated, so the
  turnaround never re-renders the one view a human signed off on.
* Each wing derives from FRONT directly, never through the other wing. A
  left/right error therefore cannot propagate across the body.
* BACK consumes both profiles, because a single messenger bag reads correctly
  on only one side; conditioning the rear view on one profile alone is what let
  the bag grow and turn blue.
"""

from __future__ import annotations

#: Views rendered by the edit dialect, in dependency order: every entry lists
#: only views produced earlier in this same tuple (plus FRONT).
EDIT_TURNAROUND_PLAN: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("THREE_QUARTER_LEFT", ("FRONT",)),
    ("PROFILE_LEFT", ("FRONT", "THREE_QUARTER_LEFT")),
    ("THREE_QUARTER_RIGHT", ("FRONT",)),
    ("PROFILE_RIGHT", ("FRONT", "THREE_QUARTER_RIGHT")),
    ("BACK", ("FRONT", "PROFILE_LEFT", "PROFILE_RIGHT")),
)

#: Views that are inherited from approved artifacts instead of rendered.
EDIT_TURNAROUND_FIXED_VIEWS: tuple[str, ...] = ("FACE_CLOSEUP", "FRONT")

#: Reference slots the edit graph must provide.
MAX_EDIT_REFERENCES = 3


def edit_turnaround_dependencies(view: str) -> tuple[str, ...]:
    """Return the earlier views one rendered view is conditioned on."""
    for name, dependencies in EDIT_TURNAROUND_PLAN:
        if name == view:
            return dependencies
    raise ValueError(f"Unknown edit-dialect turnaround view: {view}")


def edit_turnaround_order() -> tuple[str, ...]:
    """Return the rendered views in dependency order."""
    return tuple(name for name, _dependencies in EDIT_TURNAROUND_PLAN)


def edit_turnaround_production_order() -> tuple[str, ...]:
    """Return every view in the order the pipeline should produce it."""
    return (*EDIT_TURNAROUND_FIXED_VIEWS, *edit_turnaround_order())


def edit_reference_count(view: str) -> int:
    """Return how many reference slots a view needs, including the source."""
    if view in EDIT_TURNAROUND_FIXED_VIEWS:
        return 1
    return 1 + len(edit_turnaround_dependencies(view))


__all__ = [
    "EDIT_TURNAROUND_FIXED_VIEWS",
    "EDIT_TURNAROUND_PLAN",
    "MAX_EDIT_REFERENCES",
    "edit_reference_count",
    "edit_turnaround_dependencies",
    "edit_turnaround_order",
    "edit_turnaround_production_order",
]
