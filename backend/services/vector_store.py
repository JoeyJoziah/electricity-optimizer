"""
Vector Store Service

AgentDB-inspired vector database for price pattern matching,
optimization caching, and recommendation learning.

Uses numpy for vector operations and sqlite3 for persistence.
"""

import os
import json
import sqlite3
import hashlib
import logging
import threading
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any, Tuple
from collections import OrderedDict
from pathlib import Path

import numpy as np

logger = logging.getLogger(__name__)


class VectorStore:
    """
    Lightweight vector store for electricity price pattern matching.

    Stores vectors with metadata and supports cosine similarity search
    with an in-memory LRU cache for frequently accessed patterns.
    """

    def __init__(
        self,
        db_path: str = ".agentdb/electricity.db",
        cache_size: int = 500,
        dimension: int = 24,
    ):
        self._db_path = db_path
        self._cache_size = cache_size
        self._dimension = dimension
        self._lock = threading.Lock()
        self._cache: OrderedDict[str, Dict[str, Any]] = OrderedDict()
        self._init_db()

    def _init_db(self) -> None:
        """Initialize SQLite database with vector storage schema."""
        os.makedirs(os.path.dirname(self._db_path), exist_ok=True)
        with sqlite3.connect(self._db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS vectors (
                    id TEXT PRIMARY KEY,
                    domain TEXT NOT NULL,
                    vector BLOB NOT NULL,
                    metadata TEXT NOT NULL DEFAULT '{}',
                    confidence REAL DEFAULT 1.0,
                    usage_count INTEGER DEFAULT 0,
                    success_count INTEGER DEFAULT 0,
                    created_at TEXT NOT NULL,
                    last_used TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_vectors_domain
                ON vectors(domain)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_vectors_confidence
                ON vectors(confidence DESC)
            """)
            conn.commit()

    def _vector_to_bytes(self, vector: np.ndarray) -> bytes:
        """Serialize numpy vector to bytes."""
        return vector.astype(np.float32).tobytes()

    def _bytes_to_vector(self, data: bytes) -> np.ndarray:
        """Deserialize bytes to numpy vector."""
        return np.frombuffer(data, dtype=np.float32)

    def _cosine_similarity(self, a: np.ndarray, b: np.ndarray) -> float:
        """Compute cosine similarity between two vectors."""
        norm_a = np.linalg.norm(a)
        norm_b = np.linalg.norm(b)
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return float(np.dot(a, b) / (norm_a * norm_b))

    def _generate_id(self, domain: str, vector: np.ndarray) -> str:
        """Generate deterministic ID from domain and vector content."""
        content = f"{domain}:{vector.tobytes().hex()}"
        return hashlib.sha256(content.encode()).hexdigest()[:16]

    def _update_cache(self, key: str, value: Dict[str, Any]) -> None:
        """Update LRU cache with eviction."""
        with self._lock:
            if key in self._cache:
                self._cache.move_to_end(key)
            self._cache[key] = value
            while len(self._cache) > self._cache_size:
                self._cache.popitem(last=False)

    def insert(
        self,
        domain: str,
        vector: np.ndarray,
        metadata: Optional[Dict[str, Any]] = None,
        confidence: float = 1.0,
        vector_id: Optional[str] = None,
    ) -> str:
        """
        Insert a vector with metadata into the store.

        Args:
            domain: Category (e.g. 'price_pattern', 'optimization', 'recommendation')
            vector: Numpy array of floats
            metadata: Associated data (JSON-serializable)
            confidence: Quality score 0-1
            vector_id: Optional explicit ID

        Returns:
            The vector ID
        """
        if vector.shape[0] != self._dimension:
            # Auto-resize by padding or truncating
            if vector.shape[0] < self._dimension:
                vector = np.pad(vector, (0, self._dimension - vector.shape[0]))
            else:
                vector = vector[: self._dimension]

        vec_id = vector_id or self._generate_id(domain, vector)
        now = datetime.now(timezone.utc).isoformat()
        meta_json = json.dumps(metadata or {})

        with sqlite3.connect(self._db_path) as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO vectors
                (id, domain, vector, metadata, confidence, usage_count, success_count, created_at, last_used)
                VALUES (?, ?, ?, ?, ?, 0, 0, ?, ?)
                """,
                (vec_id, domain, self._vector_to_bytes(vector), meta_json, confidence, now, now),
            )
            conn.commit()

        self._update_cache(
            vec_id,
            {
                "id": vec_id,
                "domain": domain,
                "vector": vector,
                "metadata": metadata or {},
                "confidence": confidence,
            },
        )

        return vec_id

    def search(
        self,
        query_vector: np.ndarray,
        domain: Optional[str] = None,
        k: int = 5,
        min_similarity: float = 0.7,
    ) -> List[Dict[str, Any]]:
        """
        Find similar vectors using cosine similarity.

        Args:
            query_vector: Query vector
            domain: Optional domain filter
            k: Number of results to return
            min_similarity: Minimum similarity threshold

        Returns:
            List of matches with similarity scores, sorted by similarity desc
        """
        if query_vector.shape[0] != self._dimension:
            if query_vector.shape[0] < self._dimension:
                query_vector = np.pad(query_vector, (0, self._dimension - query_vector.shape[0]))
            else:
                query_vector = query_vector[: self._dimension]

        with sqlite3.connect(self._db_path) as conn:
            if domain:
                rows = conn.execute(
                    "SELECT id, domain, vector, metadata, confidence FROM vectors WHERE domain = ?",
                    (domain,),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT id, domain, vector, metadata, confidence FROM vectors"
                ).fetchall()

        results = []
        for row in rows:
            vec_id, vec_domain, vec_bytes, meta_json, confidence = row
            stored_vector = self._bytes_to_vector(vec_bytes)
            similarity = self._cosine_similarity(query_vector, stored_vector)

            if similarity >= min_similarity:
                results.append(
                    {
                        "id": vec_id,
                        "domain": vec_domain,
                        "similarity": round(similarity, 4),
                        "confidence": confidence,
                        "metadata": json.loads(meta_json),
                    }
                )

        results.sort(key=lambda x: x["similarity"], reverse=True)

        # Update usage counts for returned results
        if results:
            now = datetime.now(timezone.utc).isoformat()
            with sqlite3.connect(self._db_path) as conn:
                for r in results[:k]:
                    conn.execute(
                        "UPDATE vectors SET usage_count = usage_count + 1, last_used = ? WHERE id = ?",
                        (now, r["id"]),
                    )
                conn.commit()

        return results[:k]

    def record_outcome(self, vector_id: str, success: bool) -> None:
        """
        Record whether a retrieved pattern led to a successful outcome.
        Updates confidence based on success rate.

        Args:
            vector_id: The vector ID to update
            success: Whether the outcome was successful
        """
        with sqlite3.connect(self._db_path) as conn:
            if success:
                conn.execute(
                    "UPDATE vectors SET success_count = success_count + 1 WHERE id = ?",
                    (vector_id,),
                )
            row = conn.execute(
                "SELECT usage_count, success_count FROM vectors WHERE id = ?",
                (vector_id,),
            ).fetchone()
            if row and row[0] > 0:
                new_confidence = row[1] / row[0]
                conn.execute(
                    "UPDATE vectors SET confidence = ? WHERE id = ?",
                    (round(new_confidence, 4), vector_id),
                )
            conn.commit()

    def get_stats(self, domain: Optional[str] = None) -> Dict[str, Any]:
        """Get vector store statistics."""
        with sqlite3.connect(self._db_path) as conn:
            if domain:
                total = conn.execute(
                    "SELECT COUNT(*) FROM vectors WHERE domain = ?", (domain,)
                ).fetchone()[0]
                avg_conf = conn.execute(
                    "SELECT AVG(confidence) FROM vectors WHERE domain = ?", (domain,)
                ).fetchone()[0]
            else:
                total = conn.execute("SELECT COUNT(*) FROM vectors").fetchone()[0]
                avg_conf = conn.execute("SELECT AVG(confidence) FROM vectors").fetchone()[0]

            domains = conn.execute(
                "SELECT domain, COUNT(*) FROM vectors GROUP BY domain"
            ).fetchall()

        return {
            "total_vectors": total,
            "avg_confidence": round(avg_conf or 0, 4),
            "domains": {d: c for d, c in domains},
            "cache_size": len(self._cache),
            "dimension": self._dimension,
        }

    def prune(self, min_confidence: float = 0.3, min_usage: int = 0) -> int:
        """Remove low-quality vectors. Returns count of pruned vectors."""
        with sqlite3.connect(self._db_path) as conn:
            cursor = conn.execute(
                "DELETE FROM vectors WHERE confidence < ? AND usage_count <= ?",
                (min_confidence, min_usage),
            )
            conn.commit()
            return cursor.rowcount


# --- Domain-specific helpers ---


def price_curve_to_vector(prices: List[float], target_dim: int = 24) -> np.ndarray:
    """
    Convert a price curve (any length) into a normalized vector.
    Resamples to target_dim points and normalizes.
    """
    arr = np.array(prices, dtype=np.float32)
    if len(arr) == 0:
        return np.zeros(target_dim, dtype=np.float32)

    # Resample to target dimension
    if len(arr) != target_dim:
        indices = np.linspace(0, len(arr) - 1, target_dim)
        arr = np.interp(indices, np.arange(len(arr)), arr)

    # Normalize to unit vector for cosine similarity
    norm = np.linalg.norm(arr)
    if norm > 0:
        arr = arr / norm

    return arr


def appliance_config_to_vector(
    appliances: List[Dict[str, Any]], target_dim: int = 24
) -> np.ndarray:
    """
    Convert appliance configuration into a vector for similarity matching.
    Encodes power, duration, time windows into a fixed-size vector.
    """
    vec = np.zeros(target_dim, dtype=np.float32)

    for i, app in enumerate(appliances[:8]):  # Max 8 appliances
        base = i * 3
        if base + 2 < target_dim:
            vec[base] = app.get("power_kw", 1.0)
            vec[base + 1] = app.get("duration_hours", 1.0)
            vec[base + 2] = app.get("earliest_start", 0) / 24.0

    norm = np.linalg.norm(vec)
    if norm > 0:
        vec = vec / norm

    return vec
