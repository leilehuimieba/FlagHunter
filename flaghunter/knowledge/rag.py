"""RAG (Retrieval Augmented Generation) engine for FlagHunter."""

import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np

from ..workspaces.utils import resolve_knowledge_paths
from .embeddings import get_embeddings

try:
    from rank_bm25 import BM25Okapi
except ImportError:  # pragma: no cover - exercised by base installs without [rag]
    BM25Okapi = None


@dataclass
class Document:
    """A chunk of knowledge."""

    content: str
    source: str
    metadata: Optional[Dict[str, Any]] = None
    embedding: Optional[np.ndarray] = None
    doc_id: Optional[str] = None

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}
        if self.doc_id is None:
            self.doc_id = f"{hash(self.content)}_{hash(self.source)}"


class RAGEngine:
    """Vector search over security knowledge."""

    def __init__(
        self,
        knowledge_path: Path = Path("knowledge"),
        embedding_model: str = "text-embedding-3-small",
        use_local_embeddings: bool = False,
    ):
        """
        Initialize the RAG engine.

        Args:
            knowledge_path: Path to the knowledge directory
            embedding_model: Model to use for embeddings
            use_local_embeddings: Whether to use local embeddings (sentence-transformers)
        """
        self.knowledge_path = knowledge_path
        self.embedding_model = embedding_model
        self.use_local_embeddings = use_local_embeddings
        self.documents: List[Document] = []
        self.embeddings: Optional[np.ndarray] = None
        self._bm25 = None
        self._bm25_tokens: List[List[str]] = []
        self._indexed = False
        self._source_files: set = set()  # Track unique source files

    def index(self, force: bool = False):
        """
        Index all documents in knowledge directory.

        Args:
            force: Force re-indexing even if already indexed
        """
        if self._indexed and not force:
            return

        chunks = []
        self._source_files = set()  # Reset source file tracking

        # Resolve knowledge paths (prefer workspace if available)
        if self.knowledge_path != Path("knowledge"):
            knowledge_root = self.knowledge_path
            kp = None
        else:
            kp = resolve_knowledge_paths()
            knowledge_root = kp.get("base", Path("knowledge"))

        # If workspace has a persisted index and we're not forcing reindex, try to load it
        try:
            if kp and kp.get("using_workspace"):
                emb_dir = kp.get("embeddings")
                emb_dir.mkdir(parents=True, exist_ok=True)
                idx_path = emb_dir / "index.json"
                if idx_path.exists() and not force:
                    try:
                        self.load_index(idx_path)
                        return
                    except Exception as e:
                        logging.getLogger(__name__).exception(
                            "Failed to load persisted RAG index at %s, will re-index: %s",
                            idx_path,
                            e,
                        )
                        try:
                            from ..interface.notifier import notify

                            notify(
                                "warning",
                                f"Failed to load persisted RAG index at {idx_path}: {e}",
                            )
                        except Exception as ne:
                            logging.getLogger(__name__).exception(
                                "Failed to notify operator about RAG load failure: %s",
                                ne,
                            )
        except Exception as e:
            # Non-fatal — continue to index from sources, but log the error
            logging.getLogger(__name__).exception(
                "Error while checking for persisted workspace index: %s", e
            )

        # Process all files in knowledge directory
        from .indexer import resolve_knowledge_scan_paths

        for scan_root in resolve_knowledge_scan_paths(knowledge_root):
            for file in scan_root.rglob("*"):
                if not file.is_file():
                    continue

                try:
                    if file.suffix in [".txt", ".md"]:
                        self._source_files.add(str(file))
                        content = file.read_text(encoding="utf-8", errors="ignore")
                        file_chunks = self._chunk_text(content, source=str(file))
                        chunks.extend(file_chunks)

                    elif file.suffix == ".json":
                        self._source_files.add(str(file))
                        data = json.loads(file.read_text(encoding="utf-8"))
                        if isinstance(data, list):
                            for item in data:
                                chunks.append(
                                    Document(
                                        content=json.dumps(item, indent=2),
                                        source=str(file),
                                        metadata=(
                                            item
                                            if isinstance(item, dict)
                                            else {"data": item}
                                        ),
                                    )
                                )
                        else:
                            chunks.append(
                                Document(
                                    content=json.dumps(data, indent=2),
                                    source=str(file),
                                    metadata=(
                                        data
                                        if isinstance(data, dict)
                                        else {"data": data}
                                    ),
                                )
                            )
                except Exception as e:
                    logging.getLogger(__name__).exception(
                        "[RAG] Error processing %s: %s", file, e
                    )

        self.documents = chunks
        self._rebuild_bm25_index()

        # Generate embeddings
        if chunks:
            texts = [doc.content for doc in chunks]

            if self.use_local_embeddings:
                from .embeddings import get_embeddings_local

                self.embeddings = get_embeddings_local(texts)
            else:
                self.embeddings = get_embeddings(texts, model=self.embedding_model)

            # Store embeddings in documents
            for i, doc in enumerate(self.documents):
                doc.embedding = self.embeddings[i]

        self._indexed = True
        # If using a workspace, persist the built index for faster future loads
        try:
            if kp and kp.get("using_workspace") and self.embeddings is not None:
                emb_dir = kp.get("embeddings")
                emb_dir.mkdir(parents=True, exist_ok=True)
                idx_path = emb_dir / "index.json"
                try:
                    self.save_index(idx_path)
                except Exception as e:
                    logging.getLogger(__name__).exception(
                        "Failed to save RAG index to %s: %s", idx_path, e
                    )
                    try:
                        from ..interface.notifier import notify

                        notify(
                            "warning", f"Failed to save RAG index to {idx_path}: {e}"
                        )
                    except Exception as ne:
                        logging.getLogger(__name__).exception(
                            "Failed to notify operator about RAG save failure: %s", ne
                        )
        except Exception as e:
            logging.getLogger(__name__).exception(
                "Error while attempting to persist RAG index: %s", e
            )
            try:
                from ..interface.notifier import notify

                notify("warning", f"Error while attempting to persist RAG index: {e}")
            except Exception as ne:
                logging.getLogger(__name__).exception(
                    "Failed to notify operator about RAG persist error: %s", ne
                )

    def _chunk_text(
        self, text: str, source: str, chunk_size: int = 1000, overlap: int = 200
    ) -> List[Document]:
        """
        Split text into overlapping chunks.

        Args:
            text: The text to split
            source: The source file path
            chunk_size: Maximum chunk size in characters
            overlap: Overlap between chunks

        Returns:
            List of Document objects
        """
        chunks = []

        # Split by paragraphs first for better context
        paragraphs = text.split("\n\n")
        current_chunk = ""

        for para in paragraphs:
            if len(current_chunk) + len(para) + 2 <= chunk_size:
                current_chunk += para + "\n\n"
            else:
                if current_chunk.strip():
                    chunks.append(
                        Document(content=current_chunk.strip(), source=source)
                    )
                current_chunk = para + "\n\n"

        # Add the last chunk
        if current_chunk.strip():
            chunks.append(Document(content=current_chunk.strip(), source=source))

        # If no paragraphs were found, fall back to simple chunking
        if not chunks and text.strip():
            start = 0
            while start < len(text):
                end = start + chunk_size
                chunk = text[start:end]

                if chunk.strip():
                    chunks.append(Document(content=chunk.strip(), source=source))

                start = end - overlap

        return chunks

    def _tokenize_for_bm25(self, text: str) -> List[str]:
        """Tokenize text for exact-token lexical retrieval."""
        return re.findall(r"[a-z0-9][a-z0-9_./:-]*", text.lower())

    def _rebuild_bm25_index(self):
        """Build or refresh the optional BM25 index from current documents."""
        self._bm25 = None
        self._bm25_tokens = []

        if BM25Okapi is None or not self.documents:
            return

        tokenized_corpus = [
            self._tokenize_for_bm25(doc.content) for doc in self.documents
        ]
        if not any(tokenized_corpus):
            return

        try:
            self._bm25 = BM25Okapi(tokenized_corpus)
            self._bm25_tokens = tokenized_corpus
        except Exception as e:
            logging.getLogger(__name__).exception(
                "Failed to build BM25 RAG index; falling back to vector search: %s",
                e,
            )
            self._bm25 = None
            self._bm25_tokens = []

    def _get_query_embedding(self, query: str) -> np.ndarray:
        """Generate an embedding for a single query."""
        if self.use_local_embeddings:
            from .embeddings import get_embeddings_local

            return get_embeddings_local([query])[0]
        return get_embeddings([query], model=self.embedding_model)[0]

    def _cosine_similarities(self, query_embedding: np.ndarray) -> np.ndarray:
        """Compute cosine similarity between all document embeddings and a query."""
        return np.dot(self.embeddings, query_embedding) / (
            np.linalg.norm(self.embeddings, axis=1) * np.linalg.norm(query_embedding)
            + 1e-10
        )

    def _rank_indices_with_rrf(
        self, query: str, similarities: np.ndarray, k: int, threshold: float
    ) -> List[int]:
        """Fuse vector and BM25 rankings using reciprocal rank fusion."""
        indices_above_threshold = np.where(similarities >= threshold)[0]

        if len(indices_above_threshold) == 0:
            return []

        depth = min(len(self.documents), max(k, 20))
        sorted_vector_indices = indices_above_threshold[
            np.argsort(similarities[indices_above_threshold])[::-1]
        ]
        vector_ranked = [int(idx) for idx in sorted_vector_indices[:depth]]

        rankings = [vector_ranked]

        if self._bm25 is not None:
            query_tokens = self._tokenize_for_bm25(query)
            if query_tokens:
                bm25_scores = np.asarray(self._bm25.get_scores(query_tokens))
                positive_bm25_indices = np.where(bm25_scores > 0)[0]
                bm25_candidates = [
                    int(idx)
                    for idx in positive_bm25_indices
                    if similarities[idx] >= threshold
                ]
                bm25_ranked = sorted(
                    bm25_candidates,
                    key=lambda idx: (bm25_scores[idx], similarities[idx]),
                    reverse=True,
                )[:depth]
                if bm25_ranked:
                    rankings.append(bm25_ranked)

        rrf_k = 60
        fused_scores: Dict[int, float] = {}
        for ranking in rankings:
            for rank, idx in enumerate(ranking, start=1):
                fused_scores[idx] = fused_scores.get(idx, 0.0) + 1.0 / (
                    rrf_k + rank
                )

        return sorted(
            fused_scores,
            key=lambda idx: (fused_scores[idx], similarities[idx]),
            reverse=True,
        )[:k]

    def search(
        self, query: str, k: int = 5, threshold: float = 0.35, max_tokens: int = 1500
    ) -> List[str]:
        """
        Find relevant documents for a query.

        Args:
            query: The search query
            k: Maximum number of results to return
            threshold: Minimum similarity threshold
            max_tokens: Maximum total tokens to return (prevents context bloat)

        Returns:
            List of relevant document contents
        """
        # Guard against empty/invalid queries
        if not query or not isinstance(query, str) or not query.strip():
            return []

        if not self._indexed:
            self.index()

        if not self.documents or self.embeddings is None:
            return []

        query_embedding = self._get_query_embedding(query)
        similarities = self._cosine_similarities(query_embedding)
        top_indices = self._rank_indices_with_rrf(query, similarities, k, threshold)
        if not top_indices:
            return []

        # Collect results up to max_tokens budget
        results = []
        total_tokens = 0
        for idx in top_indices:
            content = self.documents[idx].content
            # Rough token estimate: ~4 chars per token
            chunk_tokens = len(content) // 4
            if total_tokens + chunk_tokens > max_tokens and results:
                # Stop if we'd exceed budget (but always include at least one)
                break
            results.append(content)
            total_tokens += chunk_tokens

        return results

    def search_with_scores(
        self, query: str, k: int = 5, threshold: float = 0.35
    ) -> List[tuple[Document, float]]:
        """
        Search with similarity scores.

        Args:
            query: The search query
            k: Maximum number of results to return
            threshold: Minimum similarity threshold

        Returns:
            List of (Document, score) tuples above threshold
        """
        if not self._indexed:
            self.index()

        if not self.documents or self.embeddings is None:
            return []

        query_embedding = self._get_query_embedding(query)
        similarities = self._cosine_similarities(query_embedding)
        top_indices = self._rank_indices_with_rrf(query, similarities, k, threshold)
        if not top_indices:
            return []

        return [(self.documents[i], float(similarities[i])) for i in top_indices]

    def add_document(
        self, content: str, source: str = "user", metadata: Optional[dict] = None
    ):
        """
        Add a document to the knowledge base.

        Args:
            content: The document content
            source: The source identifier
            metadata: Optional metadata
        """
        doc = Document(content=content, source=source, metadata=metadata)

        # Generate embedding
        if self.use_local_embeddings:
            from .embeddings import get_embeddings_local

            new_embedding = get_embeddings_local([content])
        else:
            new_embedding = get_embeddings([content], model=self.embedding_model)

        doc.embedding = new_embedding[0]
        self.documents.append(doc)

        # Update embeddings array
        if self.embeddings is not None:
            self.embeddings = np.vstack([self.embeddings, new_embedding])
        else:
            self.embeddings = new_embedding
        self._rebuild_bm25_index()

    def add_documents(self, documents: List[Document]):
        """
        Add multiple documents to the knowledge base.

        Args:
            documents: List of Document objects to add
        """
        if not documents:
            return

        texts = [doc.content for doc in documents]

        if self.use_local_embeddings:
            from .embeddings import get_embeddings_local

            new_embeddings = get_embeddings_local(texts)
        else:
            new_embeddings = get_embeddings(texts, model=self.embedding_model)

        for i, doc in enumerate(documents):
            doc.embedding = new_embeddings[i]
            self.documents.append(doc)

        if self.embeddings is not None:
            self.embeddings = np.vstack([self.embeddings, new_embeddings])
        else:
            self.embeddings = new_embeddings
        self._rebuild_bm25_index()

    def remove_document(self, doc_id: str) -> bool:
        """
        Remove a document by ID.

        Args:
            doc_id: The document ID to remove

        Returns:
            True if removed, False if not found
        """
        for i, doc in enumerate(self.documents):
            if doc.doc_id == doc_id:
                self.documents.pop(i)
                if self.embeddings is not None:
                    self.embeddings = np.delete(self.embeddings, i, axis=0)
                self._rebuild_bm25_index()
                return True
        return False

    def clear(self):
        """Clear all documents and embeddings."""
        self.documents.clear()
        self.embeddings = None
        self._bm25 = None
        self._bm25_tokens = []
        self._indexed = False
        self._source_files = set()

    def get_document_count(self) -> int:
        """Get the number of source files indexed."""
        return len(self._source_files)

    def get_chunk_count(self) -> int:
        """Get the number of indexed chunks (internal document segments)."""
        return len(self.documents)

    def save_index(self, path: Path):
        """
        Save the index to disk as JSON (documents) + base64-encoded embeddings.

        Uses JSON instead of pickle to eliminate the arbitrary-code-execution
        vector from untrusted index deserialization — a workspace index file is
        attacker-writable, and ``pickle.load`` on it is a classic RCE sink.
        See tests/security/test_pickle_deserialization.py.

        Args:
            path: Path to save the index
        """
        import base64

        embeddings_payload = None
        if self.embeddings is not None:
            arr = np.ascontiguousarray(self.embeddings)
            embeddings_payload = {
                "dtype": str(arr.dtype),
                "shape": list(arr.shape),
                "b64": base64.b64encode(arr.tobytes()).decode("ascii"),
            }

        data = {
            "version": 2,
            "documents": [
                {
                    "content": doc.content,
                    "source": doc.source,
                    "metadata": doc.metadata,
                    "doc_id": doc.doc_id,
                }
                for doc in self.documents
            ],
            "embeddings": embeddings_payload,
        }

        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, default=str)

    def save_index_to_workspace(
        self, root: Optional[Path] = None, filename: str = "index.json"
    ):
        """
        Convenience helper to save the index into the active workspace embeddings path.

        Args:
            root: Optional project root to resolve workspaces (defaults to cwd)
            filename: Filename to use for the saved index
        """
        from pathlib import Path as _P

        kp = resolve_knowledge_paths(root=root)
        emb_dir = kp.get("embeddings")
        emb_dir.mkdir(parents=True, exist_ok=True)
        path = _P(emb_dir) / filename
        self.save_index(path)

    def load_index(self, path: Path):
        """
        Load the index from a JSON file written by :meth:`save_index`.

        JSON-only — this method never unpickles. Pre-v2 pickle index files
        (``index.pkl``) are not read at all (the loader looks for
        ``index.json``); a stale pickle is simply ignored and the index is
        rebuilt from sources, removing the pickle RCE vector entirely.

        Args:
            path: Path to load the index from
        """
        import base64

        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        self.documents = [
            Document(
                content=d["content"],
                source=d["source"],
                metadata=d["metadata"],
                doc_id=d["doc_id"],
            )
            for d in data["documents"]
        ]

        emb = data.get("embeddings")
        if emb is not None:
            # np.frombuffer/np.dtype/reshape never execute embedded code, so a
            # tampered file can at worst raise (not run code). Copy to get a
            # writable array matching the previous pickle behaviour.
            self.embeddings = (
                np.frombuffer(
                    base64.b64decode(emb["b64"]), dtype=np.dtype(emb["dtype"])
                )
                .reshape(emb["shape"])
                .copy()
            )
        else:
            self.embeddings = None

        # Restore embeddings in documents
        if self.embeddings is not None:
            for i, doc in enumerate(self.documents):
                doc.embedding = self.embeddings[i]

        self._rebuild_bm25_index()
        self._indexed = True

    def load_index_from_workspace(
        self, root: Optional[Path] = None, filename: str = "index.json"
    ):
        """
        Convenience helper to load the index from the active workspace embeddings path.

        Args:
            root: Optional project root to resolve workspaces (defaults to cwd)
            filename: Filename used for the saved index
        """
        from pathlib import Path as _P

        kp = resolve_knowledge_paths(root=root)
        emb_dir = kp.get("embeddings")
        path = _P(emb_dir) / filename
        if not path.exists():
            raise FileNotFoundError(f"Workspace index not found: {path}")
        self.load_index(path)
