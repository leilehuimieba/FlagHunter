from __future__ import annotations

from types import SimpleNamespace

import pytest
import zipfile

import pentestagent.tools.notes as notes_module
from pentestagent.agents.pa_agent.ctf_dispatcher import CTFTaskDispatcher
from pentestagent.agents.pa_agent.ctf_state import CTFState
from pentestagent.harness.artifact_registry import ArtifactRegistry
from pentestagent.harness.session_ledger import SessionLedger
from pentestagent.knowledge.session_context import SessionContextView
from pentestagent.tools.notes import set_notes_file


class _ArtifactRegistryRuntime:
    def __init__(self):
        self.environment = SimpleNamespace(available_tools=[])

    async def browser_action(self, action: str, **kwargs):
        return {"error": f"unexpected action: {action}"}

    async def proxy_action(self, action: str, **kwargs):
        return {"status_code": 404, "body": ""}

    async def execute_command(self, command: str, timeout: int = 180):
        return SimpleNamespace(exit_code=0, stdout="", stderr="")


@pytest.mark.asyncio
async def test_dispatcher_registers_artifact_note_into_artifact_registry(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    monkeypatch.setattr(
        "pentestagent.agents.pa_agent.ctf_dispatcher.ToolGuard.require",
        lambda self, tools: {},
    )
    set_notes_file(tmp_path / "notes_artifact_registry.json")
    notes_module._notes.clear()

    dispatcher = CTFTaskDispatcher(runtime=_ArtifactRegistryRuntime(), progress_callback=None)
    dispatcher.state = CTFState(target="http://ctf.local", goal="拿到flag")
    dispatcher._setup_session_ledger(
        run_id="run-artifact-note",
        ledger_root=tmp_path / "ledgers",
    )
    dispatcher._setup_artifact_registry(
        run_id="run-artifact-note",
        registry_root=tmp_path / "artifacts",
    )

    await dispatcher._store_note(
        key="ctf_backup_candidate",
        value="found backup/source candidate",
        category="artifact",
        url="http://ctf.local/www.zip",
        strategy_kind="backup_source_leak",
    )

    records = ArtifactRegistry(tmp_path / "artifacts").list_artifacts("run-artifact-note")
    events = SessionLedger(tmp_path / "ledgers").read_events("run-artifact-note")

    assert len(dispatcher.state.artifacts) == 1
    assert dispatcher.state.artifacts[0].name == "ctf_backup_candidate"
    assert dispatcher.state.artifacts[0].location == "http://ctf.local/www.zip"

    assert len(records) == 1
    assert records[0]["run_id"] == "run-artifact-note"
    assert records[0]["kind"] == "artifact"
    assert records[0]["title"] == "ctf_backup_candidate"
    assert records[0]["location"] == "http://ctf.local/www.zip"
    assert records[0]["producer"] == "backup_source_leak"
    assert records[0]["metadata"]["category"] == "backup_candidate"
    assert records[0]["metadata"]["note_category"] == "artifact"
    assert records[0]["metadata"]["content"] == "found backup/source candidate"
    assert records[0]["metadata"]["strategy_kind"] == "backup_source_leak"
    assert [event["event_type"] for event in events] == ["artifact_registered"]
    assert events[0]["payload"]["kind"] == "artifact"
    assert events[0]["payload"]["title"] == "ctf_backup_candidate"


@pytest.mark.asyncio
async def test_dispatcher_registers_artifact_forensics_note_with_truthful_source(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    monkeypatch.setattr(
        "pentestagent.agents.pa_agent.ctf_dispatcher.ToolGuard.require",
        lambda self, tools: {},
    )
    set_notes_file(tmp_path / "notes_artifact_forensics.json")
    notes_module._notes.clear()

    dispatcher = CTFTaskDispatcher(runtime=_ArtifactRegistryRuntime(), progress_callback=None)
    dispatcher.state = CTFState(target="http://ctf.local", goal="拿到flag")
    dispatcher._setup_session_ledger(
        run_id="run-artifact-forensics-note",
        ledger_root=tmp_path / "ledgers",
    )
    dispatcher._setup_artifact_registry(
        run_id="run-artifact-forensics-note",
        registry_root=tmp_path / "artifacts",
    )

    await dispatcher._store_note(
        key="ctf_artifact_forensics",
        value='{"url":"http://ctf.local/challenge.zip","kind":"zip"}',
        category="artifact",
        url="http://ctf.local/challenge.zip",
        strategy_kind="artifact_forensics",
    )

    records = ArtifactRegistry(tmp_path / "artifacts").list_artifacts("run-artifact-forensics-note")
    events = SessionLedger(tmp_path / "ledgers").read_events("run-artifact-forensics-note")

    assert len(records) == 1
    assert records[0]["title"] == "ctf_artifact_forensics"
    assert records[0]["producer"] == "artifact_forensics"
    assert records[0]["metadata"]["category"] == "artifact_forensics_summary"
    assert records[0]["metadata"]["note_category"] == "artifact"
    assert records[0]["metadata"]["strategy_kind"] == "artifact_forensics"
    assert [event["event_type"] for event in events] == ["artifact_registered"]
    assert events[0]["payload"]["producer"] == "artifact_forensics"


@pytest.mark.asyncio
async def test_dispatcher_ingests_local_challenge_artifact_paths_into_artifact_registry(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    monkeypatch.setattr(
        "pentestagent.agents.pa_agent.ctf_dispatcher.ToolGuard.require",
        lambda self, tools: {},
    )

    local_artifact = tmp_path / "challenge.zip"
    local_artifact.write_text("zip-placeholder", encoding="utf-8")

    dispatcher = CTFTaskDispatcher(runtime=_ArtifactRegistryRuntime(), progress_callback=None)
    dispatcher.state = CTFState(target="http://ctf.local", goal="拿到flag")
    dispatcher._challenge_context = {"artifactPaths": [str(local_artifact)]}
    dispatcher._setup_session_ledger(
        run_id="run-local-artifact-ingest",
        ledger_root=tmp_path / "ledgers",
    )
    dispatcher._setup_artifact_registry(
        run_id="run-local-artifact-ingest",
        registry_root=tmp_path / "artifacts",
    )

    dispatcher._ingest_local_challenge_artifacts("http://ctf.local")

    records = ArtifactRegistry(tmp_path / "artifacts").list_artifacts("run-local-artifact-ingest")
    events = SessionLedger(tmp_path / "ledgers").read_events("run-local-artifact-ingest")

    assert len(dispatcher.state.artifacts) == 1
    assert dispatcher.state.artifacts[0].name == "challenge.zip"
    assert dispatcher.state.artifacts[0].location == str(local_artifact)

    assert len(records) == 1
    assert records[0]["kind"] == "local_challenge_artifact"
    assert records[0]["title"] == "challenge.zip"
    assert records[0]["path"] == str(local_artifact)
    assert records[0]["location"] == str(local_artifact)
    assert records[0]["producer"] == "local_challenge_context"
    assert records[0]["metadata"]["target"] == "ctf.local"
    assert records[0]["metadata"]["kind"] == "local_artifact_path"

    assert [event["event_type"] for event in events] == ["artifact_registered"]
    assert events[0]["payload"]["kind"] == "local_challenge_artifact"
    assert events[0]["payload"]["title"] == "challenge.zip"
    assert events[0]["payload"]["path"] == str(local_artifact)


@pytest.mark.asyncio
async def test_dispatcher_local_challenge_artifact_registry_entries_are_visible_in_session_context(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    monkeypatch.setattr(
        "pentestagent.agents.pa_agent.ctf_dispatcher.ToolGuard.require",
        lambda self, tools: {},
    )

    local_artifact = tmp_path / "evidence.txt"
    local_artifact.write_text("artifact-body", encoding="utf-8")

    dispatcher = CTFTaskDispatcher(runtime=_ArtifactRegistryRuntime(), progress_callback=None)
    dispatcher.state = CTFState(target="http://ctf.local", goal="拿到flag")
    dispatcher._challenge_context = {"artifactPaths": [str(local_artifact)]}
    dispatcher._setup_session_ledger(
        run_id="run-local-artifact-session-context",
        ledger_root=tmp_path / "ledgers",
    )
    dispatcher._setup_artifact_registry(
        run_id="run-local-artifact-session-context",
        registry_root=tmp_path / "artifacts",
    )

    dispatcher._ingest_local_challenge_artifacts("http://ctf.local")

    context = SessionContextView(
        ledger_root=tmp_path / "ledgers",
        artifact_root=tmp_path / "artifacts",
        checkpoint_root=tmp_path / "checkpoints",
    ).build_run_context("run-local-artifact-session-context")

    assert len(context["artifacts"]) == 1
    assert context["artifacts"][0]["kind"] == "local_challenge_artifact"
    assert context["artifacts"][0]["title"] == "evidence.txt"
    assert context["artifacts"][0]["path"] == str(local_artifact)
    assert context["artifacts"][0]["location"] == str(local_artifact)


@pytest.mark.asyncio
async def test_dispatcher_registers_explicit_challenge_path_root_into_artifact_registry(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    monkeypatch.setattr(
        "pentestagent.agents.pa_agent.ctf_dispatcher.ToolGuard.require",
        lambda self, tools: {},
    )

    challenge_dir = tmp_path / "easy_login"
    challenge_dir.mkdir()
    (challenge_dir / "docker-compose.yml").write_text(
        "services:\n  app:\n    image: easy-login\n",
        encoding="utf-8",
    )

    dispatcher = CTFTaskDispatcher(runtime=_ArtifactRegistryRuntime(), progress_callback=None)
    dispatcher.state = CTFState(target="http://ctf.local", goal="拿到flag")
    dispatcher._challenge_context = {
        "challengePath": str(challenge_dir),
        "artifactPaths": [],
    }
    dispatcher._setup_session_ledger(
        run_id="run-local-challenge-root",
        ledger_root=tmp_path / "ledgers",
    )
    dispatcher._setup_artifact_registry(
        run_id="run-local-challenge-root",
        registry_root=tmp_path / "artifacts",
    )

    dispatcher._ingest_local_challenge_artifacts("http://ctf.local")

    records = ArtifactRegistry(tmp_path / "artifacts").list_artifacts("run-local-challenge-root")
    events = SessionLedger(tmp_path / "ledgers").read_events("run-local-challenge-root")

    root_record = next(item for item in records if item["kind"] == "local_challenge_root")
    assert len(records) == 3
    assert root_record["title"] == "easy_login"
    assert root_record["path"] == str(challenge_dir)
    assert root_record["location"] == str(challenge_dir)
    assert root_record["producer"] == "local_challenge_context"
    assert root_record["metadata"]["target"] == "ctf.local"
    assert root_record["metadata"]["kind"] == "challenge_path_root"

    assert [event["event_type"] for event in events] == [
        "artifact_registered",
        "artifact_registered",
        "artifact_registered",
    ]
    assert events[0]["payload"]["kind"] == "local_challenge_root"
    assert events[0]["payload"]["title"] == "easy_login"


@pytest.mark.asyncio
async def test_dispatcher_challenge_path_root_registry_entry_is_visible_in_session_context(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    monkeypatch.setattr(
        "pentestagent.agents.pa_agent.ctf_dispatcher.ToolGuard.require",
        lambda self, tools: {},
    )

    challenge_dir = tmp_path / "challenge_root_ctx"
    challenge_dir.mkdir()

    dispatcher = CTFTaskDispatcher(runtime=_ArtifactRegistryRuntime(), progress_callback=None)
    dispatcher.state = CTFState(target="http://ctf.local", goal="拿到flag")
    dispatcher._challenge_context = {
        "challengePath": str(challenge_dir),
        "artifactPaths": [],
    }
    dispatcher._setup_session_ledger(
        run_id="run-local-challenge-root-context",
        ledger_root=tmp_path / "ledgers",
    )
    dispatcher._setup_artifact_registry(
        run_id="run-local-challenge-root-context",
        registry_root=tmp_path / "artifacts",
    )

    dispatcher._ingest_local_challenge_artifacts("http://ctf.local")

    context = SessionContextView(
        ledger_root=tmp_path / "ledgers",
        artifact_root=tmp_path / "artifacts",
        checkpoint_root=tmp_path / "checkpoints",
    ).build_run_context("run-local-challenge-root-context")

    root_entry = next(item for item in context["artifacts"] if item["kind"] == "local_challenge_root")
    assert len(context["artifacts"]) == 2
    assert root_entry["title"] == "challenge_root_ctx"
    assert root_entry["path"] == str(challenge_dir)
    assert root_entry["location"] == str(challenge_dir)


@pytest.mark.asyncio
async def test_dispatcher_registers_extracted_challenge_root_from_local_archive(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    monkeypatch.setattr(
        "pentestagent.agents.pa_agent.ctf_dispatcher.ToolGuard.require",
        lambda self, tools: {},
    )

    archive_src = tmp_path / "archive_src" / "easy_login"
    archive_src.mkdir(parents=True)
    (archive_src / "docker-compose.yml").write_text(
        "services:\n  app:\n    image: easy-login\n",
        encoding="utf-8",
    )

    archive_path = tmp_path / "easy_login.zip"
    with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.write(archive_src / "docker-compose.yml", arcname="easy_login/docker-compose.yml")

    dispatcher = CTFTaskDispatcher(runtime=_ArtifactRegistryRuntime(), progress_callback=None)
    dispatcher.state = CTFState(target="http://ctf.local", goal="拿到flag")
    dispatcher._challenge_context = {"artifactPaths": [str(archive_path)]}
    dispatcher._setup_session_ledger(
        run_id="run-local-archive-derived-root",
        ledger_root=tmp_path / "ledgers",
    )
    dispatcher._setup_artifact_registry(
        run_id="run-local-archive-derived-root",
        registry_root=tmp_path / "artifacts",
    )

    dispatcher._ingest_local_challenge_artifacts("http://ctf.local")

    records = ArtifactRegistry(tmp_path / "artifacts").list_artifacts("run-local-archive-derived-root")

    assert len(records) == 4
    original = next(item for item in records if item["kind"] == "local_challenge_artifact")
    derived = next(item for item in records if item["kind"] == "local_challenge_extracted_root")

    assert original["path"] == str(archive_path)
    assert derived["title"] == "easy_login"
    assert derived["producer"] == "local_challenge_context"
    assert derived["metadata"]["target"] == "ctf.local"
    assert derived["metadata"]["kind"] == "extracted_challenge_root"
    assert derived["metadata"]["source_artifact_path"] == str(archive_path)
    assert derived["path"]
    assert derived["location"] == derived["path"]


@pytest.mark.asyncio
async def test_dispatcher_extracted_challenge_root_from_local_archive_is_visible_in_session_context(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    monkeypatch.setattr(
        "pentestagent.agents.pa_agent.ctf_dispatcher.ToolGuard.require",
        lambda self, tools: {},
    )

    archive_src = tmp_path / "archive_ctx_src" / "easy_login_ctx"
    archive_src.mkdir(parents=True)
    (archive_src / "docker-compose.yml").write_text(
        "services:\n  app:\n    image: easy-login\n",
        encoding="utf-8",
    )

    archive_path = tmp_path / "easy_login_ctx.zip"
    with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.write(
            archive_src / "docker-compose.yml",
            arcname="easy_login_ctx/docker-compose.yml",
        )

    dispatcher = CTFTaskDispatcher(runtime=_ArtifactRegistryRuntime(), progress_callback=None)
    dispatcher.state = CTFState(target="http://ctf.local", goal="拿到flag")
    dispatcher._challenge_context = {"artifactPaths": [str(archive_path)]}
    dispatcher._setup_session_ledger(
        run_id="run-local-archive-derived-root-context",
        ledger_root=tmp_path / "ledgers",
    )
    dispatcher._setup_artifact_registry(
        run_id="run-local-archive-derived-root-context",
        registry_root=tmp_path / "artifacts",
    )

    dispatcher._ingest_local_challenge_artifacts("http://ctf.local")

    context = SessionContextView(
        ledger_root=tmp_path / "ledgers",
        artifact_root=tmp_path / "artifacts",
        checkpoint_root=tmp_path / "checkpoints",
    ).build_run_context("run-local-archive-derived-root-context")

    derived = next(item for item in context["artifacts"] if item["kind"] == "local_challenge_extracted_root")
    assert derived["title"] == "easy_login_ctx"
    assert derived["path"]
    assert derived["location"] == derived["path"]


@pytest.mark.asyncio
async def test_dispatcher_registers_compose_file_from_explicit_challenge_root(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    monkeypatch.setattr(
        "pentestagent.agents.pa_agent.ctf_dispatcher.ToolGuard.require",
        lambda self, tools: {},
    )

    challenge_dir = tmp_path / "compose_root"
    challenge_dir.mkdir()
    compose_file = challenge_dir / "docker-compose.yml"
    compose_file.write_text(
        "services:\n  app:\n    image: easy-login\n",
        encoding="utf-8",
    )

    dispatcher = CTFTaskDispatcher(runtime=_ArtifactRegistryRuntime(), progress_callback=None)
    dispatcher.state = CTFState(target="http://ctf.local", goal="拿到flag")
    dispatcher._challenge_context = {
        "challengePath": str(challenge_dir),
        "artifactPaths": [],
    }
    dispatcher._setup_session_ledger(
        run_id="run-local-compose-explicit-root",
        ledger_root=tmp_path / "ledgers",
    )
    dispatcher._setup_artifact_registry(
        run_id="run-local-compose-explicit-root",
        registry_root=tmp_path / "artifacts",
    )

    dispatcher._ingest_local_challenge_artifacts("http://ctf.local")

    records = ArtifactRegistry(tmp_path / "artifacts").list_artifacts("run-local-compose-explicit-root")
    compose_record = next(item for item in records if item["kind"] == "local_challenge_compose_file")

    assert compose_record["title"] == "docker-compose.yml"
    assert compose_record["path"] == str(compose_file)
    assert compose_record["location"] == str(compose_file)
    assert compose_record["producer"] == "local_challenge_context"
    assert compose_record["metadata"]["target"] == "ctf.local"
    assert compose_record["metadata"]["kind"] == "challenge_compose_file"
    assert compose_record["metadata"]["source_root_path"] == str(challenge_dir)


@pytest.mark.asyncio
async def test_dispatcher_registers_compose_file_from_extracted_challenge_root_in_session_context(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    monkeypatch.setattr(
        "pentestagent.agents.pa_agent.ctf_dispatcher.ToolGuard.require",
        lambda self, tools: {},
    )

    archive_src = tmp_path / "archive_compose_src" / "compose_ctx"
    archive_src.mkdir(parents=True)
    compose_file = archive_src / "docker-compose.yml"
    compose_file.write_text(
        "services:\n  app:\n    image: easy-login\n",
        encoding="utf-8",
    )

    archive_path = tmp_path / "compose_ctx.zip"
    with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.write(compose_file, arcname="compose_ctx/docker-compose.yml")

    dispatcher = CTFTaskDispatcher(runtime=_ArtifactRegistryRuntime(), progress_callback=None)
    dispatcher.state = CTFState(target="http://ctf.local", goal="拿到flag")
    dispatcher._challenge_context = {"artifactPaths": [str(archive_path)]}
    dispatcher._setup_session_ledger(
        run_id="run-local-compose-extracted-root",
        ledger_root=tmp_path / "ledgers",
    )
    dispatcher._setup_artifact_registry(
        run_id="run-local-compose-extracted-root",
        registry_root=tmp_path / "artifacts",
    )

    dispatcher._ingest_local_challenge_artifacts("http://ctf.local")

    context = SessionContextView(
        ledger_root=tmp_path / "ledgers",
        artifact_root=tmp_path / "artifacts",
        checkpoint_root=tmp_path / "checkpoints",
    ).build_run_context("run-local-compose-extracted-root")

    compose_entry = next(
        item for item in context["artifacts"] if item["kind"] == "local_challenge_compose_file"
    )
    assert compose_entry["title"] == "docker-compose.yml"
    assert compose_entry["path"]
    assert compose_entry["location"] == compose_entry["path"]


@pytest.mark.asyncio
async def test_dispatcher_registers_whitelisted_key_files_from_explicit_challenge_root(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    monkeypatch.setattr(
        "pentestagent.agents.pa_agent.ctf_dispatcher.ToolGuard.require",
        lambda self, tools: {},
    )

    challenge_dir = tmp_path / "key_files_root"
    challenge_dir.mkdir()
    (challenge_dir / "README.md").write_text("# easy_login\n", encoding="utf-8")
    (challenge_dir / "requirements.txt").write_text("flask==3.0.0\n", encoding="utf-8")
    (challenge_dir / "app.py").write_text("print('hello')\n", encoding="utf-8")

    dispatcher = CTFTaskDispatcher(runtime=_ArtifactRegistryRuntime(), progress_callback=None)
    dispatcher.state = CTFState(target="http://ctf.local", goal="拿到flag")
    dispatcher._challenge_context = {
        "challengePath": str(challenge_dir),
        "artifactPaths": [],
    }
    dispatcher._setup_session_ledger(
        run_id="run-local-key-files-explicit-root",
        ledger_root=tmp_path / "ledgers",
    )
    dispatcher._setup_artifact_registry(
        run_id="run-local-key-files-explicit-root",
        registry_root=tmp_path / "artifacts",
    )

    dispatcher._ingest_local_challenge_artifacts("http://ctf.local")

    records = ArtifactRegistry(tmp_path / "artifacts").list_artifacts("run-local-key-files-explicit-root")
    key_records = [item for item in records if item["kind"] == "local_challenge_key_file"]

    assert {item["title"] for item in key_records} == {"README.md", "requirements.txt", "app.py"}
    for item in key_records:
        assert item["producer"] == "local_challenge_context"
        assert item["metadata"]["target"] == "ctf.local"
        assert item["metadata"]["kind"] == "challenge_key_file"
        assert item["metadata"]["source_root_path"] == str(challenge_dir)
        assert item["path"] == item["location"]


@pytest.mark.asyncio
async def test_dispatcher_registers_whitelisted_key_files_from_extracted_challenge_root_in_session_context(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    monkeypatch.setattr(
        "pentestagent.agents.pa_agent.ctf_dispatcher.ToolGuard.require",
        lambda self, tools: {},
    )

    archive_src = tmp_path / "archive_key_src" / "key_ctx"
    archive_src.mkdir(parents=True)
    (archive_src / "README.md").write_text("# key_ctx\n", encoding="utf-8")
    (archive_src / "package.json").write_text('{"name":"key_ctx"}\n', encoding="utf-8")
    (archive_src / "docker-compose.yml").write_text(
        "services:\n  app:\n    image: key-ctx\n",
        encoding="utf-8",
    )

    archive_path = tmp_path / "key_ctx.zip"
    with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.write(archive_src / "README.md", arcname="key_ctx/README.md")
        zf.write(archive_src / "package.json", arcname="key_ctx/package.json")
        zf.write(
            archive_src / "docker-compose.yml",
            arcname="key_ctx/docker-compose.yml",
        )

    dispatcher = CTFTaskDispatcher(runtime=_ArtifactRegistryRuntime(), progress_callback=None)
    dispatcher.state = CTFState(target="http://ctf.local", goal="拿到flag")
    dispatcher._challenge_context = {"artifactPaths": [str(archive_path)]}
    dispatcher._setup_session_ledger(
        run_id="run-local-key-files-extracted-root",
        ledger_root=tmp_path / "ledgers",
    )
    dispatcher._setup_artifact_registry(
        run_id="run-local-key-files-extracted-root",
        registry_root=tmp_path / "artifacts",
    )

    dispatcher._ingest_local_challenge_artifacts("http://ctf.local")

    context = SessionContextView(
        ledger_root=tmp_path / "ledgers",
        artifact_root=tmp_path / "artifacts",
        checkpoint_root=tmp_path / "checkpoints",
    ).build_run_context("run-local-key-files-extracted-root")

    key_entries = [item for item in context["artifacts"] if item["kind"] == "local_challenge_key_file"]
    assert {item["title"] for item in key_entries} == {"README.md", "package.json"}
    for item in key_entries:
        assert item["path"] == item["location"]


@pytest.mark.asyncio
async def test_dispatcher_registers_local_challenge_root_summary_for_explicit_root(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    monkeypatch.setattr(
        "pentestagent.agents.pa_agent.ctf_dispatcher.ToolGuard.require",
        lambda self, tools: {},
    )

    challenge_dir = tmp_path / "summary_root"
    challenge_dir.mkdir()
    (challenge_dir / "docker-compose.yml").write_text("services:\n  app:\n    image: summary\n", encoding="utf-8")
    (challenge_dir / "README.md").write_text("# summary\n", encoding="utf-8")
    (challenge_dir / "requirements.txt").write_text("flask==3.0.0\n", encoding="utf-8")
    (challenge_dir / "app.py").write_text("print('ok')\n", encoding="utf-8")
    (challenge_dir / "notes.txt").write_text("misc\n", encoding="utf-8")

    dispatcher = CTFTaskDispatcher(runtime=_ArtifactRegistryRuntime(), progress_callback=None)
    dispatcher.state = CTFState(target="http://ctf.local", goal="拿到flag")
    dispatcher._challenge_context = {"challengePath": str(challenge_dir), "artifactPaths": []}
    dispatcher._setup_session_ledger(
        run_id="run-local-root-summary",
        ledger_root=tmp_path / "ledgers",
    )
    dispatcher._setup_artifact_registry(
        run_id="run-local-root-summary",
        registry_root=tmp_path / "artifacts",
    )

    dispatcher._ingest_local_challenge_artifacts("http://ctf.local")

    records = ArtifactRegistry(tmp_path / "artifacts").list_artifacts("run-local-root-summary")
    summary_record = next(item for item in records if item["kind"] == "local_challenge_root_summary")

    assert summary_record["title"] == "summary_root summary"
    assert summary_record["path"] == str(challenge_dir)
    assert summary_record["location"] == str(challenge_dir)
    assert summary_record["metadata"]["target"] == "ctf.local"
    assert summary_record["metadata"]["kind"] == "challenge_root_summary"
    assert summary_record["metadata"]["root_name"] == "summary_root"
    assert summary_record["metadata"]["has_compose"] is True
    assert summary_record["metadata"]["key_files"] == ["README.md", "app.py", "requirements.txt"]
    assert summary_record["metadata"]["detected_stack"] == ["python"]
    assert summary_record["metadata"]["file_count"] >= 5


@pytest.mark.asyncio
async def test_dispatcher_registers_local_challenge_root_summary_for_extracted_root_in_session_context(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    monkeypatch.setattr(
        "pentestagent.agents.pa_agent.ctf_dispatcher.ToolGuard.require",
        lambda self, tools: {},
    )

    archive_src = tmp_path / "archive_summary_src" / "summary_ctx"
    archive_src.mkdir(parents=True)
    (archive_src / "docker-compose.yml").write_text("services:\n  app:\n    image: summary-ctx\n", encoding="utf-8")
    (archive_src / "README.md").write_text("# summary ctx\n", encoding="utf-8")
    (archive_src / "package.json").write_text('{"name":"summary_ctx"}\n', encoding="utf-8")

    archive_path = tmp_path / "summary_ctx.zip"
    with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.write(archive_src / "docker-compose.yml", arcname="summary_ctx/docker-compose.yml")
        zf.write(archive_src / "README.md", arcname="summary_ctx/README.md")
        zf.write(archive_src / "package.json", arcname="summary_ctx/package.json")

    dispatcher = CTFTaskDispatcher(runtime=_ArtifactRegistryRuntime(), progress_callback=None)
    dispatcher.state = CTFState(target="http://ctf.local", goal="拿到flag")
    dispatcher._challenge_context = {"artifactPaths": [str(archive_path)]}
    dispatcher._setup_session_ledger(
        run_id="run-local-root-summary-extracted",
        ledger_root=tmp_path / "ledgers",
    )
    dispatcher._setup_artifact_registry(
        run_id="run-local-root-summary-extracted",
        registry_root=tmp_path / "artifacts",
    )

    dispatcher._ingest_local_challenge_artifacts("http://ctf.local")

    context = SessionContextView(
        ledger_root=tmp_path / "ledgers",
        artifact_root=tmp_path / "artifacts",
        checkpoint_root=tmp_path / "checkpoints",
    ).build_run_context("run-local-root-summary-extracted")

    summary_entry = next(item for item in context["artifacts"] if item["kind"] == "local_challenge_root_summary")
    assert summary_entry["title"] == "summary_ctx summary"
    assert summary_entry["path"]
    assert summary_entry["location"] == summary_entry["path"]
