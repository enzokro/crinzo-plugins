"""Tests for Fix 2+3: Causal feedback filtering and non-causal erosion.

Verifies:
- filter_causal_insights() filters by semantic similarity to task context
- feedback() dual-path: causal insights get EMA, non-causal erode toward 0.5
- causal_hits column tracks causal attribution
"""

import json
import os

import pytest


@pytest.fixture(autouse=True)
def isolated_db(tmp_path):
    """Each test gets its own isolated database."""
    db_path = str(tmp_path / "test.db")
    os.environ["HELIX_DB_PATH"] = db_path

    import lib.db.connection as conn_module
    conn_module.DB_PATH = db_path
    conn_module.reset_db()

    yield db_path

    conn_module.reset_db()
    if "HELIX_DB_PATH" in os.environ:
        del os.environ["HELIX_DB_PATH"]


class TestDualPathFeedback:
    """Tests for causal vs non-causal feedback paths."""

    def test_causal_insight_gets_ema_update(self):
        """Causally relevant insights receive standard EMA update."""
        from lib.memory.core import store, feedback, get

        result = store("When testing TypeScript exports, verify barrel file re-exports", tags=["ts"])
        name = result["name"]

        initial = get(name)
        assert initial["effectiveness"] == 0.5

        feedback([name], "delivered", causal_names=[name])

        updated = get(name)
        # EMA: 0.5 * 0.9 + 1.0 * 0.1 = 0.55
        assert abs(updated["effectiveness"] - 0.55) < 0.01
        assert updated["causal_hits"] == 1

    def test_non_causal_insight_erodes_toward_neutral(self):
        """Non-causal insights erode 10% toward 0.5."""
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
        # Erosion: 0.75 + (0.5 - 0.75) * 0.10 = 0.75 - 0.025 = 0.725
        assert abs(updated["effectiveness"] - 0.725) < 0.01
        assert updated["causal_hits"] == 0

    def test_none_causal_names_treats_all_as_causal(self):
        """causal_names=None means backward compatible: all treated as causal."""
        from lib.memory.core import store, feedback, get

        result = store("When deploying services, check health endpoints first", tags=["deploy"])
        name = result["name"]

        feedback([name], "delivered", causal_names=None)

        updated = get(name)
        # Standard EMA: 0.5 * 0.9 + 1.0 * 0.1 = 0.55
        assert abs(updated["effectiveness"] - 0.55) < 0.01
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
        """Multiple erosion cycles bring entrenched insight near 0.5."""
        from lib.memory.core import store, feedback, get
        from lib.db.connection import get_db, write_lock

        result = store("Generic middleware pattern advice that keeps getting injected", tags=["generic"])
        name = result["name"]

        db = get_db()
        with write_lock():
            db.execute("UPDATE insight SET effectiveness=0.75 WHERE name=?", (name,))
            db.commit()

        # Simulate 11 non-causal injections (like eval scenario)
        for _ in range(11):
            feedback([name], "delivered", causal_names=[])

        updated = get(name)
        # After 11 erosions of 10% toward 0.5: 0.75 → ~0.578
        # Each step: eff = eff + (0.5 - eff) * 0.10
        # Significantly lower than starting 0.75, moving toward neutral
        assert updated["effectiveness"] < 0.62
        assert updated["effectiveness"] > 0.55

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


class TestCausalHitsSchema:
    """Tests for causal_hits column in schema."""

    def test_schema_v6_has_causal_hits(self):
        """Schema v6 includes causal_hits column."""
        from lib.db.connection import get_db

        db = get_db()
        cursor = db.execute("PRAGMA table_info(insight)")
        columns = {row[1] for row in cursor.fetchall()}
        assert "causal_hits" in columns

    def test_to_dict_includes_causal_hits(self):
        """_to_dict includes causal_hits field."""
        from lib.memory.core import store, get

        result = store("When testing auth flows, verify token expiry edge cases", tags=["auth"])
        insight = get(result["name"])

        assert "causal_hits" in insight
        assert insight["causal_hits"] == 0


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

        # r1 gets causal feedback, r2 gets non-causal erosion
        feedback([r1["name"], r2["name"]], "delivered", causal_names=[r1["name"]])

        h = health()
        assert "causal_ratio" in h
        # 1 causal hit / 2 total use_count = 0.5
        assert h["causal_ratio"] == 0.5
