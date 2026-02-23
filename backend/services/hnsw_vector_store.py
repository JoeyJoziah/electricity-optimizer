"""
HNSW Vector Store

Wraps the existing VectorStore with an HNSW index for O(log n) approximate
nearest-neighbor search. SQLite remains the durable store; the HNSW index
is an in-memory acceleration layer rebuilt from SQLite on startup.

Falls back to brute-force VectorStore.search() if hnswlib is not installed.
"""

import json
import logging
import sqlite3
from typing import Optional, List, Dict, Any

import numpy as np

from services.vector_store import VectorStore

logger = logging.getLogger(__name__)

try:
    import hnswlib
    HNSW_AVAILABLE = True
except ImportError:
    HNSW_AVAILABLE = False
    logger.info("hnswlib not installed, falling back to brute-force search")


class HNSWVectorStore:
    """
    HNSW-accelerated wrapper around VectorStore.

    Provides the same insert/search/record_outcome API but uses an HNSW
    index for fast approximate nearest-neighbor queries.

    Args:
        db_path: SQLite database path (passed to VectorStore).
        dimension: Vector dimension (default 24 for hourly price curves).
        max_elements: Maximum vectors in the HNSW index.
        ef_search: HNSW search beam width (higher = more accurate, slower).
        M: HNSW graph connectivity parameter.
    """

    def __init__(
        self,
        db_path: str = ".agentdb/electricity.db",
        dimension: int = 24,
        max_elements: int = 10000,
        ef_search: int = 50,
        M: int = 16,
    ):
        self._store = VectorStore(db_path=db_path, dimension=dimension)
        self._dimension = dimension
        self._max_elements = max_elements
        self._ef_search = ef_search
        self._M = M

        # HNSW index (in-memory)
        self._index: Optional[Any] = None
        # Maps HNSW integer label -> vector string ID
        self._label_to_id: Dict[int, str] = {}
        # Maps vector string ID -> HNSW integer label
        self._id_to_label: Dict[str, int] = {}
        self._next_label: int = 0

        if HNSW_AVAILABLE:
            self._build_index()

    def _build_index(self) -> None:
        """Rebuild HNSW index from SQLite store."""
        try:
            self._index = hnswlib.Index(space="cosine", dim=self._dimension)
            self._index.init_index(
                max_elements=self._max_elements,
                ef_construction=200,
                M=self._M,
            )
            self._index.set_ef(self._ef_search)

            # Load all vectors from SQLite
            with sqlite3.connect(self._store._db_path) as conn:
                rows = conn.execute(
                    "SELECT id, vector FROM vectors"
                ).fetchall()

            if rows:
                ids = []
                vectors = []
                for vec_id, vec_bytes in rows:
                    vec = self._store._bytes_to_vector(vec_bytes)
                    if vec.shape[0] == self._dimension:
                        label = self._next_label
                        self._next_label += 1
                        self._label_to_id[label] = vec_id
                        self._id_to_label[vec_id] = label
                        ids.append(label)
                        vectors.append(vec)

                if vectors:
                    data = np.stack(vectors)
                    self._index.add_items(data, ids)

            logger.info(
                "hnsw_index_built",
                vectors=len(self._label_to_id),
                dimension=self._dimension,
            )
        except Exception as e:
            logger.warning("hnsw_index_build_failed", error=str(e))
            self._index = None

    def insert(
        self,
        domain: str,
        vector: np.ndarray,
        metadata: Optional[Dict[str, Any]] = None,
        confidence: float = 1.0,
        vector_id: Optional[str] = None,
    ) -> str:
        """
        Insert a vector into both SQLite and HNSW index.

        Args:
            domain: Category (e.g. 'recommendation', 'bias_correction').
            vector: Numpy array.
            metadata: JSON-serializable metadata.
            confidence: Quality score 0-1.
            vector_id: Optional explicit ID.

        Returns:
            The vector ID.
        """
        vec_id = self._store.insert(
            domain=domain,
            vector=vector,
            metadata=metadata,
            confidence=confidence,
            vector_id=vector_id,
        )

        # Add to HNSW index
        if self._index is not None:
            try:
                # Normalize vector dimension
                v = vector.copy()
                if v.shape[0] < self._dimension:
                    v = np.pad(v, (0, self._dimension - v.shape[0]))
                elif v.shape[0] > self._dimension:
                    v = v[:self._dimension]

                # Resize index if needed
                if self._next_label >= self._index.get_max_elements():
                    self._index.resize_index(
                        self._index.get_max_elements() + 1000
                    )

                label = self._next_label
                self._next_label += 1
                self._label_to_id[label] = vec_id
                self._id_to_label[vec_id] = label
                self._index.add_items(v.reshape(1, -1), [label])
            except Exception as e:
                logger.warning("hnsw_insert_failed", error=str(e))

        return vec_id

    def search(
        self,
        query_vector: np.ndarray,
        domain: Optional[str] = None,
        k: int = 5,
        min_similarity: float = 0.7,
    ) -> List[Dict[str, Any]]:
        """
        Search for similar vectors using HNSW (or brute-force fallback).

        Args:
            query_vector: Query vector.
            domain: Optional domain filter.
            k: Number of results.
            min_similarity: Minimum cosine similarity threshold.

        Returns:
            List of matches sorted by similarity desc.
        """
        # Fall back to brute-force if HNSW unavailable
        if self._index is None or self._index.get_current_count() == 0:
            return self._store.search(
                query_vector=query_vector,
                domain=domain,
                k=k,
                min_similarity=min_similarity,
            )

        # Normalize query vector
        q = query_vector.copy().astype(np.float32)
        if q.shape[0] < self._dimension:
            q = np.pad(q, (0, self._dimension - q.shape[0]))
        elif q.shape[0] > self._dimension:
            q = q[:self._dimension]

        try:
            # HNSW search (fetch more than k to allow domain filtering)
            fetch_k = min(k * 3, self._index.get_current_count())
            labels, distances = self._index.knn_query(q.reshape(1, -1), k=fetch_k)

            # Convert cosine distances to similarities
            # hnswlib cosine distance = 1 - cosine_similarity
            results = []
            for label, dist in zip(labels[0], distances[0]):
                vec_id = self._label_to_id.get(int(label))
                if not vec_id:
                    continue

                similarity = 1.0 - float(dist)
                if similarity < min_similarity:
                    continue

                # Get metadata from SQLite
                with sqlite3.connect(self._store._db_path) as conn:
                    row = conn.execute(
                        "SELECT domain, metadata, confidence FROM vectors WHERE id = ?",
                        (vec_id,),
                    ).fetchone()

                if not row:
                    continue

                vec_domain, meta_json, confidence = row

                # Apply domain filter
                if domain and vec_domain != domain:
                    continue

                results.append({
                    "id": vec_id,
                    "domain": vec_domain,
                    "similarity": round(similarity, 4),
                    "confidence": confidence,
                    "metadata": json.loads(meta_json),
                })

                if len(results) >= k:
                    break

            # Update usage counts
            if results:
                from datetime import datetime, timezone
                now = datetime.now(timezone.utc).isoformat()
                with sqlite3.connect(self._store._db_path) as conn:
                    for r in results:
                        conn.execute(
                            "UPDATE vectors SET usage_count = usage_count + 1, last_used = ? WHERE id = ?",
                            (now, r["id"]),
                        )
                    conn.commit()

            return results

        except Exception as e:
            logger.warning("hnsw_search_failed", error=str(e))
            return self._store.search(
                query_vector=query_vector,
                domain=domain,
                k=k,
                min_similarity=min_similarity,
            )

    def record_outcome(self, vector_id: str, success: bool) -> None:
        """Delegate to underlying VectorStore."""
        self._store.record_outcome(vector_id, success)

    def get_stats(self, domain: Optional[str] = None) -> Dict[str, Any]:
        """Get stats including HNSW index info."""
        stats = self._store.get_stats(domain)
        stats["hnsw_available"] = HNSW_AVAILABLE
        if self._index is not None:
            stats["hnsw_count"] = self._index.get_current_count()
            stats["hnsw_max_elements"] = self._index.get_max_elements()
        return stats

    def prune(self, min_confidence: float = 0.3, min_usage: int = 0) -> int:
        """Prune vectors and rebuild HNSW index."""
        count = self._store.prune(min_confidence, min_usage)
        if count > 0 and HNSW_AVAILABLE:
            # Rebuild index after pruning
            self._label_to_id.clear()
            self._id_to_label.clear()
            self._next_label = 0
            self._build_index()
        return count


_vector_store_singleton: Optional["HNSWVectorStore"] = None


def get_vector_store_singleton() -> "HNSWVectorStore":
    """Return a module-level singleton to avoid rebuilding the HNSW index per request."""
    global _vector_store_singleton
    if _vector_store_singleton is None:
        _vector_store_singleton = HNSWVectorStore()
    return _vector_store_singleton
