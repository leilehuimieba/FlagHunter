from __future__ import annotations

from flaghunter.harness.artifact_registry import ArtifactRegistry


def test_artifact_registry_registers_and_lists_run_records_in_write_order(tmp_path) -> None:
    registry = ArtifactRegistry(tmp_path)

    first = registry.register_artifact(
        run_id="run-artifacts-1",
        kind="artifact",
        title="ctf_backup_candidate",
        location="http://ctf.local/www.zip",
        producer="notes",
        metadata={"category": "artifact"},
    )
    second = registry.register_artifact(
        run_id="run-artifacts-1",
        kind="credential",
        title="admin_cookie",
        location="http://ctf.local/admin",
        producer="notes",
        metadata={"cookie": "sid=admin"},
    )
    registry.register_artifact(
        run_id="run-artifacts-2",
        kind="artifact",
        title="ignored-other-run",
        producer="notes",
    )

    records = registry.list_artifacts("run-artifacts-1")

    assert [item["artifact_id"] for item in records] == [
        first["artifact_id"],
        second["artifact_id"],
    ]
    assert [item["title"] for item in records] == [
        "ctf_backup_candidate",
        "admin_cookie",
    ]
    assert all(item["run_id"] == "run-artifacts-1" for item in records)


def test_artifact_registry_get_artifact_returns_record_by_id(tmp_path) -> None:
    registry = ArtifactRegistry(tmp_path)

    created = registry.register_artifact(
        run_id="run-artifacts-get",
        kind="artifact",
        title="ctf_flag_runtime",
        path=str(tmp_path / "flag.txt"),
        producer="dispatcher",
        metadata={"flag": "flag{runtime_ok}"},
    )

    loaded = registry.get_artifact(created["artifact_id"])

    assert loaded is not None
    assert loaded["artifact_id"] == created["artifact_id"]
    assert loaded["run_id"] == "run-artifacts-get"
    assert loaded["path"] == str(tmp_path / "flag.txt")
    assert loaded["metadata"]["flag"] == "flag{runtime_ok}"
