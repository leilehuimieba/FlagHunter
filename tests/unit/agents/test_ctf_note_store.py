import json
from types import SimpleNamespace

import pytest

from flaghunter.agents.pa_agent.ctf_dispatcher import CTFTaskDispatcher
from flaghunter.agents.pa_agent.note_store import NoteStore
from flaghunter.tools import notes as notes_module

_NOTE_STORE_MODULE = "flaghunter.agents.pa_agent.note_store"


def test_note_store_cluster_lives_in_note_store_mixin():
    for name in (
        "_store_secret_note",
        "_store_missing_tools",
        "_store_retrospective",
        "_store_note",
        "_derive_artifact_producer",
        "_derive_artifact_category",
    ):
        assert getattr(CTFTaskDispatcher, name).__module__ == _NOTE_STORE_MODULE


# --- NoteStore runs fully detached from CTFTaskDispatcher ---


class _FakeState:
    """Records add_artifact(...) call args; nothing else."""

    def __init__(self):
        self.added = []

    def add_artifact(self, name, *, location=None, source="", metadata=None):
        self.added.append(
            {
                "name": name,
                "location": location,
                "source": source,
                "metadata": metadata,
            }
        )


def _make_injection():
    artifact_records = []
    emitted = []
    notes_log = []

    def register_artifact_record(**kwargs):
        artifact_records.append(kwargs)

    def emit(message):
        emitted.append(message)

    return {
        "register_artifact_record": register_artifact_record,
        "emit": emit,
        "notes_log": notes_log,
        "artifact_records": artifact_records,
        "emitted": emitted,
    }


@pytest.mark.asyncio
async def test_store_note_writes_notes_json_and_appends_passed_in_list(tmp_path):
    notes_file = tmp_path / "notes.json"
    notes_module.set_notes_file(notes_file)

    store = NoteStore()
    state = _FakeState()
    inj = _make_injection()

    await store.store_note(
        state,
        runtime=None,
        register_artifact_record=inj["register_artifact_record"],
        emit=inj["emit"],
        notes_log=inj["notes_log"],
        key="ctf_flag",
        value="FLAG{x}",
        category="artifact",
        target="http://host/path",
    )

    # (a) notes.json content written by notes_tool
    data = json.loads(notes_file.read_text(encoding="utf-8"))
    assert "ctf_flag" in data
    assert data["ctf_flag"]["content"] == "FLAG{x}"
    assert data["ctf_flag"]["category"] == "artifact"
    assert data["ctf_flag"]["confidence"] == "high"

    # (b) the passed-in list reference is appended in place (per-call, not self-held)
    assert inj["notes_log"] == ["[artifact] ctf_flag: FLAG{x}"]
    assert not hasattr(store, "_notes_log")
    assert inj["emitted"] == ["[CTF dispatcher] note saved: ctf_flag"]

    # (d) state.add_artifact args verbatim
    assert len(state.added) == 1
    added = state.added[0]
    assert added["name"] == "ctf_flag"
    # location := metadata url|target|location; here the raw target kwarg
    assert added["location"] == "http://host/path"
    assert added["source"] == "verifier"  # ctf_flag* -> verifier
    assert added["metadata"]["category"] == "flag_verified"
    assert added["metadata"]["note_category"] == "artifact"
    assert added["metadata"]["content"] == "FLAG{x}"

    # artifact record registered once, mirroring metadata
    assert len(inj["artifact_records"]) == 1
    rec = inj["artifact_records"][0]
    assert rec["kind"] == "artifact"
    assert rec["title"] == "ctf_flag"
    assert rec["producer"] == "verifier"


@pytest.mark.asyncio
async def test_store_note_per_call_list_not_shared_across_calls(tmp_path):
    notes_module.set_notes_file(tmp_path / "notes.json")
    store = NoteStore()

    inj1 = _make_injection()
    await store.store_note(
        SimpleNamespace(add_artifact=lambda *a, **k: None),
        runtime=None,
        register_artifact_record=inj1["register_artifact_record"],
        emit=inj1["emit"],
        notes_log=inj1["notes_log"],
        key="k1",
        value="v1",
        category="finding",
    )
    inj2 = _make_injection()
    await store.store_note(
        SimpleNamespace(add_artifact=lambda *a, **k: None),
        runtime=None,
        register_artifact_record=inj2["register_artifact_record"],
        emit=inj2["emit"],
        notes_log=inj2["notes_log"],
        key="k2",
        value="v2",
        category="finding",
    )

    assert inj1["notes_log"] == ["[finding] k1: v1"]
    assert inj2["notes_log"] == ["[finding] k2: v2"]


def test_derive_artifact_producer_mapping():
    store = NoteStore()
    md = {}
    assert store.derive_artifact_producer(key="ctf_flag", category="artifact", metadata=md) == "verifier"
    assert (
        store.derive_artifact_producer(key="ctf_backup_x", category="artifact", metadata=md)
        == "backup_source_leak"
    )
    assert store.derive_artifact_producer(key="other", category="artifact", metadata=md) == "notes"
    assert (
        store.derive_artifact_producer(key="other", category="credential", metadata=md) == "credential"
    )
    assert (
        store.derive_artifact_producer(
            key="x", category="artifact", metadata={"artifact_producer": "explicit"}
        )
        == "explicit"
    )
    assert (
        store.derive_artifact_producer(
            key="x", category="artifact", metadata={"strategy_kind": "ssti"}
        )
        == "ssti"
    )


def test_derive_artifact_category_mapping():
    store = NoteStore()
    md = {}
    for key, expected in (
        ("ctf_flag_candidate", "flag_candidate"),
        ("ctf_flag_runtime", "flag_runtime"),
        ("ctf_flag", "flag_verified"),
        ("ctf_backup_candidate", "backup_candidate"),
        ("ctf_backup_analysis", "backup_analysis"),
        ("ctf_artifact_forensics", "artifact_forensics_summary"),
    ):
        assert store.derive_artifact_category(key=key, category="artifact", metadata=md) == expected
    assert store.derive_artifact_category(key="unmapped", category="artifact", metadata=md) == "artifact"
    assert (
        store.derive_artifact_category(
            key="x", category="artifact", metadata={"artifact_category": "explicit"}
        )
        == "explicit"
    )
