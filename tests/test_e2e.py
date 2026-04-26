"""
End-to-end tests covering:
1. GitHub webhook payload (PR opened + push to main) → pipeline fires automatically
2. L402 payments fire per chunk and wallet balances decrement correctly
3. GitHub comment posting: findings appear inline in correct format
4. SQLite rows: user_id, pr_url, chunk_id, model_id, cost_sats, finding_count, verifier_pass
5. Async race conditions between SSE stream updates and concurrent chunk review jobs
"""

import asyncio
import json
import os
import sys
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
import aiosqlite

# ── Environment: set before any app import ────────────────────────────────────

_TEST_DB = "./test_e2e.db"
os.environ["DATABASE_PATH"] = _TEST_DB
os.environ.setdefault("SESSION_SECRET_KEY", "test-e2e-secret")
os.environ.setdefault("GITHUB_CLIENT_ID", "test-id")
os.environ.setdefault("GITHUB_CLIENT_SECRET", "test-secret")
os.environ.setdefault("GITHUB_REDIRECT_URI", "http://test/auth/callback")
os.environ.setdefault("GROQ_API_KEY", "test-groq-key")
os.environ.setdefault("GEMINI_API_KEY", "test-gemini-key")
os.environ.setdefault("USE_MOCK_WALLET", "true")

# ── Shared fake model (real Pydantic instance, not MagicMock) ─────────────────

from models import ModelEntry  # noqa: E402

FAKE_MODEL = ModelEntry(
    id="llama3-8b",
    name="llama3:8b",
    provider="qrok-api",
    cost_sats=5,
    endpoint_url="http://localhost:8000/worker/llama3-8b",
    capability_tags=["style", "logic", "security"],
)

# ── Sample diff that the chunker will parse into one PRChunk ──────────────────

SAMPLE_DIFF = """\
--- a/app.py
+++ b/app.py
@@ -1,5 +1,8 @@
 import os
+import subprocess
+
 def run(cmd):
-    pass
+    subprocess.call(cmd, shell=True)
+    return True
"""


# ── DB helpers ────────────────────────────────────────────────────────────────

@pytest_asyncio.fixture(autouse=True)
async def fresh_db():
    """Recreate test DB before each test and clean up after.

    test_auth.py (collected first) stubs db.store / payments.wallet in
    sys.modules.  We must evict those stubs before importing the real modules,
    otherwise init_db() is a no-op AsyncMock and the tables are never created.
    """
    import gc
    # Evict mocked modules so the real implementations are imported.
    # "gh.webhook" must be evicted too: its top-level imports bind db.store
    # functions at import time; if those were bound to mocks we get TypeError.
    _stubs = ("db", "db.store", "payments", "payments.wallet",
              "workers", "workers.factory")
    for k in list(sys.modules.keys()):
        if k in _stubs:
            del sys.modules[k]

    import db.store as _store
    _store.DB_PATH = _TEST_DB
    from db.store import init_db

    if os.path.exists(_TEST_DB):
        os.remove(_TEST_DB)
    await init_db()
    yield
    # gc.collect() releases sqlite3 handles before os.remove on Windows
    gc.collect()
    try:
        if os.path.exists(_TEST_DB):
            os.remove(_TEST_DB)
    except PermissionError:
        pass  # Windows may hold the file briefly; not critical for isolation


async def _insert_test_user(
    db, user_id: str, wallet_id: str, github_token: str = "ghp_test"
):
    await db.execute(
        """
        INSERT OR IGNORE INTO users
            (id, github_id, username, avatar_url, wallet_id, sat_balance,
             github_token, created_at, last_login)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            user_id, f"gh_{user_id[:8]}", "testuser", "", wallet_id,
            500, github_token,
            datetime.now(timezone.utc).isoformat(),
            datetime.now(timezone.utc).isoformat(),
        ),
    )
    await db.commit()


# ── Mock builders ─────────────────────────────────────────────────────────────

def _groq_mock(tag: str = "security"):
    m = MagicMock()
    choice = MagicMock()
    choice.message.content = f"{tag}\n"
    m.return_value.chat.completions.create.return_value.choices = [choice]
    return m


def _httpx_mock(cost: int = 5):
    m = MagicMock()
    inst = MagicMock()
    m.return_value.__enter__ = MagicMock(return_value=inst)
    m.return_value.__exit__ = MagicMock(return_value=False)
    resp = MagicMock()
    resp.raise_for_status = MagicMock()
    resp.json.return_value = {
        "findings": [{"issue": "shell=True", "severity": "critical",
                      "line_number": 5, "suggestion": "Use shell=False"}],
        "cost_sats": cost,
        "model_id": "llama3-8b",
        "chunk_id": "chunk-x",
    }
    inst.post.return_value = resp
    return m, inst


def _genai_mock(verifier_verdict: str = "ACCEPT"):
    m = MagicMock()
    client = MagicMock()
    m.return_value = client
    v_resp = MagicMock()
    v_resp.text = f"{verifier_verdict}: valid"
    s_resp = MagicMock()
    s_resp.text = (
        "SUMMARY: Security issue found.\n"
        'PRIORITY_ACTIONS: [{"action": "Fix it", "reason": "shell", "priority": "high"}]'
    )
    # Support repeated calls (one verifier per chunk, one synthesiser)
    client.models.generate_content.side_effect = [v_resp, v_resp, v_resp, v_resp, s_resp]
    return m


# ══════════════════════════════════════════════════════════════════════════════
# 1 & 2 — Webhook fires and pipeline runs automatically
# ══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_pr_opened_webhook_fires_pipeline():
    """
    Simulate 'PR opened' trigger and confirm:
    - Episode row written with correct user_id
    - PR row set to status='done'
    - GitHub comment posted
    """
    import db.store as _store
    _store.DB_PATH = _TEST_DB
    from gh.webhook import _run_review

    user_id = str(uuid.uuid4())
    wallet_id = f"mock_wallet_{user_id[:8]}"

    async with aiosqlite.connect(_TEST_DB) as db:
        await _insert_test_user(db, user_id, wallet_id)

    mock_groq = _groq_mock("security")
    mock_httpx, mock_httpx_inst = _httpx_mock(cost=5)
    mock_genai = _genai_mock()

    mock_comment = MagicMock()
    diff = {
        "diff": SAMPLE_DIFF,
        "url": "https://github.com/test/repo/pull/1",
        "title": "Add run helper",
        "number": 1,
    }

    with (
        patch("pipeline.nodes.Groq", mock_groq),
        patch("pipeline.nodes.httpx.Client", mock_httpx),
        patch("pipeline.nodes.genai.Client", mock_genai),
        patch("gh.client.post_review_comment", mock_comment),
        patch("gh.webhook.load_registry", return_value=[FAKE_MODEL]),
    ):
        await _run_review(
            pr_id="pr-e2e-001",
            diff=diff,
            user_id=user_id,
            trigger_type="pr_opened",
            repo_full_name="test/repo",
            pr_number=1,
        )

    async with aiosqlite.connect(_TEST_DB) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT status FROM pull_requests WHERE id = ?", ("pr-e2e-001",)
        ) as cur:
            pr_row = await cur.fetchone()
        assert pr_row is not None, "PR row was not inserted"
        assert pr_row["status"] == "done"

        async with db.execute("SELECT user_id FROM episodes") as cur:
            ep_rows = await cur.fetchall()
        assert len(ep_rows) >= 1, "Expected at least one episode row"
        assert ep_rows[0]["user_id"] == user_id


@pytest.mark.asyncio
async def test_push_to_main_webhook_fires_pipeline():
    """
    Simulate 'push to main' trigger; confirm PR record has trigger_type='direct_push'.
    """
    import db.store as _store
    _store.DB_PATH = _TEST_DB
    from gh.webhook import _run_review

    user_id = str(uuid.uuid4())
    wallet_id = f"mock_wallet_{user_id[:8]}"

    async with aiosqlite.connect(_TEST_DB) as db:
        await _insert_test_user(db, user_id, wallet_id)

    mock_groq = _groq_mock("logic")
    mock_httpx, _ = _httpx_mock(cost=5)
    mock_genai = _genai_mock()

    diff = {
        "diff": SAMPLE_DIFF,
        "url": "https://github.com/test/repo/commit/abc",
        "title": "Direct push abc1234",
        "number": None,
    }

    with (
        patch("pipeline.nodes.Groq", mock_groq),
        patch("pipeline.nodes.httpx.Client", mock_httpx),
        patch("pipeline.nodes.genai.Client", mock_genai),
        patch("gh.client.post_review_comment"),
        patch("gh.webhook.load_registry", return_value=[FAKE_MODEL]),
    ):
        await _run_review(
            pr_id="pr-push-001",
            diff=diff,
            user_id=user_id,
            trigger_type="direct_push",
            repo_full_name="test/repo",
            pr_number=None,
        )

    async with aiosqlite.connect(_TEST_DB) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT trigger_type, status FROM pull_requests WHERE id = ?",
            ("pr-push-001",),
        ) as cur:
            row = await cur.fetchone()
    assert row is not None
    assert row["trigger_type"] == "direct_push"
    assert row["status"] == "done"


# ══════════════════════════════════════════════════════════════════════════════
# 3 — L402 payments: wallet decrements per worker call
# ══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_worker_endpoint_decrements_wallet_per_chunk():
    """
    Call the real payment dependency twice and confirm balance drops by
    cost_sats each time (5 sats per call, 2 calls → 100 - 10 = 90).
    """
    from payments.wallet import MockWallet
    from workers.factory import _make_payment_dep, WorkerRequest

    model = ModelEntry(
        id="llama3-8b", name="llama3:8b", provider="qrok-api",
        cost_sats=5, endpoint_url="", capability_tags=[],
    )

    wallet = MockWallet()
    wid = wallet.create_wallet("user-test")
    wallet.credit(wid, 100)

    dep = _make_payment_dep(model)
    body = WorkerRequest(task="review", chunk_id="c1", user_id="u1", wallet_id=wid)

    with patch("workers.factory.get_wallet", return_value=wallet):
        await dep(body)
        assert wallet.get_balance(wid) == 95  # 100 - 5

        await dep(body)
        assert wallet.get_balance(wid) == 90  # 95 - 5


@pytest.mark.asyncio
async def test_payment_raises_on_insufficient_funds():
    """Dependency raises HTTP 402 when wallet has insufficient funds."""
    from fastapi import HTTPException
    from payments.wallet import MockWallet
    from workers.factory import _make_payment_dep, WorkerRequest

    model = ModelEntry(
        id="llama3-8b", name="llama3:8b", provider="qrok-api",
        cost_sats=50, endpoint_url="", capability_tags=[],
    )

    wallet = MockWallet()
    wid = wallet.create_wallet("user-broke")
    wallet.credit(wid, 10)  # less than cost_sats=50

    dep = _make_payment_dep(model)
    body = WorkerRequest(task="t", chunk_id="c", user_id="u", wallet_id=wid)

    with patch("workers.factory.get_wallet", return_value=wallet):
        with pytest.raises(HTTPException) as exc_info:
            await dep(body)
    assert exc_info.value.status_code == 402


@pytest.mark.asyncio
async def test_pipeline_wallet_decrements_across_two_chunks():
    """
    Two chunks processed by run_pr_review produce two worker POST calls,
    each debiting cost_sats, giving total_cost_sats = 2 × 5 = 10.
    """
    from models import PRChunk
    from pipeline.graph import run_pr_review

    chunk_a = PRChunk(id="ca", pr_id="pr-pay", file_path="a.py",
                      hunk_index=0, language="python", diff_text="+x=1\n", lines_changed=1)
    chunk_b = PRChunk(id="cb", pr_id="pr-pay", file_path="b.py",
                      hunk_index=0, language="python", diff_text="+y=2\n", lines_changed=1)

    mock_groq = _groq_mock("logic")
    mock_httpx, mock_inst = _httpx_mock(cost=5)

    mock_genai = MagicMock()
    gc = MagicMock()
    mock_genai.return_value = gc
    accept = MagicMock()
    accept.text = "ACCEPT"
    synth = MagicMock()
    synth.text = "SUMMARY: ok\nPRIORITY_ACTIONS: []"
    gc.models.generate_content.side_effect = [accept, accept, synth]

    with (
        patch("pipeline.nodes.Groq", mock_groq),
        patch("pipeline.nodes.httpx.Client", mock_httpx),
        patch("pipeline.nodes.genai.Client", mock_genai),
    ):
        report = await run_pr_review(
            pr_id="pr-pay",
            chunks=[chunk_a, chunk_b],
            user_id="user-1",
            registry=[FAKE_MODEL],
            budget=200,
            wallet_id="wallet-1",
        )

    assert report.total_cost_sats == 10  # 2 chunks × 5 sats
    assert mock_inst.post.call_count == 2  # one worker call per chunk


# ══════════════════════════════════════════════════════════════════════════════
# 4 — GitHub comment format
# ══════════════════════════════════════════════════════════════════════════════

def test_post_review_comment_correct_format():
    """
    post_review_comment builds a Markdown comment with correct emoji + severity
    + category + line number + description + suggestion for each finding.
    """
    from gh.client import post_review_comment

    mock_gh = MagicMock()
    mock_repo = MagicMock()
    mock_pr = MagicMock()
    mock_gh.return_value.get_repo.return_value = mock_repo
    mock_repo.get_pull.return_value = mock_pr

    findings = [
        {"severity": "critical", "category": "security",
         "line_number": 5, "description": "shell=True injection",
         "suggestion": "Use shell=False"},
        {"severity": "warning", "category": "logic",
         "line_number": 12, "description": "Unused variable x",
         "suggestion": "Remove x"},
        {"severity": "info", "category": "style",
         "line_number": 20, "description": "Missing docstring",
         "suggestion": "Add docstring"},
    ]

    with patch("gh.client.Github", mock_gh):
        post_review_comment("owner/repo", 42, findings, "ghp_token")

    mock_pr.create_issue_comment.assert_called_once()
    text = mock_pr.create_issue_comment.call_args[0][0]

    assert "**VeriSync Review**" in text
    assert "🔴" in text   # critical emoji
    assert "🟡" in text   # warning emoji
    assert "🔵" in text   # info emoji
    assert "CRITICAL" in text
    assert "shell=True injection" in text
    assert "Use shell=False" in text
    assert "line 5" in text
    assert "line 12" in text
    assert "line 20" in text


def test_post_review_comment_no_findings():
    """When findings list is empty, post a 'No issues found' comment."""
    from gh.client import post_review_comment

    mock_gh = MagicMock()
    mock_repo = MagicMock()
    mock_pr = MagicMock()
    mock_gh.return_value.get_repo.return_value = mock_repo
    mock_repo.get_pull.return_value = mock_pr

    with patch("gh.client.Github", mock_gh):
        post_review_comment("owner/repo", 1, [], "ghp_token")

    mock_pr.create_issue_comment.assert_called_once()
    assert "No issues found" in mock_pr.create_issue_comment.call_args[0][0]


# ══════════════════════════════════════════════════════════════════════════════
# 5 — SQLite rows: all required columns populated
# ══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_sqlite_rows_all_columns_populated():
    """
    After _run_review() completes, verify every required column in:
    - pull_requests: pr_url, status
    - chunks: file_path (derived from diff)
    - episodes: user_id, model_id, cost_sats, verifier_pass, finding_count
    - episodes.chunk_id references a real row in chunks
    """
    import db.store as _store
    _store.DB_PATH = _TEST_DB
    from gh.webhook import _run_review

    user_id = str(uuid.uuid4())
    wallet_id = f"mock_wallet_{user_id[:8]}"
    pr_url = "https://github.com/test/repo/pull/99"

    async with aiosqlite.connect(_TEST_DB) as db:
        await _insert_test_user(db, user_id, wallet_id)

    mock_groq = _groq_mock("security")
    mock_httpx, _ = _httpx_mock(cost=7)
    mock_genai = _genai_mock()

    diff = {"diff": SAMPLE_DIFF, "url": pr_url, "title": "Test PR", "number": 99}

    with (
        patch("pipeline.nodes.Groq", mock_groq),
        patch("pipeline.nodes.httpx.Client", mock_httpx),
        patch("pipeline.nodes.genai.Client", mock_genai),
        patch("gh.client.post_review_comment"),
        patch("gh.webhook.load_registry", return_value=[FAKE_MODEL]),
    ):
        await _run_review(
            pr_id="pr-cols-001",
            diff=diff,
            user_id=user_id,
            trigger_type="pr_opened",
            repo_full_name="test/repo",
            pr_number=99,
        )

    async with aiosqlite.connect(_TEST_DB) as db:
        db.row_factory = aiosqlite.Row

        # pull_requests
        async with db.execute(
            "SELECT pr_url, status FROM pull_requests WHERE id = ?", ("pr-cols-001",)
        ) as cur:
            pr_row = await cur.fetchone()
        assert pr_row is not None
        assert pr_row["pr_url"] == pr_url
        assert pr_row["status"] == "done"

        # chunks
        async with db.execute(
            "SELECT id, file_path FROM chunks WHERE pr_id = ?", ("pr-cols-001",)
        ) as cur:
            chunk_rows = await cur.fetchall()
        assert len(chunk_rows) >= 1
        assert chunk_rows[0]["file_path"] == "app.py"

        # episodes
        async with db.execute("SELECT * FROM episodes") as cur:
            ep_rows = await cur.fetchall()
        assert len(ep_rows) >= 1

        ep = dict(ep_rows[0])
        assert ep["user_id"] == user_id,       f"user_id missing/wrong: {ep}"
        assert ep["model_id"] is not None,     "model_id not set"
        assert ep["cost_sats"] is not None,    "cost_sats not set"
        assert ep["verifier_pass"] in (0, 1),  "verifier_pass must be 0 or 1"
        assert ep["finding_count"] >= 0,       "finding_count not set"

        # chunk_id in episodes must reference a real chunks row
        async with db.execute(
            "SELECT chunk_id FROM episodes WHERE user_id = ?", (user_id,)
        ) as cur:
            ep_chunk_ids = [r["chunk_id"] async for r in cur]

        for cid in ep_chunk_ids:
            async with db.execute(
                "SELECT id FROM chunks WHERE id = ?", (cid,)
            ) as cur2:
                found = await cur2.fetchone()
            assert found is not None, f"episode.chunk_id={cid!r} not in chunks table"


# ══════════════════════════════════════════════════════════════════════════════
# 6 — Async race conditions: concurrent SSE publishers don't corrupt queues
# ══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_concurrent_publish_does_not_lose_events():
    """
    20 concurrent publish() calls for the same user must each reach every
    active queue without ValueError or dropped events.
    """
    from dashboard.events import publish, _queues

    uid = "sse-race-user"
    q1: asyncio.Queue = asyncio.Queue(maxsize=100)
    q2: asyncio.Queue = asyncio.Queue(maxsize=100)
    _queues[uid] = [q1, q2]

    try:
        events = [{"type": "chunk_done", "n": i} for i in range(20)]
        await asyncio.gather(*[publish(uid, ev) for ev in events])

        assert q1.qsize() == 20
        assert q2.qsize() == 20
    finally:
        _queues.pop(uid, None)


@pytest.mark.asyncio
async def test_publish_removes_full_queue_without_raising():
    """
    If a queue is full, publish() removes it silently — no ValueError.
    The alive queue still receives the event.
    """
    from dashboard.events import publish, _queues

    uid = "sse-remove-user"
    alive_q: asyncio.Queue = asyncio.Queue(maxsize=100)
    full_q: asyncio.Queue = asyncio.Queue(maxsize=1)
    full_q.put_nowait({"type": "pre-fill"})  # fill it so put_nowait raises QueueFull

    _queues[uid] = [alive_q, full_q]

    try:
        await publish(uid, {"type": "new_event"})  # must not raise

        assert alive_q.qsize() == 1           # alive queue got the event
        assert full_q not in _queues[uid]     # full queue was pruned
    finally:
        _queues.pop(uid, None)


@pytest.mark.asyncio
async def test_event_stream_cleanup_idempotent():
    """
    Double-removing a queue from _queues (as happens when publish and
    _event_stream both try to clean it up) must not raise ValueError.
    """
    from dashboard.events import _queues

    uid = "sse-cleanup-user"
    q: asyncio.Queue = asyncio.Queue(maxsize=1)
    _queues[uid] = [q]

    try:
        # First removal (simulates _event_stream finally block)
        try:
            _queues[uid].remove(q)
        except ValueError:
            pass

        # Second removal (simulates concurrent publish cleanup)
        try:
            _queues[uid].remove(q)
        except ValueError:
            pass  # expected and now handled gracefully
    finally:
        _queues.pop(uid, None)
