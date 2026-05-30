from __future__ import annotations

from pathlib import Path, PurePosixPath


def collect_local_challenge_preflight_warnings(challenge_path: Path) -> list[dict[str, str]]:
    compose_text = _read_compose_text(Path(challenge_path))
    if not compose_text:
        return []

    named_mounts = _parse_named_volume_mounts(compose_text)
    path_envs = _parse_path_environment_variables(compose_text)
    warnings: list[dict[str, str]] = []

    for env_var, container_path in path_envs.items():
        normalized_path = PurePosixPath(container_path)
        mounted_parent = _find_covering_named_mount(named_mounts, normalized_path)
        if not mounted_parent:
            continue

        seed_file = _find_seed_file(Path(challenge_path), normalized_path.name)
        if seed_file is None:
            continue

        warnings.append(
            {
                "kind": "seed_file_shadowed_by_named_volume",
                "env_var": env_var,
                "container_path": normalized_path.as_posix(),
                "mounted_parent": mounted_parent,
                "seed_file": str(seed_file),
                "message": (
                    f"{env_var} points to {normalized_path.as_posix()}, but compose mounts a named volume "
                    f"over {mounted_parent}; source seed file {seed_file.name} may not exist at runtime"
                ),
            }
        )

    return warnings


def _read_compose_text(challenge_path: Path) -> str:
    for name in ("docker-compose.yml", "docker-compose.yaml"):
        compose_path = challenge_path / name
        if compose_path.exists():
            return compose_path.read_text(encoding="utf-8")
    return ""


def _parse_named_volume_mounts(compose_text: str) -> list[tuple[str, str]]:
    mounts: list[tuple[str, str]] = []
    for raw_line in compose_text.splitlines():
        stripped = raw_line.strip()
        if not stripped.startswith("- "):
            continue
        mount = stripped[2:].strip().strip("'").strip('"')
        if ":" not in mount:
            continue
        source, target, *_ = mount.split(":")
        source = source.strip()
        target = target.strip()
        if not source or not target or not _looks_like_named_volume(source):
            continue
        if not target.startswith("/"):
            continue
        mounts.append((source, PurePosixPath(target).as_posix()))
    return mounts


def _parse_path_environment_variables(compose_text: str) -> dict[str, str]:
    envs: dict[str, str] = {}
    for raw_line in compose_text.splitlines():
        stripped = raw_line.strip()
        if not stripped.startswith("- "):
            continue
        entry = stripped[2:].strip().strip("'").strip('"')
        if "=" not in entry:
            continue
        key, value = entry.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key.endswith("_PATH"):
            continue
        if not value.startswith("/"):
            continue
        envs[key] = PurePosixPath(value).as_posix()
    return envs


def _looks_like_named_volume(source: str) -> bool:
    if not source:
        return False
    if source.startswith((".", "/", "${")):
        return False
    return "/" not in source and "\\" not in source


def _find_covering_named_mount(
    named_mounts: list[tuple[str, str]],
    container_path: PurePosixPath,
) -> str | None:
    normalized = container_path.as_posix()
    for _, target in named_mounts:
        if normalized == target or normalized.startswith(target.rstrip("/") + "/"):
            return target
    return None


def _find_seed_file(challenge_path: Path, basename: str) -> Path | None:
    direct = challenge_path / basename
    if direct.exists():
        return direct

    for candidate in challenge_path.rglob(basename):
        if candidate.is_file():
            return candidate
    return None
