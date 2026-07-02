"""Unit tests for the pure helpers in app.services.health.

The DB-backed aggregation is exercised end-to-end against a live corpus; these
tests pin the pure logic (clustering, text staleness, scoring) that has no
database dependency.
"""

from app.services.health import (
    cluster_pairs,
    completeness,
    divergence_summary,
    health_score,
    text_staleness_reasons,
)


class TestClusterPairs:
    def test_empty(self):
        assert cluster_pairs([]) == []

    def test_transitive_merge(self):
        # a-b and b-c must collapse into one 3-member cluster.
        clusters = cluster_pairs([("a", "b"), ("b", "c")])
        assert len(clusters) == 1
        assert clusters[0] == ["a", "b", "c"]

    def test_disjoint_clusters_sorted_largest_first(self):
        clusters = cluster_pairs([("a", "b"), ("a", "c"), ("x", "y")])
        assert [len(c) for c in clusters] == [3, 2]
        assert clusters[0] == ["a", "b", "c"]
        assert clusters[1] == ["x", "y"]

    def test_singletons_excluded(self):
        # Only the referenced pair forms a cluster.
        clusters = cluster_pairs([("a", "b")])
        assert clusters == [["a", "b"]]


class TestTextStaleness:
    def test_clean_text_has_no_reasons(self):
        assert text_staleness_reasons("how to reverse a list", "reversed(x)") == []

    def test_dated_as_of_year_flagged(self):
        reasons = text_staleness_reasons("Rate limits as of 2023 were 500 RPM", "")
        assert any("dated data" in r for r in reasons)

    def test_future_as_of_year_not_flagged(self):
        # "as of 2026" is not behind the dated-year ceiling.
        assert text_staleness_reasons("pricing as of 2026", "") == []

    def test_asof_with_month_flagged(self):
        # Sentinel's regex tolerates an intervening month token.
        reasons = text_staleness_reasons("", "quota as of June 2023 was 500 RPM")
        assert any("dated data" in r for r in reasons)

    def test_outdated_version_pin_flagged(self):
        # Explicit operator + below current major (pydantic v2) => stale.
        reasons = text_staleness_reasons("", "requires pydantic==1.8 for this")
        assert any("outdated version pin" in r for r in reasons)

    def test_current_major_pin_not_flagged(self):
        # Pinning to the current major is normal, not rot.
        assert text_staleness_reasons("", "use sqlalchemy==2.0") == []

    def test_bare_version_mention_not_flagged(self):
        # No operator => comparative prose, not a dependency pin (no FP).
        assert text_staleness_reasons("migrating from Pydantic v1 to v2", "") == []

    def test_deprecation_language_not_flagged(self):
        # Deprecation wording describes the topic, not age — deliberately no FP.
        assert text_staleness_reasons("", "orm_mode is deprecated in v2") == []


class TestCompleteness:
    def test_richer_trace_scores_higher(self):
        rich = completeness("x" * 1500, has_code=True, tag_count=5)
        poor = completeness("short", has_code=False, tag_count=0)
        assert rich > poor
        assert rich == 3.0  # 1.0 length + 1.0 code + 1.0 tags, all capped

    def test_code_block_beats_no_code_all_else_equal(self):
        with_code = completeness("same length text", has_code=True, tag_count=1)
        without = completeness("same length text", has_code=False, tag_count=1)
        assert with_code == without + 1.0


class TestDivergenceSummary:
    def test_distinct_approaches_contrast(self):
        summary = divergence_summary(
            "use redis lock acquire redis redis", "use postgres advisory_lock postgres"
        )
        assert "A favors" in summary and "B favors" in summary
        assert "redis" in summary and "postgres" in summary

    def test_shared_vocabulary_falls_back(self):
        summary = divergence_summary("identical tokens here", "identical tokens here")
        assert "review manually" in summary


class TestHealthScore:
    def test_empty_corpus_is_perfect(self):
        assert health_score(total=0, stale=0, flagged=0, conflicts=0, duplicate_traces=0) == 100

    def test_pristine_corpus_is_perfect(self):
        assert health_score(total=100, stale=0, flagged=0, conflicts=0, duplicate_traces=0) == 100

    def test_stale_and_flagged_reduce_score(self):
        score = health_score(total=100, stale=50, flagged=20, conflicts=0, duplicate_traces=0)
        assert score < 100
        assert 0 <= score <= 100

    def test_score_never_negative(self):
        # Worst case: every ratio maxed + conflict penalty capped. Raw floor is
        # 100 - 30 - 25 - 20 - 15 = 10, and the max(0, ...) clamp guarantees >= 0.
        score = health_score(total=10, stale=10, flagged=10, conflicts=10, duplicate_traces=10)
        assert score >= 0

    def test_conflicts_penalty_is_capped(self):
        # 10 and 1000 conflicts both cap the conflict penalty at 15 points.
        a = health_score(total=1000, stale=0, flagged=0, conflicts=10, duplicate_traces=0)
        b = health_score(total=1000, stale=0, flagged=0, conflicts=1000, duplicate_traces=0)
        assert a == b == 85
