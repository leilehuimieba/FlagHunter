from __future__ import annotations

from pathlib import Path

import pytest

from tests.integration.easy_login_acceptance import extract_flag
from tests.integration.local_challenge_catalog import (
    get_local_challenge_sample,
    list_local_challenge_eval_cases,
)
from tests.integration.local_challenge_runner import (
    run_active_local_challenge_sample,
    run_catalog_local_challenge_eval_case,
)


pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_local_challenge_runner_solves_easy_login_directory_variant(monkeypatch):
    sample = get_local_challenge_sample("easy_login")

    result = await run_active_local_challenge_sample(
        sample,
        variant="directory",
        monkeypatch=monkeypatch,
    )

    assert result.success is True
    assert result.flag == "flag{dummy_flag_for_testing}"


@pytest.mark.asyncio
async def test_local_challenge_runner_solves_easy_login_zip_variant(monkeypatch, tmp_path: Path):
    sample = get_local_challenge_sample("easy_login")

    result = await run_active_local_challenge_sample(
        sample,
        variant="zip",
        monkeypatch=monkeypatch,
        tmp_dir=tmp_path,
    )

    assert result.success is True
    assert result.flag == "flag{dummy_flag_for_testing}"


@pytest.mark.asyncio
async def test_local_challenge_runner_keeps_no_asset_easy_login_honest(monkeypatch):
    sample = get_local_challenge_sample("easy_login")

    result = await run_active_local_challenge_sample(
        sample,
        variant="none",
        monkeypatch=monkeypatch,
    )

    assert result.success is False
    assert result.flag is None
    assert result.reason


@pytest.mark.asyncio
async def test_local_challenge_runner_solves_easy_login_runtime_only_variant(monkeypatch):
    sample = get_local_challenge_sample("easy_login")

    result = await run_active_local_challenge_sample(
        sample,
        variant="runtime_only",
        monkeypatch=monkeypatch,
    )

    assert result.success is True
    assert result.flag == "flag{dummy_flag_for_testing}"
    assert result.reason == "docker localhost visit fallback"


@pytest.mark.asyncio
async def test_local_challenge_runner_rejects_unsupported_variant(monkeypatch):
    sample = get_local_challenge_sample("backup_node_app")

    with pytest.raises(ValueError, match="unsupported variant"):
        await run_active_local_challenge_sample(
            sample,
            variant="directory",
            monkeypatch=monkeypatch,
        )


@pytest.mark.asyncio
async def test_local_challenge_runner_keeps_backup_node_app_zip_variant_honest(monkeypatch, tmp_path: Path):
    sample = get_local_challenge_sample("backup_node_app")

    result = await run_active_local_challenge_sample(
        sample,
        variant="zip",
        monkeypatch=monkeypatch,
        tmp_dir=tmp_path,
    )

    assert result.success is False
    assert result.flag is None
    assert result.reason


@pytest.mark.asyncio
async def test_local_challenge_runner_keeps_backup_node_app_no_asset_variant_honest(monkeypatch):
    sample = get_local_challenge_sample("backup_node_app")

    result = await run_active_local_challenge_sample(
        sample,
        variant="none",
        monkeypatch=monkeypatch,
    )

    assert result.success is False
    assert result.flag is None
    assert result.reason


@pytest.mark.asyncio
async def test_local_challenge_runner_accepts_catalog_eval_case(monkeypatch, tmp_path: Path):
    case = next(
        case
        for case in list_local_challenge_eval_cases()
        if case["sample_key"] == "easy_login" and case["variant"] == "runtime_only"
    )

    result = await run_catalog_local_challenge_eval_case(
        case,
        monkeypatch=monkeypatch,
        tmp_dir=tmp_path,
    )

    assert result.success is True
    assert result.flag == "flag{dummy_flag_for_testing}"
    assert result.reason == "docker localhost visit fallback"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "case",
    list_local_challenge_eval_cases(),
    ids=lambda case: f'{case["sample_key"]}:{case["variant"]}',
)
async def test_local_challenge_eval_matrix_matches_catalog_outcome(case, monkeypatch, tmp_path: Path):
    result = await run_catalog_local_challenge_eval_case(
        case,
        monkeypatch=monkeypatch,
        tmp_dir=tmp_path,
    )

    if case["expected_outcome"] == "verified_flag":
        assert result.success is True
        assert extract_flag(result.flag) == "flag{dummy_flag_for_testing}"
        return

    if case["expected_outcome"] in {"candidate_only_honesty", "honest_no_flag"}:
        assert result.success is False
        assert result.flag is None
        assert result.reason
        assert not extract_flag(result.reason)
        return

    raise AssertionError(f'unhandled expected_outcome: {case["expected_outcome"]}')
