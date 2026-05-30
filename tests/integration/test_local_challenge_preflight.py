from __future__ import annotations

from pathlib import Path

from tests.integration.local_challenge_preflight import (
    collect_local_challenge_preflight_warnings,
)


def test_local_challenge_preflight_flags_seed_file_shadowed_by_named_volume() -> None:
    warnings = collect_local_challenge_preflight_warnings(
        Path(r"D:\webstudy\CTF\2026\长城杯\easy_time (1)")
    )

    warning = next(
        item for item in warnings if item["kind"] == "seed_file_shadowed_by_named_volume"
    )

    assert warning["env_var"] == "DB_PATH"
    assert warning["container_path"] == "/data/app.db"
    assert warning["mounted_parent"] == "/data"
    assert warning["seed_file"].endswith("app.db")


def test_local_challenge_preflight_keeps_easy_login_free_of_seed_shadow_warning() -> None:
    warnings = collect_local_challenge_preflight_warnings(
        Path(r"D:\webstudy\CTF\2026\CTF比赛题\easy_login")
    )

    assert not any(
        item["kind"] == "seed_file_shadowed_by_named_volume"
        for item in warnings
    )
