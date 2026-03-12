"""Tests for Fix 2+3: Causal feedback filtering and non-causal erosion.

Verifies:
- filter_causal_insights() filters by semantic similarity to task context
- feedback() dual-path: causal insights get EMA, non-causal erode toward 0.5
- causal_hits column tracks causal attribution
"""

import pytest


pytestmark = pytest.mark.usefixtures("isolated_db")


class TestDualPathFeedback:
    """Tests for causal vs non-causal feedback paths."""

    def test_causal_insight_gets_ema_update(self):
        """Causally relevant insights receive standard EMA update — effectiveness increases."""
        from lib.memory.core import store, feedback, get

        result = store("When testing TypeScript exports, verify barrel file re-exports", tags=["ts"])
        name = result["name"]

        initial = get(name)
        assert initial["effectiveness"] == 0.5

        feedback([name], "delivered", causal_names=[name])

        updated = get(name)
        # Directional: positive causal feedback increases effectiveness above neutral
        assert updated["effectiveness"] > 0.5
        assert updated["causal_hits"] == 1

    def test_non_causal_insight_erodes_toward_neutral(self):
        """Non-causal insights erode toward 0.5 but stay above it."""
        from lib.memory.core import store, feedback, get
        from lib.db.connection import get_db, write_lock

        result = store("When implementing middleware pipeline, use compose pattern", tags=["middleware"])
        name = result["name"]

        # Artificially set effectiveness to 0.75 (entrenched generic)
        db = get_db()
        with write_lock():
            db.execute("UPDATE insight SET effectiveness=0.75 WHERE name=?", (name,))
            db.commit()

        # Feedback with empty causal_names means this insight is non-causal
        feedback([name], "delivered", causal_names=[])

        updated = get(name)
        # Directional: eroded below 0.75, still above neutral 0.5
        assert updated["effectiveness"] < 0.75
        assert updated["effectiveness"] > 0.5
        assert updated["causal_hits"] == 0

    def test_none_causal_names_treats_all_as_causal(self):
        """causal_names=None means backward compatible: all treated as causal."""
        from lib.memory.core import store, feedback, get

        result = store("When deploying services, check health endpoints first", tags=["deploy"])
        name = result["name"]

        feedback([name], "delivered", causal_names=None)

        updated = get(name)
        # Standard EMA: 0.5 * 0.8 + 1.0 * 0.2 = 0.60
        assert abs(updated["effectiveness"] - 0.60) < 0.01
        assert updated["causal_hits"] == 1

    def test_mixed_causal_and_non_causal(self):
        """Mix of causal and non-causal insights in same feedback call."""
        from lib.memory.core import store, feedback, get

        r1 = store("When testing TypeScript exports, verify barrel re-exports", tags=["ts"])
        r2 = store("When cooking pasta, use salted boiling water for best taste", tags=["cooking"])
        name_ts = r1["name"]
        name_cook = r2["name"]

        result = feedback(
            [name_ts, name_cook],
            "delivered",
            causal_names=[name_ts]  # only TS insight is causal
        )

        assert result["causal"] == 1
        assert result["eroded"] == 1

        ts = get(name_ts)
        cook = get(name_cook)
        assert ts["causal_hits"] == 1
        assert cook["causal_hits"] == 0

    def test_erosion_converges_entrenched_to_neutral(self):
        """Multiple erosion cycles bring entrenched insight closer to 0.5 than it started."""
        from lib.memory.core import store, feedback, get
        from lib.db.connection import get_db, write_lock

        result = store("Generic middleware pattern advice that keeps getting injected", tags=["generic"])
        name = result["name"]

        start_eff = 0.75
        db = get_db()
        with write_lock():
            db.execute("UPDATE insight SET effectiveness=? WHERE name=?", (start_eff, name))
            db.commit()

        # Simulate 11 non-causal injections (like eval scenario)
        for _ in range(11):
            feedback([name], "delivered", causal_names=[])

        updated = get(name)
        # Directional: closer to neutral than starting point, still above 0.5
        assert abs(updated["effectiveness"] - 0.5) < abs(start_eff - 0.5)
        assert updated["effectiveness"] > 0.5

    def test_feedback_return_includes_causal_breakdown(self):
        """Feedback return dict includes causal and eroded counts."""
        from lib.memory.core import store, feedback

        r1 = store("Insight A: TypeScript barrel exports need index.ts updates", tags=["ts"])
        r2 = store("Insight B: Generic middleware pipeline composition pattern", tags=["generic"])

        result = feedback(
            [r1["name"], r2["name"]],
            "delivered",
            causal_names=[r1["name"]]
        )

        assert "causal" in result
        assert "eroded" in result
        assert result["causal"] == 1
        assert result["eroded"] == 1


class TestPartialOutcomeFeedback:
    """Tests for PARTIAL outcome feedback — an intermediate outcome value."""

    def test_partial_outcome_produces_feedback(self):
        """PARTIAL outcomes should produce feedback (previously they were silently skipped)."""
        from lib.memory.core import store, feedback, get

        result = store("When configuring webpack, check resolve.alias paths", tags=["webpack"])
        name = result["name"]

        fb = feedback([name], "partial", causal_names=[name])

        assert fb["updated"] == 1
        updated = get(name)
        # EMA: 0.5 * 0.8 + 0.3 * 0.2 = 0.46
        assert abs(updated["effectiveness"] - 0.46) < 0.01
        assert updated["causal_hits"] == 1
        assert updated["use_count"] == 1

    def test_partial_outcome_less_negative_than_blocked(self):
        """PARTIAL (0.3) should cause less effectiveness decline than BLOCKED (0.0)."""
        from lib.memory.core import store, feedback, get

        r_partial = store("Insight for partial test scenario with webpack config", tags=["test"])
        r_blocked = store("Insight for blocked test scenario with database setup", tags=["test"])

        feedback([r_partial["name"]], "partial", causal_names=[r_partial["name"]])
        feedback([r_blocked["name"]], "blocked", causal_names=[r_blocked["name"]])

        partial_eff = get(r_partial["name"])["effectiveness"]
        blocked_eff = get(r_blocked["name"])["effectiveness"]

        # PARTIAL (0.3) should leave higher effectiveness than BLOCKED (0.0)
        # partial: 0.5*0.8 + 0.3*0.2 = 0.46
        # blocked: 0.5*0.8 + 0.0*0.2 = 0.40
        assert partial_eff > blocked_eff

    def test_partial_non_causal_erodes(self):
        """Non-causal insights during PARTIAL outcome should erode like any other outcome."""
        from lib.memory.core import store, feedback, get
        from lib.db.connection import get_db, write_lock

        result = store("Generic advice that was present during partial completion", tags=["generic"])
        name = result["name"]

        db = get_db()
        with write_lock():
            db.execute("UPDATE insight SET effectiveness=0.70 WHERE name=?", (name,))
            db.commit()

        feedback([name], "partial", causal_names=[])

        updated = get(name)
        # Eroded from 0.70 toward 0.5
        assert updated["effectiveness"] < 0.70
        assert updated["effectiveness"] > 0.50
        assert updated["causal_hits"] == 0


    def test_feedback_error_message_lists_all_outcomes(self):
        """Invalid outcome error message should enumerate all valid outcomes including partial."""
        from lib.memory.core import feedback

        result = feedback(["fake"], "invalid")

        assert "error" in result
        assert result["updated"] == 0
        assert "partial" in result["error"]

    def test_cli_choices_include_partial(self):
        """OUTCOME_VALUES contract: 'partial' is a valid outcome key."""
        from lib.memory.core import OUTCOME_VALUES

        assert "partial" in OUTCOME_VALUES
        assert OUTCOME_VALUES["partial"] == 0.3


class TestCausalHitsSchema:
    """Tests for causal_hits column in schema."""

    # test_schema_v6_has_causal_hits removed: schema introspection via PRAGMA;
    # implicitly covered by every functional test that reads causal_hits

    def test_to_dict_includes_causal_hits(self):
        """_to_dict includes causal_hits field."""
        from lib.memory.core import store, get

        result = store("When testing auth flows, verify token expiry edge cases", tags=["auth"])
        insight = get(result["name"])

        assert "causal_hits" in insight
        assert insight["causal_hits"] == 0


class TestWeightedAttribution:
    """Test similarity-weighted feedback updates."""

    def test_high_similarity_nearly_full_update(self, isolated_db):
        """Insight at similarity 0.95 gets nearly full EMA update."""
        from lib.memory.core import store, feedback, get
        name = store("High sim test insight for weighted attribution testing purposes")["name"]
        # Pre-set effectiveness
        from lib.db.connection import get_db
        get_db().execute("UPDATE insight SET effectiveness=0.5, use_count=1 WHERE name=?", (name,))
        get_db().commit()
        feedback([name], "delivered", causal_names=[(name, 0.95)])
        result = get(name)
        # weight = (0.95 - 0.50) / (1.0 - 0.50) = 0.90
        # new_eff = 0.5 * (1 - 0.2*0.90) + 1.0 * 0.2*0.90 = 0.5*0.82 + 0.18 = 0.59
        assert result["effectiveness"] > 0.55  # significant update

    def test_low_similarity_minimal_update(self, isolated_db):
        """Insight at similarity 0.51 gets minimal EMA update."""
        from lib.memory.core import store, feedback, get
        name = store("Low sim test insight for weighted attribution testing purposes here")["name"]
        from lib.db.connection import get_db
        get_db().execute("UPDATE insight SET effectiveness=0.5, use_count=1 WHERE name=?", (name,))
        get_db().commit()
        feedback([name], "delivered", causal_names=[(name, 0.51)])
        result = get(name)
        # weight = (0.51 - 0.50) / 0.50 = 0.02
        # new_eff = 0.5 * (1 - 0.2*0.02) + 1.0 * 0.2*0.02 = 0.5*0.996 + 0.004 = 0.502
        assert 0.49 < result["effectiveness"] < 0.51  # near-zero change

    def test_threshold_exact_no_change(self, isolated_db):
        """Insight at exactly threshold similarity gets zero weight."""
        from lib.memory.core import store, feedback, get
        name = store("Threshold exact test insight for weighted attribution here now")["name"]
        from lib.db.connection import get_db
        get_db().execute("UPDATE insight SET effectiveness=0.5, use_count=1 WHERE name=?", (name,))
        get_db().commit()
        feedback([name], "delivered", causal_names=[(name, 0.50)])
        result = get(name)
        # weight = 0.0 -> no change
        assert result["effectiveness"] == 0.5

    def test_backward_compat_string_list(self, isolated_db):
        """String list (old format) still works with full weight."""
        from lib.memory.core import store, feedback, get
        name = store("Backward compat test insight for old string list format testing")["name"]
        from lib.db.connection import get_db
        get_db().execute("UPDATE insight SET effectiveness=0.5, use_count=1 WHERE name=?", (name,))
        get_db().commit()
        feedback([name], "delivered", causal_names=[name])
        result = get(name)
        # weight = 1.0 (string list -> all get full EMA)
        # new_eff = 0.5 * 0.8 + 1.0 * 0.2 = 0.6
        assert abs(result["effectiveness"] - 0.6) < 0.01


class TestHealthCausalRatio:
    """Tests for causal_ratio in health()."""

    def test_health_includes_causal_ratio(self):
        """health() reports causal_ratio metric."""
        from lib.memory.core import store, feedback, health

        r = store("When testing auth, verify token expiry", tags=["auth"])
        feedback([r["name"]], "delivered", causal_names=[r["name"]])

        h = health()
        assert "causal_ratio" in h
        assert h["causal_ratio"] == 1.0  # all feedback was causal

    def test_health_causal_ratio_with_mixed(self):
        """causal_ratio reflects mix of causal and non-causal feedback."""
        from lib.memory.core import store, feedback, health

        r1 = store("Insight one about TypeScript testing patterns", tags=["ts"])
        r2 = store("Insight two about database migration strategies", tags=["db"])

        # r1 gets causal feedback (use_count+1, causal_hits+1)
        # r2 gets non-causal erosion (use_count unchanged — erosion is the penalty)
        feedback([r1["name"], r2["name"]], "delivered", causal_names=[r1["name"]])

        h = health()
        assert "causal_ratio" in h
        # 1 causal hit / 1 use_count (non-causal doesn't increment use_count)
        assert h["causal_ratio"] == 1.0


class TestVelocityDecayReset:
    """Test that decay resets stale velocity."""

    def test_decay_resets_old_velocity(self, isolated_db):
        from lib.memory.core import store, feedback, get, decay
        r = store("Velocity decay reset test insight about checking staleness here")
        name = r["name"]
        # Give feedback to set recent_uses
        feedback([name], "delivered", causal_names=[(name, 0.90)])
        assert get(name)["recent_uses"] == 1
        # Manually set last_feedback_at to 20 days ago
        from lib.db.connection import get_db
        from datetime import datetime, timedelta
        old_date = (datetime.utcnow() - timedelta(days=20)).isoformat()
        get_db().execute("UPDATE insight SET last_feedback_at=?, last_used=? WHERE name=?", (old_date, old_date, name))
        get_db().commit()
        # Decay should reset velocity
        decay(unused_days=0)  # unused_days=0 to also trigger the main decay
        result = get(name)
        assert result["recent_uses"] == 0


class TestKnowledgeGenerality:
    """Test context spread tracking and generality-modulated decay."""

    def _make_embedding(self, seed):
        """Create a deterministic embedding from a seed."""
        import struct
        import hashlib
        h = hashlib.sha256(str(seed).encode()).digest()
        emb = []
        for i in range(256):
            emb.append((h[i % 32] + i * seed) / 255.0 - 0.5)
        # Normalize
        norm = sum(x*x for x in emb) ** 0.5
        emb = [x / norm for x in emb]
        return struct.pack(f"{len(emb)}f", *emb)

    def test_first_context_sets_centroid(self, test_db, mock_embeddings):
        from lib.memory.core import store, feedback, get
        from lib.db.connection import get_db
        r = store("Context spread first event test insight about generality scoring")
        name = r["name"]
        emb = self._make_embedding(1)
        feedback([name], "delivered", causal_names=[(name, 0.90)], context_embedding=emb)
        row = get_db().execute("SELECT context_spread, context_centroid FROM insight WHERE name=?", (name,)).fetchone()
        assert row["context_spread"] == 0.0
        assert row["context_centroid"] is not None

    def test_diverse_contexts_increase_spread(self, test_db, mock_embeddings):
        from lib.memory.core import store, feedback, get
        from lib.db.connection import get_db
        r = store("Context spread diverse test insight about generality accumulation here")
        name = r["name"]
        # Feed with diverse context embeddings
        for i in range(5):
            emb = self._make_embedding(i * 100)  # Very different seeds
            feedback([name], "delivered", causal_names=[(name, 0.90)], context_embedding=emb)
        row = get_db().execute("SELECT context_spread FROM insight WHERE name=?", (name,)).fetchone()
        assert row["context_spread"] is not None
        assert row["context_spread"] > 0  # Diverse contexts -> positive spread

    def test_identical_contexts_low_spread(self, test_db, mock_embeddings):
        from lib.memory.core import store, feedback, get
        from lib.db.connection import get_db
        r = store("Context spread identical test insight checking narrow contexts here")
        name = r["name"]
        emb = self._make_embedding(42)  # Same embedding every time
        for i in range(5):
            feedback([name], "delivered", causal_names=[(name, 0.90)], context_embedding=emb)
        row = get_db().execute("SELECT context_spread FROM insight WHERE name=?", (name,)).fetchone()
        # Same context repeatedly -> spread stays near 0
        assert row["context_spread"] is not None
        assert row["context_spread"] < 0.01

    def test_general_insight_decays_slower(self, test_db, mock_embeddings):
        from lib.memory.core import store, decay, get
        from lib.db.connection import get_db
        # Store two insights with same effectiveness
        r1 = store("General insight about patterns that apply across many contexts here")
        r2 = store("Narrow insight about one specific thing that rarely applies at all")
        # Set both to effectiveness 0.8 and use_count > 0
        get_db().execute("UPDATE insight SET effectiveness=0.8, use_count=5 WHERE name=?", (r1["name"],))
        get_db().execute("UPDATE insight SET effectiveness=0.8, use_count=5 WHERE name=?", (r2["name"],))
        # Give r1 high context_spread (general), r2 low spread (narrow)
        get_db().execute("UPDATE insight SET context_spread=0.25 WHERE name=?", (r1["name"],))
        get_db().execute("UPDATE insight SET context_spread=0.01 WHERE name=?", (r2["name"],))
        get_db().commit()
        decay(unused_days=0)
        g1 = get(r1["name"])
        g2 = get(r2["name"])
        # General insight should have decayed less
        assert g1["effectiveness"] > g2["effectiveness"]
