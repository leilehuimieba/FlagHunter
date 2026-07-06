from __future__ import annotations

import ast
import warnings
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
PRODUCTION_ROOT = REPO_ROOT / "flaghunter"


def _relative(path: Path) -> str:
    return path.relative_to(REPO_ROOT).as_posix()


def _python_sources(root: Path):
    return sorted(
        path
        for path in root.rglob("*.py")
        if "__pycache__" not in path.parts
    )


class _AddFlagVerifiedVisitor(ast.NodeVisitor):
    def __init__(self, relative_path: str):
        self.relative_path = relative_path
        self.scope: list[str] = []
        self.hits: list[tuple[str, str, int]] = []

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self.scope.append(node.name)
        self.generic_visit(node)
        self.scope.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self.scope.append(node.name)
        self.generic_visit(node)
        self.scope.pop()

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self.scope.append(node.name)
        self.generic_visit(node)
        self.scope.pop()

    def visit_Call(self, node: ast.Call) -> None:
        if (
            isinstance(node.func, ast.Attribute)
            and node.func.attr == "add_flag"
            and any(
                keyword.arg == "level"
                and isinstance(keyword.value, ast.Constant)
                and keyword.value.value == "verified"
                for keyword in node.keywords
            )
        ):
            self.hits.append(
                (
                    self.relative_path,
                    ".".join(self.scope) or "<module>",
                    node.lineno,
                )
            )
        self.generic_visit(node)


def _add_flag_verified_writes() -> list[tuple[str, str, int]]:
    hits: list[tuple[str, str, int]] = []
    for path in _python_sources(PRODUCTION_ROOT):
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", SyntaxWarning)
            tree = ast.parse(
                path.read_text(encoding="utf-8-sig"),
                filename=str(path),
            )
        visitor = _AddFlagVerifiedVisitor(_relative(path))
        visitor.visit(tree)
        hits.extend(visitor.hits)
    return hits


def _parse_source(path: str) -> ast.Module:
    source_path = REPO_ROOT / path
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", SyntaxWarning)
        return ast.parse(
            source_path.read_text(encoding="utf-8-sig"),
            filename=str(source_path),
        )


def _scope_node(tree: ast.AST, qualified_scope: str) -> ast.AST:
    wanted = qualified_scope.split(".")
    found: ast.AST | None = None

    class ScopeVisitor(ast.NodeVisitor):
        def __init__(self):
            self.scope: list[str] = []

        def visit_ClassDef(self, node: ast.ClassDef) -> None:
            nonlocal found
            self.scope.append(node.name)
            if self.scope == wanted:
                found = node
                self.scope.pop()
                return
            self.generic_visit(node)
            self.scope.pop()

        def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
            nonlocal found
            self.scope.append(node.name)
            if self.scope == wanted:
                found = node
                self.scope.pop()
                return
            self.generic_visit(node)
            self.scope.pop()

        def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
            nonlocal found
            self.scope.append(node.name)
            if self.scope == wanted:
                found = node
                self.scope.pop()
                return
            self.generic_visit(node)
            self.scope.pop()

    ScopeVisitor().visit(tree)
    assert found is not None, f"{qualified_scope} was not found"
    return found


def _file_contains(path: str, needle: str) -> bool:
    return needle in (REPO_ROOT / path).read_text(encoding="utf-8")


def test_p1_verified_legacy_bucket_writes_stay_verifier_only() -> None:
    allowed: set[tuple[str, str]] = {
        ("flaghunter/agents/pa_agent/verifier.py", "CTFVerifier.verify_flag"),
        (
            "flaghunter/agents/pa_agent/verifier.py",
            "CTFVerifier._attempt_submit_if_configured",
        ),
        (
            "flaghunter/agents/pa_agent/verifier.py",
            "CTFVerifier._attempt_user_confirmation",
        ),
    }

    unexpected = [
        (path, scope, line)
        for path, scope, line in _add_flag_verified_writes()
        if (path, scope) not in allowed
    ]

    assert unexpected == []


def test_p1_proof_authority_write_calls_stay_in_verifier_and_state_only() -> None:
    allowed_calls: set[tuple[str, str, str]] = {
        (
            "flaghunter/agents/pa_agent/verifier.py",
            "CTFVerifier._sync_flag_claim",
            "upgrade_claim_to_verified",
        ),
        (
            "flaghunter/agents/pa_agent/verifier.py",
            "CTFVerifier._append_flag_verification_record",
            "append_verification_record",
        ),
        (
            "flaghunter/agents/pa_agent/verifier.py",
            "CTFVerifier._ensure_result_trace",
            "record_verification_receipt",
        ),
    }
    allowed_definitions: set[tuple[str, str, str]] = {
        (
            "flaghunter/agents/pa_agent/ctf_state.py",
            "CTFState.upgrade_claim_to_verified",
            "upgrade_claim_to_verified",
        ),
        (
            "flaghunter/agents/pa_agent/ctf_state.py",
            "CTFState.append_verification_record",
            "append_verification_record",
        ),
        (
            "flaghunter/agents/pa_agent/ctf_state.py",
            "CTFState.record_verification_receipt",
            "record_verification_receipt",
        ),
    }
    guarded_names = {
        "upgrade_claim_to_verified",
        "append_verification_record",
        "record_verification_receipt",
    }
    offenders: list[tuple[str, str, str, int]] = []

    class ProofAuthorityVisitor(ast.NodeVisitor):
        def __init__(self, relative_path: str):
            self.relative_path = relative_path
            self.scope: list[str] = []

        def visit_ClassDef(self, node: ast.ClassDef) -> None:
            self.scope.append(node.name)
            self.generic_visit(node)
            self.scope.pop()

        def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
            self.scope.append(node.name)
            scope_name = ".".join(self.scope)
            if node.name in guarded_names:
                key = (self.relative_path, scope_name, node.name)
                if key not in allowed_definitions:
                    offenders.append((self.relative_path, scope_name, node.name, node.lineno))
            self.generic_visit(node)
            self.scope.pop()

        def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
            self.visit_FunctionDef(node)  # type: ignore[arg-type]

        def visit_Call(self, node: ast.Call) -> None:
            call_name = ""
            if isinstance(node.func, ast.Attribute):
                call_name = node.func.attr
            elif isinstance(node.func, ast.Name):
                call_name = node.func.id
            if call_name in guarded_names:
                scope_name = ".".join(self.scope)
                key = (self.relative_path, scope_name, call_name)
                if key not in allowed_calls:
                    offenders.append((self.relative_path, scope_name, call_name, node.lineno))
            self.generic_visit(node)

    for path in _python_sources(PRODUCTION_ROOT):
        visitor = ProofAuthorityVisitor(_relative(path))
        visitor.visit(_parse_source(_relative(path)))

    assert offenders == []


def test_p1_verified_decision_references_stay_in_verifier_and_state_only() -> None:
    allowed: set[tuple[str, str]] = {
        (
            "flaghunter/agents/pa_agent/verifier.py",
            "CTFVerifier._append_flag_verification_record",
        ),
        (
            "flaghunter/agents/pa_agent/verifier.py",
            "CTFVerifier._record_decision_for_result",
        ),
        (
            "flaghunter/agents/pa_agent/ctf_state.py",
            "CTFState._has_sufficient_verified_record",
        ),
    }
    offenders: list[tuple[str, str, int]] = []

    class VerifiedDecisionVisitor(ast.NodeVisitor):
        def __init__(self, relative_path: str):
            self.relative_path = relative_path
            self.scope: list[str] = []

        def visit_ClassDef(self, node: ast.ClassDef) -> None:
            self.scope.append(node.name)
            self.generic_visit(node)
            self.scope.pop()

        def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
            self.scope.append(node.name)
            self.generic_visit(node)
            self.scope.pop()

        def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
            self.scope.append(node.name)
            self.generic_visit(node)
            self.scope.pop()

        def visit_Attribute(self, node: ast.Attribute) -> None:
            if (
                node.attr == "VERIFIED"
                and isinstance(node.value, ast.Name)
                and node.value.id == "VerificationDecision"
            ):
                scope_name = ".".join(self.scope) or "<module>"
                key = (self.relative_path, scope_name)
                if key not in allowed:
                    offenders.append((self.relative_path, scope_name, node.lineno))
            self.generic_visit(node)

    for path in _python_sources(PRODUCTION_ROOT):
        visitor = VerifiedDecisionVisitor(_relative(path))
        visitor.visit(_parse_source(_relative(path)))

    assert offenders == []


def test_p1_proof_authority_port_actions_remain_unwired_outside_port_and_adapter() -> None:
    allowed_definitions: set[tuple[str, str, str]] = {
        (
            "flaghunter/ports/proof_authority.py",
            "ProofAuthorityPort.append_proof_record",
            "append_proof_record",
        ),
        (
            "flaghunter/ports/proof_authority.py",
            "ProofAuthorityPort.confirm_claim",
            "confirm_claim",
        ),
        (
            "flaghunter/adapters/proof/proof_authority_adapter.py",
            "ProofAuthorityAdapter.append_proof_record",
            "append_proof_record",
        ),
        (
            "flaghunter/adapters/proof/proof_authority_adapter.py",
            "ProofAuthorityAdapter.confirm_claim",
            "confirm_claim",
        ),
    }
    allowed_calls: set[tuple[str, str, str]] = {
        (
            "flaghunter/adapters/proof/proof_authority_adapter.py",
            "ProofAuthorityAdapter.append_proof_record",
            "append_proof_record",
        ),
        (
            "flaghunter/adapters/proof/proof_authority_adapter.py",
            "ProofAuthorityAdapter.confirm_claim",
            "confirm_claim",
        ),
    }
    guarded_names = {"append_proof_record", "confirm_claim"}
    offenders: list[tuple[str, str, str, int]] = []

    class ProofPortActionVisitor(ast.NodeVisitor):
        def __init__(self, relative_path: str):
            self.relative_path = relative_path
            self.scope: list[str] = []

        def visit_ClassDef(self, node: ast.ClassDef) -> None:
            self.scope.append(node.name)
            self.generic_visit(node)
            self.scope.pop()

        def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
            self.scope.append(node.name)
            scope_name = ".".join(self.scope)
            if node.name in guarded_names:
                key = (self.relative_path, scope_name, node.name)
                if key not in allowed_definitions:
                    offenders.append((self.relative_path, scope_name, node.name, node.lineno))
            self.generic_visit(node)
            self.scope.pop()

        def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
            self.scope.append(node.name)
            scope_name = ".".join(self.scope)
            if node.name in guarded_names:
                key = (self.relative_path, scope_name, node.name)
                if key not in allowed_definitions:
                    offenders.append((self.relative_path, scope_name, node.name, node.lineno))
            self.generic_visit(node)
            self.scope.pop()

        def visit_Call(self, node: ast.Call) -> None:
            call_name = ""
            if isinstance(node.func, ast.Attribute):
                call_name = node.func.attr
            elif isinstance(node.func, ast.Name):
                call_name = node.func.id
            if call_name in guarded_names:
                scope_name = ".".join(self.scope) or "<module>"
                key = (self.relative_path, scope_name, call_name)
                if key not in allowed_calls:
                    offenders.append((self.relative_path, scope_name, call_name, node.lineno))
            self.generic_visit(node)

    for path in _python_sources(PRODUCTION_ROOT):
        visitor = ProofPortActionVisitor(_relative(path))
        visitor.visit(_parse_source(_relative(path)))

    assert offenders == []


def test_p1_proof_authority_adapter_stays_unwired_from_production_imports() -> None:
    allowed_paths = {
        "flaghunter/adapters/proof/__init__.py",
        "flaghunter/adapters/proof/proof_authority_adapter.py",
    }
    guarded_names = {"ProofAuthorityAdapter", "ProofAuthorityPort"}
    offenders: list[tuple[str, str, int]] = []

    class ProofAdapterImportVisitor(ast.NodeVisitor):
        def __init__(self, relative_path: str):
            self.relative_path = relative_path

        def _allow_current_path(self) -> bool:
            return self.relative_path in allowed_paths

        def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
            module_name = node.module or ""
            imported_names = {alias.name for alias in node.names}
            if (
                not self._allow_current_path()
                and module_name.startswith("flaghunter.adapters.proof")
                and "ProofAuthorityAdapter" in imported_names
            ):
                offenders.append(
                    (self.relative_path, "ProofAuthorityAdapter import", node.lineno)
                )
            if (
                not self._allow_current_path()
                and module_name in {"flaghunter.ports", "flaghunter.ports.proof_authority"}
                and "ProofAuthorityPort" in imported_names
            ):
                offenders.append(
                    (self.relative_path, "ProofAuthorityPort import", node.lineno)
                )
            self.generic_visit(node)

        def visit_Attribute(self, node: ast.Attribute) -> None:
            if not self._allow_current_path() and node.attr in guarded_names:
                offenders.append((self.relative_path, f"attribute {node.attr}", node.lineno))
            self.generic_visit(node)

        def visit_Name(self, node: ast.Name) -> None:
            if not self._allow_current_path() and node.id in guarded_names:
                offenders.append((self.relative_path, f"name {node.id}", node.lineno))
            self.generic_visit(node)

    for path in _python_sources(PRODUCTION_ROOT):
        visitor = ProofAdapterImportVisitor(_relative(path))
        visitor.visit(_parse_source(_relative(path)))

    assert offenders == []


def test_p1_verifier_adapter_stays_unwired_from_production_imports() -> None:
    allowed_paths = {
        "flaghunter/adapters/proof/__init__.py",
        "flaghunter/adapters/proof/verifier_adapter.py",
    }
    offenders: list[tuple[str, str, int]] = []

    class VerifierAdapterImportVisitor(ast.NodeVisitor):
        def __init__(self, relative_path: str):
            self.relative_path = relative_path

        def _allow_current_path(self) -> bool:
            return self.relative_path in allowed_paths

        def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
            module_name = node.module or ""
            imported_names = {alias.name for alias in node.names}
            if (
                not self._allow_current_path()
                and module_name.startswith("flaghunter.adapters.proof")
                and "VerifierAdapter" in imported_names
            ):
                offenders.append((self.relative_path, "VerifierAdapter import", node.lineno))
            self.generic_visit(node)

        def visit_Attribute(self, node: ast.Attribute) -> None:
            if not self._allow_current_path() and node.attr == "VerifierAdapter":
                offenders.append((self.relative_path, "attribute VerifierAdapter", node.lineno))
            self.generic_visit(node)

        def visit_Name(self, node: ast.Name) -> None:
            if not self._allow_current_path() and node.id == "VerifierAdapter":
                offenders.append((self.relative_path, "name VerifierAdapter", node.lineno))
            self.generic_visit(node)

    for path in _python_sources(PRODUCTION_ROOT):
        visitor = VerifierAdapterImportVisitor(_relative(path))
        visitor.visit(_parse_source(_relative(path)))

    assert offenders == []


def test_p1_control_and_ingress_paths_do_not_emit_verification_decisions() -> None:
    guarded_paths = [
        "flaghunter/agents/pa_agent/coordinator.py",
        "flaghunter/interface/control_contract.py",
        "flaghunter/interface/web_ingress_handoff.py",
        "flaghunter/mcp/server/mcp_tools.py",
        "flaghunter/tools/executor.py",
    ]

    offenders = [
        path
        for path in guarded_paths
        if _file_contains(path, "build_verification_decision_event")
        or _file_contains(path, "verification_decision")
    ]

    assert offenders == []


def test_p1_executor_and_context_surfacing_do_not_mint_verified_or_emit_decisions() -> None:
    guarded_paths = [
        "flaghunter/tools/executor.py",
        "flaghunter/agents/pa_agent/session_context.py",
        "flaghunter/agents/pa_agent/context_assembler.py",
        "flaghunter/agents/pa_agent/audit_views.py",
    ]
    forbidden_tokens = {
        "build_verification_decision_event",
        "verification_decision",
        "upgrade_claim_to_verified",
        "append_verification_record",
    }
    offenders: list[tuple[str, str, int]] = []

    for path in guarded_paths:
        text = (REPO_ROOT / path).read_text(encoding="utf-8")
        offenders.extend((path, token, 0) for token in forbidden_tokens if token in text)
        tree = _parse_source(path)
        for call in ast.walk(tree):
            if not isinstance(call, ast.Call):
                continue
            if (
                isinstance(call.func, ast.Attribute)
                and call.func.attr == "add_flag"
                and any(
                    keyword.arg == "level"
                    and isinstance(keyword.value, ast.Constant)
                    and keyword.value.value == "verified"
                    for keyword in call.keywords
                )
            ):
                offenders.append((path, "add_flag(level=verified)", call.lineno))
            if (
                isinstance(call.func, ast.Attribute)
                and call.func.attr == "create_claim"
                and any(
                    keyword.arg == "level"
                    and isinstance(keyword.value, ast.Constant)
                    and keyword.value.value == "verified"
                    for keyword in call.keywords
                )
            ):
                offenders.append((path, "create_claim(level=verified)", call.lineno))

    assert offenders == []


def test_p1_claim_views_can_only_record_non_verified_structured_facts() -> None:
    path = "flaghunter/agents/pa_agent/claim_views.py"
    forbidden_tokens = {
        "build_verification_decision_event",
        "verification_decision",
        "upgrade_claim_to_verified",
        "append_verification_record",
        "add_flag(",
    }
    text = (REPO_ROOT / path).read_text(encoding="utf-8")
    offenders: list[tuple[str, str, int]] = [
        (path, token, 0) for token in forbidden_tokens if token in text
    ]
    tree = _parse_source(path)

    structured_fact_scope = _scope_node(tree, "record_structured_claim_fact")
    structured_fact_source = ast.get_source_segment(text, structured_fact_scope) or ""
    if "ClaimLevel.VERIFIED" in structured_fact_source:
        offenders.append((path, "record_structured_claim_fact ClaimLevel.VERIFIED", 0))
    if "ClaimLevel.RETRACTED" in structured_fact_source:
        offenders.append((path, "record_structured_claim_fact ClaimLevel.RETRACTED", 0))
    if "level not in {ClaimLevel.ASSUMPTION.value, ClaimLevel.CONJECTURE.value}" not in structured_fact_source:
        offenders.append((path, "record_structured_claim_fact low-level allowlist", 0))

    for call in ast.walk(tree):
        if not isinstance(call, ast.Call):
            continue
        if (
            isinstance(call.func, ast.Attribute)
            and call.func.attr == "create_claim"
            and any(
                keyword.arg == "level"
                and (
                    (
                        isinstance(keyword.value, ast.Constant)
                        and keyword.value.value == "verified"
                    )
                    or (
                        isinstance(keyword.value, ast.Attribute)
                        and keyword.value.attr == "VERIFIED"
                    )
                )
                for keyword in call.keywords
            )
        ):
            offenders.append((path, "create_claim(level=verified)", call.lineno))

    assert offenders == []


def test_p2h_completion_control_paths_do_not_write_verification_proof() -> None:
    guarded_files = [
        "flaghunter/agents/pa_agent/control_receipts.py",
        "flaghunter/harness/control_receipts.py",
        "flaghunter/tools/finish/__init__.py",
    ]
    forbidden_tokens = {
        "build_verification_decision_event",
        "verification_decision",
        "append_verification_record",
        "upgrade_claim_to_verified",
        "verified_flags",
    }
    offenders: list[tuple[str, str, int]] = []

    for path in guarded_files:
        text = (REPO_ROOT / path).read_text(encoding="utf-8")
        offenders.extend((path, token, 0) for token in forbidden_tokens if token in text)
        tree = _parse_source(path)
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr in {"add_flag", "create_claim"}
                and any(
                    keyword.arg == "level"
                    and isinstance(keyword.value, ast.Constant)
                    and keyword.value.value == "verified"
                    for keyword in node.keywords
                )
            ):
                offenders.append((path, f"{node.func.attr}(level=verified)", node.lineno))

    dispatcher_scope = _scope_node(
        _parse_source("flaghunter/agents/pa_agent/ctf_dispatcher.py"),
        "CTFTaskDispatcher._record_completion_control_receipt",
    )
    dispatcher_source = ast.get_source_segment(
        (REPO_ROOT / "flaghunter/agents/pa_agent/ctf_dispatcher.py").read_text(
            encoding="utf-8"
        ),
        dispatcher_scope,
    ) or ""
    offenders.extend(
        ("flaghunter/agents/pa_agent/ctf_dispatcher.py", token, 0)
        for token in forbidden_tokens
        if token in dispatcher_source
    )
    for node in ast.walk(dispatcher_scope):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr in {"add_flag", "create_claim"}
            and any(
                keyword.arg == "level"
                and isinstance(keyword.value, ast.Constant)
                and keyword.value.value == "verified"
                for keyword in node.keywords
            )
        ):
            offenders.append(
                (
                    "flaghunter/agents/pa_agent/ctf_dispatcher.py",
                    f"{node.func.attr}(level=verified)",
                    node.lineno,
                )
            )

    assert offenders == []


def test_p2i_evidence_snapshot_is_read_only() -> None:
    guarded_paths = [
        "flaghunter/agents/pa_agent/evidence_snapshot.py",
        "flaghunter/agents/pa_agent/reasoning_evidence_context.py",
    ]
    forbidden_tokens = {
        "create_claim",
        "append_verification_record",
        "upgrade_claim_to_verified",
        "add_flag(",
        "verification_decision",
        "build_verification_decision_event",
        "verified_flags",
    }
    offenders: list[tuple[str, str]] = []

    for path in guarded_paths:
        text = (REPO_ROOT / path).read_text(encoding="utf-8")
        offenders.extend((path, token) for token in forbidden_tokens if token in text)

    assert offenders == []


def test_p2j_ledger_event_readback_paths_do_not_write_proof() -> None:
    guarded_paths = [
        "flaghunter/agents/pa_agent/ledger_event_views.py",
    ]
    forbidden_tokens = {
        "create_claim",
        "append_verification_record",
        "upgrade_claim_to_verified",
        "add_flag(",
        "build_verification_decision_event",
        "verification_decision",
        "verified_flags",
    }
    offenders: list[tuple[str, str]] = []

    for path in guarded_paths:
        text = (REPO_ROOT / path).read_text(encoding="utf-8")
        offenders.extend((path, token) for token in forbidden_tokens if token in text)

    assert offenders == []


def test_p2j_audit_event_builders_do_not_add_verification_decision_writers() -> None:
    path = "flaghunter/harness/audit_events.py"
    tree = _parse_source(path)
    allowed = {"build_verification_decision_event"}
    offenders: list[str] = []

    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef):
            continue
        if node.name in allowed:
            continue
        source = ast.get_source_segment(
            (REPO_ROOT / path).read_text(encoding="utf-8"),
            node,
        ) or ""
        if "verification_decision" in source:
            offenders.append(node.name)
        if "verified_flags" in source:
            offenders.append(node.name)

    assert offenders == []


def test_p3_solve_node_schema_graph_and_contracts_do_not_write_proof() -> None:
    path = "flaghunter/agents/pa_agent/solve_node.py"
    forbidden_tokens = {
        "create_claim",
        "append_verification_record",
        "upgrade_claim_to_verified",
        "add_flag(",
        "build_verification_decision_event",
        "verification_decision",
        "verified_flags",
        'level="verified"',
        "level='verified'",
    }
    text = (REPO_ROOT / path).read_text(encoding="utf-8")

    offenders = [(path, token) for token in forbidden_tokens if token in text]

    assert offenders == []


def test_p4_task_dag_plan_schema_and_readback_do_not_write_proof() -> None:
    path = "flaghunter/domain/challenge/contracts/task_dag_plan.py"
    forbidden_tokens = {
        "create_claim",
        "append_verification_record",
        "upgrade_claim_to_verified",
        "add_flag(",
        "build_verification_decision_event",
        "verification_decision",
        "verified_flags",
        'level="verified"',
        "level='verified'",
    }
    text = (REPO_ROOT / path).read_text(encoding="utf-8")

    offenders = [(path, token) for token in forbidden_tokens if token in text]

    assert offenders == []


def test_p4b_task_dag_state_and_session_scopes_do_not_write_proof() -> None:
    forbidden_tokens = {
        "create_claim",
        "append_verification_record",
        "upgrade_claim_to_verified",
        "add_flag(",
        "build_verification_decision_event",
        "verification_decision",
        "verified_flags",
        'level="verified"',
        "level='verified'",
    }
    guarded_scopes = [
        (
            "flaghunter/agents/pa_agent/ctf_state.py",
            "CTFState.set_task_dag_plan",
        ),
        (
            "flaghunter/agents/pa_agent/ctf_state.py",
            "CTFState.get_task_dag_plan",
        ),
        (
            "flaghunter/agents/pa_agent/ctf_state.py",
            "_coerce_task_dag_plan",
        ),
        (
            "flaghunter/agents/pa_agent/session_context.py",
            "_format_task_dag_plan_summary",
        ),
    ]
    offenders: list[tuple[str, str, str]] = []

    for path, scope in guarded_scopes:
        source = ast.get_source_segment(
            (REPO_ROOT / path).read_text(encoding="utf-8"),
            _scope_node(_parse_source(path), scope),
        ) or ""
        offenders.extend(
            (path, scope, token) for token in forbidden_tokens if token in source
        )

    assert offenders == []


def test_p4b_ready_selector_and_transition_scopes_do_not_write_proof() -> None:
    forbidden_tokens = {
        "create_claim",
        "append_verification_record",
        "upgrade_claim_to_verified",
        "add_flag(",
        "build_verification_decision_event",
        "verification_decision",
        "verified_flags",
        'level="verified"',
        "level='verified'",
    }
    path = "flaghunter/domain/challenge/contracts/task_dag_plan.py"
    guarded_scopes = [
        "select_next_ready_task",
        "mark_task_ready",
        "mark_task_running",
        "mark_task_finished",
    ]
    offenders: list[tuple[str, str, str]] = []

    for scope in guarded_scopes:
        source = ast.get_source_segment(
            (REPO_ROOT / path).read_text(encoding="utf-8"),
            _scope_node(_parse_source(path), scope),
        ) or ""
        offenders.extend((path, scope, token) for token in forbidden_tokens if token in source)

    assert offenders == []


def test_p4b_task_dag_p3_mapping_scopes_do_not_write_proof() -> None:
    forbidden_tokens = {
        "create_claim",
        "append_verification_record",
        "upgrade_claim_to_verified",
        "add_flag(",
        "build_verification_decision_event",
        "verification_decision",
        "verified_flags",
        'level="verified"',
        "level='verified'",
    }
    path = "flaghunter/agents/pa_agent/task_dag_p3_mapping.py"
    guarded_scopes = [
        "build_task_brief_for_dag_node",
        "build_solve_node_for_dag_node",
        "link_solve_node_to_task",
        "apply_solve_node_receipt_to_task",
    ]
    offenders: list[tuple[str, str, str]] = []

    for scope in guarded_scopes:
        source = ast.get_source_segment(
            (REPO_ROOT / path).read_text(encoding="utf-8"),
            _scope_node(_parse_source(path), scope),
        ) or ""
        offenders.extend((path, scope, token) for token in forbidden_tokens if token in source)

    assert offenders == []


def test_p4b_task_dag_p3_bridge_scopes_do_not_write_proof_or_execute() -> None:
    forbidden_tokens = {
        "create_claim",
        "append_verification_record",
        "upgrade_claim_to_verified",
        "add_flag(",
        "build_verification_decision_event",
        "verification_decision",
        "verified_flags",
        'level="verified"',
        "level='verified'",
        "ctf_dispatcher",
        "RecoveryController",
        "WorkerPool",
        "CrewOrchestrator",
        "execute_tools",
        "_execute_tools",
        "run_task",
    }
    path = "flaghunter/agents/pa_agent/task_dag_p3_bridge.py"
    guarded_scopes = [
        "record_task_dag_p3_start",
        "record_task_dag_p3_receipt",
    ]
    offenders: list[tuple[str, str, str]] = []

    for scope in guarded_scopes:
        source = ast.get_source_segment(
            (REPO_ROOT / path).read_text(encoding="utf-8"),
            _scope_node(_parse_source(path), scope),
        ) or ""
        offenders.extend((path, scope, token) for token in forbidden_tokens if token in source)

    assert offenders == []


def test_p4b_task_dag_local_shim_scopes_do_not_write_proof_or_execute() -> None:
    forbidden_tokens = {
        "create_claim",
        "append_verification_record",
        "upgrade_claim_to_verified",
        "add_flag(",
        "build_verification_decision_event",
        "verification_decision",
        "verified_flags",
        'level="verified"',
        "level='verified'",
        "ctf_dispatcher",
        "StrategyRegistry",
        "CapabilityRegistry",
        "RecoveryController",
        "WorkerPool",
        "CrewOrchestrator",
        "execute_tools",
        "_execute_tools",
        "run_task",
        "subprocess",
        "tool_call",
    }
    path = "flaghunter/agents/pa_agent/task_dag_local_shim.py"
    guarded_scopes = [
        "start_next_ready_task_for_local_dag",
        "apply_local_dag_task_receipt",
    ]
    offenders: list[tuple[str, str, str]] = []

    for scope in guarded_scopes:
        source = ast.get_source_segment(
            (REPO_ROOT / path).read_text(encoding="utf-8"),
            _scope_node(_parse_source(path), scope),
        ) or ""
        offenders.extend((path, scope, token) for token in forbidden_tokens if token in source)

    assert offenders == []


def test_p4b_task_dag_local_caller_scopes_do_not_write_proof_or_execute() -> None:
    forbidden_tokens = {
        "create_claim",
        "append_verification_record",
        "upgrade_claim_to_verified",
        "add_flag(",
        "build_verification_decision_event",
        "verification_decision",
        "verified_flags",
        'level="verified"',
        "level='verified'",
        "ctf_dispatcher",
        "CTFTaskDispatcher",
        "StrategyRegistry",
        "CapabilityRegistry",
        "RecoveryController",
        "WorkerPool",
        "CrewOrchestrator",
        "execute_tools",
        "_execute_tools",
        "run_task",
        "subprocess",
        "tool_call",
        "record_solve_node",
        "record_task_brief",
        "record_solve_node_receipt",
        "set_task_dag_plan",
        "record_task_dag_p3_start",
        "record_task_dag_p3_receipt",
    }
    path = "flaghunter/agents/pa_agent/task_dag_local_caller.py"
    guarded_scopes = [
        "local_dag_start_next",
        "local_dag_apply_receipt",
    ]
    offenders: list[tuple[str, str, str]] = []

    for scope in guarded_scopes:
        source = ast.get_source_segment(
            (REPO_ROOT / path).read_text(encoding="utf-8"),
            _scope_node(_parse_source(path), scope),
        ) or ""
        offenders.extend((path, scope, token) for token in forbidden_tokens if token in source)

    assert offenders == []


def test_p4b_task_dag_receipt_factory_scopes_do_not_write_proof_execute_or_apply() -> None:
    forbidden_tokens = {
        "create_claim",
        "append_verification_record",
        "upgrade_claim_to_verified",
        "add_flag(",
        "build_verification_decision_event",
        "verification_decision",
        "verified_flags",
        'level="verified"',
        "level='verified'",
        "ToolExecutor",
        "execute_tools",
        "_execute_tools",
        "run_task",
        "subprocess",
        "ctf_dispatcher",
        "CTFTaskDispatcher",
        "RecoveryController",
        "WorkerPool",
        "CrewOrchestrator",
        "local_dag_apply_receipt",
        "apply_local_dag_task_receipt",
        "record_task_dag_p3_receipt",
        "record_solve_node_receipt",
        "set_task_dag_plan",
    }
    path = "flaghunter/agents/pa_agent/task_dag_receipt_factory.py"
    guarded_scopes = [
        "build_local_task_dag_receipt",
    ]
    offenders: list[tuple[str, str, str]] = []

    for scope in guarded_scopes:
        source = ast.get_source_segment(
            (REPO_ROOT / path).read_text(encoding="utf-8"),
            _scope_node(_parse_source(path), scope),
        ) or ""
        offenders.extend((path, scope, token) for token in forbidden_tokens if token in source)

    assert offenders == []


def test_p4b_task_dag_outcome_source_scopes_do_not_write_proof_execute_apply_or_build_receipt() -> None:
    forbidden_tokens = {
        "create_claim",
        "append_verification_record",
        "upgrade_claim_to_verified",
        "add_flag(",
        "build_verification_decision_event",
        "verification_decision",
        "verified_flags",
        'level="verified"',
        "level='verified'",
        "ToolExecutor",
        "execute_tools",
        "_execute_tools",
        "run_task",
        "subprocess",
        "ctf_dispatcher",
        "CTFTaskDispatcher",
        "RecoveryController",
        "WorkerPool",
        "CrewOrchestrator",
        "build_local_task_dag_receipt",
        "local_dag_apply_receipt",
        "apply_local_dag_task_receipt",
        "record_task_dag_p3_receipt",
        "record_solve_node_receipt",
        "set_task_dag_plan",
    }
    path = "flaghunter/agents/pa_agent/task_dag_outcome_source.py"
    guarded_scopes = [
        "build_manual_task_dag_outcome",
        "manual_task_dag_outcome_from_dict",
    ]
    offenders: list[tuple[str, str, str]] = []

    for scope in guarded_scopes:
        source = ast.get_source_segment(
            (REPO_ROOT / path).read_text(encoding="utf-8"),
            _scope_node(_parse_source(path), scope),
        ) or ""
        offenders.extend((path, scope, token) for token in forbidden_tokens if token in source)

    assert offenders == []


def test_p4b_task_dag_dry_result_adapter_scopes_do_not_write_proof_execute_apply_or_build_receipt() -> None:
    forbidden_tokens = {
        "create_claim",
        "append_verification_record",
        "upgrade_claim_to_verified",
        "add_flag(",
        "build_verification_decision_event",
        "verification_decision",
        "verified_flags",
        'level="verified"',
        "level='verified'",
        "ToolExecutor",
        "execute_tools",
        "_execute_tools",
        "run_task",
        "subprocess",
        "ctf_dispatcher",
        "CTFTaskDispatcher",
        "RecoveryController",
        "WorkerPool",
        "CrewOrchestrator",
        "build_local_task_dag_receipt",
        "local_dag_apply_receipt",
        "apply_local_dag_task_receipt",
        "record_task_dag_p3_receipt",
        "record_solve_node_receipt",
        "set_task_dag_plan",
        "CTFState",
    }
    path = "flaghunter/agents/pa_agent/task_dag_dry_result_adapter.py"
    guarded_scopes = [
        "build_task_dag_outcome_from_dry_result",
    ]
    offenders: list[tuple[str, str, str]] = []

    for scope in guarded_scopes:
        source = ast.get_source_segment(
            (REPO_ROOT / path).read_text(encoding="utf-8"),
            _scope_node(_parse_source(path), scope),
        ) or ""
        offenders.extend((path, scope, token) for token in forbidden_tokens if token in source)

    assert offenders == []


def test_p4c_task_dag_recovery_proposal_scopes_do_not_execute_mutate_or_write_proof() -> None:
    forbidden_tokens = {
        "create_claim",
        "append_verification_record",
        "upgrade_claim_to_verified",
        "add_flag(",
        "build_verification_decision_event",
        "verification_decision",
        "verified_flags",
        'level="verified"',
        "level='verified'",
        "ToolExecutor",
        "execute_tools",
        "_execute_tools",
        "run_task",
        "subprocess",
        "ctf_dispatcher",
        "CTFTaskDispatcher",
        "RecoveryController",
        "WorkerPool",
        "CrewOrchestrator",
        "build_local_task_dag_receipt",
        "local_dag_apply_receipt",
        "apply_local_dag_task_receipt",
        "record_task_dag_p3_receipt",
        "record_solve_node_receipt",
        "set_task_dag_plan",
    }
    forbidden_import_modules = {
        "flaghunter.agents.pa_agent.recovery",
        "flaghunter.agents.pa_agent.ctf_dispatcher",
        "flaghunter.tools.executor",
        "flaghunter.agents.crew.worker_pool",
        "flaghunter.agents.crew.orchestrator",
        ".recovery",
        ".ctf_dispatcher",
    }
    forbidden_import_names = {
        "RecoveryController",
        "CTFTaskDispatcher",
        "ToolExecutor",
        "WorkerPool",
        "CrewOrchestrator",
    }
    path = "flaghunter/agents/pa_agent/task_dag_recovery_proposal.py"
    guarded_scopes = [
        "TaskDAGRecoveryProposal.to_dict",
        "propose_task_dag_recovery",
    ]
    offenders: list[tuple[str, str, str]] = []
    tree = _parse_source(path)

    for scope in guarded_scopes:
        source = ast.get_source_segment(
            (REPO_ROOT / path).read_text(encoding="utf-8"),
            _scope_node(tree, scope),
        ) or ""
        offenders.extend((path, scope, token) for token in forbidden_tokens if token in source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name in forbidden_import_modules or alias.name in forbidden_import_names:
                    offenders.append((path, "import", alias.name))
        if isinstance(node, ast.ImportFrom):
            module = node.module or ""
            normalized_module = f".{module}" if node.level else module
            if module in forbidden_import_modules or normalized_module in forbidden_import_modules:
                offenders.append((path, "import", normalized_module))
            for alias in node.names:
                if alias.name in forbidden_import_names:
                    offenders.append((path, "import", alias.name))

    assert offenders == []


def test_p4c_task_dag_recovery_proposal_readback_scopes_do_not_execute_mutate_or_write_proof() -> None:
    forbidden_tokens = {
        "create_claim",
        "append_verification_record",
        "upgrade_claim_to_verified",
        "add_flag(",
        "build_verification_decision_event",
        "verification_decision",
        "verified_flags",
        'level="verified"',
        "level='verified'",
        "ToolExecutor",
        "execute_tools",
        "_execute_tools",
        "run_task",
        "subprocess",
        "ctf_dispatcher",
        "CTFTaskDispatcher",
        "RecoveryController",
        "WorkerPool",
        "CrewOrchestrator",
        "build_local_task_dag_receipt",
        "local_dag_apply_receipt",
        "apply_local_dag_task_receipt",
        "record_task_dag_p3_receipt",
        "record_solve_node_receipt",
        "set_task_dag_plan",
    }
    forbidden_import_modules = {
        "flaghunter.agents.pa_agent.recovery",
        "flaghunter.agents.pa_agent.ctf_dispatcher",
        "flaghunter.tools.executor",
        "flaghunter.agents.crew.worker_pool",
        "flaghunter.agents.crew.orchestrator",
        ".recovery",
        ".ctf_dispatcher",
    }
    forbidden_import_names = {
        "RecoveryController",
        "CTFTaskDispatcher",
        "ToolExecutor",
        "WorkerPool",
        "CrewOrchestrator",
    }
    path = "flaghunter/agents/pa_agent/task_dag_recovery_proposal_readback.py"
    guarded_scopes = [
        "TaskDAGRecoveryProposalRecord.to_dict",
        "proposal_to_readback_record",
        "normalize_task_dag_recovery_proposal_record",
        "build_task_dag_recovery_proposal_readback",
    ]
    offenders: list[tuple[str, str, str]] = []
    tree = _parse_source(path)
    text = (REPO_ROOT / path).read_text(encoding="utf-8")

    for scope in guarded_scopes:
        source = ast.get_source_segment(text, _scope_node(tree, scope)) or ""
        offenders.extend((path, scope, token) for token in forbidden_tokens if token in source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name in forbidden_import_modules or alias.name in forbidden_import_names:
                    offenders.append((path, "import", alias.name))
        if isinstance(node, ast.ImportFrom):
            module = node.module or ""
            normalized_module = f".{module}" if node.level else module
            if module in forbidden_import_modules or normalized_module in forbidden_import_modules:
                offenders.append((path, "import", normalized_module))
            for alias in node.names:
                if alias.name in forbidden_import_names:
                    offenders.append((path, "import", alias.name))

    assert offenders == []


def test_p4c_task_dag_recovery_review_scopes_do_not_execute_mutate_or_write_proof() -> None:
    forbidden_tokens = {
        "create_claim",
        "append_verification_record",
        "upgrade_claim_to_verified",
        "add_flag(",
        "build_verification_decision_event",
        "verification_decision",
        "verified_flags",
        'level="verified"',
        "level='verified'",
        "ToolExecutor",
        "execute_tools",
        "_execute_tools",
        "run_task",
        "subprocess",
        "ctf_dispatcher",
        "CTFTaskDispatcher",
        "RecoveryController",
        "WorkerPool",
        "CrewOrchestrator",
        "build_local_task_dag_receipt",
        "local_dag_apply_receipt",
        "apply_local_dag_task_receipt",
        "record_task_dag_p3_receipt",
        "record_solve_node_receipt",
        "set_task_dag_plan",
    }
    forbidden_import_modules = {
        "flaghunter.agents.pa_agent.recovery",
        "flaghunter.agents.pa_agent.ctf_dispatcher",
        "flaghunter.tools.executor",
        "flaghunter.agents.crew.worker_pool",
        "flaghunter.agents.crew.orchestrator",
        ".recovery",
        ".ctf_dispatcher",
    }
    forbidden_import_names = {
        "RecoveryController",
        "CTFTaskDispatcher",
        "ToolExecutor",
        "WorkerPool",
        "CrewOrchestrator",
    }
    path = "flaghunter/agents/pa_agent/task_dag_recovery_review.py"
    guarded_scopes = [
        "TaskDAGRecoveryReview.to_dict",
        "select_task_dag_recovery_proposal",
        "build_task_dag_recovery_review",
    ]
    offenders: list[tuple[str, str, str]] = []
    tree = _parse_source(path)
    text = (REPO_ROOT / path).read_text(encoding="utf-8")

    for scope in guarded_scopes:
        source = ast.get_source_segment(text, _scope_node(tree, scope)) or ""
        offenders.extend((path, scope, token) for token in forbidden_tokens if token in source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name in forbidden_import_modules or alias.name in forbidden_import_names:
                    offenders.append((path, "import", alias.name))
        if isinstance(node, ast.ImportFrom):
            module = node.module or ""
            normalized_module = f".{module}" if node.level else module
            if module in forbidden_import_modules or normalized_module in forbidden_import_modules:
                offenders.append((path, "import", normalized_module))
            for alias in node.names:
                if alias.name in forbidden_import_names:
                    offenders.append((path, "import", alias.name))

    assert offenders == []


def test_p4d_task_dag_crew_bridge_scopes_do_not_execute_mutate_or_write_proof() -> None:
    forbidden_tokens = {
        "create_claim",
        "append_verification_record",
        "upgrade_claim_to_verified",
        "add_flag(",
        "build_verification_decision_event",
        "verification_decision",
        "verified_flags",
        'level="verified"',
        "level='verified'",
        "ToolExecutor",
        "execute_tools",
        "_execute_tools",
        "run_task",
        "subprocess",
        "ctf_dispatcher",
        "CTFTaskDispatcher",
        "RecoveryController",
        "WorkerPool",
        "CrewOrchestrator",
        "build_local_task_dag_receipt",
        "local_dag_apply_receipt",
        "apply_local_dag_task_receipt",
        "record_task_dag_p3_receipt",
        "record_solve_node_receipt",
        "set_task_dag_plan",
    }
    forbidden_import_modules = {
        "flaghunter.agents.pa_agent.recovery",
        "flaghunter.agents.pa_agent.ctf_dispatcher",
        "flaghunter.tools.executor",
        "flaghunter.agents.crew.worker_pool",
        "flaghunter.agents.crew.orchestrator",
        ".recovery",
        ".ctf_dispatcher",
    }
    forbidden_import_names = {
        "RecoveryController",
        "CTFTaskDispatcher",
        "ToolExecutor",
        "WorkerPool",
        "CrewOrchestrator",
    }
    path = "flaghunter/agents/pa_agent/task_dag_crew_bridge.py"
    guarded_scopes = [
        "TaskDAGCrewBridgeRequest.to_dict",
        "TaskDAGCrewBridgeReceipt.to_dict",
        "build_task_dag_crew_bridge_request",
        "normalize_task_dag_crew_bridge_receipt",
    ]
    offenders: list[tuple[str, str, str]] = []
    tree = _parse_source(path)
    text = (REPO_ROOT / path).read_text(encoding="utf-8")

    for scope in guarded_scopes:
        source = ast.get_source_segment(text, _scope_node(tree, scope)) or ""
        offenders.extend((path, scope, token) for token in forbidden_tokens if token in source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name in forbidden_import_modules or alias.name in forbidden_import_names:
                    offenders.append((path, "import", alias.name))
        if isinstance(node, ast.ImportFrom):
            module = node.module or ""
            normalized_module = f".{module}" if node.level else module
            if module in forbidden_import_modules or normalized_module in forbidden_import_modules:
                offenders.append((path, "import", normalized_module))
            for alias in node.names:
                if alias.name in forbidden_import_names:
                    offenders.append((path, "import", alias.name))

    assert offenders == []


def test_p4d_task_dag_crew_bridge_readback_scopes_do_not_execute_mutate_or_write_proof() -> None:
    forbidden_tokens = {
        "create_claim",
        "append_verification_record",
        "upgrade_claim_to_verified",
        "add_flag(",
        "build_verification_decision_event",
        "verification_decision",
        "verified_flags",
        'level="verified"',
        "level='verified'",
        "ToolExecutor",
        "execute_tools",
        "_execute_tools",
        "run_task",
        "subprocess",
        "ctf_dispatcher",
        "CTFTaskDispatcher",
        "RecoveryController",
        "WorkerPool",
        "CrewOrchestrator",
        "build_local_task_dag_receipt",
        "local_dag_apply_receipt",
        "apply_local_dag_task_receipt",
        "record_task_dag_p3_receipt",
        "record_solve_node_receipt",
        "set_task_dag_plan",
    }
    forbidden_import_modules = {
        "flaghunter.agents.pa_agent.recovery",
        "flaghunter.agents.pa_agent.ctf_dispatcher",
        "flaghunter.tools.executor",
        "flaghunter.agents.crew.worker_pool",
        "flaghunter.agents.crew.orchestrator",
        ".recovery",
        ".ctf_dispatcher",
    }
    forbidden_import_names = {
        "RecoveryController",
        "CTFTaskDispatcher",
        "ToolExecutor",
        "WorkerPool",
        "CrewOrchestrator",
    }
    path = "flaghunter/agents/pa_agent/task_dag_crew_bridge_readback.py"
    guarded_scopes = [
        "TaskDAGCrewBridgePreviewRecord.to_dict",
        "build_task_dag_crew_bridge_preview",
        "load_task_dag_crew_bridge_preview_records",
    ]
    offenders: list[tuple[str, str, str]] = []
    tree = _parse_source(path)
    text = (REPO_ROOT / path).read_text(encoding="utf-8")

    for scope in guarded_scopes:
        source = ast.get_source_segment(text, _scope_node(tree, scope)) or ""
        offenders.extend((path, scope, token) for token in forbidden_tokens if token in source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name in forbidden_import_modules or alias.name in forbidden_import_names:
                    offenders.append((path, "import", alias.name))
        if isinstance(node, ast.ImportFrom):
            module = node.module or ""
            normalized_module = f".{module}" if node.level else module
            if module in forbidden_import_modules or normalized_module in forbidden_import_modules:
                offenders.append((path, "import", normalized_module))
            for alias in node.names:
                if alias.name in forbidden_import_names:
                    offenders.append((path, "import", alias.name))

    assert offenders == []


def test_p4d_task_dag_crew_bridge_handoff_scopes_do_not_execute_mutate_or_write_proof() -> None:
    forbidden_tokens = {
        "create_claim",
        "append_verification_record",
        "upgrade_claim_to_verified",
        "add_flag(",
        "build_verification_decision_event",
        "verification_decision",
        "verified_flags",
        'level="verified"',
        "level='verified'",
        "ToolExecutor",
        "execute_tools",
        "_execute_tools",
        "run_task",
        "subprocess",
        "ctf_dispatcher",
        "CTFTaskDispatcher",
        "RecoveryController",
        "WorkerPool",
        "CrewOrchestrator",
        "build_local_task_dag_receipt",
        "local_dag_apply_receipt",
        "apply_local_dag_task_receipt",
        "record_task_dag_p3_receipt",
        "record_solve_node_receipt",
        "set_task_dag_plan",
    }
    forbidden_import_modules = {
        "flaghunter.agents.pa_agent.recovery",
        "flaghunter.agents.pa_agent.ctf_dispatcher",
        "flaghunter.tools.executor",
        "flaghunter.agents.crew.worker_pool",
        "flaghunter.agents.crew.orchestrator",
        ".recovery",
        ".ctf_dispatcher",
    }
    forbidden_import_names = {
        "RecoveryController",
        "CTFTaskDispatcher",
        "ToolExecutor",
        "WorkerPool",
        "CrewOrchestrator",
    }
    path = "flaghunter/agents/pa_agent/task_dag_crew_bridge_handoff.py"
    guarded_scopes = [
        "TaskDAGCrewBridgeHandoffItem.to_dict",
        "TaskDAGCrewBridgeHandoffEnvelope.to_dict",
        "build_task_dag_crew_bridge_handoff_envelope",
        "load_task_dag_crew_bridge_handoff_items",
    ]
    offenders: list[tuple[str, str, str]] = []
    tree = _parse_source(path)
    text = (REPO_ROOT / path).read_text(encoding="utf-8")

    for scope in guarded_scopes:
        source = ast.get_source_segment(text, _scope_node(tree, scope)) or ""
        offenders.extend((path, scope, token) for token in forbidden_tokens if token in source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name in forbidden_import_modules or alias.name in forbidden_import_names:
                    offenders.append((path, "import", alias.name))
        if isinstance(node, ast.ImportFrom):
            module = node.module or ""
            normalized_module = f".{module}" if node.level else module
            if module in forbidden_import_modules or normalized_module in forbidden_import_modules:
                offenders.append((path, "import", normalized_module))
            for alias in node.names:
                if alias.name in forbidden_import_names:
                    offenders.append((path, "import", alias.name))

    assert offenders == []


def test_p4d_task_dag_crew_bridge_admission_scopes_do_not_execute_mutate_or_write_proof() -> None:
    forbidden_tokens = {
        "create_claim",
        "append_verification_record",
        "upgrade_claim_to_verified",
        "add_flag(",
        "build_verification_decision_event",
        "verification_decision",
        "verified_flags",
        'level="verified"',
        "level='verified'",
        "ToolExecutor",
        "execute_tools",
        "_execute_tools",
        "run_task",
        "subprocess",
        "ctf_dispatcher",
        "CTFTaskDispatcher",
        "RecoveryController",
        "WorkerPool",
        "CrewOrchestrator",
        "build_local_task_dag_receipt",
        "local_dag_apply_receipt",
        "apply_local_dag_task_receipt",
        "record_task_dag_p3_receipt",
        "record_solve_node_receipt",
        "set_task_dag_plan",
    }
    forbidden_import_modules = {
        "flaghunter.agents.pa_agent.recovery",
        "flaghunter.agents.pa_agent.ctf_dispatcher",
        "flaghunter.tools.executor",
        "flaghunter.agents.crew.worker_pool",
        "flaghunter.agents.crew.orchestrator",
        ".recovery",
        ".ctf_dispatcher",
    }
    forbidden_import_names = {
        "RecoveryController",
        "CTFTaskDispatcher",
        "ToolExecutor",
        "WorkerPool",
        "CrewOrchestrator",
    }
    path = "flaghunter/agents/pa_agent/task_dag_crew_bridge_admission.py"
    guarded_scopes = [
        "TaskDAGCrewBridgeAdmissionItem.to_dict",
        "TaskDAGCrewBridgeAdmissionPackage.to_dict",
        "build_task_dag_crew_bridge_admission_package",
        "load_task_dag_crew_bridge_admission_items",
    ]
    offenders: list[tuple[str, str, str]] = []
    tree = _parse_source(path)
    text = (REPO_ROOT / path).read_text(encoding="utf-8")

    for scope in guarded_scopes:
        source = ast.get_source_segment(text, _scope_node(tree, scope)) or ""
        offenders.extend((path, scope, token) for token in forbidden_tokens if token in source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name in forbidden_import_modules or alias.name in forbidden_import_names:
                    offenders.append((path, "import", alias.name))
        if isinstance(node, ast.ImportFrom):
            module = node.module or ""
            normalized_module = f".{module}" if node.level else module
            if module in forbidden_import_modules or normalized_module in forbidden_import_modules:
                offenders.append((path, "import", normalized_module))
            for alias in node.names:
                if alias.name in forbidden_import_names:
                    offenders.append((path, "import", alias.name))

    assert offenders == []


def test_p4e_task_dag_replay_audit_scopes_do_not_execute_mutate_or_write_proof() -> None:
    forbidden_tokens = {
        "create_claim",
        "append_verification_record",
        "upgrade_claim_to_verified",
        "add_flag(",
        "build_verification_decision_event",
        "verification_decision",
        "verified_flags",
        'level="verified"',
        "level='verified'",
        "ToolExecutor",
        "execute_tools",
        "_execute_tools",
        "run_task",
        "subprocess",
        "ctf_dispatcher",
        "CTFTaskDispatcher",
        "RecoveryController",
        "WorkerPool",
        "CrewOrchestrator",
        "build_local_task_dag_receipt",
        "local_dag_apply_receipt",
        "apply_local_dag_task_receipt",
        "record_task_dag_p3_receipt",
        "record_solve_node_receipt",
        "set_task_dag_plan",
    }
    forbidden_import_modules = {
        "flaghunter.agents.pa_agent.recovery",
        "flaghunter.agents.pa_agent.ctf_dispatcher",
        "flaghunter.tools.executor",
        "flaghunter.agents.crew.worker_pool",
        "flaghunter.agents.crew.orchestrator",
        ".recovery",
        ".ctf_dispatcher",
    }
    forbidden_import_names = {
        "RecoveryController",
        "CTFTaskDispatcher",
        "ToolExecutor",
        "WorkerPool",
        "CrewOrchestrator",
    }
    path = "flaghunter/agents/pa_agent/task_dag_replay_audit.py"
    guarded_scopes = [
        "TaskDAGReplayAuditEvent.to_dict",
        "TaskDAGReplayAuditIndex.to_dict",
        "build_task_dag_replay_audit_index",
        "load_task_dag_replay_audit_events",
    ]
    offenders: list[tuple[str, str, str]] = []
    tree = _parse_source(path)
    text = (REPO_ROOT / path).read_text(encoding="utf-8")

    for scope in guarded_scopes:
        source = ast.get_source_segment(text, _scope_node(tree, scope)) or ""
        offenders.extend((path, scope, token) for token in forbidden_tokens if token in source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name in forbidden_import_modules or alias.name in forbidden_import_names:
                    offenders.append((path, "import", alias.name))
        if isinstance(node, ast.ImportFrom):
            module = node.module or ""
            normalized_module = f".{module}" if node.level else module
            if module in forbidden_import_modules or normalized_module in forbidden_import_modules:
                offenders.append((path, "import", normalized_module))
            for alias in node.names:
                if alias.name in forbidden_import_names:
                    offenders.append((path, "import", alias.name))

    assert offenders == []


def test_p4e_task_dag_replay_audit_readback_scopes_do_not_execute_mutate_or_write_proof() -> None:
    forbidden_tokens = {
        "create_claim",
        "append_verification_record",
        "upgrade_claim_to_verified",
        "add_flag(",
        "build_verification_decision_event",
        "verification_decision",
        "verified_flags",
        'level="verified"',
        "level='verified'",
        "ToolExecutor",
        "execute_tools",
        "_execute_tools",
        "run_task",
        "subprocess",
        "ctf_dispatcher",
        "CTFTaskDispatcher",
        "RecoveryController",
        "WorkerPool",
        "CrewOrchestrator",
        "build_local_task_dag_receipt",
        "local_dag_apply_receipt",
        "apply_local_dag_task_receipt",
        "record_task_dag_p3_receipt",
        "record_solve_node_receipt",
        "set_task_dag_plan",
    }
    forbidden_import_modules = {
        "flaghunter.agents.pa_agent.recovery",
        "flaghunter.agents.pa_agent.ctf_dispatcher",
        "flaghunter.tools.executor",
        "flaghunter.agents.crew.worker_pool",
        "flaghunter.agents.crew.orchestrator",
        ".recovery",
        ".ctf_dispatcher",
    }
    forbidden_import_names = {
        "RecoveryController",
        "CTFTaskDispatcher",
        "ToolExecutor",
        "WorkerPool",
        "CrewOrchestrator",
    }
    path = "flaghunter/agents/pa_agent/task_dag_replay_audit_readback.py"
    guarded_scopes = [
        "TaskDAGReplayAuditReadbackRow.to_dict",
        "TaskDAGReplayAuditReadbackPackage.to_dict",
        "build_task_dag_replay_audit_readback",
        "load_task_dag_replay_audit_readback_rows",
    ]
    offenders: list[tuple[str, str, str]] = []
    tree = _parse_source(path)
    text = (REPO_ROOT / path).read_text(encoding="utf-8")

    for scope in guarded_scopes:
        source = ast.get_source_segment(text, _scope_node(tree, scope)) or ""
        offenders.extend((path, scope, token) for token in forbidden_tokens if token in source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name in forbidden_import_modules or alias.name in forbidden_import_names:
                    offenders.append((path, "import", alias.name))
        if isinstance(node, ast.ImportFrom):
            module = node.module or ""
            normalized_module = f".{module}" if node.level else module
            if module in forbidden_import_modules or normalized_module in forbidden_import_modules:
                offenders.append((path, "import", normalized_module))
            for alias in node.names:
                if alias.name in forbidden_import_names:
                    offenders.append((path, "import", alias.name))

    assert offenders == []


def test_p4e_task_dag_replay_audit_view_scopes_do_not_execute_mutate_or_write_proof() -> None:
    forbidden_tokens = {
        "create_claim",
        "append_verification_record",
        "upgrade_claim_to_verified",
        "add_flag(",
        "build_verification_decision_event",
        "verification_decision",
        "verified_flags",
        'level="verified"',
        "level='verified'",
        "ToolExecutor",
        "execute_tools",
        "_execute_tools",
        "run_task",
        "subprocess",
        "ctf_dispatcher",
        "CTFTaskDispatcher",
        "RecoveryController",
        "WorkerPool",
        "CrewOrchestrator",
        "build_local_task_dag_receipt",
        "local_dag_apply_receipt",
        "apply_local_dag_task_receipt",
        "record_task_dag_p3_receipt",
        "record_solve_node_receipt",
        "set_task_dag_plan",
    }
    forbidden_import_modules = {
        "flaghunter.agents.pa_agent.recovery",
        "flaghunter.agents.pa_agent.ctf_dispatcher",
        "flaghunter.tools.executor",
        "flaghunter.agents.crew.worker_pool",
        "flaghunter.agents.crew.orchestrator",
        ".recovery",
        ".ctf_dispatcher",
    }
    forbidden_import_names = {
        "RecoveryController",
        "CTFTaskDispatcher",
        "ToolExecutor",
        "WorkerPool",
        "CrewOrchestrator",
    }
    path = "flaghunter/agents/pa_agent/task_dag_replay_audit_view.py"
    guarded_scopes = [
        "TaskDAGReplayAuditViewItem.to_dict",
        "TaskDAGReplayAuditView.to_dict",
        "build_task_dag_replay_audit_view",
        "load_task_dag_replay_audit_view_items",
    ]
    offenders: list[tuple[str, str, str]] = []
    tree = _parse_source(path)
    text = (REPO_ROOT / path).read_text(encoding="utf-8")

    for scope in guarded_scopes:
        source = ast.get_source_segment(text, _scope_node(tree, scope)) or ""
        offenders.extend((path, scope, token) for token in forbidden_tokens if token in source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name in forbidden_import_modules or alias.name in forbidden_import_names:
                    offenders.append((path, "import", alias.name))
        if isinstance(node, ast.ImportFrom):
            module = node.module or ""
            normalized_module = f".{module}" if node.level else module
            if module in forbidden_import_modules or normalized_module in forbidden_import_modules:
                offenders.append((path, "import", normalized_module))
            for alias in node.names:
                if alias.name in forbidden_import_names:
                    offenders.append((path, "import", alias.name))

    assert offenders == []


def test_p4e_task_dag_replay_audit_bundle_scopes_do_not_execute_mutate_or_write_proof() -> None:
    forbidden_tokens = {
        "create_claim",
        "append_verification_record",
        "upgrade_claim_to_verified",
        "add_flag(",
        "build_verification_decision_event",
        "verification_decision",
        "verified_flags",
        'level="verified"',
        "level='verified'",
        "ToolExecutor",
        "execute_tools",
        "_execute_tools",
        "run_task",
        "subprocess",
        "ctf_dispatcher",
        "CTFTaskDispatcher",
        "RecoveryController",
        "WorkerPool",
        "CrewOrchestrator",
        "build_local_task_dag_receipt",
        "local_dag_apply_receipt",
        "apply_local_dag_task_receipt",
        "record_task_dag_p3_receipt",
        "record_solve_node_receipt",
        "set_task_dag_plan",
    }
    forbidden_import_modules = {
        "flaghunter.agents.pa_agent.recovery",
        "flaghunter.agents.pa_agent.ctf_dispatcher",
        "flaghunter.tools.executor",
        "flaghunter.agents.crew.worker_pool",
        "flaghunter.agents.crew.orchestrator",
        ".recovery",
        ".ctf_dispatcher",
    }
    forbidden_import_names = {
        "RecoveryController",
        "CTFTaskDispatcher",
        "ToolExecutor",
        "WorkerPool",
        "CrewOrchestrator",
    }
    path = "flaghunter/agents/pa_agent/task_dag_replay_audit_bundle.py"
    guarded_scopes = [
        "TaskDAGReplayAuditBundle.to_dict",
        "build_task_dag_replay_audit_bundle",
        "load_task_dag_replay_audit_bundle_items",
    ]
    offenders: list[tuple[str, str, str]] = []
    tree = _parse_source(path)
    text = (REPO_ROOT / path).read_text(encoding="utf-8")

    for scope in guarded_scopes:
        source = ast.get_source_segment(text, _scope_node(tree, scope)) or ""
        offenders.extend((path, scope, token) for token in forbidden_tokens if token in source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name in forbidden_import_modules or alias.name in forbidden_import_names:
                    offenders.append((path, "import", alias.name))
        if isinstance(node, ast.ImportFrom):
            module = node.module or ""
            normalized_module = f".{module}" if node.level else module
            if module in forbidden_import_modules or normalized_module in forbidden_import_modules:
                offenders.append((path, "import", normalized_module))
            for alias in node.names:
                if alias.name in forbidden_import_names:
                    offenders.append((path, "import", alias.name))

    assert offenders == []


def test_p3d_state_and_dispatcher_bridge_scopes_do_not_write_proof() -> None:
    forbidden_tokens = {
        "create_claim",
        "append_verification_record",
        "upgrade_claim_to_verified",
        "add_flag(",
        "build_verification_decision_event",
        "verification_decision",
        "verified_flags",
        'level="verified"',
        "level='verified'",
    }
    guarded_scopes = [
        (
            "flaghunter/agents/pa_agent/ctf_state.py",
            "CTFState.record_solve_node",
        ),
        (
            "flaghunter/agents/pa_agent/ctf_state.py",
            "CTFState.record_task_brief",
        ),
        (
            "flaghunter/agents/pa_agent/ctf_state.py",
            "CTFState.record_solve_node_receipt",
        ),
        (
            "flaghunter/agents/pa_agent/ctf_dispatcher.py",
            "CTFTaskDispatcher._record_p3_strategy_attempt_start",
        ),
        (
            "flaghunter/agents/pa_agent/ctf_dispatcher.py",
            "CTFTaskDispatcher._record_p3_strategy_attempt_receipt",
        ),
    ]
    offenders: list[tuple[str, str, str]] = []

    for path, scope in guarded_scopes:
        source = ast.get_source_segment(
            (REPO_ROOT / path).read_text(encoding="utf-8"),
            _scope_node(_parse_source(path), scope),
        ) or ""
        offenders.extend(
            (path, scope, token) for token in forbidden_tokens if token in source
        )

    assert offenders == []


def test_p3e_and_p3f_readback_surfacing_paths_do_not_write_proof() -> None:
    guarded_paths = [
        "flaghunter/agents/pa_agent/p3_solve_readback.py",
    ]
    forbidden_tokens = {
        "create_claim",
        "append_verification_record",
        "upgrade_claim_to_verified",
        "add_flag(",
        "build_verification_decision_event",
        "verification_decision",
        "verified_flags",
        'level="verified"',
        "level='verified'",
    }
    offenders: list[tuple[str, str]] = []

    for path in guarded_paths:
        text = (REPO_ROOT / path).read_text(encoding="utf-8")
        offenders.extend((path, token) for token in forbidden_tokens if token in text)

    assert offenders == []


def test_p3f_crew_blackboard_and_swarm_paths_do_not_write_proof() -> None:
    guarded_paths = [
        "flaghunter/agents/crew/swarm_bridge.py",
        "flaghunter/agents/pa_agent/ctf_crew_coordinator.py",
        "flaghunter/agents/pa_agent/ctf_crew_runner.py",
        "flaghunter/agents/pa_agent/blackboard.py",
        "flaghunter/agents/pa_agent/blackboard_adapter.py",
    ]
    forbidden_tokens = {
        "append_verification_record",
        "upgrade_claim_to_verified",
        "build_verification_decision_event",
        "verification_decision",
        'level="verified"',
        "level='verified'",
    }
    offenders: list[tuple[str, str]] = []

    for path in guarded_paths:
        text = (REPO_ROOT / path).read_text(encoding="utf-8")
        offenders.extend((path, token) for token in forbidden_tokens if token in text)

        tree = _parse_source(path)
        visitor = _AddFlagVerifiedVisitor(path)
        visitor.visit(tree)
        offenders.extend(
            (relative_path, f"add_flag(level=verified) at {scope}:{line}")
            for relative_path, scope, line in visitor.hits
        )

    assert offenders == []


def test_p1_verify_or_submit_flag_contract_reads_canonical_claim_without_writing_proof() -> None:
    node = _scope_node(
        _parse_source("flaghunter/agents/pa_agent/coordinator.py"),
        "CTFCoordinator._apply_verified_flag_contract",
    )
    calls = list(ast.walk(node))
    call_names = {
        call.func.id
        for call in calls
        if isinstance(call, ast.Call) and isinstance(call.func, ast.Name)
    }
    add_flag_calls = [
        call.lineno
        for call in calls
        if isinstance(call, ast.Call)
        and isinstance(call.func, ast.Attribute)
        and call.func.attr == "add_flag"
    ]
    forbidden_literals = {
        constant.value
        for constant in calls
        if isinstance(constant, ast.Constant)
        and constant.value
        in {
            "blackboard-verified-flag",
            "control_verified_flag",
            "verification_decision",
        }
    }

    assert "_existing_canonical_verified_flag" in call_names
    assert "build_verification_decision_event" not in call_names
    assert add_flag_calls == []
    assert forbidden_literals == set()


def test_p1_removed_verified_bypass_tokens_do_not_return_to_production_code() -> None:
    forbidden_tokens = {
        "control_verified_flag",
        "blackboard-verified-flag",
    }
    offenders: list[tuple[str, str]] = []

    for path in _python_sources(PRODUCTION_ROOT):
        text = path.read_text(encoding="utf-8")
        for token in forbidden_tokens:
            if token in text:
                offenders.append((_relative(path), token))

    assert offenders == []


def test_p1_verified_flag_consumers_document_selector_only_contract() -> None:
    guarded_paths = [
        "flaghunter/agents/pa_agent/coordinator.py",
        "flaghunter/interface/control_contract.py",
        "flaghunter/interface/web_ingress_handoff.py",
        "flaghunter/mcp/server/mcp_tools.py",
    ]
    missing_contract: list[tuple[str, int, str]] = []

    for relative_path in guarded_paths:
        lines = (REPO_ROOT / relative_path).read_text(encoding="utf-8").splitlines()
        for index, line in enumerate(lines):
            if "verifiedFlag" not in line:
                continue
            if "verifiedFlag" in line and line.strip().startswith('"verifiedFlag":'):
                continue
            window = "\n".join(lines[max(0, index - 16) : min(len(lines), index + 9)])
            if "selector" in window and "proof" in window:
                continue
            if "verifiedFlags" in line:
                continue
            missing_contract.append((relative_path, index + 1, line.strip()))

    assert missing_contract == []
