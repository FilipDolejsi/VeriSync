"""Tests for the personalised contextual bandit router (router/router.py)."""
import sqlite3
import sys
import uuid
from datetime import datetime, timezone

import numpy as np
import pytest

TEST_DB = "./test_router_pers.db"


# ── Helpers ────────────────────────────────────────────────────────────────────

def _fresh_modules():
    """Evict cached db.store + router + registry modules and reimport with TEST_DB.

    test_webhook.py stubs sys.modules["registry.loader"] with a MagicMock whose
    load_registry returns [].  Evicting it here forces a real re-import.
    """
    for k in list(sys.modules):
        if k in ("db", "db.store", "router", "router.router", "registry", "registry.loader"):
            del sys.modules[k]
    import db.store
    db.store.DB_PATH = TEST_DB
    return db.store


def _clear_tables():
    """Truncate test data without deleting the file (avoids Windows WinError 32)."""
    try:
        with sqlite3.connect(TEST_DB) as conn:
            conn.execute("DELETE FROM episodes")
            conn.execute("DELETE FROM chunks")
            conn.execute("DELETE FROM pull_requests")
            conn.commit()
    except Exception:
        pass


def _seed_user_episodes(
    db_path: str,
    user_id: str,
    repo_full_name: str,
    tier: int,
    n: int,
    registry,
):
    """Insert n passing episodes for a given user/repo/tier."""
    model = registry[tier]
    diff = "--- a/x.py\n+++ b/x.py\n@@ -1 +1 @@\n-old\n+new\n"
    with sqlite3.connect(db_path) as conn:
        for _ in range(n):
            pr_id = str(uuid.uuid4())
            cid   = str(uuid.uuid4())
            conn.execute(
                """
                INSERT OR IGNORE INTO pull_requests
                    (id, user_id, repo_full_name, pr_number, pr_title, pr_url,
                     trigger_type, status, started_at)
                VALUES (?, ?, ?, 0, '', '', 'seed', 'done', ?)
                """,
                (pr_id, user_id, repo_full_name, datetime.now(timezone.utc).isoformat()),
            )
            conn.execute(
                """
                INSERT OR IGNORE INTO chunks
                    (id, pr_id, file_path, hunk_index, language, lines_changed, diff_text)
                VALUES (?, ?, '', 0, 'python', 1, ?)
                """,
                (cid, pr_id, diff),
            )
            conn.execute(
                """
                INSERT INTO episodes
                    (id, chunk_id, user_id, repo_full_name, model_id, tier_index,
                     verifier_pass, cost_sats, finding_count, diff_text, timestamp)
                VALUES (?, ?, ?, ?, ?, ?, 1, ?, 1, ?, ?)
                """,
                (
                    str(uuid.uuid4()), cid,
                    user_id, repo_full_name,
                    model.id, tier, model.cost_sats, diff,
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
        conn.commit()


# ── Tests ──────────────────────────────────────────────────────────────────────

def test_cold_start_returns_valid_tier():
    """With no router model, predict_model returns a valid tier index without raising."""
    _fresh_modules()
    from registry.loader import load_registry
    from router.router import predict_model

    registry = load_registry()
    result = predict_model(
        task="def foo():\n+    pass",
        classifier_tag="style",
        registry=registry,
        language="python",
        lines_changed=2,
        file_path="utils.py",
        user_id="unknown-user",
        repo_full_name="unknown/repo",
    )

    assert "model_id"   in result
    assert "tier_index" in result
    assert 0 <= result["tier_index"] < len(registry)


def test_feature_vector_shape():
    """_build_features returns a 1-D numpy array that includes user/repo embedding slots."""
    _fresh_modules()
    from registry.loader import load_registry
    from router.router import _build_features, USER_REPO_EMBED_DIM

    registry = load_registry()
    vec = _build_features(
        text="def foo(): pass",
        tag="style",
        registry=registry,
        language="python",
        lines_changed=3,
        file_path="utils.py",
        user_embedding=None,
        repo_embedding=None,
    )

    assert isinstance(vec, np.ndarray)
    assert vec.ndim == 1
    # Vector must contain at least both user + repo embedding slots
    assert vec.shape[0] >= 2 * USER_REPO_EMBED_DIM


@pytest.mark.asyncio
async def test_personalisation_after_seeding():
    """After seeding alice (high-tier security) and bob (low-tier style), the router
    should predict a higher tier for alice than for bob once trained."""
    store = _fresh_modules()
    await store.init_db()
    _clear_tables()

    from registry.loader import load_registry
    registry = load_registry()

    high_tier = min(4, len(registry) - 1)   # tier 4 = gemini-flash (security)
    low_tier  = 0                            # tier 0 = llama3-8b (style)

    # Need >= MIN_EPISODES_PERSONAL (5) per entity to get personalised embeddings
    _seed_user_episodes(TEST_DB, "user_alice", "alice/fintech-app", high_tier, 6, registry)
    _seed_user_episodes(TEST_DB, "user_bob",   "bob/personal-blog", low_tier,  6, registry)

    from router.router import train_router, predict_model

    result = train_router(registry)
    # Training may return {} if sklearn is unavailable or single-class; skip prediction in that case
    if not result:
        pytest.skip("train_router returned no artefact (single class or missing dependency)")

    alice_result = predict_model(
        task=(
            "--- a/auth.py\n+++ b/auth.py\n@@ -1 +1 @@\n"
            "-token = user_id\n+token = secrets.token_urlsafe(32)"
        ),
        classifier_tag="security",
        registry=registry,
        language="python",
        lines_changed=2,
        file_path="auth.py",
        user_id="user_alice",
        repo_full_name="alice/fintech-app",
    )
    bob_result = predict_model(
        task="--- a/style.py\n+++ b/style.py\n@@ -1 +1 @@\n-def Foo(): pass\n+def foo(): pass",
        classifier_tag="style",
        registry=registry,
        language="python",
        lines_changed=1,
        file_path="style.py",
        user_id="user_bob",
        repo_full_name="bob/personal-blog",
    )

    assert 0 <= alice_result["tier_index"] < len(registry)
    assert 0 <= bob_result["tier_index"] < len(registry)
    # After personalisation alice (security) should route to an equal or higher tier than bob (style)
    assert alice_result["tier_index"] >= bob_result["tier_index"]
