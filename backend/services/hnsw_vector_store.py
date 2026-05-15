"""
HNSW Vector Store

Wraps the existing VectorStore with an HNSW index for O(log n) approximate
nearest-neighbor search. SQLite remains the durable store; the HNSW index
is an in-memory acceleration layer rebuilt from SQLite on startup.

Falls back to brute-force VectorStore.search() if hnswlib is not installed.
"""

import asyncio
import json
import sqlite3
import time
from datetime import UTC
from typing import Any, Optional

import numpy as np
import structlog

from services.vector_store import VectorStore

logger = structlog.get_logger(__name__)

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
        ef_search: int = 32,
        M: int = 12,
    ):
        # Defaults tuned as starting points for 24-dim cosine, k<=10, corpus <100k.
        # M=12: lower graph connectivity than the M=16 default (which targets
        #   ~1536-dim OpenAI embeddings). At 24 dims, M=12 yields the same recall
        #   with ~25% less graph memory.
        # ef_search=32: tighter beam than the 50 default; for k<=10 queries the
        #   extra recall headroom above 32 is mostly wasted, and p99 latency
        #   drops proportionally. Bump back up if recall_check() shows <0.95.
        # Retune once corpus is real: run recall_check() at N=1k, 10k, 50k and
        # adjust M / ef_search to hold recall@10 >= 0.95 with the lowest viable ef.
        self._store = VectorStore(db_path=db_path, dimension=dimension)
        self._dimension = dimension
        self._max_elements = max_elements
        # Hard cap to prevent unbounded memory growth (each vector ~100B + graph overhead)
        self._max_elements_cap = 100_000
        self._ef_search = ef_search
        self._M = M

        # HNSW index (in-memory)
        self._index: Any | None = None
        # Maps HNSW integer label -> vector string ID
        self._label_to_id: dict[int, str] = {}
        # Maps vector string ID -> HNSW integer label
        self._id_to_label: dict[str, int] = {}
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
                rows = conn.execute("SELECT id, vector FROM vectors").fetchall()

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
        metadata: dict[str, Any] | None = None,
        confidence: float = 1.0,
        vector_id: str | None = None,
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
                    v = v[: self._dimension]

                # Resize index if needed (geometric doubling amortizes O(1) per insert)
                if self._next_label >= self._index.get_max_elements():
                    new_size = self._index.get_max_elements() * 2
                    if new_size > self._max_elements_cap:
                        logger.warning("hnsw_index_at_cap", max=self._max_elements_cap)
                        return vec_id  # Skip HNSW, still in SQLite
                    self._index.resize_index(new_size)

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
        domain: str | None = None,
        k: int = 5,
        min_similarity: float = 0.7,
    ) -> list[dict[str, Any]]:
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
            q = q[: self._dimension]

        try:
            # HNSW search (fetch more than k to allow domain filtering)
            fetch_k = min(k * 3, self._index.get_current_count())
            t0 = time.perf_counter()
            labels, distances = self._index.knn_query(q.reshape(1, -1), k=fetch_k)
            query_latency_ms = (time.perf_counter() - t0) * 1000.0
            logger.debug(
                "hnsw_query",
                latency_ms=round(query_latency_ms, 3),
                fetch_k=fetch_k,
                ef_search=getattr(self, "_ef_search", None),
                index_count=self._index.get_current_count(),
            )

            # Collect candidates from HNSW results
            candidate_ids = []
            candidate_similarities = []
            for label, dist in zip(labels[0], distances[0]):
                vec_id = self._label_to_id.get(int(label))
                if not vec_id:
                    continue
                similarity = 1.0 - float(dist)
                if similarity < min_similarity:
                    continue
                candidate_ids.append(vec_id)
                candidate_similarities.append(similarity)

            if not candidate_ids:
                return []

            # Batch metadata lookup (single connection instead of per-result)
            with sqlite3.connect(self._store._db_path) as conn:
                placeholders = ",".join("?" for _ in candidate_ids)
                rows = conn.execute(
                    f"SELECT id, domain, metadata, confidence FROM vectors WHERE id IN ({placeholders})",
                    candidate_ids,
                ).fetchall()

            metadata_map = {row[0]: row for row in rows}

            results = []
            for vec_id, similarity in zip(candidate_ids, candidate_similarities):
                row = metadata_map.get(vec_id)
                if not row:
                    continue
                _, vec_domain, meta_json, confidence = row
                if domain and vec_domain != domain:
                    continue
                results.append(
                    {
                        "id": vec_id,
                        "domain": vec_domain,
                        "similarity": round(similarity, 4),
                        "confidence": confidence,
                        "metadata": json.loads(meta_json),
                    }
                )
                if len(results) >= k:
                    break

            # Batch usage count update — single UPDATE ... WHERE id IN (...)
            # instead of per-row statements (19-P1-4 / P2 performance fix).
            if results:
                from datetime import datetime

                now = datetime.now(UTC).isoformat()
                result_ids = [r["id"] for r in results]
                placeholders = ",".join("?" for _ in result_ids)
                with sqlite3.connect(self._store._db_path) as conn:
                    conn.execute(
                        f"UPDATE vectors SET usage_count = usage_count + 1, last_used = ? WHERE id IN ({placeholders})",
                        [now, *result_ids],
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

    def get_stats(self, domain: str | None = None) -> dict[str, Any]:
        """Get stats including HNSW index info."""
        stats = self._store.get_stats(domain)
        stats["hnsw_available"] = HNSW_AVAILABLE
        if self._index is not None:
            count = self._index.get_current_count()
            stats["hnsw_count"] = count
            stats["hnsw_max_elements"] = self._index.get_max_elements()
            stats["hnsw_ef_search"] = self._ef_search
            stats["hnsw_M"] = self._M
            # Rough memory estimate: vector storage (float32) + graph links.
            # Per hnswlib docs, graph overhead ~= M * 2 * (level0_links_size + ...)
            # ~= M * 8 bytes/link * 2 (in/out) per node. We approximate as
            # vector_bytes + 4 * M * count for the link layer.
            vector_bytes = count * self._dimension * 4
            graph_bytes = count * self._M * 8 * 2
            stats["hnsw_memory_estimate_bytes"] = vector_bytes + graph_bytes
        return stats

    def recall_check(self, sample_size: int = 100, k: int = 10) -> dict[str, Any]:
        """
        Measure recall@k by sampling stored vectors and comparing HNSW top-k
        against brute-force cosine top-k on the same population.

        Returns dict with recall, sample_size, k, and per-query latency stats.
        Use this to validate parameter changes (M, ef_search) hold recall >= 0.95.
        """
        if self._index is None:
            return {"error": "hnsw_unavailable", "recall": None}

        count = self._index.get_current_count()
        if count == 0:
            return {"error": "empty_index", "recall": None, "sample_size": 0}

        with sqlite3.connect(self._store._db_path) as conn:
            rows = conn.execute(
                "SELECT id, vector FROM vectors ORDER BY RANDOM() LIMIT ?",
                (min(sample_size, count),),
            ).fetchall()

        # Load full corpus once for brute-force comparison
        with sqlite3.connect(self._store._db_path) as conn:
            all_rows = conn.execute("SELECT id, vector FROM vectors").fetchall()

        corpus_ids = [r[0] for r in all_rows]
        corpus_vecs = np.stack([self._store._bytes_to_vector(r[1]) for r in all_rows]).astype(
            np.float32
        )
        # Pre-normalize for cosine
        norms = np.linalg.norm(corpus_vecs, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        corpus_norm = corpus_vecs / norms

        hits = 0
        total = 0
        latencies: list[float] = []

        for _, vec_bytes in rows:
            q = self._store._bytes_to_vector(vec_bytes).astype(np.float32)
            qn = q / max(float(np.linalg.norm(q)), 1e-9)

            # Brute-force ground truth
            sims = corpus_norm @ qn
            top_k_idx = np.argsort(-sims)[:k]
            truth_ids = {corpus_ids[i] for i in top_k_idx}

            # HNSW result
            t0 = time.perf_counter()
            labels, _ = self._index.knn_query(q.reshape(1, -1), k=k)
            latencies.append((time.perf_counter() - t0) * 1000.0)
            hnsw_ids = {self._label_to_id.get(int(lbl)) for lbl in labels[0]}
            hnsw_ids.discard(None)

            hits += len(truth_ids & hnsw_ids)
            total += k

        latencies_sorted = sorted(latencies)
        n = len(latencies_sorted)
        return {
            "recall": round(hits / total, 4) if total else None,
            "sample_size": len(rows),
            "k": k,
            "corpus_size": count,
            "ef_search": self._ef_search,
            "M": self._M,
            "p50_latency_ms": round(latencies_sorted[n // 2], 3) if n else None,
            "p99_latency_ms": (
                round(latencies_sorted[min(n - 1, int(n * 0.99))], 3) if n else None
            ),
        }

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

    # --- Async wrappers (run sync SQLite I/O in a thread) ---

    async def async_insert(
        self,
        domain: str,
        vector: np.ndarray,
        metadata: dict[str, Any] | None = None,
        confidence: float = 1.0,
        vector_id: str | None = None,
    ) -> str:
        """Async wrapper for insert — runs SQLite I/O in a thread."""
        return await asyncio.to_thread(
            self.insert,
            domain,
            vector,
            metadata,
            confidence,
            vector_id,
        )

    async def async_search(
        self,
        query_vector: np.ndarray,
        domain: str | None = None,
        k: int = 5,
        min_similarity: float = 0.7,
    ) -> list[dict[str, Any]]:
        """Async wrapper for search — runs SQLite I/O in a thread."""
        return await asyncio.to_thread(
            self.search,
            query_vector,
            domain,
            k,
            min_similarity,
        )

    async def async_record_outcome(self, vector_id: str, success: bool) -> None:
        """Async wrapper for record_outcome."""
        await asyncio.to_thread(self.record_outcome, vector_id, success)

    async def async_get_stats(self, domain: str | None = None) -> dict[str, Any]:
        """Async wrapper for get_stats."""
        return await asyncio.to_thread(self.get_stats, domain)

    async def async_prune(self, min_confidence: float = 0.3, min_usage: int = 0) -> int:
        """Async wrapper for prune."""
        return await asyncio.to_thread(self.prune, min_confidence, min_usage)


_vector_store_singleton: Optional["HNSWVectorStore"] = None


def get_vector_store_singleton() -> "HNSWVectorStore":
    """Return a module-level singleton to avoid rebuilding the HNSW index per request."""
    global _vector_store_singleton
    if _vector_store_singleton is None:
        _vector_store_singleton = HNSWVectorStore()
    return _vector_store_singleton
