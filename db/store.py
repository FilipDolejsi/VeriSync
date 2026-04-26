import os
import contextlib
import sqlite3
import uuid
import aiosqlite

DB_PATH = os.environ.get("DATABASE_PATH", "./verisync.db")


@contextlib.asynccontextmanager
async def get_db():
    db = await aiosqlite.connect(DB_PATH)
    db.row_factory = aiosqlite.Row
    try:
        yield db
    finally:
        await db.close()


async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                github_id TEXT UNIQUE NOT NULL,
                username TEXT,
                avatar_url TEXT,
                wallet_id TEXT,
                sat_balance INTEGER DEFAULT 0,
                github_token TEXT,
                created_at TEXT,
                last_login TEXT
            );

            CREATE TABLE IF NOT EXISTS watched_repos (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL REFERENCES users(id),
                repo_full_name TEXT NOT NULL,
                webhook_id INTEGER,
                webhook_secret TEXT,
                active INTEGER DEFAULT 1,
                UNIQUE(user_id, repo_full_name)
            );

            CREATE TABLE IF NOT EXISTS pull_requests (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL REFERENCES users(id),
                repo_full_name TEXT,
                pr_number INTEGER,
                pr_title TEXT,
                pr_url TEXT,
                trigger_type TEXT,
                status TEXT DEFAULT 'pending',
                total_cost_sats INTEGER DEFAULT 0,
                started_at TEXT,
                completed_at TEXT
            );

            CREATE TABLE IF NOT EXISTS chunks (
                id TEXT PRIMARY KEY,
                pr_id TEXT NOT NULL REFERENCES pull_requests(id),
                file_path TEXT,
                hunk_index INTEGER,
                language TEXT,
                classifier_tag TEXT,
                lines_changed INTEGER,
                diff_text TEXT
            );

            CREATE TABLE IF NOT EXISTS episodes (
                id TEXT PRIMARY KEY,
                chunk_id TEXT NOT NULL REFERENCES chunks(id),
                user_id TEXT,
                repo_full_name TEXT,
                model_id TEXT,
                tier_index INTEGER,
                classifier_tag TEXT,
                provider TEXT,
                verifier_pass INTEGER,
                cost_sats INTEGER,
                finding_count INTEGER,
                diff_text TEXT,
                router_predicted_id TEXT,
                router_predicted_tier INTEGER,
                router_confidence REAL,
                timestamp TEXT
            );

            CREATE TABLE IF NOT EXISTS findings (
                id TEXT PRIMARY KEY,
                chunk_id TEXT NOT NULL REFERENCES chunks(id),
                model_id TEXT,
                severity TEXT,
                category TEXT,
                line_number INTEGER,
                description TEXT,
                suggestion TEXT,
                confidence REAL,
                accepted INTEGER DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS transactions (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL REFERENCES users(id),
                to_model_id TEXT,
                amount_sats INTEGER,
                chunk_id TEXT,
                timestamp TEXT
            );
        """)
        await db.commit()

    # Migrate existing databases that pre-date these columns
    _run_migrations()


def _run_migrations():
    """Add columns introduced after initial schema without breaking existing DBs."""
    migrations = [
        ("chunks",   "diff_text TEXT"),
        ("episodes", "classifier_tag TEXT"),
        ("episodes", "repo_full_name TEXT"),
        ("episodes", "diff_text TEXT"),
    ]
    with sqlite3.connect(DB_PATH) as conn:
        for table, col_def in migrations:
            try:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {col_def}")
                conn.commit()
            except sqlite3.OperationalError:
                pass  # column already exists


# ── Users ─────────────────────────────────────────────────────────────────────

async def upsert_user(db: aiosqlite.Connection, user: dict):
    await db.execute("""
        INSERT INTO users (id, github_id, username, avatar_url, wallet_id, sat_balance, github_token, created_at, last_login)
        VALUES (:id, :github_id, :username, :avatar_url, :wallet_id, :sat_balance, :github_token, :created_at, :last_login)
        ON CONFLICT(github_id) DO UPDATE SET
            username=excluded.username,
            avatar_url=excluded.avatar_url,
            wallet_id=excluded.wallet_id,
            github_token=excluded.github_token,
            last_login=excluded.last_login
    """, user)
    await db.commit()


async def get_user_by_github_id(db: aiosqlite.Connection, github_id: str) -> dict | None:
    async with db.execute("SELECT * FROM users WHERE github_id = ?", (github_id,)) as cur:
        row = await cur.fetchone()
        return dict(row) if row else None


async def get_user_by_id(db: aiosqlite.Connection, user_id: str) -> dict | None:
    async with db.execute("SELECT * FROM users WHERE id = ?", (user_id,)) as cur:
        row = await cur.fetchone()
        return dict(row) if row else None


async def get_github_token(db: aiosqlite.Connection, user_id: str) -> str | None:
    async with db.execute("SELECT github_token FROM users WHERE id = ?", (user_id,)) as cur:
        row = await cur.fetchone()
        return row["github_token"] if row else None


async def update_sat_balance(db: aiosqlite.Connection, user_id: str, delta: int):
    await db.execute(
        "UPDATE users SET sat_balance = sat_balance + ? WHERE id = ?",
        (delta, user_id),
    )
    await db.commit()


# ── Watched repos ─────────────────────────────────────────────────────────────

async def store_watched_repo(db: aiosqlite.Connection, watched: dict):
    await db.execute("""
        INSERT INTO watched_repos (id, user_id, repo_full_name, webhook_id, webhook_secret, active)
        VALUES (:id, :user_id, :repo_full_name, :webhook_id, :webhook_secret, :active)
        ON CONFLICT(user_id, repo_full_name) DO UPDATE SET
            webhook_id=excluded.webhook_id,
            webhook_secret=excluded.webhook_secret,
            active=excluded.active
    """, watched)
    await db.commit()


async def get_watched_repo(db: aiosqlite.Connection, repo_full_name: str) -> dict | None:
    async with db.execute(
        "SELECT * FROM watched_repos WHERE repo_full_name = ? AND active = 1",
        (repo_full_name,),
    ) as cur:
        row = await cur.fetchone()
        return dict(row) if row else None


async def deactivate_watched_repo(db: aiosqlite.Connection, user_id: str, repo_full_name: str):
    await db.execute(
        "UPDATE watched_repos SET active = 0 WHERE user_id = ? AND repo_full_name = ?",
        (user_id, repo_full_name),
    )
    await db.commit()


# ── Pull requests ──────────────────────────────────────────────────────────────

async def write_pull_request(db: aiosqlite.Connection, pr_data: dict) -> str:
    pr_id = pr_data.get("id") or str(uuid.uuid4())
    await db.execute("""
        INSERT OR IGNORE INTO pull_requests
            (id, user_id, repo_full_name, pr_number, pr_title, pr_url,
             trigger_type, status, started_at)
        VALUES (:id, :user_id, :repo_full_name, :pr_number, :pr_title, :pr_url,
                :trigger_type, :status, :started_at)
    """, {**pr_data, "id": pr_id})
    await db.commit()
    return pr_id


async def update_pr_status(
    db: aiosqlite.Connection, pr_id: str, status: str, total_cost_sats: int = 0
):
    from datetime import datetime, timezone
    await db.execute(
        """
        UPDATE pull_requests
        SET status = ?, total_cost_sats = ?, completed_at = ?
        WHERE id = ?
        """,
        (status, total_cost_sats, datetime.now(timezone.utc).isoformat(), pr_id),
    )
    await db.commit()


# ── Chunks ─────────────────────────────────────────────────────────────────────

async def write_chunk(db: aiosqlite.Connection, chunk) -> str:
    """Insert a chunk record. Accepts a PRChunk model or a plain dict."""
    if hasattr(chunk, "model_dump"):
        data = chunk.model_dump()
    elif isinstance(chunk, dict):
        data = chunk
    else:
        raise TypeError(f"Unsupported chunk type: {type(chunk)}")

    chunk_id = data.get("id") or str(uuid.uuid4())
    await db.execute(
        """
        INSERT OR IGNORE INTO chunks
            (id, pr_id, file_path, hunk_index, language, lines_changed, diff_text)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            chunk_id,
            data.get("pr_id"),
            data.get("file_path"),
            data.get("hunk_index", 0),
            data.get("language", "unknown"),
            data.get("lines_changed", 0),
            data.get("diff_text", ""),
        ),
    )
    await db.commit()
    return chunk_id


# ── Findings ───────────────────────────────────────────────────────────────────

async def write_finding(db: aiosqlite.Connection, finding) -> str:
    if hasattr(finding, "model_dump"):
        data = finding.model_dump()
    elif isinstance(finding, dict):
        data = finding
    else:
        raise TypeError(f"Unsupported finding type: {type(finding)}")

    finding_id = data.get("id") or str(uuid.uuid4())
    await db.execute(
        """
        INSERT OR IGNORE INTO findings
            (id, chunk_id, model_id, severity, category, line_number,
             description, suggestion, confidence, accepted)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            finding_id,
            data.get("chunk_id"),
            data.get("model_id"),
            data.get("severity", "info"),
            data.get("category", "logic"),
            data.get("line_number"),
            data.get("description", ""),
            data.get("suggestion", ""),
            data.get("confidence", 0.0),
            1 if data.get("accepted") else 0,
        ),
    )
    await db.commit()
    return finding_id


# ── Transactions ───────────────────────────────────────────────────────────────

async def write_transaction(db: aiosqlite.Connection, tx) -> str:
    if hasattr(tx, "model_dump"):
        data = tx.model_dump()
    elif isinstance(tx, dict):
        data = tx
    else:
        raise TypeError(f"Unsupported tx type: {type(tx)}")

    tx_id = data.get("id") or str(uuid.uuid4())
    await db.execute(
        """
        INSERT OR IGNORE INTO transactions
            (id, user_id, to_model_id, amount_sats, chunk_id, timestamp)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            tx_id,
            data.get("user_id"),
            data.get("to_model_id"),
            data.get("amount_sats", 0),
            data.get("chunk_id"),
            data.get("timestamp"),
        ),
    )
    await db.commit()
    return tx_id


# ── Episodes (async) ──────────────────────────────────────────────────────────

async def get_all_episodes() -> list[dict]:
    """Return all episodes joined with their chunk's diff_text and metadata."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("""
            SELECT
                e.id, e.chunk_id, e.user_id, e.model_id, e.tier_index,
                e.classifier_tag, e.verifier_pass, e.cost_sats,
                e.finding_count, e.timestamp,
                c.diff_text, c.language, c.lines_changed, c.file_path
            FROM episodes e
            LEFT JOIN chunks c ON c.id = e.chunk_id
        """) as cur:
            rows = await cur.fetchall()
            return [dict(r) for r in rows]


async def get_episodes_since(timestamp: str) -> list[dict]:
    """Return episodes whose timestamp is after the given ISO string."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM episodes WHERE timestamp > ?", (timestamp,)
        ) as cur:
            rows = await cur.fetchall()
            return [dict(r) for r in rows]


# ── Dashboard queries (async) ─────────────────────────────────────────────────

async def get_user_history(user_id: str) -> list[dict]:
    """All PRs for a user with aggregate finding counts, newest first."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("""
            SELECT
                pr.id, pr.repo_full_name, pr.pr_number, pr.pr_title,
                pr.pr_url, pr.trigger_type, pr.status,
                pr.total_cost_sats, pr.started_at, pr.completed_at,
                COUNT(DISTINCT f.id) AS finding_count,
                COUNT(DISTINCT c.id)  AS chunk_count
            FROM pull_requests pr
            LEFT JOIN chunks  c ON c.pr_id  = pr.id
            LEFT JOIN findings f ON f.chunk_id = c.id
            WHERE pr.user_id = ?
            GROUP BY pr.id
            ORDER BY pr.started_at DESC
        """, (user_id,)) as cur:
            rows = await cur.fetchall()
            return [dict(r) for r in rows]


async def get_analytics(user_id: str) -> dict:
    """Aggregated stats: spend by model, findings by severity, totals, router stats."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row

        async with db.execute("""
            SELECT e.model_id,
                   SUM(e.cost_sats)  AS total_sats,
                   COUNT(*)          AS chunk_count
            FROM episodes e
            JOIN chunks c        ON c.id  = e.chunk_id
            JOIN pull_requests pr ON pr.id = c.pr_id
            WHERE pr.user_id = ?
            GROUP BY e.model_id
        """, (user_id,)) as cur:
            spend_by_model = [dict(r) for r in await cur.fetchall()]

        async with db.execute("""
            SELECT f.severity, COUNT(*) AS count
            FROM findings f
            JOIN chunks c        ON c.id  = f.chunk_id
            JOIN pull_requests pr ON pr.id = c.pr_id
            WHERE pr.user_id = ?
            GROUP BY f.severity
        """, (user_id,)) as cur:
            findings_by_severity = {
                r["severity"]: r["count"] for r in await cur.fetchall()
            }

        async with db.execute("""
            SELECT
                COUNT(DISTINCT pr.id)  AS total_prs,
                COALESCE(SUM(pr.total_cost_sats), 0) AS total_spent,
                COALESCE(AVG(CASE WHEN e.verifier_pass = 1
                                  THEN 1.0 ELSE 0.0 END), 0) AS verifier_pass_rate
            FROM pull_requests pr
            LEFT JOIN chunks  c ON c.pr_id  = pr.id
            LEFT JOIN episodes e ON e.chunk_id = c.id
            WHERE pr.user_id = ?
        """, (user_id,)) as cur:
            row = await cur.fetchone()
            totals = dict(row) if row else {}

    try:
        from router.router import get_router_stats
        router_stats = get_router_stats()
    except Exception:
        router_stats = {}

    return {
        "spend_by_model":      spend_by_model,
        "findings_by_severity": findings_by_severity,
        "totals":              totals,
        "router":              router_stats,
    }


# ── Synchronous DBStore for LangGraph nodes ───────────────────────────────────

class DBStore:
    """Synchronous DB operations for pipeline nodes that cannot be async."""

    def write_episode(self, episode):
        """
        Persist an Episode dataclass to the episodes table.
        diff_text is truncated to 2000 chars to keep storage manageable.
        """
        try:
            diff_text = (getattr(episode, "diff_text", "") or "")[:2000]
            with sqlite3.connect(DB_PATH) as conn:
                episode_id = str(uuid.uuid4())
                conn.execute(
                    """
                    INSERT INTO episodes (
                        id, chunk_id, user_id, repo_full_name, model_id,
                        tier_index, classifier_tag, verifier_pass, cost_sats,
                        finding_count, diff_text, timestamp
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        episode_id,
                        episode.chunk_id,
                        getattr(episode, "user_id", None),
                        getattr(episode, "repo_full_name", None),
                        episode.model_id,
                        episode.tier_index,
                        getattr(episode, "classifier_tag", None),
                        1 if episode.verifier_accepted else 0,
                        getattr(episode, "cost_sats", 0),
                        len(episode.findings) if episode.findings else 0,
                        diff_text,
                        episode.timestamp,
                    ),
                )
                conn.commit()
        except Exception as e:
            print(f"Error writing episode to DB: {e}")


# ── Synchronous helpers for the router training thread ────────────────────────

def get_all_episodes_sync() -> list[dict]:
    """
    Return all successful episodes joined with chunk metadata.
    Prefers e.diff_text (stored on episode) over c.diff_text (stored on chunk),
    and includes repo_full_name for personalisation features.
    Used by train_router().
    """
    try:
        with sqlite3.connect(DB_PATH) as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.execute("""
                SELECT
                    e.id, e.chunk_id, e.user_id, e.repo_full_name, e.model_id,
                    e.tier_index, e.classifier_tag, e.verifier_pass, e.cost_sats,
                    e.finding_count, e.timestamp,
                    COALESCE(e.diff_text, c.diff_text) AS diff_text,
                    c.language, c.lines_changed, c.file_path
                FROM episodes e
                LEFT JOIN chunks c ON c.id = e.chunk_id
                WHERE e.verifier_pass = 1
            """)
            return [dict(r) for r in cur.fetchall()]
    except Exception:
        return []


def get_episode_count_sync() -> int:
    """Return total number of episode rows (used by retrain loop)."""
    try:
        with sqlite3.connect(DB_PATH) as conn:
            cur = conn.execute("SELECT COUNT(*) FROM episodes")
            row = cur.fetchone()
            return row[0] if row else 0
    except Exception:
        return 0


# ── Reputation queries ────────────────────────────────────────────────────────

def _default_reputation(model_id: str, cost_sats: float) -> dict:
    """Safe defaults when a model has no episode history yet."""
    return {
        "model_id":        model_id,
        "total_reviews":   0,
        "pass_rate":       0.5,
        "avg_cost_sats":   float(cost_sats),
        "avg_findings":    0.0,
        "effective_cost":  float(cost_sats),
        "reputation_score": 0.5,
    }


def _row_to_reputation(model_id: str, row, default_cost_sats: float) -> dict:
    """Convert a DB row (or None) into a reputation dict."""
    if not row or row["total_reviews"] == 0:
        return _default_reputation(model_id, default_cost_sats)

    pass_rate = float(row["pass_rate"] or 0.0)
    avg_cost  = float(row["avg_cost_sats"] or default_cost_sats)
    avg_finds = float(row["avg_findings"] or 0.0)

    effective_cost = (avg_cost / pass_rate) if pass_rate > 0 else float("inf")
    reputation_score = min(1.0, pass_rate * avg_finds)

    return {
        "model_id":        model_id,
        "total_reviews":   int(row["total_reviews"]),
        "pass_rate":       pass_rate,
        "avg_cost_sats":   avg_cost,
        "avg_findings":    avg_finds,
        "effective_cost":  effective_cost,
        "reputation_score": reputation_score,
    }


_REPUTATION_SQL = """
    SELECT
        COUNT(*)                                AS total_reviews,
        AVG(CAST(verifier_pass  AS REAL))       AS pass_rate,
        AVG(CAST(cost_sats      AS REAL))       AS avg_cost_sats,
        AVG(CAST(finding_count  AS REAL))       AS avg_findings
    FROM episodes
    WHERE model_id = ?
"""

_ALL_REPUTATIONS_SQL = """
    SELECT
        model_id,
        COUNT(*)                                AS total_reviews,
        AVG(CAST(verifier_pass  AS REAL))       AS pass_rate,
        AVG(CAST(cost_sats      AS REAL))       AS avg_cost_sats,
        AVG(CAST(finding_count  AS REAL))       AS avg_findings
    FROM episodes
    GROUP BY model_id
"""


async def get_model_reputation(model_id: str, default_cost_sats: float = 10.0) -> dict:
    """
    Query the episodes table for a specific model's historical performance.

    Returns a dict with keys: model_id, total_reviews, pass_rate, avg_cost_sats,
    avg_findings, effective_cost (= avg_cost / pass_rate), reputation_score
    (= pass_rate * avg_findings, capped at 1.0).

    Falls back to safe defaults (pass_rate=0.5, effective_cost=cost_sats) when
    the model has no episode history yet.
    """
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(_REPUTATION_SQL, (model_id,)) as cur:
            row = await cur.fetchone()
    return _row_to_reputation(model_id, row, default_cost_sats)


async def get_all_model_reputations() -> list[dict]:
    """
    Return reputation dicts for every model_id that appears in the episodes table.
    Used by the dashboard leaderboard endpoint.
    """
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(_ALL_REPUTATIONS_SQL) as cur:
            rows = await cur.fetchall()
    return [
        _row_to_reputation(r["model_id"], r, float(r["avg_cost_sats"] or 10))
        for r in rows
    ]


def get_model_reputation_sync(model_id: str, default_cost_sats: float = 10.0) -> dict:
    """
    Synchronous version of get_model_reputation for use inside LangGraph nodes
    (which run in a sync context).  Same return shape as the async version.
    """
    try:
        with sqlite3.connect(DB_PATH) as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.execute(_REPUTATION_SQL, (model_id,))
            row = cur.fetchone()
        return _row_to_reputation(model_id, row, default_cost_sats)
    except Exception:
        return _default_reputation(model_id, default_cost_sats)


def get_all_model_reputations_sync() -> list[dict]:
    """Synchronous version of get_all_model_reputations."""
    try:
        with sqlite3.connect(DB_PATH) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(_ALL_REPUTATIONS_SQL).fetchall()
        return [
            _row_to_reputation(r["model_id"], r, float(r["avg_cost_sats"] or 10))
            for r in rows
        ]
    except Exception:
        return []
