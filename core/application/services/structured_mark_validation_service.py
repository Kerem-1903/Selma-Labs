from __future__ import annotations

import math
from collections.abc import Sequence

import numpy as np
from PIL import Image

from core.domain.value_objects.structured_mark import MarkAnchor, StructuredMark
from core.domain.value_objects.structured_mark_report import StructuredMarkReport

Point = tuple[int, int]
Component = list[Point]
BBox = tuple[float, float, float, float]


def project_anchor(anchor: MarkAnchor, head_bbox: BBox) -> tuple[float, float]:
    left, top, right, bottom = head_bbox
    return (
        left + anchor.x_center * (right - left),
        top + anchor.y_root * (bottom - top),
    )


def _hex_to_rgb(value: str) -> tuple[int, int, int]:
    value = value.lstrip("#")
    return tuple(int(value[index : index + 2], 16) for index in (0, 2, 4))


class StructuredMarkValidationService:
    def __init__(
        self,
        *,
        min_component_area: int = 4,
        anchor_tolerance_ratio: float = 0.12,
    ) -> None:
        if min_component_area < 1:
            raise ValueError("Minimum component area must be positive.")
        if not 0.0 < anchor_tolerance_ratio <= 1.0:
            raise ValueError("Anchor tolerance ratio must be between 0 and 1.")
        self._min_area = min_component_area
        self._anchor_tolerance_ratio = anchor_tolerance_ratio

    def validate(
        self,
        image: Image.Image,
        mark: StructuredMark,
        head_bbox: BBox,
        expected_root_xy: tuple[float, float],
    ) -> StructuredMarkReport:
        left, top, right, bottom = (int(value) for value in head_bbox)
        crop = image.convert("RGB").crop((left, top, right, bottom))
        lab = self._rgb_to_lab(np.asarray(crop, dtype=np.float64))
        reference = self._rgb_to_lab(
            np.asarray(_hex_to_rgb(mark.color_hex), dtype=np.float64)
        )
        delta_e = self._delta_e(lab, reference)
        mask = delta_e <= mark.color_tolerance_delta_e
        components = self._connected_components(mask)
        shifted = [
            [(y + top, x + left) for y, x in component] for component in components
        ]

        primary = self._nearest_by_centroid(shifted, expected_root_xy)
        root_x: float | None = None
        root_y: float | None = None
        distance: float | None = None
        mean_delta_e: float | None = None
        max_delta_e: float | None = None
        if primary is not None:
            root_y_int, root_x_int = min(primary, key=lambda point: point)
            root_x = float(root_x_int)
            root_y = float(root_y_int)
            distance = math.hypot(
                root_x - expected_root_xy[0], root_y - expected_root_xy[1]
            )
            component_delta_e = delta_e[
                [y - top for y, _ in primary],
                [x - left for _, x in primary],
            ]
            mean_delta_e = float(component_delta_e.mean())
            max_delta_e = float(component_delta_e.max())

        midline = (left + right) / 2.0
        actual_side = None
        if root_x is not None:
            actual_side = "viewer_left" if root_x < midline else "viewer_right"

        head_extent = max(float(right - left), float(bottom - top))
        anchor_tolerance = max(4.0, head_extent * self._anchor_tolerance_ratio)
        checks = (
            ("color_tolerance", bool(components)),
            ("component_count", len(components) == mark.count),
            ("side", actual_side == mark.viewer_side),
            (
                "anchor_distance",
                distance is not None and distance <= anchor_tolerance,
            ),
            (
                "mirror_exclusivity",
                not (
                    mark.mirror_side != "none"
                    and self._has_mirrored_component(shifted, expected_root_xy, midline)
                ),
            ),
        )
        return StructuredMarkReport(
            mark_id=mark.id,
            passed=all(ok for _, ok in checks),
            expected_count=mark.count,
            detected_count=len(components),
            matched_pixels=int(mask.sum()),
            mean_delta_e=mean_delta_e,
            max_delta_e=max_delta_e,
            anchor_distance_px=distance,
            detected_root_x=root_x,
            detected_root_y=root_y,
            expected_side=mark.viewer_side,
            actual_side=actual_side,
            checks=checks,
        )

    @staticmethod
    def _linearize_srgb(channel: np.ndarray) -> np.ndarray:
        channel = channel / 255.0
        return np.where(
            channel <= 0.04045,
            channel / 12.92,
            ((channel + 0.055) / 1.055) ** 2.4,
        )

    @staticmethod
    def _lab_transform(channel: np.ndarray) -> np.ndarray:
        delta = 6.0 / 29.0
        return np.where(
            channel > delta**3,
            np.cbrt(channel),
            channel / (3.0 * delta**2) + 4.0 / 29.0,
        )

    def _rgb_to_lab(self, rgb: np.ndarray) -> np.ndarray:
        red, green, blue = rgb[..., 0], rgb[..., 1], rgb[..., 2]
        red, green, blue = (
            self._linearize_srgb(red),
            self._linearize_srgb(green),
            self._linearize_srgb(blue),
        )
        x = 0.4124564 * red + 0.3575761 * green + 0.1804375 * blue
        y = 0.2126729 * red + 0.7151522 * green + 0.0721750 * blue
        z = 0.0193339 * red + 0.1191920 * green + 0.9503041 * blue
        fx, fy, fz = (
            self._lab_transform(x / 0.95047),
            self._lab_transform(y),
            self._lab_transform(z / 1.08883),
        )
        return np.stack(
            [116.0 * fy - 16.0, 500.0 * (fx - fy), 200.0 * (fy - fz)],
            axis=-1,
        )

    @staticmethod
    def _delta_e(first: np.ndarray, second: np.ndarray) -> np.ndarray:
        return np.sqrt(((first - second) ** 2).sum(axis=-1))

    def _connected_components(self, mask: np.ndarray) -> list[Component]:
        height, width = mask.shape
        visited = np.zeros((height, width), dtype=bool)
        components: list[Component] = []
        ys, xs = np.nonzero(mask)
        for start_y, start_x in zip(ys.tolist(), xs.tolist()):
            if visited[start_y, start_x]:
                continue
            stack = [(start_y, start_x)]
            visited[start_y, start_x] = True
            component: Component = []
            while stack:
                y, x = stack.pop()
                component.append((y, x))
                for delta_y in (-1, 0, 1):
                    for delta_x in (-1, 0, 1):
                        neighbor_y, neighbor_x = y + delta_y, x + delta_x
                        if (
                            (delta_y or delta_x)
                            and 0 <= neighbor_y < height
                            and 0 <= neighbor_x < width
                            and mask[neighbor_y, neighbor_x]
                            and not visited[neighbor_y, neighbor_x]
                        ):
                            visited[neighbor_y, neighbor_x] = True
                            stack.append((neighbor_y, neighbor_x))
            if len(component) >= self._min_area:
                components.append(component)
        return components

    @staticmethod
    def _nearest_by_centroid(
        components: Sequence[Component], expected: tuple[float, float]
    ) -> Component | None:
        def distance(component: Component) -> float:
            count = len(component)
            centroid_y = sum(y for y, _ in component) / count
            centroid_x = sum(x for _, x in component) / count
            return math.hypot(centroid_x - expected[0], centroid_y - expected[1])

        return min(components, key=distance, default=None)

    def _has_mirrored_component(
        self,
        components: Sequence[Component],
        expected: tuple[float, float],
        midline: float,
    ) -> bool:
        expected_on_left = expected[0] <= midline
        for component in components:
            opposite_pixels = sum(
                1
                for _, x in component
                if (expected_on_left and x > midline)
                or (not expected_on_left and x < midline)
            )
            if opposite_pixels >= self._min_area:
                return True
        return False
