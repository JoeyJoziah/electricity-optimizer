"""
Tests for the Vector Store Service (backend/services/vector_store.py)

Tests cover:
- insert() - add vector entry
- search() - similarity search
- record_outcome() - feedback recording and confidence update
- prune() - cleanup low-quality entries
- get_stats() - store statistics
- Domain-specific helpers: price_curve_to_vector, appliance_config_to_vector
"""

import os
import tempfile
import pytest
import numpy as np

from services.vector_store import (
    VectorStore,
    price_curve_to_vector,
    appliance_config_to_vector,
)


@pytest.fixture
def tmp_db_path():
    """Create a temporary database path for isolated tests."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield os.path.join(tmpdir, "test_vectors.db")


@pytest.fixture
def store(tmp_db_path):
    """Create a fresh VectorStore instance with a temp DB."""
    return VectorStore(db_path=tmp_db_path, cache_size=50, dimension=24)


# =============================================================================
# INSERT
# =============================================================================


class TestInsert:
    """Tests for VectorStore.insert()."""

    def test_insert_returns_id(self, store):
        """Insert should return a non-empty string ID."""
        vec = np.random.rand(24).astype(np.float32)
        vec_id = store.insert("price_pattern", vec)
        assert isinstance(vec_id, str)
        assert len(vec_id) > 0

    def test_insert_with_explicit_id(self, store):
        """When vector_id is provided, it should be used as-is."""
        vec = np.random.rand(24).astype(np.float32)
        vec_id = store.insert("test_domain", vec, vector_id="explicit-id-1")
        assert vec_id == "explicit-id-1"

    def test_insert_with_metadata(self, store):
        """Metadata should be stored and retrievable via search."""
        vec = np.ones(24, dtype=np.float32)
        store.insert(
            "price_pattern",
            vec,
            metadata={"region": "US_CT", "hour": 14},
        )

        results = store.search(vec, domain="price_pattern", min_similarity=0.99)
        assert len(results) > 0
        assert results[0]["metadata"]["region"] == "US_CT"

    def test_insert_auto_pads_short_vector(self, store):
        """Vectors shorter than dimension should be zero-padded."""
        short_vec = np.ones(10, dtype=np.float32)
        vec_id = store.insert("test", short_vec)
        assert vec_id is not None

        # Search with padded equivalent should find it
        padded = np.pad(short_vec, (0, 14))
        results = store.search(padded, min_similarity=0.99)
        assert len(results) > 0

    def test_insert_truncates_long_vector(self, store):
        """Vectors longer than dimension should be truncated."""
        long_vec = np.ones(48, dtype=np.float32)
        vec_id = store.insert("test", long_vec)
        assert vec_id is not None

    def test_insert_with_confidence(self, store):
        """Custom confidence should be stored."""
        vec = np.random.rand(24).astype(np.float32)
        store.insert("test", vec, confidence=0.75, vector_id="conf-test")
        results = store.search(vec, min_similarity=0.0)
        match = [r for r in results if r["id"] == "conf-test"]
        assert len(match) == 1
        assert match[0]["confidence"] == 0.75


# =============================================================================
# SEARCH
# =============================================================================


class TestSearch:
    """Tests for VectorStore.search()."""

    def test_search_returns_similar(self, store):
        """Searching with the same vector should find it."""
        vec = np.random.rand(24).astype(np.float32)
        store.insert("domain_a", vec, vector_id="s1")

        results = store.search(vec, min_similarity=0.9)
        assert len(results) >= 1
        ids = [r["id"] for r in results]
        assert "s1" in ids

    def test_search_respects_domain_filter(self, store):
        """Domain filter should exclude vectors from other domains."""
        vec = np.random.rand(24).astype(np.float32)
        store.insert("domain_a", vec, vector_id="da")
        store.insert("domain_b", vec, vector_id="db")

        results = store.search(vec, domain="domain_a", min_similarity=0.9)
        ids = [r["id"] for r in results]
        assert "da" in ids
        assert "db" not in ids

    def test_search_respects_min_similarity(self, store):
        """Results below min_similarity should be excluded."""
        vec_a = np.ones(24, dtype=np.float32)
        vec_b = -np.ones(24, dtype=np.float32)  # opposite direction
        store.insert("test", vec_a, vector_id="same")
        store.insert("test", vec_b, vector_id="opposite")

        results = store.search(vec_a, min_similarity=0.5)
        ids = [r["id"] for r in results]
        assert "same" in ids
        assert "opposite" not in ids

    def test_search_limits_results_to_k(self, store):
        """Should return at most k results."""
        base = np.ones(24, dtype=np.float32)
        for i in range(10):
            noise = np.random.normal(0, 0.01, 24).astype(np.float32)
            store.insert("test", base + noise, vector_id=f"v{i}")

        results = store.search(base, k=3, min_similarity=0.0)
        assert len(results) <= 3

    def test_search_sorted_by_similarity(self, store):
        """Results should be sorted by similarity descending."""
        base = np.ones(24, dtype=np.float32)
        for i in range(5):
            noise = np.random.normal(0, 0.05 * (i + 1), 24).astype(np.float32)
            store.insert("test", base + noise, vector_id=f"v{i}")

        results = store.search(base, k=5, min_similarity=0.0)
        similarities = [r["similarity"] for r in results]
        assert similarities == sorted(similarities, reverse=True)

    def test_search_empty_store(self, store):
        """Searching an empty store should return empty list."""
        vec = np.random.rand(24).astype(np.float32)
        results = store.search(vec)
        assert results == []


# =============================================================================
# RECORD OUTCOME
# =============================================================================


class TestRecordOutcome:
    """Tests for VectorStore.record_outcome()."""

    def test_record_success_updates_confidence(self, store):
        """Recording a success should increase the success_count."""
        vec = np.random.rand(24).astype(np.float32)
        vid = store.insert("test", vec, confidence=1.0)

        # First usage_count is 0 from insert, so search increments to 1
        store.search(vec, min_similarity=0.0)
        store.record_outcome(vid, success=True)

        # Confidence should be success_count / usage_count = 1/1 = 1.0
        results = store.search(vec, min_similarity=0.0)
        match = [r for r in results if r["id"] == vid]
        assert len(match) == 1
        assert match[0]["confidence"] == 1.0

    def test_record_failure_lowers_confidence(self, store):
        """Recording failures should decrease confidence over time."""
        vec = np.random.rand(24).astype(np.float32)
        vid = store.insert("test", vec, confidence=1.0)

        # Search to bump usage_count
        store.search(vec, min_similarity=0.0)
        store.search(vec, min_similarity=0.0)
        # Record one success and one failure
        store.record_outcome(vid, success=True)
        store.record_outcome(vid, success=False)

        results = store.search(vec, min_similarity=0.0)
        match = [r for r in results if r["id"] == vid]
        assert len(match) == 1
        # confidence = success_count / usage_count
        assert match[0]["confidence"] < 1.0

    def test_record_outcome_nonexistent_id(self, store):
        """Recording outcome for nonexistent ID should not raise."""
        # Should silently do nothing
        store.record_outcome("nonexistent-id", success=True)


# =============================================================================
# PRUNE
# =============================================================================


class TestPrune:
    """Tests for VectorStore.prune()."""

    def test_prune_removes_low_confidence(self, store):
        """Vectors below min_confidence should be removed."""
        vec_a = np.random.rand(24).astype(np.float32)
        vec_b = np.random.rand(24).astype(np.float32)
        store.insert("test", vec_a, confidence=0.1, vector_id="low")
        store.insert("test", vec_b, confidence=0.9, vector_id="high")

        removed = store.prune(min_confidence=0.5)
        assert removed == 1

        # Only high-confidence vector should remain
        stats = store.get_stats()
        assert stats["total_vectors"] == 1

    def test_prune_returns_count(self, store):
        """Prune should return the number of removed vectors."""
        for i in range(5):
            vec = np.random.rand(24).astype(np.float32)
            store.insert("test", vec, confidence=0.1, vector_id=f"low{i}")

        removed = store.prune(min_confidence=0.5)
        assert removed == 5

    def test_prune_respects_usage_count(self, store):
        """Vectors with usage above min_usage should be kept even if low confidence."""
        vec = np.random.rand(24).astype(np.float32)
        store.insert("test", vec, confidence=0.1, vector_id="used")

        # Bump usage via search
        store.search(vec, min_similarity=0.0)
        store.search(vec, min_similarity=0.0)

        # Prune with min_usage=1 should keep vectors with usage > 1
        removed = store.prune(min_confidence=0.5, min_usage=1)
        assert removed == 0

    def test_prune_empty_store(self, store):
        """Pruning an empty store should return 0."""
        removed = store.prune()
        assert removed == 0


# =============================================================================
# GET STATS
# =============================================================================


class TestGetStats:
    """Tests for VectorStore.get_stats()."""

    def test_stats_empty_store(self, store):
        """Empty store should report 0 vectors."""
        stats = store.get_stats()
        assert stats["total_vectors"] == 0
        assert stats["avg_confidence"] == 0
        assert stats["dimension"] == 24

    def test_stats_after_inserts(self, store):
        """Stats should reflect inserted vectors."""
        for i in range(3):
            vec = np.random.rand(24).astype(np.float32)
            store.insert("price_pattern", vec)
        for i in range(2):
            vec = np.random.rand(24).astype(np.float32)
            store.insert("recommendation", vec)

        stats = store.get_stats()
        assert stats["total_vectors"] == 5
        assert stats["domains"]["price_pattern"] == 3
        assert stats["domains"]["recommendation"] == 2

    def test_stats_domain_filter(self, store):
        """Stats with domain filter should count only that domain."""
        vec_a = np.random.rand(24).astype(np.float32)
        vec_b = np.random.rand(24).astype(np.float32)
        store.insert("alpha", vec_a)
        store.insert("beta", vec_b)

        stats = store.get_stats(domain="alpha")
        assert stats["total_vectors"] == 1


# =============================================================================
# DOMAIN-SPECIFIC HELPERS
# =============================================================================


class TestHelpers:
    """Tests for price_curve_to_vector and appliance_config_to_vector."""

    def test_price_curve_to_vector_correct_dim(self):
        """Output should have the target dimension."""
        prices = [0.20 + i * 0.01 for i in range(48)]
        vec = price_curve_to_vector(prices, target_dim=24)
        assert vec.shape == (24,)

    def test_price_curve_to_vector_normalized(self):
        """Output should be approximately unit-normalized."""
        prices = [0.20 + i * 0.01 for i in range(24)]
        vec = price_curve_to_vector(prices, target_dim=24)
        norm = np.linalg.norm(vec)
        assert abs(norm - 1.0) < 1e-5

    def test_price_curve_empty_returns_zeros(self):
        """Empty price list should return zero vector."""
        vec = price_curve_to_vector([], target_dim=24)
        assert np.all(vec == 0)

    def test_appliance_config_to_vector_correct_dim(self):
        """Output should have the target dimension."""
        configs = [
            {"power_kw": 1.5, "duration_hours": 2.0, "earliest_start": 6},
            {"power_kw": 0.8, "duration_hours": 1.0, "earliest_start": 18},
        ]
        vec = appliance_config_to_vector(configs, target_dim=24)
        assert vec.shape == (24,)

    def test_appliance_config_to_vector_empty(self):
        """Empty config list should return zero vector."""
        vec = appliance_config_to_vector([], target_dim=24)
        assert np.all(vec == 0)
