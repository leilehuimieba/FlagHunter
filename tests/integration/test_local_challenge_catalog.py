from __future__ import annotations

from pathlib import Path

from tests.integration.local_challenge_catalog import (
    build_challenge_context,
    get_local_challenge_sample,
    list_local_challenge_eval_cases,
    list_local_challenge_samples,
)


def test_local_challenge_catalog_contains_active_easy_login_sample() -> None:
    samples = list_local_challenge_samples()
    easy_login = get_local_challenge_sample("easy_login")

    assert "easy_login" in {sample.key for sample in samples}
    assert easy_login.status == "active"
    assert easy_login.mode == "ctf"
    assert easy_login.mode_subtype == "web"
    assert easy_login.challenge_path.exists()
    assert "flag{" not in easy_login.minimal_prompt.lower()
    assert "/login -> /visit -> /admin" not in easy_login.minimal_prompt
    assert easy_login.supported_variants == ("directory", "zip", "none", "runtime_only")
    assert easy_login.primary_eval_focus == "runtime_and_asset_dual_path"


def test_local_challenge_catalog_marks_backup_node_app_as_candidate_honesty_sample() -> None:
    backup = get_local_challenge_sample("backup_node_app")

    assert backup.status == "candidate"
    assert backup.expected_outcome == "candidate_only_honesty"
    assert backup.challenge_path.exists()
    assert backup.challenge_path.name == "backup.zip"
    assert "www.zip" not in backup.minimal_prompt.lower()
    assert "flag{" not in backup.minimal_prompt.lower()
    assert backup.supported_variants == ("zip", "none")
    assert backup.primary_eval_focus == "source_only_honesty"


def test_local_challenge_catalog_builds_easy_login_directory_and_zip_contexts(tmp_path: Path) -> None:
    easy_login = get_local_challenge_sample("easy_login")

    directory_context = build_challenge_context(easy_login, variant="directory")
    zip_context = build_challenge_context(easy_login, variant="zip", tmp_dir=tmp_path)

    assert directory_context["challengePath"] == str(easy_login.challenge_path)
    assert directory_context["artifactPaths"] == []

    assert zip_context["challengePath"] is None
    assert len(zip_context["artifactPaths"]) == 1
    assert zip_context["artifactPaths"][0].endswith(".zip")
    assert Path(zip_context["artifactPaths"][0]).exists()


def test_local_challenge_catalog_exposes_supported_variants_as_runner_contract() -> None:
    easy_login = get_local_challenge_sample("easy_login")
    backup = get_local_challenge_sample("backup_node_app")

    assert "runtime_only" in easy_login.supported_variants
    assert "directory" not in backup.supported_variants


def test_local_challenge_catalog_builds_programmatic_eval_case_index() -> None:
    cases = list_local_challenge_eval_cases()
    keys = {(case["sample_key"], case["variant"]) for case in cases}

    assert ("easy_login", "directory") in keys
    assert ("easy_login", "zip") in keys
    assert ("easy_login", "none") in keys
    assert ("easy_login", "runtime_only") in keys
    assert ("backup_node_app", "zip") in keys
    assert ("backup_node_app", "none") in keys

    easy_runtime_case = next(
        case for case in cases if case["sample_key"] == "easy_login" and case["variant"] == "runtime_only"
    )
    assert easy_runtime_case["expected_outcome"] == "verified_flag"
    assert easy_runtime_case["status"] == "active"

    backup_zip_case = next(
        case for case in cases if case["sample_key"] == "backup_node_app" and case["variant"] == "zip"
    )
    assert backup_zip_case["expected_outcome"] == "candidate_only_honesty"
    assert backup_zip_case["status"] == "candidate"
