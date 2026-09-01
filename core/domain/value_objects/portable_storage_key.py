from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath


@dataclass(frozen=True, slots=True)
class PortableStorageKey:
    """Canonical relative object-storage key.

    Persisted keys use one representation on every operating system. Physical
    filesystem adapters may map this value to an OS-specific path internally,
    but domain metadata never contains backslashes, drive letters, traversal
    segments, or a non-canonical POSIX spelling.
    """

    value: str

    def __post_init__(self) -> None:
        if not isinstance(self.value, str):
            raise TypeError("Portable storage key must be a string.")
        if not self.value or self.value != self.value.strip():
            raise ValueError("Portable storage key must not be empty or padded.")
        if "\\" in self.value:
            raise ValueError("Portable storage key must use POSIX '/' separators.")
        if ":" in self.value or "\x00" in self.value:
            raise ValueError("Portable storage key contains a forbidden character.")

        path = PurePosixPath(self.value)
        if not path.parts or path.is_absolute() or ".." in path.parts:
            raise ValueError("Portable storage key must be relative and contained.")
        if path.as_posix() != self.value or any(
            part in {"", ".", ".."} for part in path.parts
        ):
            raise ValueError("Portable storage key must use canonical POSIX form.")

    @property
    def suffix(self) -> str:
        return PurePosixPath(self.value).suffix.casefold()

    @property
    def name(self) -> str:
        return PurePosixPath(self.value).name

    def require_suffix(self, *allowed: str) -> PortableStorageKey:
        normalized = {suffix.casefold() for suffix in allowed}
        if self.suffix not in normalized:
            expected = ", ".join(sorted(normalized))
            raise ValueError(f"Portable storage key must use one of: {expected}.")
        return self

    def __str__(self) -> str:
        return self.value
