"""Canonical bytes and checksum helpers for the Wan checkpoint contract."""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Mapping
from datetime import date, datetime, timezone
from enum import Enum
from typing import Any

UTC_TIMESTAMP_FORMAT = "%Y-%m-%dT%H:%M:%S.%fZ"
_TIMESTAMP_TEXT = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})$"
)


def normalize_timestamp(value: datetime) -> str:
    """Return the ADR-009 UTC timestamp representation."""
    if value.tzinfo is None:
        raise ValueError("Wan timestamps must be timezone-aware.")
    return value.astimezone(timezone.utc).strftime(UTC_TIMESTAMP_FORMAT)


def _normalize(value: Any) -> Any:
    if isinstance(value, datetime):
        return normalize_timestamp(value)
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Enum):
        return _normalize(value.value)
    if isinstance(value, str) and _TIMESTAMP_TEXT.fullmatch(value):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return value
        return normalize_timestamp(parsed)
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("NaN and Infinity are not valid Wan checkpoint values.")
        if value == 0.0:
            return 0
        # Keep finite floats as floats. A large float can be mathematically
        # integral while its shortest decimal representation is scientific
        # notation; converting it with int() would emit the exact binary
        # integer (for example ...667584) instead of the RFC-8785 decimal
        # (for example ...670000).
        return value
    if isinstance(value, Mapping):
        return {str(key): _normalize(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_normalize(item) for item in value]
    if isinstance(value, (str, int, bool)) or value is None:
        return value
    raise TypeError(f"Unsupported Wan checkpoint value: {type(value).__name__}")


def _canonical_number(value: float) -> str:
    """Render an IEEE-754 number using the RFC-8785/ECMAScript thresholds."""
    if not math.isfinite(value):
        raise ValueError("NaN and Infinity are not valid Wan checkpoint values.")
    if value == 0.0:
        return "0"
    sign = "-" if value < 0 else ""
    text = repr(abs(value))
    if "e" not in text and "E" not in text:
        return sign + (text.removesuffix(".0"))

    mantissa, exponent_text = text.lower().split("e")
    exponent = int(exponent_text)
    digits = mantissa.replace(".", "")
    decimal_position = (mantissa.find(".") if "." in mantissa else len(mantissa)) + exponent
    magnitude = abs(value)
    if 1e-6 <= magnitude < 1e21:
        if decimal_position <= 0:
            rendered = "0." + ("0" * -decimal_position) + digits
        elif decimal_position >= len(digits):
            rendered = digits + ("0" * (decimal_position - len(digits)))
        else:
            rendered = digits[:decimal_position] + "." + digits[decimal_position:]
        return sign + rendered

    coefficient = digits[0]
    tail = digits[1:]
    rendered = coefficient + (("." + tail) if tail else "")
    scientific_exponent = decimal_position - 1
    return f"{sign}{rendered}e{'+' if scientific_exponent >= 0 else ''}{scientific_exponent}"


def _encode_canonical(value: Any) -> str:
    if value is None:
        return "null"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, int) and not isinstance(value, bool):
        return str(value)
    if isinstance(value, float):
        return _canonical_number(value)
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    if isinstance(value, Mapping):
        entries = sorted(((str(key), item) for key, item in value.items()), key=lambda pair: pair[0])
        return "{" + ",".join(
            _encode_canonical(key) + ":" + _encode_canonical(item) for key, item in entries
        ) + "}"
    if isinstance(value, (list, tuple)):
        return "[" + ",".join(_encode_canonical(item) for item in value) + "]"
    raise TypeError(f"Unsupported Wan checkpoint value: {type(value).__name__}")


def canonical_json_bytes(value: Any) -> bytes:
    """Serialize a JSON-compatible value according to ADR-009 and RFC 8785."""
    return _encode_canonical(_normalize(value)).encode("utf-8")


def sha256_hex(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def job_checksum(job: Mapping[str, Any]) -> str:
    """Checksum only the canonical job payload, never the envelope checksum."""
    return sha256_hex(canonical_json_bytes(job))


def migrate_v1_envelope(envelope: Mapping[str, Any]) -> dict[str, Any]:
    """Convert the original envelope without mutating or dropping job fields."""
    if not isinstance(envelope, Mapping):
        raise TypeError("Wan checkpoint envelope must be an object.")
    job = envelope.get("job")
    if not isinstance(job, Mapping):
        raise TypeError("Wan checkpoint envelope requires a job object.")
    migrated_job = dict(job)
    migrated_job.setdefault("revision", int(envelope.get("revision", 0)))
    result = dict(envelope)
    result["schema_version"] = 2
    result["revision"] = int(migrated_job["revision"])
    result["job"] = migrated_job
    result["checksum"] = job_checksum(migrated_job)
    result.setdefault("updated_at", migrated_job.get("updated_at"))
    result.setdefault("committed", True)
    return result


def verify_envelope(envelope: Mapping[str, Any]) -> None:
    if envelope.get("schema_version") != 2:
        raise ValueError("Wan checkpoint has an unsupported schema.")
    if envelope.get("committed") is not True:
        raise ValueError("Uncommitted Wan checkpoint is not authoritative.")
    job = envelope.get("job")
    checksum = envelope.get("checksum")
    if not isinstance(job, Mapping) or not isinstance(checksum, str):
        raise TypeError("Wan checkpoint checksum envelope is malformed.")
    if job_checksum(job) != checksum:
        raise ValueError("Wan checkpoint checksum mismatch.")
    if int(envelope.get("revision", -1)) != int(job.get("revision", -2)):
        raise ValueError("Wan checkpoint revision does not match its job payload.")
