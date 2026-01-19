from pathlib import Path

from pentestagent.knowledge.indexer import KnowledgeIndexer
from pentestagent.knowledge.rag import RAGEngine
from pentestagent.workspaces.manager import WorkspaceManager


def test_rag_and_indexer_use_workspace(tmp_path, monkeypatch):
    # Use tmp_path as the project root
    monkeypatch.chdir(tmp_path)

    wm = WorkspaceManager(root=tmp_path)
    name = "ws_test"
    wm.create(name)
    wm.set_active(name)

    # Create a sample source file in the workspace sources
    src_dir = tmp_path / "workspaces" / name / "knowledge" / "sources"
    src_dir.mkdir(parents=True, exist_ok=True)
    sample = src_dir / "sample.md"
    sample.write_text("# Sample\n\nThis is a test knowledge document for RAG indexing.")

    # Ensure KnowledgeIndexer picks up the workspace source when indexing default 'knowledge'
    ki = KnowledgeIndexer()
    docs, result = ki.index_directory(Path("knowledge"))

    assert result.indexed_files >= 1
    assert len(docs) >= 1
    # Ensure the document source path points at the workspace file
    assert any("workspaces" in d.source and "sample.md" in d.source for d in docs)

    # Now run RAGEngine to build embeddings and verify saved index file appears
    rag = RAGEngine(use_local_embeddings=True)
    rag.index()

    emb_path = tmp_path / "workspaces" / name / "knowledge" / "embeddings" / "index.pkl"
    assert emb_path.exists(), f"Expected saved index at {emb_path}"

    # Ensure RAG engine has documents/chunks loaded
    assert rag.get_chunk_count() >= 1
    assert rag.get_document_count() >= 1

    # Now create a new RAGEngine and ensure it loads the persisted index instead of re-indexing
    # Record the persisted index mtime so we can assert it is not overwritten by a re-index
    mtime_before = emb_path.stat().st_mtime

    rag2 = RAGEngine(use_local_embeddings=True)
    # If load-on-init doesn't run, calling index() would re-index and rewrite the file
    rag2.index()
    assert rag2.get_chunk_count() >= 1

    mtime_after = emb_path.stat().st_mtime
    assert mtime_after == mtime_before, "Expected persisted index to be loaded, not re-written"
