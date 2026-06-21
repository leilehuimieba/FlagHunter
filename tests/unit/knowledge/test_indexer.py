"""Tests for flaghunter.knowledge.indexer (KnowledgeIndexer)."""

import json
from pathlib import Path

import pytest

from flaghunter.knowledge.indexer import (
    IndexingResult,
    KnowledgeIndexer,
    resolve_knowledge_scan_paths,
)
from flaghunter.knowledge.rag import Document


# ---------------------------------------------------------------------------
# IndexingResult
# ---------------------------------------------------------------------------

class TestIndexingResult:
    def test_fields_accessible(self):
        r = IndexingResult(total_files=3, indexed_files=2, total_chunks=10, errors=[])
        assert r.total_files == 3
        assert r.indexed_files == 2
        assert r.total_chunks == 10
        assert r.errors == []


# ---------------------------------------------------------------------------
# KnowledgeIndexer.index_file — text files
# ---------------------------------------------------------------------------

class TestIndexFile:
    def test_index_txt_file(self, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("This is a test document with some content.", encoding="utf-8")
        indexer = KnowledgeIndexer()
        docs = indexer.index_file(f)
        assert len(docs) >= 1
        assert all(isinstance(d, Document) for d in docs)

    def test_index_md_file(self, tmp_path):
        f = tmp_path / "test.md"
        f.write_text("# Title\n\nSome markdown content.\n\n## Section\n\nMore content.", encoding="utf-8")
        indexer = KnowledgeIndexer()
        docs = indexer.index_file(f)
        assert len(docs) >= 1

    def test_index_json_file(self, tmp_path):
        f = tmp_path / "data.json"
        f.write_text(json.dumps([{"a": 1}, {"b": 2}]), encoding="utf-8")
        indexer = KnowledgeIndexer()
        docs = indexer.index_file(f)
        assert len(docs) == 2

    def test_index_json_object_file(self, tmp_path):
        f = tmp_path / "obj.json"
        f.write_text(json.dumps({"key": "value", "number": 42}), encoding="utf-8")
        indexer = KnowledgeIndexer()
        docs = indexer.index_file(f)
        assert len(docs) >= 1

    def test_index_uppercase_json_uses_json_branch(self, tmp_path, monkeypatch):
        # Regression: `.JSON` (uppercase) is dispatched as a data file via the
        # lowercased suffix, but the inner branch used the case-sensitive raw
        # suffix and fell through to the YAML loader. Poison the yaml import so
        # that any attempt to parse this file as YAML raises loudly.
        import builtins

        real_import = builtins.__import__

        def _no_yaml(name, *args, **kwargs):
            if name == "yaml":
                raise AssertionError("uppercase .JSON must not use the YAML branch")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", _no_yaml)

        f = tmp_path / "DATA.JSON"
        f.write_text(json.dumps([{"a": 1}, {"b": 2}]), encoding="utf-8")
        indexer = KnowledgeIndexer()
        docs = indexer.index_file(f)
        assert len(docs) == 2

    def test_uppercase_json_matches_lowercase(self, tmp_path):
        payload = json.dumps([{"a": 1}, {"b": 2}, {"c": 3}])
        lower = tmp_path / "data.json"
        upper = tmp_path / "data.JSON"
        lower.write_text(payload, encoding="utf-8")
        upper.write_text(payload, encoding="utf-8")
        indexer = KnowledgeIndexer()
        lower_docs = indexer.index_file(lower)
        upper_docs = indexer.index_file(upper)
        assert len(upper_docs) == len(lower_docs)
        assert [d.content for d in upper_docs] == [d.content for d in lower_docs]

    def test_unsupported_extension_returns_empty(self, tmp_path):
        f = tmp_path / "binary.exe"
        f.write_bytes(b"\x00\x01\x02")
        indexer = KnowledgeIndexer()
        docs = indexer.index_file(f)
        assert docs == []

    def test_empty_txt_returns_empty(self, tmp_path):
        f = tmp_path / "empty.txt"
        f.write_text("", encoding="utf-8")
        indexer = KnowledgeIndexer()
        docs = indexer.index_file(f)
        assert docs == []

    def test_document_has_source(self, tmp_path):
        f = tmp_path / "src.txt"
        f.write_text("content here", encoding="utf-8")
        indexer = KnowledgeIndexer()
        docs = indexer.index_file(f)
        assert docs[0].source == str(f)

    def test_document_content_non_empty(self, tmp_path):
        f = tmp_path / "content.txt"
        f.write_text("non empty content", encoding="utf-8")
        indexer = KnowledgeIndexer()
        docs = indexer.index_file(f)
        assert all(d.content.strip() for d in docs)


# ---------------------------------------------------------------------------
# KnowledgeIndexer._chunk_text
# ---------------------------------------------------------------------------

class TestChunkText:
    def test_short_text_single_chunk(self):
        indexer = KnowledgeIndexer(chunk_size=1000)
        docs = indexer._chunk_text("short text", "test_source")
        assert len(docs) == 1

    def test_long_text_multiple_chunks(self):
        long_text = "paragraph.\n\n" * 200
        indexer = KnowledgeIndexer(chunk_size=100, chunk_overlap=20)
        docs = indexer._chunk_text(long_text, "source")
        assert len(docs) > 1

    def test_markdown_sections_split(self):
        md = "# Section 1\ncontent one\n\n# Section 2\ncontent two\n\n# Section 3\ncontent three"
        indexer = KnowledgeIndexer(chunk_size=1000)
        docs = indexer._chunk_text(md, "source")
        assert len(docs) >= 2


# ---------------------------------------------------------------------------
# KnowledgeIndexer.index_directory
# ---------------------------------------------------------------------------

class TestIndexDirectory:
    def test_nonexistent_directory_returns_error(self):
        indexer = KnowledgeIndexer()
        docs, result = indexer.index_directory(Path("/nonexistent/path"))
        assert docs == []
        assert result.total_files == 0
        assert len(result.errors) > 0

    def test_empty_directory_zero_docs(self, tmp_path):
        indexer = KnowledgeIndexer()
        docs, result = indexer.index_directory(tmp_path)
        assert docs == []
        assert result.total_files == 0

    def test_directory_with_files(self, tmp_path):
        (tmp_path / "a.txt").write_text("content a", encoding="utf-8")
        (tmp_path / "b.txt").write_text("content b", encoding="utf-8")
        indexer = KnowledgeIndexer()
        docs, result = indexer.index_directory(tmp_path)
        assert result.total_files == 2
        assert result.indexed_files == 2
        assert len(docs) >= 2

    def test_directory_skips_unsupported(self, tmp_path):
        (tmp_path / "good.txt").write_text("keep this", encoding="utf-8")
        (tmp_path / "bad.bin").write_bytes(b"\x00\x01")
        indexer = KnowledgeIndexer()
        docs, result = indexer.index_directory(tmp_path)
        assert result.indexed_files == 1

    def test_corrupt_json_recorded_in_errors(self, tmp_path):
        (tmp_path / "corrupt.json").write_text("{invalid}", encoding="utf-8")
        indexer = KnowledgeIndexer()
        docs, result = indexer.index_directory(tmp_path)
        assert len(result.errors) > 0


class TestResolveKnowledgeScanPaths:
    def test_resolves_sources_and_sessions_from_base(self, tmp_path):
        base = tmp_path / "knowledge"
        (base / "sources").mkdir(parents=True)
        (base / "sessions").mkdir(parents=True)
        (base / "retrospective_export").mkdir(parents=True)

        roots = resolve_knowledge_scan_paths(base)
        assert base / "sources" in roots
        assert base / "sessions" in roots
        assert base / "retrospective_export" in roots

    def test_resolves_sibling_sessions_from_sources_dir(self, tmp_path):
        sources = tmp_path / "knowledge" / "sources"
        sessions = tmp_path / "knowledge" / "sessions"
        retro_export = tmp_path / "knowledge" / "retrospective_export"
        sources.mkdir(parents=True)
        sessions.mkdir(parents=True)
        retro_export.mkdir(parents=True)

        roots = resolve_knowledge_scan_paths(sources)
        assert sources in roots
        assert sessions in roots
        assert retro_export in roots


# ---------------------------------------------------------------------------
# KnowledgeIndexer.create_knowledge_structure
# ---------------------------------------------------------------------------

class TestCreateKnowledgeStructure:
    def test_creates_expected_directories(self, tmp_path):
        indexer = KnowledgeIndexer()
        base = tmp_path / "knowledge"
        indexer.create_knowledge_structure(base)
        assert (base / "cves").is_dir()
        assert (base / "wordlists").is_dir()
        assert (base / "exploits").is_dir()
        assert (base / "methodologies").is_dir()
        assert (base / "custom").is_dir()

    def test_creates_readme(self, tmp_path):
        indexer = KnowledgeIndexer()
        base = tmp_path / "knowledge"
        indexer.create_knowledge_structure(base)
        assert (base / "methodologies" / "README.md").exists()

    def test_creates_wordlist(self, tmp_path):
        indexer = KnowledgeIndexer()
        base = tmp_path / "knowledge"
        indexer.create_knowledge_structure(base)
        wordlist = (base / "wordlists" / "common.txt").read_text()
        assert "admin" in wordlist
