"""B-07 — canonical dependency manifest + reproducible lock (F-11).

pyproject.toml ``[project.dependencies]`` is the single source of runtime
dependency declarations; ``requirements.txt`` and ``requirements.lock`` are
generated from it by ``scripts/lock_dependencies.py``. Before B-07 the three
declaration files disagreed (requirements.txt listed only jinja2 while
pyproject declared 24 packages) and no lockfile existed, so builds were not
reproducible. These guards keep the generated files honest:

  * requirements.txt is an exact mirror of the canonical specifiers (no drift);
  * requirements.lock is fully exact-pinned (``==`` only — reproducible) and
    covers every canonical top-level dependency.

Version numbers in the lock are intentionally **not** asserted (they float with
the resolved environment); only the drift-free structure is pinned, so the test
is stable across environments while the lock file itself carries the exact pins.
"""

from __future__ import annotations

import importlib.util
import re
import tomllib
from pathlib import Path

from packaging.utils import canonicalize_name

REPO_ROOT = Path(__file__).resolve().parents[2]
PYPROJECT = REPO_ROOT / "pyproject.toml"
REQUIREMENTS = REPO_ROOT / "requirements.txt"
LOCKFILE = REPO_ROOT / "requirements.lock"


def _load_script():
    path = REPO_ROOT / "scripts" / "lock_dependencies.py"
    spec = importlib.util.spec_from_file_location("lock_dependencies", path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def _canonical_specifiers() -> list[str]:
    data = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    return list(data["project"]["dependencies"])


def _canonical_names() -> set[str]:
    from packaging.requirements import Requirement

    return {canonicalize_name(Requirement(s).name) for s in _canonical_specifiers()}


def _lock_pins() -> dict[str, str]:
    pins: dict[str, str] = {}
    for line in LOCKFILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        assert "==" in line, f"lock line is not exact-pinned: {line!r}"
        name, _, version = line.partition("==")
        pins[canonicalize_name(name)] = version
    return pins


def test_generated_files_exist():
    assert REQUIREMENTS.exists()
    assert LOCKFILE.exists()


def test_requirements_mirrors_canonical_source_exactly():
    """requirements.txt must be byte-for-byte what the canonical source renders."""
    module = _load_script()
    expected = module.render_requirements(_canonical_specifiers())
    assert REQUIREMENTS.read_text(encoding="utf-8") == expected


def test_generated_files_carry_do_not_edit_banner():
    for path in (REQUIREMENTS, LOCKFILE):
        head = path.read_text(encoding="utf-8")
        assert "GENERATED" in head
        assert "pyproject.toml" in head
        assert "scripts/lock_dependencies.py" in head


def test_lock_is_fully_exact_pinned():
    """Every dependency line pins an exact version — the reproducibility property."""
    text = LOCKFILE.read_text(encoding="utf-8")
    loose = re.compile(r"[<>~!]=|[<>](?!=)")
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        assert "==" in line, f"unpinned dependency in lock: {line!r}"
        assert not loose.search(line), f"non-exact specifier in lock: {line!r}"


def test_lock_covers_every_canonical_top_level_dependency():
    pinned = set(_lock_pins())
    missing = _canonical_names() - pinned
    assert not missing, f"canonical deps absent from lock: {sorted(missing)}"


def test_lock_includes_transitive_dependencies():
    """The lock is a full closure, not just the top level (reproducible build)."""
    pins = _lock_pins()
    # More entries than the top-level set proves transitive deps are captured.
    assert len(pins) > len(_canonical_names())


def test_check_mode_passes_for_committed_requirements():
    """requirements.txt is environment-independent, so --check must agree with it."""
    module = _load_script()
    expected = module.render_requirements(module.read_canonical_dependencies())
    assert REQUIREMENTS.read_text(encoding="utf-8") == expected
