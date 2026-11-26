"""Build reproducible delivery scenarios and verify their on-disk integrity."""

from __future__ import annotations

import hashlib
import json
import random
import re
import shutil
import tempfile
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence
from uuid import NAMESPACE_URL, uuid5

MAX_BYTES = 8 * 1024 * 1024
MAX_DELIVERIES = 10_000
DEFAULT_START = "2000-01-01T00:00:00Z"
ORDERS = ("original", "reverse", "shuffle")


def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n").encode("utf-8")


def _pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in items:
        if key in result:
            raise ValueError(f"Duplicate JSON key: {key!r}")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise ValueError(f"Non-standard JSON number: {value}")


def _read_json(path: Path) -> Any:
    # Bound the actual read, including when stat metadata is stale.
    with path.open("rb") as handle:
        raw = handle.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise ValueError(f"JSON input exceeds {MAX_BYTES} bytes: {path}")
    return json.loads(raw.decode("utf-8"), object_pairs_hook=_pairs, parse_constant=_reject_constant)


def _time(value: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError("created_at and start must be ISO 8601 strings with a timezone")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"Invalid timestamp: {value!r}") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"Timestamp needs a timezone: {value!r}")
    return parsed.astimezone(timezone.utc)


def _text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > 512:
        raise ValueError(f"{name} must be a non-empty string of at most 512 characters")
    return value


def load_events(path: str | Path) -> list[dict[str, Any]]:
    """Read a JSON array; event validation happens in create_scenario."""
    value = _read_json(Path(path))
    if not isinstance(value, list):
        raise ValueError("Input must be a JSON array of events")
    return value


@dataclass(frozen=True)
class Delivery:
    event: dict[str, Any]
    copy: int


@dataclass(frozen=True)
class Scenario:
    deliveries: tuple[Delivery, ...]
    seed: int
    order: str


@dataclass(frozen=True)
class Summary:
    deliveries: int
    unique_events: int
    duplicates: int


def create_scenario(
    events: Sequence[Mapping[str, Any]], *, copies: int = 1,
    order: str = "original", seed: int = 0, start: str = DEFAULT_START,
) -> Scenario:
    """Normalize logical events, then duplicate and order deliveries.

    IDs are stable UUID5 values derived from each source event and its index.
    A seed controls delivery order only; changing it preserves event identity.
    """
    if not isinstance(events, (list, tuple)) or not events:
        raise ValueError("Provide a non-empty list or tuple of events")
    if type(copies) is not int or not 1 <= copies <= 100:
        raise ValueError("copies must be an integer between 1 and 100")
    if type(seed) is not int:
        raise ValueError("seed must be an integer")
    if order not in ORDERS:
        raise ValueError(f"order must be one of {', '.join(ORDERS)}")
    if len(events) * copies > MAX_DELIVERIES:
        raise ValueError(f"Scenario exceeds {MAX_DELIVERIES} deliveries")
    base = _time(start)
    normalized: list[dict[str, Any]] = []
    ids: set[str] = set()
    for index, source in enumerate(events):
        if not isinstance(source, Mapping):
            raise ValueError(f"Event {index + 1} must be an object")
        unknown = set(source) - {"id", "type", "created_at", "data"}
        if unknown:
            raise ValueError(f"Event {index + 1}: put provider-specific fields inside data")
        kind = _text(source.get("type"), "type")
        if not isinstance(source.get("data"), dict):
            raise ValueError(f"Event {index + 1}: data must be an object")
        # Validate JSON serializability and detach nested data from the caller.
        source_bytes = _json_bytes(dict(source))
        if len(source_bytes) > MAX_BYTES:
            raise ValueError(f"Event {index + 1} exceeds {MAX_BYTES} bytes")
        detached = json.loads(source_bytes)
        digest = hashlib.sha256(source_bytes).hexdigest()
        event_id = _text(source["id"], "id") if "id" in source else f"evt_{uuid5(NAMESPACE_URL, f'hookfixture:v1:{index}:{digest}').hex}"
        if event_id in ids:
            raise ValueError(f"Repeated source event id {event_id!r}; use copies to create duplicate deliveries")
        ids.add(event_id)
        created = _time(source["created_at"]) if "created_at" in source else base + timedelta(seconds=index)
        normalized.append({
            "id": event_id, "type": kind,
            "created_at": created.isoformat().replace("+00:00", "Z"),
            "data": detached["data"],
        })
    deliveries = [Delivery(event, copy) for event in normalized for copy in range(1, copies + 1)]
    if order == "reverse":
        deliveries.reverse()
    elif order == "shuffle":
        random.Random(seed).shuffle(deliveries)
    return Scenario(tuple(deliveries), seed, order)


def _summary(deliveries: Sequence[Delivery]) -> Summary:
    count = len({delivery.event["id"] for delivery in deliveries})
    return Summary(len(deliveries), count, len(deliveries) - count)


def write_scenario(scenario: Scenario, destination: str | Path) -> Path:
    """Write into a new directory. Existing paths are never overwritten.

    A staging directory keeps failed writes from leaving a partial scenario.
    The parent directory must already exist.
    """
    dest = Path(destination).absolute()
    if dest.exists() or dest.is_symlink():
        raise FileExistsError(f"Output already exists: {dest}; choose a new directory")
    if not dest.parent.is_dir():
        raise ValueError(f"Output parent does not exist: {dest.parent}")
    if not scenario.deliveries or len(scenario.deliveries) > MAX_DELIVERIES:
        raise ValueError("Scenario must contain between 1 and 10,000 deliveries")
    stage = Path(tempfile.mkdtemp(prefix=".hookfixture-", dir=dest.parent))
    try:
        records = []
        for index, delivery in enumerate(scenario.deliveries, 1):
            filename = f"{index:06d}.json"
            raw = _json_bytes(delivery.event)
            (stage / filename).write_bytes(raw)
            records.append({
                "file": filename, "event_id": delivery.event["id"],
                "copy": delivery.copy, "sha256": hashlib.sha256(raw).hexdigest(),
            })
        summary = _summary(scenario.deliveries)
        manifest = {
            "format_version": 1, "seed": scenario.seed, "order": scenario.order,
            "summary": {
                "deliveries": summary.deliveries, "unique_events": summary.unique_events,
                "duplicates": summary.duplicates,
            },
            "deliveries": records,
        }
        (stage / "manifest.json").write_bytes(_json_bytes(manifest))
        # Validate before publishing so mutated library objects fail cleanly.
        verify_scenario(stage / "manifest.json")
        # mkdir reserves the target exclusively; this prevents overwriting even
        # an empty directory created by another process while files were staged.
        dest.mkdir()
        try:
            for child in stage.iterdir():
                child.rename(dest / child.name)
        except BaseException:
            shutil.rmtree(dest)
            raise
    finally:
        shutil.rmtree(stage)
    return dest / "manifest.json"


def verify_scenario(manifest_path: str | Path) -> Summary:
    """Check schema, checksums, normalized events and duplicate consistency.

    Checksums detect accidental edits; this is not an authenticity signature.
    Delivery order is the order of records in the manifest.
    """
    path = Path(manifest_path)
    manifest = _read_json(path)
    if not isinstance(manifest, dict) or type(manifest.get("format_version")) is not int or manifest["format_version"] != 1:
        raise ValueError("Unsupported or missing manifest format_version (expected 1)")
    if type(manifest.get("seed")) is not int or manifest.get("order") not in ORDERS:
        raise ValueError("Manifest needs a valid seed and order")
    records = manifest.get("deliveries")
    if not isinstance(records, list) or not 1 <= len(records) <= MAX_DELIVERIES:
        raise ValueError("Manifest must list between 1 and 10,000 deliveries")
    filenames: set[str] = set()
    payloads: dict[str, bytes] = {}
    copies: dict[str, set[int]] = {}
    for record in records:
        if not isinstance(record, dict):
            raise ValueError("Each manifest delivery must be an object")
        filename = record.get("file")
        if not isinstance(filename, str) or not re.fullmatch(r"[0-9]{6}\.json", filename):
            raise ValueError("Fixture filenames must be six digits followed by .json")
        if filename in filenames:
            raise ValueError(f"Repeated fixture filename: {filename}")
        filenames.add(filename)
        fixture = path.parent / filename
        if fixture.is_symlink():
            raise ValueError(f"Fixture must be a regular file, not a symlink: {filename}")
        with fixture.open("rb") as handle:
            raw = handle.read(MAX_BYTES + 1)
        if len(raw) > MAX_BYTES:
            raise ValueError(f"Fixture exceeds {MAX_BYTES} bytes: {filename}")
        digest = hashlib.sha256(raw).hexdigest()
        if record.get("sha256") != digest:
            raise ValueError(f"Checksum mismatch: {filename}")
        # Parse exactly the bytes whose checksum was verified.
        event = json.loads(raw.decode("utf-8"), object_pairs_hook=_pairs, parse_constant=_reject_constant)
        if not isinstance(event, dict) or set(event) != {"id", "type", "created_at", "data"}:
            raise ValueError(f"Invalid event envelope: {filename}")
        normalized = create_scenario([event]).deliveries[0].event
        if event != normalized:
            raise ValueError(f"Event must use normalized UTC timestamps: {filename}")
        event_id = event["id"]
        if record.get("event_id") != event_id:
            raise ValueError(f"Manifest event_id does not match fixture: {filename}")
        copy = record.get("copy")
        if type(copy) is not int or not 1 <= copy <= 100:
            raise ValueError(f"Invalid copy number: {filename}")
        if copy in copies.setdefault(event_id, set()):
            raise ValueError(f"Repeated copy number for {event_id}")
        copies[event_id].add(copy)
        canonical = _json_bytes(event)
        if event_id in payloads and payloads[event_id] != canonical:
            raise ValueError(f"Conflicting payloads share event id: {event_id}")
        payloads[event_id] = canonical
    for event_id, values in copies.items():
        if values != set(range(1, len(values) + 1)):
            raise ValueError(f"Copy numbers must start at 1 without gaps: {event_id}")
    summary = Summary(len(records), len(payloads), len(records) - len(payloads))
    expected = {"deliveries": summary.deliveries, "unique_events": summary.unique_events, "duplicates": summary.duplicates}
    actual = manifest.get("summary")
    if not isinstance(actual, dict) or any(type(actual.get(k)) is not int for k in expected) or actual != expected:
        raise ValueError("Manifest summary does not match its deliveries")
    return summary
