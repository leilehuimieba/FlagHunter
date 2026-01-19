import os
from pathlib import Path

import pytest

from pentestagent.workspaces.manager import WorkspaceManager, WorkspaceError


def test_invalid_workspace_names(tmp_path: Path):
    wm = WorkspaceManager(root=tmp_path)
    bad_names = ["../escape", "name/with/slash", "..", ""]
    # overlong name
    bad_names.append("a" * 65)
    for n in bad_names:
        with pytest.raises(WorkspaceError):
            wm.create(n)


def test_create_and_idempotent(tmp_path: Path):
    wm = WorkspaceManager(root=tmp_path)
    name = "eng1"
    meta = wm.create(name)
    assert (tmp_path / "workspaces" / name).exists()
    assert (tmp_path / "workspaces" / name / "meta.yaml").exists()
    # create again should not raise and should return meta
    meta2 = wm.create(name)
    assert meta2["name"] == name


def test_set_get_active(tmp_path: Path):
    wm = WorkspaceManager(root=tmp_path)
    name = "activews"
    wm.create(name)
    wm.set_active(name)
    assert wm.get_active() == name
    marker = tmp_path / "workspaces" / ".active"
    assert marker.exists()
    assert marker.read_text(encoding="utf-8").strip() == name


def test_add_list_remove_targets(tmp_path: Path):
    wm = WorkspaceManager(root=tmp_path)
    name = "targets"
    wm.create(name)
    added = wm.add_targets(name, ["192.168.1.1", "192.168.0.0/16", "Example.COM"])  # hostname mixed case
    # normalized entries
    assert "192.168.1.1" in added
    assert "192.168.0.0/16" in added
    assert "example.com" in added
    # dedupe
    added2 = wm.add_targets(name, ["192.168.1.1", "example.com"])
    assert len(added2) == len(added)
    # remove
    after = wm.remove_target(name, "192.168.1.1")
    assert "192.168.1.1" not in after


def test_persistence_across_instances(tmp_path: Path):
    wm1 = WorkspaceManager(root=tmp_path)
    name = "persist"
    wm1.create(name)
    wm1.add_targets(name, ["10.0.0.1", "host.local"])

    # new manager instance reads from disk
    wm2 = WorkspaceManager(root=tmp_path)
    targets = wm2.list_targets(name)
    assert "10.0.0.1" in targets
    assert "host.local" in targets


def test_last_target_persistence(tmp_path: Path):
    wm = WorkspaceManager(root=tmp_path)
    a = "wsA"
    b = "wsB"
    wm.create(a)
    wm.create(b)

    t1 = "192.168.0.4"
    t2 = "192.168.0.165"

    # set last target on workspace A and B
    norm1 = wm.set_last_target(a, t1)
    norm2 = wm.set_last_target(b, t2)

    # persisted in meta
    assert wm.get_meta_field(a, "last_target") == norm1
    assert wm.get_meta_field(b, "last_target") == norm2

    # targets list contains the last target
    assert norm1 in wm.list_targets(a)
    assert norm2 in wm.list_targets(b)

    # new manager instance still sees last_target
    wm2 = WorkspaceManager(root=tmp_path)
    assert wm2.get_meta_field(a, "last_target") == norm1
    assert wm2.get_meta_field(b, "last_target") == norm2
