"""Quality gate execution and optimization acceptance evidence.

The quality manifest answers two separate questions:

* Did an executable gate pass for this checkout?
* Is an optimization backlog item accepted with all required evidence?

Keeping those questions separate prevents a skipped command, an unavailable tool,
or a successful unit test from being reported as operational acceptance.
"""

from __future__ import annotations

import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1
_IDENTIFIER_RE = re.compile(r"^[a-z][a-z0-9-]*$")
_ACCEPTANCE_ID_RE = re.compile(r"^([A-F])-(\d{2})$")
_MAX_CAPTURE_CHARS = 40_000


class ManifestError(ValueError):
    """Raised when a quality manifest, guide, or evidence file is invalid."""


class CheckStatus(str, Enum):
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"
    UNAVAILABLE = "unavailable"
    ERROR = "error"


class AcceptanceStatus(str, Enum):
    PASSED = "passed"
    FAILED = "failed"
    PENDING = "pending"


class AcceptanceMode(str, Enum):
    AUTOMATED = "automated"
    HYBRID = "hybrid"
    EXTERNAL = "external"
    MANUAL = "manual"


@dataclass(frozen=True)
class CommandOutcome:
    exit_code: int
    stdout: str
    stderr: str
    duration_seconds: float


@dataclass(frozen=True)
class BacklogItem:
    id: str
    phase: str
    priority: str
    work_item: str
    deliverable: str
    acceptance_target: str


@dataclass(frozen=True)
class GateDefinition:
    id: str
    title: str
    category: str
    kind: str
    blocking: bool
    timeout_seconds: int
    covers: tuple[str, ...]
    handler: str | None = None
    command: tuple[str, ...] = ()
    requires_modules: tuple[str, ...] = ()
    requires_commands: tuple[str, ...] = ()
    options: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AcceptanceRule:
    id: str
    mode: AcceptanceMode
    gates: tuple[str, ...]
    owner: str
    evidence_requirements: tuple[str, ...]


@dataclass(frozen=True)
class QualityManifest:
    schema_version: int
    profiles: Mapping[str, tuple[str, ...]]
    gates: Mapping[str, GateDefinition]
    acceptance: Mapping[str, AcceptanceRule]


@dataclass(frozen=True)
class EvidenceItem:
    status: str
    recorded_at: str
    reviewer: str
    artifacts: tuple[str, ...]
    notes: str


@dataclass(frozen=True)
class AcceptanceEvidence:
    schema_version: int
    commit: str
    items: Mapping[str, EvidenceItem]


@dataclass(frozen=True)
class GateContext:
    repo_root: Path
    gate: GateDefinition
    commit: str
    changed_python: tuple[str, ...]


@dataclass(frozen=True)
class GateResult:
    id: str
    title: str
    category: str
    blocking: bool
    status: CheckStatus
    detail: str
    command: tuple[str, ...]
    exit_code: int | None
    duration_seconds: float
    stdout: str = ""
    stderr: str = ""


@dataclass(frozen=True)
class AcceptanceResult:
    id: str
    mode: AcceptanceMode
    owner: str
    status: AcceptanceStatus
    detail: str
    gates: tuple[str, ...]
    evidence_requirements: tuple[str, ...]


@dataclass(frozen=True)
class QualityReport:
    schema_version: int
    profile: str
    commit: str
    generated_at: str
    overall_status: str
    exit_code: int
    evidence_status: str
    gates: tuple[GateResult, ...]
    acceptance: Mapping[str, AcceptanceResult]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schemaVersion": self.schema_version,
            "profile": self.profile,
            "commit": self.commit,
            "generatedAt": self.generated_at,
            "overallStatus": self.overall_status,
            "exitCode": self.exit_code,
            "evidenceStatus": self.evidence_status,
            "summary": {
                "gates": _count_values(result.status for result in self.gates),
                "acceptance": _count_values(
                    result.status for result in self.acceptance.values()
                ),
            },
            "gates": [_gate_result_dict(result) for result in self.gates],
            "acceptance": {
                item_id: _acceptance_result_dict(result)
                for item_id, result in self.acceptance.items()
            },
        }


CommandExecutor = Callable[..., CommandOutcome]
BuiltinHandler = Callable[[GateContext], CommandOutcome]


def _count_values(values: Sequence[Enum] | Any) -> dict[str, int]:
    counts: dict[str, int] = {}
    for value in values:
        key = value.value if isinstance(value, Enum) else str(value)
        counts[key] = counts.get(key, 0) + 1
    return counts


def _gate_result_dict(result: GateResult) -> dict[str, Any]:
    payload = asdict(result)
    payload["status"] = result.status.value
    payload["command"] = list(result.command)
    payload["durationSeconds"] = payload.pop("duration_seconds")
    payload["exitCode"] = payload.pop("exit_code")
    return payload


def _acceptance_result_dict(result: AcceptanceResult) -> dict[str, Any]:
    payload = asdict(result)
    payload["mode"] = result.mode.value
    payload["status"] = result.status.value
    payload["evidenceRequirements"] = list(result.evidence_requirements)
    del payload["evidence_requirements"]
    payload["gates"] = list(result.gates)
    return payload


def _reject_duplicate_json_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ManifestError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _load_json(path: Path) -> Any:
    try:
        return json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=_reject_duplicate_json_keys,
        )
    except ManifestError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ManifestError(f"cannot read JSON from {path}: {exc}") from exc


def _mapping(value: Any, location: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ManifestError(f"{location} must be an object")
    return value


def _string(value: Any, location: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ManifestError(f"{location} must be a non-empty string")
    return value.strip()


def _string_list(value: Any, location: str) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise ManifestError(f"{location} must be an array")
    result: list[str] = []
    for index, item in enumerate(value):
        result.append(_string(item, f"{location}[{index}]"))
    if len(set(result)) != len(result):
        raise ManifestError(f"{location} contains duplicate values")
    return tuple(result)


def _check_keys(
    value: Mapping[str, Any],
    *,
    location: str,
    required: set[str],
    optional: set[str] = frozenset(),
) -> None:
    missing = required - value.keys()
    unknown = value.keys() - required - optional
    if missing:
        raise ManifestError(f"{location} is missing: {', '.join(sorted(missing))}")
    if unknown:
        raise ManifestError(
            f"{location} has unknown fields: {', '.join(sorted(unknown))}"
        )


def load_manifest(path: str | Path) -> QualityManifest:
    """Load and strictly validate a schema-versioned quality manifest."""

    manifest_path = Path(path)
    raw = _mapping(_load_json(manifest_path), "manifest")
    _check_keys(
        raw,
        location="manifest",
        required={"schemaVersion", "profiles", "gates", "acceptance"},
        optional={"description"},
    )
    if raw["schemaVersion"] != SCHEMA_VERSION:
        raise ManifestError(
            f"unsupported manifest schemaVersion: {raw['schemaVersion']!r}"
        )

    raw_acceptance = _mapping(raw["acceptance"], "acceptance")
    acceptance: dict[str, AcceptanceRule] = {}
    for item_id, item_value in raw_acceptance.items():
        if not _ACCEPTANCE_ID_RE.fullmatch(item_id):
            raise ManifestError(f"invalid acceptance ID: {item_id!r}")
        item = _mapping(item_value, f"acceptance.{item_id}")
        _check_keys(
            item,
            location=f"acceptance.{item_id}",
            required={"mode", "gates", "owner", "evidenceRequirements"},
        )
        try:
            mode = AcceptanceMode(_string(item["mode"], f"acceptance.{item_id}.mode"))
        except ValueError as exc:
            allowed = ", ".join(mode.value for mode in AcceptanceMode)
            raise ManifestError(
                f"acceptance.{item_id}.mode must be one of: {allowed}"
            ) from exc
        gates = _string_list(item["gates"], f"acceptance.{item_id}.gates")
        evidence_requirements = _string_list(
            item["evidenceRequirements"],
            f"acceptance.{item_id}.evidenceRequirements",
        )
        if mode is AcceptanceMode.AUTOMATED and not gates:
            raise ManifestError(f"automated acceptance {item_id} requires gates")
        if mode is AcceptanceMode.HYBRID and (not gates or not evidence_requirements):
            raise ManifestError(
                f"hybrid acceptance {item_id} requires gates and evidence"
            )
        if (
            mode in {AcceptanceMode.EXTERNAL, AcceptanceMode.MANUAL}
            and not evidence_requirements
        ):
            raise ManifestError(f"{mode.value} acceptance {item_id} requires evidence")
        acceptance[item_id] = AcceptanceRule(
            id=item_id,
            mode=mode,
            gates=gates,
            owner=_string(item["owner"], f"acceptance.{item_id}.owner"),
            evidence_requirements=evidence_requirements,
        )

    raw_gates = raw["gates"]
    if not isinstance(raw_gates, list):
        raise ManifestError("gates must be an array")
    gates: dict[str, GateDefinition] = {}
    for index, gate_value in enumerate(raw_gates):
        location = f"gates[{index}]"
        gate = _mapping(gate_value, location)
        _check_keys(
            gate,
            location=location,
            required={
                "id",
                "title",
                "category",
                "kind",
                "blocking",
                "timeoutSeconds",
                "covers",
            },
            optional={
                "handler",
                "command",
                "requiresModules",
                "requiresCommands",
                "options",
            },
        )
        gate_id = _string(gate["id"], f"{location}.id")
        if not _IDENTIFIER_RE.fullmatch(gate_id):
            raise ManifestError(f"invalid gate ID: {gate_id!r}")
        if gate_id in gates:
            raise ManifestError(f"duplicate gate ID: {gate_id}")
        kind = _string(gate["kind"], f"{location}.kind")
        if kind not in {"builtin", "command"}:
            raise ManifestError(f"{location}.kind must be builtin or command")
        blocking = gate["blocking"]
        if not isinstance(blocking, bool):
            raise ManifestError(f"{location}.blocking must be a boolean")
        timeout = gate["timeoutSeconds"]
        if isinstance(timeout, bool) or not isinstance(timeout, int) or timeout <= 0:
            raise ManifestError(f"{location}.timeoutSeconds must be a positive integer")
        covers = _string_list(gate["covers"], f"{location}.covers")
        unknown_covers = set(covers) - acceptance.keys()
        if unknown_covers:
            raise ManifestError(
                f"{location}.covers has unknown acceptance IDs: "
                f"{', '.join(sorted(unknown_covers))}"
            )
        handler_value = gate.get("handler")
        command_value = gate.get("command", [])
        handler = None
        command: tuple[str, ...] = ()
        if kind == "builtin":
            handler = _string(handler_value, f"{location}.handler")
            if "command" in gate:
                raise ManifestError(f"{location} builtin gate cannot define command")
        else:
            command = _string_list(command_value, f"{location}.command")
            if not command:
                raise ManifestError(f"{location}.command cannot be empty")
            if "handler" in gate:
                raise ManifestError(f"{location} command gate cannot define handler")
        options = gate.get("options", {})
        if not isinstance(options, dict):
            raise ManifestError(f"{location}.options must be an object")
        gates[gate_id] = GateDefinition(
            id=gate_id,
            title=_string(gate["title"], f"{location}.title"),
            category=_string(gate["category"], f"{location}.category"),
            kind=kind,
            blocking=blocking,
            timeout_seconds=timeout,
            covers=covers,
            handler=handler,
            command=command,
            requires_modules=_string_list(
                gate.get("requiresModules", []), f"{location}.requiresModules"
            ),
            requires_commands=_string_list(
                gate.get("requiresCommands", []), f"{location}.requiresCommands"
            ),
            options=dict(options),
        )

    raw_profiles = _mapping(raw["profiles"], "profiles")
    if not raw_profiles:
        raise ManifestError("profiles cannot be empty")
    profiles: dict[str, tuple[str, ...]] = {}
    for name, profile_value in raw_profiles.items():
        if not _IDENTIFIER_RE.fullmatch(name):
            raise ManifestError(f"invalid profile name: {name!r}")
        profile_gates = _string_list(profile_value, f"profiles.{name}")
        unknown_gates = set(profile_gates) - gates.keys()
        if unknown_gates:
            raise ManifestError(
                f"profiles.{name} references unknown gate: "
                f"{', '.join(sorted(unknown_gates))}"
            )
        profiles[name] = profile_gates

    return QualityManifest(
        schema_version=SCHEMA_VERSION,
        profiles=profiles,
        gates=gates,
        acceptance=acceptance,
    )


def load_evidence(path: str | Path) -> AcceptanceEvidence:
    """Load external acceptance evidence without treating it as executable data."""

    evidence_path = Path(path)
    raw = _mapping(_load_json(evidence_path), "evidence")
    _check_keys(
        raw,
        location="evidence",
        required={"schemaVersion", "commit", "items"},
    )
    if raw["schemaVersion"] != SCHEMA_VERSION:
        raise ManifestError(
            f"unsupported evidence schemaVersion: {raw['schemaVersion']!r}"
        )
    commit = _string(raw["commit"], "evidence.commit")
    raw_items = _mapping(raw["items"], "evidence.items")
    items: dict[str, EvidenceItem] = {}
    for item_id, item_value in raw_items.items():
        if not _ACCEPTANCE_ID_RE.fullmatch(item_id):
            raise ManifestError(f"invalid evidence item ID: {item_id!r}")
        location = f"evidence.items.{item_id}"
        item = _mapping(item_value, location)
        _check_keys(
            item,
            location=location,
            required={"status", "recordedAt", "reviewer", "artifacts", "notes"},
        )
        status = _string(item["status"], f"{location}.status")
        if status not in {"passed", "failed"}:
            raise ManifestError(f"{location}.status must be passed or failed")
        recorded_at = _string(item["recordedAt"], f"{location}.recordedAt")
        _validate_timestamp(recorded_at, f"{location}.recordedAt")
        artifacts = _string_list(item["artifacts"], f"{location}.artifacts")
        if status == "passed" and not artifacts:
            raise ManifestError(f"{location}.artifacts cannot be empty when passed")
        notes = item["notes"]
        if not isinstance(notes, str):
            raise ManifestError(f"{location}.notes must be a string")
        items[item_id] = EvidenceItem(
            status=status,
            recorded_at=recorded_at,
            reviewer=_string(item["reviewer"], f"{location}.reviewer"),
            artifacts=artifacts,
            notes=notes.strip(),
        )
    return AcceptanceEvidence(SCHEMA_VERSION, commit, items)


def _validate_timestamp(value: str, location: str) -> None:
    candidate = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError as exc:
        raise ManifestError(f"{location} must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None:
        raise ManifestError(f"{location} must include a timezone")


def _split_markdown_row(line: str) -> list[str]:
    stripped = line.strip()
    if not stripped.startswith("|"):
        return []
    body = stripped[1:-1] if stripped.endswith("|") else stripped[1:]
    cells: list[str] = []
    current: list[str] = []
    escaped = False
    for character in body:
        if escaped:
            current.append(character)
            escaped = False
        elif character == "\\":
            current.append(character)
            escaped = True
        elif character == "|":
            cells.append("".join(current).strip().replace("\\|", "|"))
            current = []
        else:
            current.append(character)
    cells.append("".join(current).strip().replace("\\|", "|"))
    return cells


def _is_markdown_separator(cells: Sequence[str]) -> bool:
    return bool(cells) and all(
        re.fullmatch(r":?-{3,}:?", cell.replace(" ", "")) for cell in cells
    )


def parse_optimization_backlog(path: str | Path) -> dict[str, BacklogItem]:
    """Parse only canonical backlog tables from the optimization guide."""

    guide_path = Path(path)
    try:
        lines = guide_path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError) as exc:
        raise ManifestError(
            f"cannot read optimization guide {guide_path}: {exc}"
        ) from exc

    required_columns = ["ID", "优先级", "工作项", "预期产物", "验收目标"]
    items: dict[str, BacklogItem] = {}
    index = 0
    while index < len(lines) - 1:
        header = _split_markdown_row(lines[index])
        separator = _split_markdown_row(lines[index + 1])
        if not (
            all(column in header for column in required_columns)
            and len(separator) == len(header)
            and _is_markdown_separator(separator)
        ):
            index += 1
            continue
        positions = {column: header.index(column) for column in required_columns}
        index += 2
        while index < len(lines):
            cells = _split_markdown_row(lines[index])
            if not cells or len(cells) != len(header):
                break
            item_id = cells[positions["ID"]]
            match = _ACCEPTANCE_ID_RE.fullmatch(item_id)
            if match:
                if item_id in items:
                    raise ManifestError(f"duplicate backlog item: {item_id}")
                items[item_id] = BacklogItem(
                    id=item_id,
                    phase=match.group(1),
                    priority=cells[positions["优先级"]],
                    work_item=cells[positions["工作项"]],
                    deliverable=cells[positions["预期产物"]],
                    acceptance_target=cells[positions["验收目标"]],
                )
            index += 1
    if not items:
        raise ManifestError(f"no optimization backlog tables found in {guide_path}")
    return items


def validate_manifest_against_backlog(
    manifest: QualityManifest,
    backlog: Mapping[str, BacklogItem],
) -> None:
    """Require a one-to-one mapping between the guide and acceptance rules."""

    expected = set(backlog)
    actual = set(manifest.acceptance)
    missing = expected - actual
    unexpected = actual - expected
    problems: list[str] = []
    if missing:
        problems.append(f"missing acceptance items: {', '.join(sorted(missing))}")
    if unexpected:
        problems.append(f"unexpected acceptance items: {', '.join(sorted(unexpected))}")
    dangling_rules = {
        item_id: sorted(set(rule.gates) - manifest.gates.keys())
        for item_id, rule in manifest.acceptance.items()
        if set(rule.gates) - manifest.gates.keys()
    }
    for item_id, unknown_gates in dangling_rules.items():
        problems.append(
            f"acceptance.{item_id} references unknown gates: "
            f"{', '.join(unknown_gates)}"
        )
    if problems:
        raise ManifestError("; ".join(problems))


class QualityRunner:
    """Execute a manifest profile and derive evidence-aware acceptance states."""

    def __init__(
        self,
        manifest: QualityManifest,
        *,
        repo_root: str | Path,
        command_executor: CommandExecutor | None = None,
        builtin_handlers: Mapping[str, BuiltinHandler] | None = None,
        module_available: Callable[[str], bool] | None = None,
        command_available: Callable[[str], bool] | None = None,
    ) -> None:
        self.manifest = manifest
        self.repo_root = Path(repo_root).resolve()
        self.command_executor = command_executor or _execute_command
        self.builtin_handlers = dict(builtin_handlers or {})
        self.module_available = module_available or _module_available
        self.command_available = command_available or (
            lambda name: shutil.which(name) is not None
        )

    def run(
        self,
        profile: str,
        *,
        commit: str,
        changed_python: Sequence[str | Path] | None = None,
        evidence: AcceptanceEvidence | None = None,
        require_acceptance: bool = False,
        acceptance_ids: Sequence[str] | None = None,
    ) -> QualityReport:
        if profile not in self.manifest.profiles:
            raise ManifestError(f"unknown quality profile: {profile}")
        commit = _string(commit, "commit")
        changed = tuple(str(path).replace("\\", "/") for path in (changed_python or ()))
        gate_results = tuple(
            self._run_gate(self.manifest.gates[gate_id], commit, changed)
            for gate_id in self.manifest.profiles[profile]
        )
        evidence_status = (
            "not_provided"
            if evidence is None
            else "matched" if evidence.commit == commit else "stale"
        )
        accepted_evidence = evidence if evidence_status == "matched" else None
        acceptance = self._evaluate_acceptance(gate_results, accepted_evidence)

        blocking_failure = any(
            result.blocking
            and result.status
            in {CheckStatus.FAILED, CheckStatus.UNAVAILABLE, CheckStatus.ERROR}
            for result in gate_results
        )
        required_failure = False
        if require_acceptance:
            selected = tuple(acceptance_ids or acceptance.keys())
            unknown = set(selected) - acceptance.keys()
            if unknown:
                raise ManifestError(
                    f"unknown required acceptance IDs: {', '.join(sorted(unknown))}"
                )
            required_failure = any(
                acceptance[item_id].status is not AcceptanceStatus.PASSED
                for item_id in selected
            )
        exit_code = 1 if blocking_failure or required_failure else 0
        has_advisory_problem = any(
            not result.blocking
            and result.status
            in {CheckStatus.FAILED, CheckStatus.UNAVAILABLE, CheckStatus.ERROR}
            for result in gate_results
        )
        overall_status = (
            "failed"
            if exit_code
            else "passed_with_advisories" if has_advisory_problem else "passed"
        )
        return QualityReport(
            schema_version=SCHEMA_VERSION,
            profile=profile,
            commit=commit,
            generated_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            overall_status=overall_status,
            exit_code=exit_code,
            evidence_status=evidence_status,
            gates=gate_results,
            acceptance=acceptance,
        )

    def _run_gate(
        self,
        gate: GateDefinition,
        commit: str,
        changed_python: tuple[str, ...],
    ) -> GateResult:
        if gate.kind == "command" and "{changed_python}" in gate.command:
            if not changed_python:
                return GateResult(
                    id=gate.id,
                    title=gate.title,
                    category=gate.category,
                    blocking=gate.blocking,
                    status=CheckStatus.SKIPPED,
                    detail="No changed Python files; gate was not executed.",
                    command=gate.command,
                    exit_code=None,
                    duration_seconds=0.0,
                )

        missing_modules = [
            name for name in gate.requires_modules if not self.module_available(name)
        ]
        missing_commands = [
            name for name in gate.requires_commands if not self.command_available(name)
        ]
        if missing_modules or missing_commands:
            missing: list[str] = []
            if missing_modules:
                missing.append(f"Python modules: {', '.join(missing_modules)}")
            if missing_commands:
                missing.append(f"commands: {', '.join(missing_commands)}")
            return GateResult(
                id=gate.id,
                title=gate.title,
                category=gate.category,
                blocking=gate.blocking,
                status=CheckStatus.UNAVAILABLE,
                detail="Missing required " + "; ".join(missing),
                command=gate.command,
                exit_code=None,
                duration_seconds=0.0,
            )

        context = GateContext(self.repo_root, gate, commit, changed_python)
        command: tuple[str, ...] = ()
        started = time.monotonic()
        try:
            if gate.kind == "builtin":
                handler = self.builtin_handlers.get(gate.handler or "")
                if handler is None:
                    return GateResult(
                        id=gate.id,
                        title=gate.title,
                        category=gate.category,
                        blocking=gate.blocking,
                        status=CheckStatus.UNAVAILABLE,
                        detail=f"Built-in handler is not registered: {gate.handler}",
                        command=(),
                        exit_code=None,
                        duration_seconds=0.0,
                    )
                outcome = handler(context)
            else:
                command = _expand_command(gate.command, context)
                outcome = self.command_executor(
                    command,
                    cwd=self.repo_root,
                    timeout_seconds=gate.timeout_seconds,
                )
            if not isinstance(outcome, CommandOutcome):
                raise TypeError("gate executor did not return CommandOutcome")
        except FileNotFoundError as exc:
            return GateResult(
                id=gate.id,
                title=gate.title,
                category=gate.category,
                blocking=gate.blocking,
                status=CheckStatus.UNAVAILABLE,
                detail=f"Command is unavailable: {exc}",
                command=command,
                exit_code=None,
                duration_seconds=time.monotonic() - started,
            )
        except subprocess.TimeoutExpired as exc:
            return GateResult(
                id=gate.id,
                title=gate.title,
                category=gate.category,
                blocking=gate.blocking,
                status=CheckStatus.FAILED,
                detail=f"Gate timed out after {gate.timeout_seconds} seconds: {exc}",
                command=command,
                exit_code=124,
                duration_seconds=time.monotonic() - started,
            )
        except Exception as exc:  # The report must preserve a broken gate as a result.
            return GateResult(
                id=gate.id,
                title=gate.title,
                category=gate.category,
                blocking=gate.blocking,
                status=CheckStatus.ERROR,
                detail=f"Gate execution error: {type(exc).__name__}: {exc}",
                command=command,
                exit_code=None,
                duration_seconds=time.monotonic() - started,
            )

        stdout = _truncate(outcome.stdout)
        stderr = _truncate(outcome.stderr)
        status = CheckStatus.PASSED if outcome.exit_code == 0 else CheckStatus.FAILED
        detail = _outcome_detail(outcome)
        return GateResult(
            id=gate.id,
            title=gate.title,
            category=gate.category,
            blocking=gate.blocking,
            status=status,
            detail=detail,
            command=command,
            exit_code=outcome.exit_code,
            duration_seconds=outcome.duration_seconds,
            stdout=stdout,
            stderr=stderr,
        )

    def _evaluate_acceptance(
        self,
        gate_results: Sequence[GateResult],
        evidence: AcceptanceEvidence | None,
    ) -> dict[str, AcceptanceResult]:
        by_gate = {result.id: result for result in gate_results}
        results: dict[str, AcceptanceResult] = {}
        for item_id, rule in self.manifest.acceptance.items():
            gate_state, gate_detail = _gate_acceptance_state(rule, by_gate)
            evidence_item = evidence.items.get(item_id) if evidence else None
            evidence_state = evidence_item.status if evidence_item else "missing"

            if gate_state == "failed" or evidence_state == "failed":
                status = AcceptanceStatus.FAILED
                detail = (
                    gate_detail
                    if gate_state == "failed"
                    else "External evidence failed."
                )
            elif rule.mode is AcceptanceMode.AUTOMATED:
                status = (
                    AcceptanceStatus.PASSED
                    if gate_state == "passed"
                    else AcceptanceStatus.PENDING
                )
                detail = gate_detail
            elif rule.mode is AcceptanceMode.HYBRID:
                if gate_state == "passed" and evidence_state == "passed":
                    status = AcceptanceStatus.PASSED
                    detail = "Automated gates and matching external evidence passed."
                else:
                    status = AcceptanceStatus.PENDING
                    missing_parts: list[str] = []
                    if gate_state != "passed":
                        missing_parts.append(gate_detail)
                    if evidence_state != "passed":
                        missing_parts.append("Matching external evidence is required.")
                    detail = " ".join(missing_parts)
            else:
                status = (
                    AcceptanceStatus.PASSED
                    if evidence_state == "passed"
                    else AcceptanceStatus.PENDING
                )
                detail = (
                    "Matching external evidence passed."
                    if status is AcceptanceStatus.PASSED
                    else "Matching external evidence is required."
                )
            results[item_id] = AcceptanceResult(
                id=item_id,
                mode=rule.mode,
                owner=rule.owner,
                status=status,
                detail=detail,
                gates=rule.gates,
                evidence_requirements=rule.evidence_requirements,
            )
        return results


def _gate_acceptance_state(
    rule: AcceptanceRule,
    gate_results: Mapping[str, GateResult],
) -> tuple[str, str]:
    if not rule.gates:
        return "not_required", "No automated gate is required."
    present = [gate_results.get(gate_id) for gate_id in rule.gates]
    failed = [
        result
        for result in present
        if result is not None
        and result.status
        in {CheckStatus.FAILED, CheckStatus.UNAVAILABLE, CheckStatus.ERROR}
    ]
    if failed:
        labels = ", ".join(f"{result.id}={result.status.value}" for result in failed)
        return "failed", f"Required gates did not pass: {labels}."
    pending = [
        gate_id
        for gate_id, result in zip(rule.gates, present, strict=False)
        if result is None or result.status is CheckStatus.SKIPPED
    ]
    if pending:
        return "pending", f"Required gates were not executed: {', '.join(pending)}."
    return "passed", "All required automated gates passed."


def _expand_command(command: Sequence[str], context: GateContext) -> tuple[str, ...]:
    expanded: list[str] = []
    for argument in command:
        if argument == "{changed_python}":
            expanded.extend(context.changed_python)
            continue
        expanded.append(
            argument.replace("{python}", sys.executable)
            .replace("{repo_root}", str(context.repo_root))
            .replace("{commit}", context.commit)
        )
    return tuple(expanded)


def _module_available(name: str) -> bool:
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ModuleNotFoundError, ValueError):
        return False


def _execute_command(
    command: tuple[str, ...],
    *,
    cwd: Path,
    timeout_seconds: int,
) -> CommandOutcome:
    started = time.monotonic()
    environment = os.environ.copy()
    environment.setdefault("PYTHONUTF8", "1")
    completed = subprocess.run(
        command,
        cwd=cwd,
        env=environment,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        timeout=timeout_seconds,
        shell=False,
        check=False,
    )
    return CommandOutcome(
        exit_code=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
        duration_seconds=time.monotonic() - started,
    )


def _outcome_detail(outcome: CommandOutcome) -> str:
    output = outcome.stderr.strip() or outcome.stdout.strip()
    if outcome.exit_code == 0:
        return _truncate(output or "Gate completed successfully.", 4_000)
    return _truncate(
        f"Command exited with {outcome.exit_code}." + (f" {output}" if output else ""),
        4_000,
    )


def _truncate(value: str, limit: int = _MAX_CAPTURE_CHARS) -> str:
    if len(value) <= limit:
        return value
    return value[:limit] + f"\n... truncated {len(value) - limit} characters"


def write_reports(
    report: QualityReport,
    output_directory: str | Path,
) -> tuple[Path, Path]:
    """Atomically write machine-readable JSON and a review-friendly summary."""

    output_dir = Path(output_directory)
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "quality-report.json"
    markdown_path = output_dir / "quality-report.md"
    json_text = json.dumps(report.to_dict(), ensure_ascii=False, indent=2) + "\n"
    markdown_text = _render_markdown(report)
    _atomic_write(json_path, json_text)
    _atomic_write(markdown_path, markdown_text)
    return json_path, markdown_path


def _atomic_write(path: Path, content: str) -> None:
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
            temporary_path = Path(handle.name)
        os.replace(temporary_path, path)
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()


def _render_markdown(report: QualityReport) -> str:
    lines = [
        "# Quality Acceptance Report",
        "",
        f"- Profile: `{report.profile}`",
        f"- Commit: `{report.commit}`",
        f"- Generated: `{report.generated_at}`",
        f"- Overall: **{report.overall_status}**",
        f"- Evidence: `{report.evidence_status}`",
        "",
        "## Gate Results",
        "",
        "| Gate | Category | Blocking | Status | Duration | Detail |",
        "|---|---|---:|---|---:|---|",
    ]
    for result in report.gates:
        lines.append(
            "| "
            + " | ".join(
                [
                    _markdown_cell(result.id),
                    _markdown_cell(result.category),
                    "yes" if result.blocking else "no",
                    result.status.value,
                    f"{result.duration_seconds:.3f}s",
                    _markdown_cell(result.detail),
                ]
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "## Acceptance Results",
            "",
            "| Item | Mode | Owner | Status | Required gates | Detail |",
            "|---|---|---|---|---|---|",
        ]
    )
    for item_id, result in report.acceptance.items():
        lines.append(
            "| "
            + " | ".join(
                [
                    item_id,
                    result.mode.value,
                    _markdown_cell(result.owner),
                    result.status.value,
                    _markdown_cell(", ".join(result.gates) or "none"),
                    _markdown_cell(result.detail),
                ]
            )
            + " |"
        )
    lines.append("")
    return "\n".join(lines)


def _markdown_cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\r", " ").replace("\n", " ")
