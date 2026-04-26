"""Tests for the reputation system (db/store.py reputation queries)."""
import sqlite3
import sys
import uuid
from datetime import datetime, timezone

import pytest

TEST_DB = "./test_reputation.db"


# ── Helpers ────────────────────────────────────────────────────────────────────

def _fresh_store():
    """Evict cached db.store module and reimport with TEST_DB."""
    for k in list(sys.modules):
        if k in ("db", "db.store"):
            del sys.modules[k]
    import db.store
    db.store.DB_PATH = TEST_DB
    return db.store


def _clear_tables():
    """Truncate test tables between tests.

    Avoids os.remove() which raises PermissionError on Windows when an aiosqlite
    connection from the previous test hasn't fully released the file handle yet.
    """
    try:
        with sqlite3.connect(TEST_DB) as conn:
            conn.execute("DELETE FROM episodes")
            conn.execute("DELETE FROM chunks")
            conn.execute("DELETE FROM pull_requests")
            conn.commit()
    except Exception:
        pass  # tables don't exist yet on the very first run


def _seed_episodes(db_path: str, model_id: str, rows: list[dict]):
    """Insert minimal pull_request + chunk + episode rows for reputation tests."""
    with sqlite3.connect(db_path) as conn:
        pr_id = str(uuid.uuid4())
        conn.execute(
            """
            INSERT OR IGNORE INTO pull_requests
                (id, user_id, repo_full_name, pr_number, pr_title, pr_url,
                 trigger_type, status, started_at)
            VALUES (?, 'u1', 'r/repo', 0, '', '', 'seed', 'done', ?)
            """,
            (pr_id, datetime.now(timezone.utc).isoformat()),
        )
        for row in rows:
            cid = str(uuid.uuid4())
            conn.execute(
                """
                INSERT OR IGNORE INTO chunks
                    (id, pr_id, file_path, hunk_index, language, lines_changed)
                VALUES (?, ?, '', 0, 'python', 1)
                """,
                (cid, pr_id),
            )
            conn.execute(
                """
                INSERT INTO episodes
                    (id, chunk_id, user_id, model_id, tier_index,
                     verifier_pass, cost_sats, finding_count, timestamp)
                VALUES (?, ?, 'u1', ?, 0, ?, ?, ?, ?)
                """,
                (
                    str(uuid.uuid4()), cid, model_id,
                    row["verifier_pass"], row["cost_sats"], row["finding_count"],
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
        conn.commit()


# ── Tests ──────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_reputation_empty_db_defaults():
    """A model with no episodes gets safe defaults: pass_rate=0.5, effective_cost=cost_sats."""
    store = _fresh_store()
    await store.init_db()
    _clear_tables()

    rep = await store.get_model_reputation("unknown-model", default_cost_sats=40.0)

    assert rep["model_id"] == "unknown-model"
    assert rep["total_reviews"] == 0
    assert rep["pass_rate"] == 0.5
    assert rep["effective_cost"] == 40.0
    assert 0.0 <= rep["reputation_score"] <= 1.0


@pytest.mark.asyncio
async def test_reputation_calculation():
    """Verify effective_cost = avg_cost / pass_rate with seeded episodes."""
    store = _fresh_store()
    await store.init_db()
    _clear_tables()

    # 4 episodes: 3 pass, 1 fail; cost 10 each; 2 findings per passing episode
    _seed_episodes(TEST_DB, "gemini-flash", [
        {"verifier_pass": 1, "cost_sats": 10, "finding_count": 2},
        {"verifier_pass": 1, "cost_sats": 10, "finding_count": 2},
        {"verifier_pass": 1, "cost_sats": 10, "finding_count": 2},
        {"verifier_pass": 0, "cost_sats": 10, "finding_count": 0},
    ])

    rep = await store.get_model_reputation("gemini-flash", default_cost_sats=40.0)

    assert rep["total_reviews"] == 4
    assert abs(rep["pass_rate"] - 0.75) < 0.01
    assert abs(rep["avg_cost_sats"] - 10.0) < 0.01
    # effective_cost = 10 / 0.75 ≈ 13.33
    assert abs(rep["effective_cost"] - (10.0 / 0.75)) < 0.1
    assert 0.0 <= rep["reputation_score"] <= 1.0


@pytest.mark.asyncio
async def test_reputation_sort_by_effective_cost():
    """get_all_model_reputations: cheap high-quality model has lower effective_cost than pricey flaky one."""
    store = _fresh_store()
    await store.init_db()
    _clear_tables()

    # cheap-model: perfect pass rate → effective_cost = 5 / 1.0 = 5
    _seed_episodes(TEST_DB, "cheap-model", [
        {"verifier_pass": 1, "cost_sats": 5, "finding_count": 1},
        {"verifier_pass": 1, "cost_sats": 5, "finding_count": 1},
    ])
    # pricey-model: 50% pass rate → effective_cost = 50 / 0.5 = 100
    _seed_episodes(TEST_DB, "pricey-model", [
        {"verifier_pass": 1, "cost_sats": 50, "finding_count": 1},
        {"verifier_pass": 0, "cost_sats": 50, "finding_count": 0},
    ])

    all_reps = await store.get_all_model_reputations()
    by_id = {r["model_id"]: r for r in all_reps}

    assert "cheap-model"  in by_id
    assert "pricey-model" in by_id
    assert by_id["cheap-model"]["effective_cost"] < by_id["pricey-model"]["effective_cost"]
