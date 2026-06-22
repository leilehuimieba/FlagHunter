"""Security tests: RAG index persistence must not use pickle (H5 hardening).

History: the RAG engine used to persist its index / document store as a pickle
file (``embeddings/index.pkl``). A compromised or maliciously crafted pickle
file executes arbitrary code during deserialization (classic pickle RCE), and a
workspace index file is attacker-writable.

H5 replaced pickle with JSON (documents) + base64-encoded embeddings, and
renamed the on-disk artifact to ``index.json`` so the loader never touches a
legacy pickle.

These tests:
1. Document the pickle RCE vector (why we moved away from it).
2. Verify ``RAGEngine.save_index`` / ``load_index`` use JSON, not pickle.
3. Verify a malicious pickle dropped at the index path does NOT execute on load.
4. Verify benign round-trip (documents + embeddings) survives save/load.
"""

import os
import pickle

import pytest


# ---------------------------------------------------------------------------
# Helpers — a module-level pickle RCE payload used to prove load_index is safe
# ---------------------------------------------------------------------------

# Module-level state so pickle can resolve callables by reference
_rce_executed: list = []


def _rce_trigger():
    """Module-level function — pickle can serialize its reference."""
    _rce_executed.append("EXECUTED")


class _RCEPayload:
    """Pickle payload that calls a module-level function on deserialization."""
    def __reduce__(self):
        return (_rce_trigger, ())


def _make_malicious_pickle() -> bytes:
    return pickle.dumps(_RCEPayload())


# ---------------------------------------------------------------------------
# Risk documentation — why pickle was removed (the vector is real)
# ---------------------------------------------------------------------------

class TestPickleRiskDocumentation:
    def test_pickle_module_allows_code_execution(self):
        """Standard pickle.loads executes arbitrary code on deserialization.

        This proves the attack vector that H5 eliminated for the RAG index —
        it is NOT a claim that pickle itself was blocked.
        """
        class LocalExploit:
            def __reduce__(self):
                return (os.getenv, ("HOME",))  # safe: just reads HOME env var

        payload = pickle.dumps(LocalExploit())
        result = pickle.loads(payload)
        assert result == os.getenv("HOME"), "pickle.loads executes the __reduce__ callable"

    def test_module_level_rce_payload_executes(self):
        """The RCE payload used below really does execute on unpickling."""
        _rce_executed.clear()
        pickle.loads(_make_malicious_pickle())
        assert "EXECUTED" in _rce_executed, (
            "Module-level pickle RCE payload did not execute — "
            "verify the _RCEPayload class is correct."
        )


# ---------------------------------------------------------------------------
# RAG engine hardening — the index uses JSON, never pickle
# ---------------------------------------------------------------------------

class TestRAGIndexHardened:
    def test_save_index_uses_json_not_pickle(self):
        import inspect
        from flaghunter.knowledge.rag import RAGEngine
        source = inspect.getsource(RAGEngine.save_index)
        assert "json.dump" in source, "save_index must serialize via JSON"
        assert "pickle.dump" not in source, "save_index must not write pickle"

    def test_load_index_uses_json_not_pickle(self):
        import inspect
        from flaghunter.knowledge.rag import RAGEngine
        source = inspect.getsource(RAGEngine.load_index)
        assert "json.load" in source, "load_index must read JSON"
        assert "pickle.load" not in source, "load_index must not unpickle"

    def test_save_index_writes_json_file(self, tmp_path):
        import json
        import numpy as np
        from flaghunter.knowledge.rag import Document, RAGEngine

        engine = RAGEngine(knowledge_path=tmp_path)
        engine.documents = [
            Document(content="test document", source="test",
                     embedding=np.array([0.1, 0.2, 0.3], dtype=np.float32))
        ]
        engine.embeddings = np.array([[0.1, 0.2, 0.3]], dtype=np.float32)
        path = tmp_path / "idx.json"
        engine.save_index(path)

        assert path.exists()
        raw = path.read_bytes()
        # NOT a pickle: pickle protocol 2+ files start with the \x80 opcode.
        assert raw[0] != 0x80, "index file must not be a pickle stream"
        # IS valid JSON with the expected shape.
        parsed = json.loads(path.read_text(encoding="utf-8"))
        assert parsed["version"] == 2
        assert parsed["documents"][0]["content"] == "test document"

    def test_round_trip_preserves_documents_and_embeddings(self, tmp_path):
        import numpy as np
        from flaghunter.knowledge.rag import Document, RAGEngine

        engine = RAGEngine(knowledge_path=tmp_path)
        engine.documents = [Document(content="hello security", source="test.txt")]
        engine.embeddings = np.array([[0.1, 0.2, 0.3, 0.4]], dtype=np.float32)
        path = tmp_path / "idx.json"
        engine.save_index(path)

        engine2 = RAGEngine(knowledge_path=tmp_path)
        engine2.load_index(path)

        assert len(engine2.documents) == 1
        assert engine2.documents[0].content == "hello security"
        assert engine2.embeddings is not None
        np.testing.assert_allclose(engine2.embeddings, engine.embeddings)
        # per-doc embedding restored from the matrix
        np.testing.assert_allclose(engine2.documents[0].embedding, engine.embeddings[0])

    def test_load_index_refuses_pickle_rce_payload(self, tmp_path):
        """A malicious pickle dropped at the index path does NOT execute.

        load_index uses json.load, which raises on raw pickle bytes instead of
        unpickling them — the RCE vector is gone even if an attacker writes a
        crafted file to the (attacker-writable) workspace index path.
        """
        from flaghunter.knowledge.rag import RAGEngine

        _rce_executed.clear()
        path = tmp_path / "idx.json"
        path.write_bytes(_make_malicious_pickle())

        engine = RAGEngine(knowledge_path=tmp_path)
        with pytest.raises(Exception):
            engine.load_index(path)
        assert "EXECUTED" not in _rce_executed, (
            "load_index executed a pickle payload — the JSON loader must never unpickle"
        )


# ---------------------------------------------------------------------------
# Recommendations (informational assertions about the safe primitives used)
# ---------------------------------------------------------------------------

class TestPickleHardeningPrimitives:
    def test_json_is_a_safe_alternative(self):
        import json
        data = {"key": "value", "numbers": [1, 2, 3]}
        assert json.loads(json.dumps(data)) == data

    def test_numpy_frombuffer_is_data_only(self):
        """np.frombuffer reconstructs arrays from raw bytes without executing code."""
        import base64
        import numpy as np

        arr = np.array([1.0, 2.0, 3.0], dtype=np.float32)
        b64 = base64.b64encode(arr.tobytes()).decode("ascii")
        restored = np.frombuffer(base64.b64decode(b64), dtype=np.float32)
        np.testing.assert_allclose(restored, arr)
