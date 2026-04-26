import os
import contextlib
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
                lines_changed INTEGER
            );

            CREATE TABLE IF NOT EXISTS episodes (
                id TEXT PRIMARY KEY,
                chunk_id TEXT NOT NULL REFERENCES chunks(id),
                user_id TEXT,
                model_id TEXT,
                tier_index INTEGER,
                provider TEXT,
                verifier_pass INTEGER,
                cost_sats INTEGER,
                finding_count INTEGER,
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


async def list_watched_repos(db: aiosqlite.Connection, user_id: str) -> list[dict]:
    async with db.execute(
        """
        SELECT repo_full_name, webhook_id, active
        FROM watched_repos
        WHERE user_id = ? AND active = 1
        ORDER BY repo_full_name ASC
        """,
        (user_id,),
    ) as cur:
        return [dict(row) for row in await cur.fetchall()]


# ── Dashboard queries ─────────────────────────────────────────────────────────

async def get_pr_history(db: aiosqlite.Connection, user_id: str, limit: int = 20, offset: int = 0) -> list[dict]:
    async with db.execute("""
        SELECT pr.*, COUNT(f.id) as finding_count,
               SUM(CASE WHEN f.severity='critical' THEN 1 ELSE 0 END) as critical_count,
               SUM(CASE WHEN f.severity='warning'  THEN 1 ELSE 0 END) as warning_count,
               SUM(CASE WHEN f.severity='info'     THEN 1 ELSE 0 END) as info_count
        FROM pull_requests pr
        LEFT JOIN chunks c ON c.pr_id = pr.id
        LEFT JOIN findings f ON f.chunk_id = c.id
        WHERE pr.user_id = ?
        GROUP BY pr.id
        ORDER BY pr.started_at DESC
        LIMIT ? OFFSET ?
    """, (user_id, limit, offset)) as cur:
        return [dict(r) for r in await cur.fetchall()]


async def get_spend_analytics(db: aiosqlite.Connection, user_id: str) -> dict:
    async with db.execute("""
        SELECT COALESCE(SUM(pr.total_cost_sats), 0) as total_sats,
               COUNT(DISTINCT pr.id) as total_prs
        FROM pull_requests pr WHERE pr.user_id = ?
    """, (user_id,)) as cur:
        totals = dict(await cur.fetchone())

    async with db.execute("""
        SELECT e.model_id,
               COUNT(*) as calls,
               COALESCE(SUM(e.cost_sats), 0) as cost_sats,
               COALESCE(AVG(e.finding_count), 0) as avg_findings,
               COALESCE(AVG(e.verifier_pass), 0) as pass_rate
        FROM episodes e
        JOIN chunks c ON c.id = e.chunk_id
        JOIN pull_requests pr ON pr.id = c.pr_id
        WHERE pr.user_id = ?
        GROUP BY e.model_id
        ORDER BY cost_sats DESC
    """, (user_id,)) as cur:
        totals["model_breakdown"] = [dict(r) for r in await cur.fetchall()]

    return totals


async def get_finding_analytics(db: aiosqlite.Connection, user_id: str) -> dict:
    async with db.execute("""
        SELECT f.severity, f.category, COUNT(*) as count
        FROM findings f
        JOIN chunks c ON c.id = f.chunk_id
        JOIN pull_requests pr ON pr.id = c.pr_id
        WHERE pr.user_id = ?
        GROUP BY f.severity, f.category
        ORDER BY count DESC
    """, (user_id,)) as cur:
        rows = [dict(r) for r in await cur.fetchall()]

    async with db.execute("""
        SELECT c.file_path, COUNT(f.id) as finding_count
        FROM findings f
        JOIN chunks c ON c.id = f.chunk_id
        JOIN pull_requests pr ON pr.id = c.pr_id
        WHERE pr.user_id = ?
        GROUP BY c.file_path
        ORDER BY finding_count DESC
        LIMIT 10
    """, (user_id,)) as cur:
        hotspots = [dict(r) for r in await cur.fetchall()]

    return {"by_type": rows, "hotspot_files": hotspots}


# ── Synchronous DBStore for LangGraph Nodes ───────────────────────────────────

import sqlite3
import uuid

class DBStore:
    """
    Synchronous DB operations for nodes that cannot be async.
    """
    def write_episode(self, episode):
        """
        Writes an Episode to the database synchronously.
        """
        try:
            with sqlite3.connect(DB_PATH) as conn:
                cur = conn.cursor()
                episode_id = str(uuid.uuid4())
                cur.execute(
                    """
                    INSERT INTO episodes (
                        id, chunk_id, user_id, model_id, tier_index,
                        verifier_pass, cost_sats, finding_count, timestamp
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        episode_id,
                        episode.chunk_id,
                        getattr(episode, "user_id", None),
                        episode.model_id,
                        episode.tier_index,
                        1 if episode.verifier_accepted else 0,
                        getattr(episode, "cost_sats", 0),
                        len(episode.findings) if episode.findings else 0,
                        episode.timestamp,
                    )
                )
                conn.commit()
        except Exception as e:
            print(f"Error writing episode to DB: {e}")
