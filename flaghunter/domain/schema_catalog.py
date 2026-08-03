"""Schema registry domain types and in-memory implementation.

The schema registry's domain layer holds three responsibilities:

1. Define the canonical record shape (``SchemaRecord``) and the
   lifecycle enum (``SchemaStatus``).
2. Define the compatibility contract — what *reader* and *writer*
   declarations look like, and what makes a (reader, writer) pair safe.
3. Provide an in-memory implementation that any test or CLI can use
   without bringing up the rest of the application.

The shapes are intentionally **mapping-shaped** at the port boundary
(see ``flaghunter.ports.schema_registry``) so that future adapters
(JSON file, remote registry) can hydrate records without inheriting
these dataclasses. The dataclasses here are the *canonical Python
form* used by the in-memory implementation; conversions happen at the
adapter boundary.
"""

from __future__ import annotations

import threading
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from enum import Enum

SCHEMA_REGISTRY_DOMAIN_VERSION = "domain.schema-catalog.v1"


class SchemaStatus(str, Enum):
    """Lifecycle of a single schema version.

    DRAFT — registered but not yet consumed by a real adapter.
    ACTIVE — the canonical version for new writes; readers must support it.
    DEPRECATED — still readable; new writes must use a newer version.
    RETIRED — not readable; only retained for audit / migration history.
    """

    DRAFT = "draft"
    ACTIVE = "active"
    DEPRECATED = "deprecated"
    RETIRED = "retired"


@dataclass(frozen=True)
class SchemaRecord:
    """Canonical schema record shape.

    Fields match §10.3 of the optimization guide (schema_id + version,
    owner, status, reader/writer compatibility, migration path, storage
    location, lifecycle dates). All fields are required except
    ``migration_from`` / ``migration_to`` / ``reader_compat`` /
    ``writer_compat`` / ``deprecation_target`` which are populated when
    relevant.
    """

    schema_id: str
    version: str
    owner: str
    status: SchemaStatus
    description: str = ""
    storage_location: str = ""
    introduced_at: str = ""
    last_written_at: str = ""
    removal_target: str = ""
    reader_compat: tuple[str, ...] = ()
    writer_compat: tuple[str, ...] = ()
    migration_from: tuple[str, ...] = ()
    migration_to: str = ""

    def to_mapping(self) -> dict[str, object]:
        return {
            "schema_id": self.schema_id,
            "version": self.version,
            "owner": self.owner,
            "status": self.status.value,
            "description": self.description,
            "storage_location": self.storage_location,
            "introduced_at": self.introduced_at,
            "last_written_at": self.last_written_at,
            "removal_target": self.removal_target,
            "reader_compat": list(self.reader_compat),
            "writer_compat": list(self.writer_compat),
            "migration_from": list(self.migration_from),
            "migration_to": self.migration_to,
        }


_REQUIRED_KEYS: tuple[str, ...] = (
    "schema_id",
    "version",
    "owner",
    "status",
)


def record_from_mapping(payload: Mapping[str, object]) -> SchemaRecord:
    """Build a SchemaRecord from a mapping (port-boundary shape).

    Raises ``ValueError`` if any required key is missing or if ``status``
    is not a known ``SchemaStatus`` value.
    """
    missing = [k for k in _REQUIRED_KEYS if k not in payload]
    if missing:
        raise ValueError(f"schema record missing required keys: {missing}")
    try:
        status = SchemaStatus(str(payload["status"]))
    except ValueError as exc:
        valid = ", ".join(s.value for s in SchemaStatus)
        raise ValueError(
            f"schema record has unknown status: {payload['status']!r}; "
            f"expected one of: {valid}"
        ) from exc
    return SchemaRecord(
        schema_id=str(payload["schema_id"]),
        version=str(payload["version"]),
        owner=str(payload["owner"]),
        status=status,
        description=str(payload.get("description", "")),
        storage_location=str(payload.get("storage_location", "")),
        introduced_at=str(payload.get("introduced_at", "")),
        last_written_at=str(payload.get("last_written_at", "")),
        removal_target=str(payload.get("removal_target", "")),
        reader_compat=tuple(str(v) for v in payload.get("reader_compat", ())),
        writer_compat=tuple(str(v) for v in payload.get("writer_compat", ())),
        migration_from=tuple(str(v) for v in payload.get("migration_from", ())),
        migration_to=str(payload.get("migration_to", "")),
    )


def _version_key(version: str) -> tuple[int, ...]:
    """Turn ``v1`` / ``v2.3`` into a comparable tuple.

    Non-numeric segments sort as ``-1`` (worst) so that ``v1`` < ``v2.3``
    < ``v10`` is consistent regardless of the segment count. Versions
    that do not start with ``v`` (e.g. legacy ``"1.7"``) are split on
    ``.`` directly.
    """
    raw = version[1:] if version.startswith("v") else version
    parts: list[int] = []
    for segment in raw.split("."):
        try:
            parts.append(int(segment))
        except ValueError:
            parts.append(-1)
    return tuple(parts)


def is_reader_compatible(
    reader: SchemaRecord,
    writer: SchemaRecord,
) -> bool:
    """Default compatibility rule: reader must be at or after writer's
    version, must be in the writer's ``reader_compat`` list, and must
    not be RETIRED.
    """
    if reader.status is SchemaStatus.RETIRED:
        return False
    if writer.reader_compat and reader.schema_id not in {
        rid.split("@")[0] for rid in writer.reader_compat
    }:
        return False
    return _version_key(reader.version) >= _version_key(writer.version)


class InMemorySchemaRegistry:
    """Thread-safe in-memory implementation of the schema registry port.

    Lookup is keyed by ``(schema_id, version)``; ``latest()`` returns the
    most recent ACTIVE version using ``_version_key`` ordering. Active
    schemas with no owner are rejected on registration (this is the
    C-01 acceptance target: "every active schema has an owner").
    """

    def __init__(self) -> None:
        self._records: dict[tuple[str, str], SchemaRecord] = {}
        self._lock = threading.Lock()

    def register(self, record: Mapping[str, object]) -> None:
        schema_record = record_from_mapping(record)
        if schema_record.status is SchemaStatus.ACTIVE and not schema_record.owner:
            raise ValueError(
                f"active schema {schema_record.schema_id}@"
                f"{schema_record.version} has no owner"
            )
        key = (schema_record.schema_id, schema_record.version)
        with self._lock:
            existing = self._records.get(key)
            if (
                existing is not None
                and existing.to_mapping() != schema_record.to_mapping()
            ):
                raise ValueError(
                    f"duplicate registration for {key}: existing record "
                    f"differs from new payload"
                )
            self._records[key] = schema_record

    def get(self, schema_id: str, version: str) -> Mapping[str, object] | None:
        with self._lock:
            record = self._records.get((schema_id, version))
        return record.to_mapping() if record is not None else None

    def latest(self, schema_id: str) -> Mapping[str, object] | None:
        with self._lock:
            candidates = [
                r
                for (sid, _), r in self._records.items()
                if sid == schema_id and r.status is SchemaStatus.ACTIVE
            ]
        if not candidates:
            return None
        candidates.sort(key=lambda r: _version_key(r.version), reverse=True)
        return candidates[0].to_mapping()

    def find_by_owner(self, owner: str) -> Sequence[Mapping[str, object]]:
        with self._lock:
            return [r.to_mapping() for r in self._records.values() if r.owner == owner]

    def active_schemas(self) -> Sequence[Mapping[str, object]]:
        with self._lock:
            return [
                r.to_mapping()
                for r in self._records.values()
                if r.status is SchemaStatus.ACTIVE
            ]

    def is_compatible(
        self,
        reader: Mapping[str, object],
        writer: Mapping[str, object],
    ) -> bool:
        reader_record = record_from_mapping(reader)
        writer_record = record_from_mapping(writer)
        return is_reader_compatible(reader_record, writer_record)

    def __iter__(self) -> Iterator[Mapping[str, object]]:
        with self._lock:
            snapshot = [r.to_mapping() for r in self._records.values()]
        return iter(snapshot)

    def __len__(self) -> int:
        with self._lock:
            return len(self._records)
