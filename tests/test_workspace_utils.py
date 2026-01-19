import os
import tarfile
from pathlib import Path
import pytest
from pentestagent.workspaces.utils import export_workspace, import_workspace
from pentestagent.workspaces.manager import WorkspaceManager

def test_export_import_workspace(tmp_path):
    wm = WorkspaceManager(root=tmp_path)
    name = "expimp"
    wm.create(name)
    wm.add_targets(name, ["10.1.1.1", "host1.local"])
    # Add a file to workspace
    loot_dir = tmp_path / "workspaces" / name / "loot"
    loot_dir.mkdir(parents=True, exist_ok=True)
    (loot_dir / "loot.txt").write_text("lootdata")

    # Export
    archive = export_workspace(name, root=tmp_path)
    assert archive.exists()
    with tarfile.open(archive, "r:gz") as tf:
        members = tf.getnames()
        assert any("loot.txt" in m for m in members)
        assert any("meta.yaml" in m for m in members)

    # Remove workspace, then import
    ws_dir = tmp_path / "workspaces" / name
    for rootdir, dirs, files in os.walk(ws_dir, topdown=False):
        for f in files:
            os.remove(Path(rootdir) / f)
        for d in dirs:
            os.rmdir(Path(rootdir) / d)
    os.rmdir(ws_dir)
    assert not ws_dir.exists()

    imported = import_workspace(archive, root=tmp_path)
    assert imported == name
    assert (tmp_path / "workspaces" / name / "loot" / "loot.txt").exists()
    assert (tmp_path / "workspaces" / name / "meta.yaml").exists()


def test_import_workspace_missing_meta(tmp_path):
    # Create a tar.gz without meta.yaml
    archive = tmp_path / "bad.tar.gz"
    with tarfile.open(archive, "w:gz") as tf:
        tf.add(__file__, arcname="not_meta.txt")
    with pytest.raises(ValueError):
        import_workspace(archive, root=tmp_path)


def test_import_workspace_already_exists(tmp_path):
    wm = WorkspaceManager(root=tmp_path)
    name = "dupe"
    wm.create(name)
    archive = export_workspace(name, root=tmp_path)
    with pytest.raises(FileExistsError):
        import_workspace(archive, root=tmp_path)
