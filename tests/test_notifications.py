

def test_workspace_meta_write_failure_emits_notification(tmp_path, monkeypatch):
    """Simulate a meta.yaml write failure and ensure notifier receives a warning."""
    from pentestagent.interface import notifier
    from pentestagent.workspaces.manager import WorkspaceManager

    captured = []

    def cb(level, message):
        captured.append((level, message))

    notifier.register_callback(cb)

    wm = WorkspaceManager(root=tmp_path)
    # Create workspace first so initial meta is written successfully
    wm.create("testws")

    # Patch _write_meta to raise when called during set_active's meta update
    def bad_write(self, name, meta):
        raise RuntimeError("disk error")

    monkeypatch.setattr(WorkspaceManager, "_write_meta", bad_write)

    # Calling set_active should attempt to update meta and trigger notification
    wm.set_active("testws")

    assert len(captured) >= 1
    # Find a warning notification
    assert any("Failed to update workspace meta" in m for _, m in captured)


def test_rag_index_save_failure_emits_notification(tmp_path, monkeypatch):
    """Simulate RAG save failure during index persistence and ensure notifier gets a warning."""
    from pentestagent.interface import notifier
    from pentestagent.knowledge.rag import RAGEngine

    captured = []

    def cb(level, message):
        captured.append((level, message))

    notifier.register_callback(cb)

    # Prepare a small knowledge tree under tmp_path
    ws = tmp_path / "workspaces" / "ws1"
    src = ws / "knowledge" / "sources"
    src.mkdir(parents=True, exist_ok=True)
    f = src / "doc.txt"
    f.write_text("hello world")


    # Patch resolve_knowledge_paths in the RAG module to point to our tmp workspace
    def fake_resolve(root=None):
        return {
            "using_workspace": True,
            "sources": src,
            "embeddings": ws / "knowledge" / "embeddings",
        }

    monkeypatch.setattr("pentestagent.knowledge.rag.resolve_knowledge_paths", fake_resolve)

    # Ensure embeddings generation returns deterministic array (avoid external calls)
    import numpy as np

    monkeypatch.setattr(
        "pentestagent.knowledge.rag.get_embeddings",
        lambda texts, model=None: np.zeros((len(texts), 8)),
    )

    # Patch save_index to raise
    def bad_save(self, path):
        raise RuntimeError("write failed")

    monkeypatch.setattr(RAGEngine, "save_index", bad_save)

    rag = RAGEngine()  # uses default knowledge_path -> resolve_knowledge_paths
    # Force indexing which will attempt to save and trigger notifier
    rag.index(force=True)

    assert len(captured) >= 1
    assert any("Failed to save RAG index" in m or "persist RAG index" in m for _, m in captured)
