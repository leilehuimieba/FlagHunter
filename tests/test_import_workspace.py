import tarfile
import warnings

# Suppress DeprecationWarning from the stdlib `tarfile` regarding future
# changes to `extractall()` behavior; tests exercise archive extraction
# and are not affected by the warning.
warnings.filterwarnings("ignore", category=DeprecationWarning, module="tarfile")
from pathlib import Path

import pytest

from pentestagent.workspaces.utils import import_workspace


def make_tar_with_dir(source_dir: Path, archive_path: Path, store_subpath: Path = None):
    # Create a tar.gz archive containing the contents of source_dir.
    with tarfile.open(archive_path, "w:gz") as tf:
        for p in source_dir.rglob("*"):
            rel = p.relative_to(source_dir.parent)
            # Optionally store paths under a custom subpath
            arcname = str(rel)
            if store_subpath:
                # Prepend the store_subpath (e.g., workspaces/name/...)
                arcname = str(store_subpath / p.relative_to(source_dir))
            tf.add(str(p), arcname=arcname)


def test_import_workspace_nested(tmp_path):
    # Create a workspace dir structure under a temporary dir
    src_root = tmp_path / "src"
    ws_name = "import-test"
    ws_dir = src_root / "workspaces" / ws_name
    ws_dir.mkdir(parents=True)
    # write meta.yaml
    meta = ws_dir / "meta.yaml"
    meta.write_text("name: import-test\n")
    # add a file
    (ws_dir / "notes.txt").write_text("hello")

    archive = tmp_path / "ws_nested.tar.gz"
    # Create archive that stores workspaces/<name>/...
    make_tar_with_dir(ws_dir, archive, store_subpath=Path("workspaces") / ws_name)

    dest_root = tmp_path / "dest"
    dest_root.mkdir()

    import warnings
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", category=DeprecationWarning, module="tarfile")
        name = import_workspace(archive, root=dest_root)
    assert name == ws_name
    dest_ws = dest_root / "workspaces" / ws_name
    assert dest_ws.exists()
    assert (dest_ws / "meta.yaml").exists()


def test_import_workspace_flat(tmp_path):
    # Create a folder that is directly the workspace (not nested under workspaces/)
    src = tmp_path / "srcflat"
    src.mkdir()
    (src / "meta.yaml").write_text("name: flat-test\n")
    (src / "data.txt").write_text("x")

    archive = tmp_path / "ws_flat.tar.gz"
    # Archive the src folder contents directly (no workspaces/ prefix)
    with tarfile.open(archive, "w:gz") as tf:
        for p in src.rglob("*"):
            tf.add(str(p), arcname=str(p.relative_to(src.parent)))

    dest_root = tmp_path / "dest2"
    dest_root.mkdir()

    import warnings
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", category=DeprecationWarning, module="tarfile")
        name = import_workspace(archive, root=dest_root)
    assert name == "flat-test"
    assert (dest_root / "workspaces" / "flat-test" / "meta.yaml").exists()


def test_import_workspace_missing_meta(tmp_path):
    # Archive without meta.yaml
    src = tmp_path / "empty"
    src.mkdir()
    (src / "file.txt").write_text("x")
    archive = tmp_path / "no_meta.tar.gz"
    with tarfile.open(archive, "w:gz") as tf:
        for p in src.rglob("*"):
            tf.add(str(p), arcname=str(p.relative_to(src.parent)))

    dest_root = tmp_path / "dest3"
    dest_root.mkdir()

    with pytest.raises(ValueError):
        import warnings
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", category=DeprecationWarning, module="tarfile")
            import_workspace(archive, root=dest_root)
