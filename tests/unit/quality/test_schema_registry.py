"""Schema registry tests (C-01 — §13.4 of the optimization guide).

C-01 acceptance: every ACTIVE schema registered with the system has
an explicit owner. These tests lock that contract and the smaller
invariants the registry must satisfy:

* record_from_mapping validates the required fields;
* InMemorySchemaRegistry rejects ACTIVE records with no owner;
* register_all_active_schemas() is idempotent and self-consistent;
* compatibility checks follow the version-ordering rules;
* the registry satisfies the SchemaRegistryPort protocol structurally.

The tests are intentionally **structural** — they never spin up a real
adapter or read from disk, so a regression in the registry surfaces
without any flaky external dependency.
"""

from __future__ import annotations

import threading
from collections.abc import Mapping

import pytest

from flaghunter.domain import (
    InMemorySchemaRegistry,
    SchemaRecord,
    SchemaStatus,
    is_reader_compatible,
    known_active_schema_count,
    record_from_mapping,
    register_all_active_schemas,
)
from flaghunter.ports import SchemaRegistryPort

# --- Helpers ------------------------------------------------------------


def _record(
    schema_id: str = "test.schema",
    version: str = "v1",
    owner: str = "test.owner",
    status: SchemaStatus = SchemaStatus.ACTIVE,
) -> dict[str, object]:
    return SchemaRecord(
        schema_id=schema_id,
        version=version,
        owner=owner,
        status=status,
    ).to_mapping()


# --- Validation ---------------------------------------------------------


def test_record_from_mapping_requires_schema_id() -> None:
    payload = {"version": "v1", "owner": "x", "status": "active"}
    with pytest.raises(ValueError, match="schema_id"):
        record_from_mapping(payload)


def test_record_from_mapping_requires_version() -> None:
    payload = {"schema_id": "x", "owner": "x", "status": "active"}
    with pytest.raises(ValueError, match="version"):
        record_from_mapping(payload)


def test_record_from_mapping_requires_owner() -> None:
    payload = {"schema_id": "x", "version": "v1", "status": "active"}
    with pytest.raises(ValueError, match="owner"):
        record_from_mapping(payload)


def test_record_from_mapping_requires_status() -> None:
    payload = {"schema_id": "x", "version": "v1", "owner": "x"}
    with pytest.raises(ValueError, match="status"):
        record_from_mapping(payload)


def test_record_from_mapping_rejects_unknown_status() -> None:
    payload = {"schema_id": "x", "version": "v1", "owner": "x", "status": "wip"}
    with pytest.raises(ValueError, match="unknown status"):
        record_from_mapping(payload)


def test_record_from_mapping_round_trip_preserves_fields() -> None:
    original = SchemaRecord(
        schema_id="x",
        version="v1",
        owner="o",
        status=SchemaStatus.ACTIVE,
        description="d",
        storage_location="s",
        introduced_at="2026-08-03",
        reader_compat=("a", "b"),
        writer_compat=("c",),
        migration_from=("v0",),
        migration_to="v2",
    )
    rebuilt = record_from_mapping(original.to_mapping())
    assert rebuilt == original


# --- Registry behaviour -------------------------------------------------


def test_register_and_get_round_trip() -> None:
    registry = InMemorySchemaRegistry()
    registry.register(_record())
    assert registry.get("test.schema", "v1") is not None
    assert registry.get("test.schema", "v2") is None
    assert registry.get("missing", "v1") is None


def test_register_rejects_duplicate_with_different_payload() -> None:
    registry = InMemorySchemaRegistry()
    registry.register(_record(schema_id="dup", version="v1", owner="a"))
    with pytest.raises(ValueError, match="duplicate registration"):
        registry.register(_record(schema_id="dup", version="v1", owner="b"))


def test_register_rejects_active_with_no_owner() -> None:
    """C-01 acceptance: an ACTIVE schema must have an owner."""
    registry = InMemorySchemaRegistry()
    with pytest.raises(ValueError, match="no owner"):
        registry.register(
            SchemaRecord(
                schema_id="orphan",
                version="v1",
                owner="",
                status=SchemaStatus.ACTIVE,
            ).to_mapping()
        )


def test_register_allows_draft_without_owner() -> None:
    registry = InMemorySchemaRegistry()
    registry.register(
        SchemaRecord(
            schema_id="wip",
            version="v0.1",
            owner="",
            status=SchemaStatus.DRAFT,
        ).to_mapping()
    )
    assert registry.get("wip", "v0.1") is not None


def test_register_is_idempotent_when_payload_unchanged() -> None:
    registry = InMemorySchemaRegistry()
    payload = _record(schema_id="stable", version="v1")
    registry.register(payload)
    registry.register(payload)  # Must not raise.
    assert len(registry) == 1


def test_latest_returns_highest_version_active() -> None:
    registry = InMemorySchemaRegistry()
    registry.register(_record(version="v1"))
    registry.register(_record(version="v2"))
    registry.register(_record(version="v3"))
    registry.register(
        SchemaRecord(
            schema_id="test.schema",
            version="v4",
            owner="test.owner",
            status=SchemaStatus.DEPRECATED,
        ).to_mapping()
    )
    latest = registry.latest("test.schema")
    assert latest is not None
    assert latest["version"] == "v3"


def test_latest_handles_non_uniform_segments() -> None:
    registry = InMemorySchemaRegistry()
    registry.register(_record(version="v2.3"))
    registry.register(_record(version="v10"))
    latest = registry.latest("test.schema")
    assert latest is not None
    assert latest["version"] == "v10"


def test_latest_returns_none_for_missing_schema() -> None:
    registry = InMemorySchemaRegistry()
    assert registry.latest("does.not.exist") is None


def test_find_by_owner_is_exact_match() -> None:
    registry = InMemorySchemaRegistry()
    registry.register(_record(schema_id="a", owner="alice"))
    registry.register(_record(schema_id="b", owner="alice"))
    registry.register(_record(schema_id="c", owner="bob"))
    assert {r["schema_id"] for r in registry.find_by_owner("alice")} == {"a", "b"}
    assert {r["schema_id"] for r in registry.find_by_owner("bob")} == {"c"}
    assert registry.find_by_owner("nobody") == []


def test_active_schemas_filters_by_status() -> None:
    registry = InMemorySchemaRegistry()
    registry.register(_record(schema_id="a", version="v1", status=SchemaStatus.ACTIVE))
    registry.register(
        _record(schema_id="a", version="v2", status=SchemaStatus.DEPRECATED)
    )
    registry.register(_record(schema_id="b", version="v1", status=SchemaStatus.DRAFT))
    registry.register(_record(schema_id="c", version="v1", status=SchemaStatus.RETIRED))
    active = registry.active_schemas()
    assert {r["schema_id"] for r in active} == {"a"}


# --- Compatibility ------------------------------------------------------


def test_is_reader_compatible_orders_versions() -> None:
    v1 = SchemaRecord(
        schema_id="x", version="v1", owner="o", status=SchemaStatus.ACTIVE
    )
    v2 = SchemaRecord(
        schema_id="x", version="v2", owner="o", status=SchemaStatus.ACTIVE
    )
    assert is_reader_compatible(v2, v1) is True
    assert is_reader_compatible(v1, v2) is False


def test_is_reader_compatible_rejects_retired_reader() -> None:
    reader = SchemaRecord(
        schema_id="x",
        version="v2",
        owner="o",
        status=SchemaStatus.RETIRED,
    )
    writer = SchemaRecord(
        schema_id="x", version="v1", owner="o", status=SchemaStatus.ACTIVE
    )
    assert is_reader_compatible(reader, writer) is False


def test_is_reader_compatible_honours_reader_compat_list() -> None:
    writer = SchemaRecord(
        schema_id="x",
        version="v2",
        owner="o",
        status=SchemaStatus.ACTIVE,
        reader_compat=("y@v3",),
    )
    matching = SchemaRecord(
        schema_id="y",
        version="v3",
        owner="o",
        status=SchemaStatus.ACTIVE,
    )
    other = SchemaRecord(
        schema_id="z",
        version="v5",
        owner="o",
        status=SchemaStatus.ACTIVE,
    )
    assert is_reader_compatible(matching, writer) is True
    assert is_reader_compatible(other, writer) is False


def test_registry_is_compatible_round_trip() -> None:
    registry = InMemorySchemaRegistry()
    registry.register(_record(version="v1", owner="o"))
    registry.register(
        SchemaRecord(
            schema_id="test.schema",
            version="v2",
            owner="o",
            status=SchemaStatus.ACTIVE,
        ).to_mapping()
    )
    v1 = registry.get("test.schema", "v1")
    v2 = registry.get("test.schema", "v2")
    assert v1 is not None and v2 is not None
    assert registry.is_compatible(v2, v1) is True
    assert registry.is_compatible(v1, v2) is False


# --- Protocol conformance ----------------------------------------------


def test_in_memory_registry_satisfies_port_protocol() -> None:
    """The in-memory implementation must be a structural SchemaRegistryPort."""
    registry = InMemorySchemaRegistry()
    assert isinstance(registry, SchemaRegistryPort)


# --- C-01 acceptance ----------------------------------------------------


def test_every_active_schema_in_canonical_catalog_has_owner() -> None:
    """§13.4 C-01 acceptance target: every active schema has an owner.

    The canonical catalog lives in
    :func:`flaghunter.domain.active_schemas.register_all_active_schemas`
    and is the only sanctioned way to introduce a new active schema.
    The owner field is required and the registry refuses active records
    without one; this test fails loud the moment a new schema is added
    to the catalog without being given a module owner.
    """
    registry = InMemorySchemaRegistry()
    register_all_active_schemas(registry)
    for record in registry.active_schemas():
        assert record["owner"], (
            f"C-01 violation: {record['schema_id']}@{record['version']} "
            f"is ACTIVE but has no owner"
        )


def test_known_active_schema_count_matches_actual_registration() -> None:
    """``known_active_schema_count`` must equal the ACTIVE set the
    catalog installs. A drift between the two means a new schema was
    added to the catalog without updating the count, which would break
    downstream size assertions.
    """
    registry = InMemorySchemaRegistry()
    register_all_active_schemas(registry)
    assert known_active_schema_count() == len(registry.active_schemas())


def test_no_duplicate_schema_id_and_version_pairs() -> None:
    registry = InMemorySchemaRegistry()
    register_all_active_schemas(registry)
    seen: set[tuple[str, str]] = set()
    for record in registry:
        key = (str(record["schema_id"]), str(record["version"]))
        assert key not in seen, f"duplicate (id, version) pair: {key}"
        seen.add(key)


def test_all_active_schemas_use_challenge_or_well_known_naming() -> None:
    """Per §10.3 of the optimization guide: public core schemas use the
    ``<namespace>.<noun>`` form; the legacy ``p2/p3/p4`` working names
    must not appear in the canonical catalog.
    """
    registry = InMemorySchemaRegistry()
    register_all_active_schemas(registry)
    forbidden_prefixes = ("p2.", "p3.", "p4.")
    for record in registry.active_schemas():
        sid = str(record["schema_id"])
        for prefix in forbidden_prefixes:
            assert not sid.startswith(prefix), (
                f"schema {sid} uses a forbidden p2/p3/p4 working name; "
                f"per §10.3 these must be retired in favour of "
                f"<namespace>.<noun>"
            )


def test_active_schemas_use_semantic_v_prefix_versions() -> None:
    """Per §10.3: integer and string versions must not be mixed on the
    same schema. The canonical seed uses the ``v`` prefix; legacy
    ``"1.7"`` style versions are rejected here.
    """
    registry = InMemorySchemaRegistry()
    register_all_active_schemas(registry)
    for record in registry.active_schemas():
        version = str(record["version"])
        assert version.startswith("v"), (
            f"schema {record['schema_id']} uses non-semantic version "
            f"{version!r}; the canonical naming is the v-prefix form"
        )


# --- Thread safety ------------------------------------------------------


def test_registry_is_safe_under_concurrent_register() -> None:
    registry = InMemorySchemaRegistry()
    payload = _record(schema_id="concurrent", version="v1")
    errors: list[BaseException] = []

    def worker() -> None:
        try:
            for _ in range(50):
                registry.register(payload)
        except BaseException as exc:  # pragma: no cover - re-raised below
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert errors == []
    assert len(registry) == 1


# --- Return-type contract for the port ---------------------------------


def test_get_returns_a_plain_mapping() -> None:
    """Records returned by the port are Mapping-typed so that future
    adapters (JSON / remote) can hydrate the same shape without the
    caller caring about the backing store.
    """
    registry = InMemorySchemaRegistry()
    registry.register(_record())
    record = registry.get("test.schema", "v1")
    assert isinstance(record, Mapping)
    assert record["schema_id"] == "test.schema"
