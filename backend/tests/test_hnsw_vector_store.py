"""
Tests for the HNSW Vector Store Service (backend/services/hnsw_vector_store.py)

Tests cover:
- Construction: With and without hnswlib available
- _build_index: Builds from SQLite, empty DB, dimension mismatch, build failure
- insert: Dual insert (SQLite + HNSW), HNSW failure graceful, resize, pad/truncate
- search: HNSW path, domain filter, brute-force fallback, min_similarity, usage counts
- record_outcome: Delegation to underlying VectorStore
- get_stats: Base stats plus HNSW info
- prune: Prune + rebuild, skip rebuild when nothing pruned
- Singleton: get_vector_store_singleton returns same instance
"""

import json
import sqlite3
from unittest.mock import MagicMock, patch, PropertyMock, call

import numpy as np
import pytest


# =============================================================================
# CONSTRUCTION
# =============================================================================


class TestConstruction:
    """Tests for HNSWVectorStore.__init__ with and without hnswlib."""

    @patch("services.hnsw_vector_store.VectorStore")
    @patch("services.hnsw_vector_store.HNSW_AVAILABLE", True)
    def test_init_with_hnsw_available_calls_build_index(self, mock_vs_cls):
        """When hnswlib is available, constructor should call _build_index."""
        mock_store = MagicMock()
        mock_vs_cls.return_value = mock_store

        with patch("services.hnsw_vector_store.HNSWVectorStore._build_index") as mock_build:
            from services.hnsw_vector_store import HNSWVectorStore
            store = HNSWVectorStore(db_path="/tmp/test.db", dimension=24)

            mock_build.assert_called_once()
            assert store._dimension == 24
            assert store._max_elements == 10000
            assert store._ef_search == 50
            assert store._M == 16

    @patch("services.hnsw_vector_store.VectorStore")
    @patch("services.hnsw_vector_store.HNSW_AVAILABLE", False)
    def test_init_without_hnsw_skips_build_index(self, mock_vs_cls):
        """When hnswlib is not available, constructor should not call _build_index."""
        mock_store = MagicMock()
        mock_vs_cls.return_value = mock_store

        with patch("services.hnsw_vector_store.HNSWVectorStore._build_index") as mock_build:
            from services.hnsw_vector_store import HNSWVectorStore
            store = HNSWVectorStore(db_path="/tmp/test.db", dimension=24)

            mock_build.assert_not_called()
            assert store._index is None

    @patch("services.hnsw_vector_store.VectorStore")
    @patch("services.hnsw_vector_store.HNSW_AVAILABLE", False)
    def test_init_custom_parameters(self, mock_vs_cls):
        """Custom parameters should be stored correctly."""
        mock_vs_cls.return_value = MagicMock()

        from services.hnsw_vector_store import HNSWVectorStore
        store = HNSWVectorStore(
            db_path="/tmp/custom.db",
            dimension=128,
            max_elements=50000,
            ef_search=100,
            M=32,
        )

        assert store._dimension == 128
        assert store._max_elements == 50000
        assert store._ef_search == 100
        assert store._M == 32
        mock_vs_cls.assert_called_once_with(db_path="/tmp/custom.db", dimension=128)

    @patch("services.hnsw_vector_store.VectorStore")
    @patch("services.hnsw_vector_store.HNSW_AVAILABLE", False)
    def test_init_label_maps_empty(self, mock_vs_cls):
        """Label maps and next_label counter should be initialized empty."""
        mock_vs_cls.return_value = MagicMock()

        from services.hnsw_vector_store import HNSWVectorStore
        store = HNSWVectorStore(db_path="/tmp/test.db")

        assert store._label_to_id == {}
        assert store._id_to_label == {}
        assert store._next_label == 0


# =============================================================================
# BUILD INDEX
# =============================================================================


class TestBuildIndex:
    """Tests for HNSWVectorStore._build_index."""

    @patch("services.hnsw_vector_store.sqlite3")
    @patch("services.hnsw_vector_store.hnswlib")
    @patch("services.hnsw_vector_store.VectorStore")
    @patch("services.hnsw_vector_store.HNSW_AVAILABLE", True)
    def test_build_index_from_sqlite(self, mock_vs_cls, mock_hnswlib, mock_sqlite):
        """Should load vectors from SQLite and add them to the HNSW index."""
        mock_store = MagicMock()
        mock_store._db_path = "/tmp/test.db"
        mock_vs_cls.return_value = mock_store

        # Prepare mock SQLite data
        vec_data = np.array([0.1, 0.2, 0.3] * 8, dtype=np.float32)  # 24-dim
        mock_store._bytes_to_vector.return_value = vec_data

        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchall.return_value = [
            ("vec-1", vec_data.tobytes()),
            ("vec-2", vec_data.tobytes()),
        ]
        mock_sqlite.connect.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_sqlite.connect.return_value.__exit__ = MagicMock(return_value=False)

        # Prepare mock HNSW index
        mock_index = MagicMock()
        mock_hnswlib.Index.return_value = mock_index

        from services.hnsw_vector_store import HNSWVectorStore
        store = HNSWVectorStore(db_path="/tmp/test.db", dimension=24)

        # HNSW index should have been initialized
        mock_hnswlib.Index.assert_called_with(space="cosine", dim=24)
        mock_index.init_index.assert_called_once_with(
            max_elements=10000, ef_construction=200, M=16
        )
        mock_index.set_ef.assert_called_once_with(50)

        # Two vectors should have been added
        assert mock_index.add_items.called
        assert store._next_label == 2
        assert store._label_to_id[0] == "vec-1"
        assert store._label_to_id[1] == "vec-2"
        assert store._id_to_label["vec-1"] == 0
        assert store._id_to_label["vec-2"] == 1

    @patch("services.hnsw_vector_store.sqlite3")
    @patch("services.hnsw_vector_store.hnswlib")
    @patch("services.hnsw_vector_store.VectorStore")
    @patch("services.hnsw_vector_store.HNSW_AVAILABLE", True)
    def test_build_index_empty_db(self, mock_vs_cls, mock_hnswlib, mock_sqlite):
        """With no vectors in SQLite, HNSW index should be created but empty."""
        mock_store = MagicMock()
        mock_store._db_path = "/tmp/test.db"
        mock_vs_cls.return_value = mock_store

        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchall.return_value = []
        mock_sqlite.connect.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_sqlite.connect.return_value.__exit__ = MagicMock(return_value=False)

        mock_index = MagicMock()
        mock_hnswlib.Index.return_value = mock_index

        from services.hnsw_vector_store import HNSWVectorStore
        store = HNSWVectorStore(db_path="/tmp/test.db", dimension=24)

        # Index created but add_items never called
        mock_hnswlib.Index.assert_called_once()
        mock_index.add_items.assert_not_called()
        assert store._next_label == 0
        assert len(store._label_to_id) == 0

    @patch("services.hnsw_vector_store.sqlite3")
    @patch("services.hnsw_vector_store.hnswlib")
    @patch("services.hnsw_vector_store.VectorStore")
    @patch("services.hnsw_vector_store.HNSW_AVAILABLE", True)
    def test_build_index_skips_mismatched_dimensions(self, mock_vs_cls, mock_hnswlib, mock_sqlite):
        """Vectors with wrong dimension should be skipped during build."""
        mock_store = MagicMock()
        mock_store._db_path = "/tmp/test.db"
        mock_vs_cls.return_value = mock_store

        # One 24-dim vector (correct) and one 12-dim vector (wrong)
        good_vec = np.ones(24, dtype=np.float32)
        bad_vec = np.ones(12, dtype=np.float32)
        mock_store._bytes_to_vector.side_effect = [good_vec, bad_vec]

        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchall.return_value = [
            ("vec-good", good_vec.tobytes()),
            ("vec-bad", bad_vec.tobytes()),
        ]
        mock_sqlite.connect.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_sqlite.connect.return_value.__exit__ = MagicMock(return_value=False)

        mock_index = MagicMock()
        mock_hnswlib.Index.return_value = mock_index

        from services.hnsw_vector_store import HNSWVectorStore
        store = HNSWVectorStore(db_path="/tmp/test.db", dimension=24)

        # Only one vector should be in the maps
        assert store._next_label == 1
        assert "vec-good" in store._id_to_label
        assert "vec-bad" not in store._id_to_label

    @patch("services.hnsw_vector_store.logger")
    @patch("services.hnsw_vector_store.sqlite3")
    @patch("services.hnsw_vector_store.hnswlib")
    @patch("services.hnsw_vector_store.VectorStore")
    @patch("services.hnsw_vector_store.HNSW_AVAILABLE", True)
    def test_build_index_failure_sets_index_none(self, mock_vs_cls, mock_hnswlib, mock_sqlite, mock_logger):
        """If build fails, _index should be set to None (graceful degradation)."""
        mock_store = MagicMock()
        mock_store._db_path = "/tmp/test.db"
        mock_vs_cls.return_value = mock_store

        # Make hnswlib.Index raise an exception
        mock_hnswlib.Index.side_effect = RuntimeError("HNSW init failed")

        from services.hnsw_vector_store import HNSWVectorStore
        store = HNSWVectorStore(db_path="/tmp/test.db", dimension=24)

        assert store._index is None
        mock_logger.warning.assert_called_once()


# =============================================================================
# INSERT
# =============================================================================


class TestInsert:
    """Tests for HNSWVectorStore.insert."""

    def _make_store(self, mock_vs_cls, mock_index=None):
        """Helper to create an HNSWVectorStore with mocked internals."""
        mock_store = MagicMock()
        mock_store.insert.return_value = "generated-id"
        mock_vs_cls.return_value = mock_store

        from services.hnsw_vector_store import HNSWVectorStore
        store = HNSWVectorStore.__new__(HNSWVectorStore)
        store._store = mock_store
        store._dimension = 24
        store._max_elements = 100
        store._ef_search = 50
        store._M = 16
        store._index = mock_index
        store._label_to_id = {}
        store._id_to_label = {}
        store._next_label = 0
        return store

    @patch("services.hnsw_vector_store.VectorStore")
    def test_insert_into_sqlite_and_hnsw(self, mock_vs_cls):
        """Insert should add to both SQLite (via VectorStore) and HNSW index."""
        mock_index = MagicMock()
        mock_index.get_max_elements.return_value = 100
        store = self._make_store(mock_vs_cls, mock_index=mock_index)

        vec = np.random.rand(24).astype(np.float32)
        result = store.insert("test_domain", vec, metadata={"key": "val"}, confidence=0.9)

        # VectorStore.insert should be called
        store._store.insert.assert_called_once_with(
            domain="test_domain",
            vector=vec,
            metadata={"key": "val"},
            confidence=0.9,
            vector_id=None,
        )
        assert result == "generated-id"

        # HNSW index should have the vector added
        mock_index.add_items.assert_called_once()
        assert store._label_to_id[0] == "generated-id"
        assert store._id_to_label["generated-id"] == 0
        assert store._next_label == 1

    @patch("services.hnsw_vector_store.VectorStore")
    def test_insert_with_explicit_vector_id(self, mock_vs_cls):
        """Explicit vector_id should be passed through to VectorStore."""
        mock_index = MagicMock()
        mock_index.get_max_elements.return_value = 100
        store = self._make_store(mock_vs_cls, mock_index=mock_index)
        store._store.insert.return_value = "explicit-id"

        vec = np.random.rand(24).astype(np.float32)
        result = store.insert("domain", vec, vector_id="explicit-id")

        assert result == "explicit-id"
        store._store.insert.assert_called_once()
        assert store._store.insert.call_args.kwargs.get("vector_id") == "explicit-id"

    @patch("services.hnsw_vector_store.VectorStore")
    def test_insert_without_hnsw_index(self, mock_vs_cls):
        """When _index is None, insert should still work via SQLite only."""
        store = self._make_store(mock_vs_cls, mock_index=None)

        vec = np.random.rand(24).astype(np.float32)
        result = store.insert("test", vec)

        assert result == "generated-id"
        store._store.insert.assert_called_once()
        # No HNSW operations (no exception)
        assert store._next_label == 0

    @patch("services.hnsw_vector_store.logger")
    @patch("services.hnsw_vector_store.VectorStore")
    def test_insert_hnsw_failure_graceful(self, mock_vs_cls, mock_logger):
        """If HNSW add_items fails, insert should still return the ID from SQLite."""
        mock_index = MagicMock()
        mock_index.get_max_elements.return_value = 100
        mock_index.add_items.side_effect = RuntimeError("HNSW error")
        store = self._make_store(mock_vs_cls, mock_index=mock_index)

        vec = np.random.rand(24).astype(np.float32)
        result = store.insert("test", vec)

        # Should still return the SQLite ID
        assert result == "generated-id"
        mock_logger.warning.assert_called()

    @patch("services.hnsw_vector_store.VectorStore")
    def test_insert_resizes_index_when_full(self, mock_vs_cls):
        """When HNSW index is at capacity, it should resize before inserting."""
        mock_index = MagicMock()
        mock_index.get_max_elements.return_value = 5
        store = self._make_store(mock_vs_cls, mock_index=mock_index)
        store._next_label = 5  # At capacity

        vec = np.random.rand(24).astype(np.float32)
        store.insert("test", vec)

        mock_index.resize_index.assert_called_once_with(5 * 2)
        mock_index.add_items.assert_called_once()

    @patch("services.hnsw_vector_store.VectorStore")
    def test_insert_does_not_resize_when_space_available(self, mock_vs_cls):
        """When space is available, resize should not be called."""
        mock_index = MagicMock()
        mock_index.get_max_elements.return_value = 100
        store = self._make_store(mock_vs_cls, mock_index=mock_index)
        store._next_label = 5  # Well under 100

        vec = np.random.rand(24).astype(np.float32)
        store.insert("test", vec)

        mock_index.resize_index.assert_not_called()

    @patch("services.hnsw_vector_store.VectorStore")
    def test_insert_pads_short_vector(self, mock_vs_cls):
        """Vectors shorter than dimension should be zero-padded for HNSW."""
        mock_index = MagicMock()
        mock_index.get_max_elements.return_value = 100
        store = self._make_store(mock_vs_cls, mock_index=mock_index)

        short_vec = np.ones(10, dtype=np.float32)
        store.insert("test", short_vec)

        # Check the vector passed to add_items is 24-dim
        added_data = mock_index.add_items.call_args[0][0]
        assert added_data.shape == (1, 24)
        # First 10 elements should be 1.0, rest 0.0
        np.testing.assert_array_equal(added_data[0, :10], np.ones(10))
        np.testing.assert_array_equal(added_data[0, 10:], np.zeros(14))

    @patch("services.hnsw_vector_store.VectorStore")
    def test_insert_truncates_long_vector(self, mock_vs_cls):
        """Vectors longer than dimension should be truncated for HNSW."""
        mock_index = MagicMock()
        mock_index.get_max_elements.return_value = 100
        store = self._make_store(mock_vs_cls, mock_index=mock_index)

        long_vec = np.arange(48, dtype=np.float32)
        store.insert("test", long_vec)

        added_data = mock_index.add_items.call_args[0][0]
        assert added_data.shape == (1, 24)
        np.testing.assert_array_equal(added_data[0], np.arange(24, dtype=np.float32))

    @patch("services.hnsw_vector_store.VectorStore")
    def test_insert_multiple_increments_labels(self, mock_vs_cls):
        """Multiple inserts should increment label counters correctly."""
        mock_index = MagicMock()
        mock_index.get_max_elements.return_value = 100
        store = self._make_store(mock_vs_cls, mock_index=mock_index)

        store._store.insert.side_effect = ["id-0", "id-1", "id-2"]

        for _ in range(3):
            vec = np.random.rand(24).astype(np.float32)
            store.insert("test", vec)

        assert store._next_label == 3
        assert store._label_to_id == {0: "id-0", 1: "id-1", 2: "id-2"}
        assert store._id_to_label == {"id-0": 0, "id-1": 1, "id-2": 2}


# =============================================================================
# SEARCH
# =============================================================================


class TestSearch:
    """Tests for HNSWVectorStore.search."""

    def _make_store_for_search(self, index=None):
        """Helper to create an HNSWVectorStore ready for search testing."""
        from services.hnsw_vector_store import HNSWVectorStore

        store = HNSWVectorStore.__new__(HNSWVectorStore)
        store._store = MagicMock()
        store._store._db_path = "/tmp/test.db"
        store._dimension = 24
        store._max_elements = 100
        store._ef_search = 50
        store._M = 16
        store._index = index
        store._label_to_id = {}
        store._id_to_label = {}
        store._next_label = 0
        return store

    def test_search_falls_back_when_index_none(self):
        """When _index is None, should delegate to VectorStore.search."""
        store = self._make_store_for_search(index=None)
        store._store.search.return_value = [{"id": "fallback-1", "similarity": 0.8}]

        query = np.random.rand(24).astype(np.float32)
        results = store.search(query, domain="test", k=5, min_similarity=0.5)

        store._store.search.assert_called_once_with(
            query_vector=query,
            domain="test",
            k=5,
            min_similarity=0.5,
        )
        assert results == [{"id": "fallback-1", "similarity": 0.8}]

    def test_search_falls_back_when_index_empty(self):
        """When HNSW index has 0 elements, should fall back to brute-force."""
        mock_index = MagicMock()
        mock_index.get_current_count.return_value = 0
        store = self._make_store_for_search(index=mock_index)
        store._store.search.return_value = []

        query = np.random.rand(24).astype(np.float32)
        results = store.search(query)

        store._store.search.assert_called_once()
        mock_index.knn_query.assert_not_called()

    @patch("services.hnsw_vector_store.sqlite3")
    def test_search_uses_hnsw_when_available(self, mock_sqlite):
        """When HNSW index is populated, should use knn_query."""
        mock_index = MagicMock()
        mock_index.get_current_count.return_value = 10
        # knn_query returns (labels_2d, distances_2d)
        mock_index.knn_query.return_value = (
            np.array([[0, 1]]),
            np.array([[0.1, 0.2]]),  # cosine distance: similarity = 1 - dist
        )

        store = self._make_store_for_search(index=mock_index)
        store._label_to_id = {0: "vec-a", 1: "vec-b"}
        store._id_to_label = {"vec-a": 0, "vec-b": 1}
        store._next_label = 2

        # Mock SQLite batch metadata lookup (fetchall returns all rows at once)
        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchall.return_value = [
            ("vec-a", "recommendation", '{"region": "CT"}', 0.95),
            ("vec-b", "recommendation", '{"region": "NY"}', 0.85),
        ]
        mock_sqlite.connect.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_sqlite.connect.return_value.__exit__ = MagicMock(return_value=False)

        query = np.random.rand(24).astype(np.float32)
        results = store.search(query, k=5, min_similarity=0.5)

        mock_index.knn_query.assert_called_once()
        assert len(results) == 2
        # similarity = 1 - distance
        assert results[0]["id"] == "vec-a"
        assert results[0]["similarity"] == round(1.0 - 0.1, 4)
        assert results[0]["metadata"] == {"region": "CT"}
        assert results[1]["id"] == "vec-b"
        assert results[1]["similarity"] == round(1.0 - 0.2, 4)

    @patch("services.hnsw_vector_store.sqlite3")
    def test_search_with_domain_filter(self, mock_sqlite):
        """Domain filter should exclude results from other domains."""
        mock_index = MagicMock()
        mock_index.get_current_count.return_value = 10
        mock_index.knn_query.return_value = (
            np.array([[0, 1]]),
            np.array([[0.05, 0.1]]),
        )

        store = self._make_store_for_search(index=mock_index)
        store._label_to_id = {0: "vec-match", 1: "vec-other"}

        # First result in domain "target", second in "other"
        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchall.return_value = [
            ("vec-match", "target", '{}', 0.9),
            ("vec-other", "other", '{}', 0.8),
        ]
        mock_sqlite.connect.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_sqlite.connect.return_value.__exit__ = MagicMock(return_value=False)

        query = np.random.rand(24).astype(np.float32)
        results = store.search(query, domain="target", k=5, min_similarity=0.5)

        assert len(results) == 1
        assert results[0]["id"] == "vec-match"
        assert results[0]["domain"] == "target"

    @patch("services.hnsw_vector_store.sqlite3")
    def test_search_respects_min_similarity(self, mock_sqlite):
        """Results below min_similarity threshold should be filtered out."""
        mock_index = MagicMock()
        mock_index.get_current_count.return_value = 10
        # distance 0.05 -> sim 0.95 (above 0.9), distance 0.5 -> sim 0.5 (below 0.9)
        mock_index.knn_query.return_value = (
            np.array([[0, 1]]),
            np.array([[0.05, 0.5]]),
        )

        store = self._make_store_for_search(index=mock_index)
        store._label_to_id = {0: "close", 1: "far"}

        mock_conn = MagicMock()
        # Only "close" passes min_similarity=0.9 (dist 0.05 -> sim 0.95)
        # "far" is filtered before batch lookup (dist 0.5 -> sim 0.5 < 0.9)
        mock_conn.execute.return_value.fetchall.return_value = [
            ("close", "test", '{}', 0.9),
        ]
        mock_sqlite.connect.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_sqlite.connect.return_value.__exit__ = MagicMock(return_value=False)

        query = np.random.rand(24).astype(np.float32)
        results = store.search(query, min_similarity=0.9)

        assert len(results) == 1
        assert results[0]["id"] == "close"

    @patch("services.hnsw_vector_store.sqlite3")
    def test_search_limits_to_k_results(self, mock_sqlite):
        """Should return at most k results even if more pass the threshold."""
        mock_index = MagicMock()
        mock_index.get_current_count.return_value = 20
        # Return 5 close neighbors
        labels = np.array([[0, 1, 2, 3, 4]])
        distances = np.array([[0.01, 0.02, 0.03, 0.04, 0.05]])
        mock_index.knn_query.return_value = (labels, distances)

        store = self._make_store_for_search(index=mock_index)
        for i in range(5):
            store._label_to_id[i] = f"vec-{i}"

        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchall.return_value = [
            (f"vec-{i}", "test", '{}', 0.9) for i in range(5)
        ]
        mock_sqlite.connect.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_sqlite.connect.return_value.__exit__ = MagicMock(return_value=False)

        query = np.random.rand(24).astype(np.float32)
        results = store.search(query, k=2, min_similarity=0.5)

        # Should be limited to k=2
        assert len(results) == 2

    @patch("services.hnsw_vector_store.sqlite3")
    def test_search_updates_usage_counts(self, mock_sqlite):
        """After returning results, usage_count and last_used should be updated."""
        mock_index = MagicMock()
        mock_index.get_current_count.return_value = 5
        mock_index.knn_query.return_value = (
            np.array([[0]]),
            np.array([[0.1]]),
        )

        store = self._make_store_for_search(index=mock_index)
        store._label_to_id = {0: "vec-1"}

        mock_conn = MagicMock()
        # Batch metadata lookup returns all rows
        mock_conn.execute.return_value.fetchall.return_value = [
            ("vec-1", "test", '{"k": "v"}', 0.9),
        ]
        mock_sqlite.connect.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_sqlite.connect.return_value.__exit__ = MagicMock(return_value=False)

        query = np.random.rand(24).astype(np.float32)
        results = store.search(query, min_similarity=0.5)

        assert len(results) == 1

        # Check that UPDATE was called for usage_count
        update_calls = [
            c for c in mock_conn.execute.call_args_list
            if "UPDATE vectors SET usage_count" in str(c)
        ]
        assert len(update_calls) >= 1
        mock_conn.commit.assert_called()

    @patch("services.hnsw_vector_store.sqlite3")
    def test_search_skips_unknown_labels(self, mock_sqlite):
        """Labels not in _label_to_id should be skipped."""
        mock_index = MagicMock()
        mock_index.get_current_count.return_value = 5
        mock_index.knn_query.return_value = (
            np.array([[0, 99]]),  # label 99 not in maps
            np.array([[0.1, 0.2]]),
        )

        store = self._make_store_for_search(index=mock_index)
        store._label_to_id = {0: "known-vec"}  # Only label 0 known

        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchall.return_value = [
            ("known-vec", "test", '{}', 0.9),
        ]
        mock_sqlite.connect.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_sqlite.connect.return_value.__exit__ = MagicMock(return_value=False)

        query = np.random.rand(24).astype(np.float32)
        results = store.search(query, min_similarity=0.5)

        assert len(results) == 1
        assert results[0]["id"] == "known-vec"

    @patch("services.hnsw_vector_store.sqlite3")
    def test_search_skips_missing_sqlite_rows(self, mock_sqlite):
        """If SQLite has no row for a vector ID, it should be skipped."""
        mock_index = MagicMock()
        mock_index.get_current_count.return_value = 5
        mock_index.knn_query.return_value = (
            np.array([[0]]),
            np.array([[0.1]]),
        )

        store = self._make_store_for_search(index=mock_index)
        store._label_to_id = {0: "orphaned-vec"}

        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchall.return_value = []  # Row not found
        mock_sqlite.connect.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_sqlite.connect.return_value.__exit__ = MagicMock(return_value=False)

        query = np.random.rand(24).astype(np.float32)
        results = store.search(query, min_similarity=0.5)

        assert results == []

    @patch("services.hnsw_vector_store.logger")
    def test_search_falls_back_on_knn_error(self, mock_logger):
        """If knn_query raises an exception, should fall back to brute-force."""
        mock_index = MagicMock()
        mock_index.get_current_count.return_value = 5
        mock_index.knn_query.side_effect = RuntimeError("HNSW search error")

        store = self._make_store_for_search(index=mock_index)
        store._store.search.return_value = [{"id": "bf-result", "similarity": 0.75}]

        query = np.random.rand(24).astype(np.float32)
        results = store.search(query, domain="test", k=3, min_similarity=0.6)

        store._store.search.assert_called_once_with(
            query_vector=query,
            domain="test",
            k=3,
            min_similarity=0.6,
        )
        assert results == [{"id": "bf-result", "similarity": 0.75}]
        mock_logger.warning.assert_called()

    @patch("services.hnsw_vector_store.sqlite3")
    def test_search_pads_short_query_vector(self, mock_sqlite):
        """Query vectors shorter than dimension should be zero-padded."""
        mock_index = MagicMock()
        mock_index.get_current_count.return_value = 5
        mock_index.knn_query.return_value = (np.array([[0]]), np.array([[0.1]]))

        store = self._make_store_for_search(index=mock_index)
        store._label_to_id = {0: "vec-1"}

        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchall.return_value = [
            ("vec-1", "test", '{}', 0.9),
        ]
        mock_sqlite.connect.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_sqlite.connect.return_value.__exit__ = MagicMock(return_value=False)

        short_query = np.ones(10, dtype=np.float32)
        store.search(short_query, min_similarity=0.5)

        # Verify the query passed to knn_query was padded to (1, 24)
        called_query = mock_index.knn_query.call_args[0][0]
        assert called_query.shape == (1, 24)

    @patch("services.hnsw_vector_store.sqlite3")
    def test_search_truncates_long_query_vector(self, mock_sqlite):
        """Query vectors longer than dimension should be truncated."""
        mock_index = MagicMock()
        mock_index.get_current_count.return_value = 5
        mock_index.knn_query.return_value = (np.array([[0]]), np.array([[0.1]]))

        store = self._make_store_for_search(index=mock_index)
        store._label_to_id = {0: "vec-1"}

        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchall.return_value = [
            ("vec-1", "test", '{}', 0.9),
        ]
        mock_sqlite.connect.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_sqlite.connect.return_value.__exit__ = MagicMock(return_value=False)

        long_query = np.ones(48, dtype=np.float32)
        store.search(long_query, min_similarity=0.5)

        called_query = mock_index.knn_query.call_args[0][0]
        assert called_query.shape == (1, 24)

    @patch("services.hnsw_vector_store.sqlite3")
    def test_search_fetch_k_capped_at_index_count(self, mock_sqlite):
        """fetch_k should be min(k*3, current_count) to avoid requesting more than available."""
        mock_index = MagicMock()
        mock_index.get_current_count.return_value = 2  # Only 2 vectors
        mock_index.knn_query.return_value = (
            np.array([[0, 1]]),
            np.array([[0.1, 0.2]]),
        )

        store = self._make_store_for_search(index=mock_index)
        store._label_to_id = {0: "v0", 1: "v1"}

        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchall.return_value = [
            ("v0", "test", '{}', 0.9),
            ("v1", "test", '{}', 0.8),
        ]
        mock_sqlite.connect.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_sqlite.connect.return_value.__exit__ = MagicMock(return_value=False)

        query = np.random.rand(24).astype(np.float32)
        store.search(query, k=10, min_similarity=0.5)

        # fetch_k should be min(10*3, 2) = 2
        knn_call_k = mock_index.knn_query.call_args[1].get("k") or mock_index.knn_query.call_args[0][1]
        assert knn_call_k == 2

    @patch("services.hnsw_vector_store.sqlite3")
    def test_search_no_usage_update_when_no_results(self, mock_sqlite):
        """When search returns no results, usage update should be skipped."""
        mock_index = MagicMock()
        mock_index.get_current_count.return_value = 5
        # All distances yield similarity below threshold
        mock_index.knn_query.return_value = (
            np.array([[0]]),
            np.array([[0.9]]),  # sim = 0.1, below any reasonable threshold
        )

        store = self._make_store_for_search(index=mock_index)
        store._label_to_id = {0: "vec-1"}

        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchone.return_value = ("test", '{}', 0.5)
        mock_sqlite.connect.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_sqlite.connect.return_value.__exit__ = MagicMock(return_value=False)

        query = np.random.rand(24).astype(np.float32)
        results = store.search(query, min_similarity=0.9)

        assert results == []
        # commit for usage update should not be called (no results to update)
        # (Note: the connect for metadata lookup may still happen)
        update_calls = [
            c for c in mock_conn.execute.call_args_list
            if "UPDATE vectors SET usage_count" in str(c)
        ]
        assert len(update_calls) == 0


# =============================================================================
# RECORD OUTCOME
# =============================================================================


class TestRecordOutcome:
    """Tests for HNSWVectorStore.record_outcome."""

    def test_record_outcome_delegates_to_store(self):
        """record_outcome should delegate directly to the underlying VectorStore."""
        from services.hnsw_vector_store import HNSWVectorStore
        store = HNSWVectorStore.__new__(HNSWVectorStore)
        store._store = MagicMock()

        store.record_outcome("vec-123", success=True)
        store._store.record_outcome.assert_called_once_with("vec-123", True)

    def test_record_outcome_failure(self):
        """record_outcome with success=False should be passed through."""
        from services.hnsw_vector_store import HNSWVectorStore
        store = HNSWVectorStore.__new__(HNSWVectorStore)
        store._store = MagicMock()

        store.record_outcome("vec-456", success=False)
        store._store.record_outcome.assert_called_once_with("vec-456", False)


# =============================================================================
# GET STATS
# =============================================================================


class TestGetStats:
    """Tests for HNSWVectorStore.get_stats."""

    @patch("services.hnsw_vector_store.HNSW_AVAILABLE", True)
    def test_get_stats_with_hnsw_index(self):
        """Should include HNSW count and max_elements when index is present."""
        from services.hnsw_vector_store import HNSWVectorStore
        store = HNSWVectorStore.__new__(HNSWVectorStore)
        store._store = MagicMock()
        store._store.get_stats.return_value = {
            "total_vectors": 42,
            "avg_confidence": 0.85,
            "domains": {"test": 42},
            "cache_size": 10,
            "dimension": 24,
        }

        mock_index = MagicMock()
        mock_index.get_current_count.return_value = 42
        mock_index.get_max_elements.return_value = 10000
        store._index = mock_index

        stats = store.get_stats()

        assert stats["total_vectors"] == 42
        assert stats["hnsw_available"] is True
        assert stats["hnsw_count"] == 42
        assert stats["hnsw_max_elements"] == 10000

    @patch("services.hnsw_vector_store.HNSW_AVAILABLE", False)
    def test_get_stats_without_hnsw(self):
        """Without HNSW, stats should not include hnsw_count."""
        from services.hnsw_vector_store import HNSWVectorStore
        store = HNSWVectorStore.__new__(HNSWVectorStore)
        store._store = MagicMock()
        store._store.get_stats.return_value = {
            "total_vectors": 10,
            "avg_confidence": 0.7,
            "domains": {},
            "cache_size": 5,
            "dimension": 24,
        }
        store._index = None

        stats = store.get_stats()

        assert stats["hnsw_available"] is False
        assert "hnsw_count" not in stats
        assert "hnsw_max_elements" not in stats

    @patch("services.hnsw_vector_store.HNSW_AVAILABLE", True)
    def test_get_stats_with_domain_filter(self):
        """Domain filter should be passed through to the underlying store."""
        from services.hnsw_vector_store import HNSWVectorStore
        store = HNSWVectorStore.__new__(HNSWVectorStore)
        store._store = MagicMock()
        store._store.get_stats.return_value = {"total_vectors": 5}
        store._index = None

        store.get_stats(domain="recommendation")

        store._store.get_stats.assert_called_once_with("recommendation")


# =============================================================================
# PRUNE
# =============================================================================


class TestPrune:
    """Tests for HNSWVectorStore.prune."""

    @patch("services.hnsw_vector_store.HNSW_AVAILABLE", True)
    def test_prune_rebuilds_hnsw_when_vectors_removed(self):
        """After pruning vectors, HNSW index should be rebuilt."""
        from services.hnsw_vector_store import HNSWVectorStore
        store = HNSWVectorStore.__new__(HNSWVectorStore)
        store._store = MagicMock()
        store._store.prune.return_value = 3
        store._label_to_id = {0: "a", 1: "b", 2: "c"}
        store._id_to_label = {"a": 0, "b": 1, "c": 2}
        store._next_label = 3

        with patch.object(store, "_build_index") as mock_build:
            count = store.prune(min_confidence=0.5, min_usage=1)

        assert count == 3
        store._store.prune.assert_called_once_with(0.5, 1)
        mock_build.assert_called_once()
        # Maps should have been cleared before rebuild
        assert store._label_to_id == {}
        assert store._id_to_label == {}
        assert store._next_label == 0

    @patch("services.hnsw_vector_store.HNSW_AVAILABLE", True)
    def test_prune_skips_rebuild_when_nothing_removed(self):
        """If prune returns 0, HNSW index should not be rebuilt."""
        from services.hnsw_vector_store import HNSWVectorStore
        store = HNSWVectorStore.__new__(HNSWVectorStore)
        store._store = MagicMock()
        store._store.prune.return_value = 0
        store._label_to_id = {0: "a"}
        store._id_to_label = {"a": 0}
        store._next_label = 1

        with patch.object(store, "_build_index") as mock_build:
            count = store.prune(min_confidence=0.3)

        assert count == 0
        mock_build.assert_not_called()
        # Maps should remain unchanged
        assert store._label_to_id == {0: "a"}
        assert store._next_label == 1

    @patch("services.hnsw_vector_store.HNSW_AVAILABLE", False)
    def test_prune_skips_rebuild_when_hnsw_unavailable(self):
        """When HNSW is not available, prune should not try to rebuild."""
        from services.hnsw_vector_store import HNSWVectorStore
        store = HNSWVectorStore.__new__(HNSWVectorStore)
        store._store = MagicMock()
        store._store.prune.return_value = 5
        store._label_to_id = {}
        store._id_to_label = {}
        store._next_label = 0

        with patch.object(store, "_build_index") as mock_build:
            count = store.prune()

        assert count == 5
        mock_build.assert_not_called()

    @patch("services.hnsw_vector_store.HNSW_AVAILABLE", True)
    def test_prune_default_parameters(self):
        """Default parameters should be min_confidence=0.3, min_usage=0."""
        from services.hnsw_vector_store import HNSWVectorStore
        store = HNSWVectorStore.__new__(HNSWVectorStore)
        store._store = MagicMock()
        store._store.prune.return_value = 0
        store._label_to_id = {}
        store._id_to_label = {}
        store._next_label = 0

        store.prune()

        store._store.prune.assert_called_once_with(0.3, 0)


# =============================================================================
# SINGLETON
# =============================================================================


class TestSingleton:
    """Tests for get_vector_store_singleton."""

    @patch("services.hnsw_vector_store._vector_store_singleton", None)
    @patch("services.hnsw_vector_store.HNSWVectorStore")
    def test_singleton_creates_instance_on_first_call(self, mock_hnsw_cls):
        """First call should create a new HNSWVectorStore instance."""
        mock_instance = MagicMock()
        mock_hnsw_cls.return_value = mock_instance

        from services.hnsw_vector_store import get_vector_store_singleton
        result = get_vector_store_singleton()

        mock_hnsw_cls.assert_called_once()
        assert result is mock_instance

    @patch("services.hnsw_vector_store.HNSWVectorStore")
    def test_singleton_returns_same_instance(self, mock_hnsw_cls):
        """Subsequent calls should return the same instance."""
        import services.hnsw_vector_store as module

        mock_instance = MagicMock()
        original = module._vector_store_singleton
        try:
            module._vector_store_singleton = mock_instance

            result1 = module.get_vector_store_singleton()
            result2 = module.get_vector_store_singleton()

            assert result1 is result2
            assert result1 is mock_instance
            # Should not create a new instance
            mock_hnsw_cls.assert_not_called()
        finally:
            module._vector_store_singleton = original

    @patch("services.hnsw_vector_store.HNSWVectorStore")
    def test_singleton_only_creates_once(self, mock_hnsw_cls):
        """Even with multiple calls, constructor should only be called once."""
        import services.hnsw_vector_store as module

        original = module._vector_store_singleton
        try:
            module._vector_store_singleton = None
            mock_instance = MagicMock()
            mock_hnsw_cls.return_value = mock_instance

            for _ in range(5):
                module.get_vector_store_singleton()

            mock_hnsw_cls.assert_called_once()
        finally:
            module._vector_store_singleton = original


# =============================================================================
# EDGE CASES & INTEGRATION-STYLE
# =============================================================================


class TestEdgeCases:
    """Edge cases and boundary conditions."""

    @patch("services.hnsw_vector_store.VectorStore")
    def test_insert_then_search_without_hnsw(self, mock_vs_cls):
        """Full insert-search cycle without HNSW should work via brute-force."""
        from services.hnsw_vector_store import HNSWVectorStore
        store = HNSWVectorStore.__new__(HNSWVectorStore)
        mock_store = MagicMock()
        mock_store.insert.return_value = "test-id"
        mock_store.search.return_value = [{"id": "test-id", "similarity": 0.99}]
        store._store = mock_store
        store._dimension = 24
        store._index = None
        store._label_to_id = {}
        store._id_to_label = {}
        store._next_label = 0

        vec = np.ones(24, dtype=np.float32)
        vid = store.insert("test", vec)
        results = store.search(vec, min_similarity=0.9)

        assert vid == "test-id"
        assert len(results) == 1
        mock_store.search.assert_called_once()

    @patch("services.hnsw_vector_store.sqlite3")
    def test_search_with_json_metadata_parsing(self, mock_sqlite):
        """Metadata JSON should be correctly parsed from SQLite rows."""
        mock_index = MagicMock()
        mock_index.get_current_count.return_value = 1
        mock_index.knn_query.return_value = (
            np.array([[0]]),
            np.array([[0.05]]),
        )

        from services.hnsw_vector_store import HNSWVectorStore
        store = HNSWVectorStore.__new__(HNSWVectorStore)
        store._store = MagicMock()
        store._store._db_path = "/tmp/test.db"
        store._dimension = 24
        store._index = mock_index
        store._label_to_id = {0: "meta-vec"}
        store._id_to_label = {"meta-vec": 0}
        store._next_label = 1

        complex_meta = json.dumps({
            "region": "US_CT",
            "hour": 14,
            "prices": [0.1, 0.2, 0.3],
            "nested": {"key": "value"},
        })

        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchall.return_value = [
            ("meta-vec", "recommendation", complex_meta, 0.95),
        ]
        mock_sqlite.connect.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_sqlite.connect.return_value.__exit__ = MagicMock(return_value=False)

        query = np.random.rand(24).astype(np.float32)
        results = store.search(query, min_similarity=0.5)

        assert len(results) == 1
        assert results[0]["metadata"]["region"] == "US_CT"
        assert results[0]["metadata"]["prices"] == [0.1, 0.2, 0.3]
        assert results[0]["metadata"]["nested"]["key"] == "value"

    @patch("services.hnsw_vector_store.VectorStore")
    def test_insert_copies_vector_before_modification(self, mock_vs_cls):
        """Insert should not modify the original vector array."""
        mock_index = MagicMock()
        mock_index.get_max_elements.return_value = 100

        from services.hnsw_vector_store import HNSWVectorStore
        store = HNSWVectorStore.__new__(HNSWVectorStore)
        store._store = MagicMock()
        store._store.insert.return_value = "id-1"
        store._dimension = 24
        store._index = mock_index
        store._label_to_id = {}
        store._id_to_label = {}
        store._next_label = 0

        original = np.ones(10, dtype=np.float32)
        original_copy = original.copy()
        store.insert("test", original)

        # Original vector should not be modified
        np.testing.assert_array_equal(original, original_copy)

    @patch("services.hnsw_vector_store.sqlite3")
    def test_search_with_zero_vector(self, mock_sqlite):
        """Searching with a zero vector should not crash."""
        mock_index = MagicMock()
        mock_index.get_current_count.return_value = 5
        mock_index.knn_query.return_value = (
            np.array([[0]]),
            np.array([[1.0]]),  # max distance, sim = 0.0
        )

        from services.hnsw_vector_store import HNSWVectorStore
        store = HNSWVectorStore.__new__(HNSWVectorStore)
        store._store = MagicMock()
        store._store._db_path = "/tmp/test.db"
        store._dimension = 24
        store._index = mock_index
        store._label_to_id = {0: "vec-1"}
        store._id_to_label = {"vec-1": 0}
        store._next_label = 1

        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchone.return_value = ("test", '{}', 0.5)
        mock_sqlite.connect.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_sqlite.connect.return_value.__exit__ = MagicMock(return_value=False)

        zero_query = np.zeros(24, dtype=np.float32)
        results = store.search(zero_query, min_similarity=0.5)

        # similarity = 1 - 1.0 = 0.0, below threshold, so empty
        assert results == []

    @patch("services.hnsw_vector_store.sqlite3")
    def test_search_no_domain_filter_returns_all_domains(self, mock_sqlite):
        """Without domain filter, results from all domains should be included."""
        mock_index = MagicMock()
        mock_index.get_current_count.return_value = 10
        mock_index.knn_query.return_value = (
            np.array([[0, 1, 2]]),
            np.array([[0.05, 0.1, 0.15]]),
        )

        from services.hnsw_vector_store import HNSWVectorStore
        store = HNSWVectorStore.__new__(HNSWVectorStore)
        store._store = MagicMock()
        store._store._db_path = "/tmp/test.db"
        store._dimension = 24
        store._index = mock_index
        store._label_to_id = {0: "v0", 1: "v1", 2: "v2"}
        store._id_to_label = {"v0": 0, "v1": 1, "v2": 2}
        store._next_label = 3

        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchall.return_value = [
            ("v0", "price_pattern", '{}', 0.9),
            ("v1", "recommendation", '{}', 0.8),
            ("v2", "bias_correction", '{}', 0.7),
        ]
        mock_sqlite.connect.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_sqlite.connect.return_value.__exit__ = MagicMock(return_value=False)

        query = np.random.rand(24).astype(np.float32)
        results = store.search(query, domain=None, min_similarity=0.5)

        assert len(results) == 3
        domains = {r["domain"] for r in results}
        assert domains == {"price_pattern", "recommendation", "bias_correction"}

    @patch("services.hnsw_vector_store.VectorStore")
    def test_insert_with_none_metadata(self, mock_vs_cls):
        """Insert with metadata=None should work without errors."""
        mock_index = MagicMock()
        mock_index.get_max_elements.return_value = 100

        from services.hnsw_vector_store import HNSWVectorStore
        store = HNSWVectorStore.__new__(HNSWVectorStore)
        store._store = MagicMock()
        store._store.insert.return_value = "id-none-meta"
        store._dimension = 24
        store._index = mock_index
        store._label_to_id = {}
        store._id_to_label = {}
        store._next_label = 0

        vec = np.random.rand(24).astype(np.float32)
        vid = store.insert("test", vec, metadata=None)

        assert vid == "id-none-meta"
        store._store.insert.assert_called_once_with(
            domain="test",
            vector=vec,
            metadata=None,
            confidence=1.0,
            vector_id=None,
        )
