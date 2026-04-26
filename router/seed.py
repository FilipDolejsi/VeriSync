"""
Generate synthetic review episodes across all tiers so the RL router
has enough training data to make meaningful predictions from the start.

Run once before demo: python -m router.seed
"""
import sqlite3
import uuid
from datetime import datetime, timezone, timedelta
import random
import os

DB_PATH = os.environ.get("DATABASE_PATH", "./verisync.db")

TIERS = [
    {"model_id": "llama3-8b",   "tier_index": 0, "cost_sats": 5},
    {"model_id": "mistral-7b",  "tier_index": 1, "cost_sats": 10},
    {"model_id": "gemma2-9b",   "tier_index": 2, "cost_sats": 12},
    {"model_id": "llama3-70b",  "tier_index": 3, "cost_sats": 18},
    {"model_id": "claude-haiku","tier_index": 4, "cost_sats": 40},
    {"model_id": "claude-sonnet","tier_index": 5, "cost_sats": 150},
]

TAGS = ["style", "logic", "security", "architecture", "test-coverage"]

# Which tier each tag actually needs most of the time (ground truth for seeding)
OPTIMAL_TIER = {
    "style":        0,  # llama3-8b is fine
    "logic":        2,  # gemma2-9b
    "security":     5,  # claude-sonnet
    "architecture": 4,  # claude-haiku
    "test-coverage":2,  # gemma2-9b
}


def _now_minus(days: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()


def seed(n_episodes: int = 80):
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.cursor()

        # Ensure tables exist (idempotent — init_db already ran, but safe to call)
        cur.executescript("""
            CREATE TABLE IF NOT EXISTS chunks (
                id TEXT PRIMARY KEY, pr_id TEXT, file_path TEXT,
                hunk_index INTEGER, language TEXT, classifier_tag TEXT, lines_changed INTEGER
            );
            CREATE TABLE IF NOT EXISTS episodes (
                id TEXT PRIMARY KEY, chunk_id TEXT, model_id TEXT,
                tier_index INTEGER, provider TEXT, verifier_pass INTEGER,
                cost_sats INTEGER, finding_count INTEGER,
                router_predicted_id TEXT, router_predicted_tier INTEGER,
                router_confidence REAL, timestamp TEXT
            );
        """)

        inserted = 0
        for i in range(n_episodes):
            tag = random.choice(TAGS)
            optimal = OPTIMAL_TIER[tag]

            # 70% of episodes use the optimal tier (good data), 30% use a random tier
            if random.random() < 0.70:
                tier = TIERS[optimal]
                verifier_pass = 1 if random.random() < 0.85 else 0
            else:
                tier = random.choice(TIERS)
                verifier_pass = 1 if random.random() < 0.45 else 0

            finding_count = random.randint(0, 4) if verifier_pass else 0
            provider = "anthropic" if "claude" in tier["model_id"] else "ollama"

            chunk_id = str(uuid.uuid4())
            episode_id = str(uuid.uuid4())
            pr_id = str(uuid.uuid4())

            cur.execute("""
                INSERT OR IGNORE INTO chunks
                (id, pr_id, file_path, hunk_index, language, classifier_tag, lines_changed)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (chunk_id, pr_id, f"src/file_{i}.py", i % 10,
                  "python", tag, random.randint(5, 80)))

            cur.execute("""
                INSERT OR IGNORE INTO episodes
                (id, chunk_id, model_id, tier_index, provider, verifier_pass,
                 cost_sats, finding_count, router_predicted_id,
                 router_predicted_tier, router_confidence, timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                episode_id, chunk_id,
                tier["model_id"], tier["tier_index"], provider,
                verifier_pass, tier["cost_sats"], finding_count,
                tier["model_id"], tier["tier_index"],
                round(random.uniform(0.55, 0.95), 2),
                _now_minus(random.randint(0, 30)),
            ))
            inserted += 1

        conn.commit()
        print(f"Seeded {inserted} synthetic episodes into {DB_PATH}")
        print(f"Tag distribution: {TAGS}")
        print(f"Optimal tiers: {OPTIMAL_TIER}")


if __name__ == "__main__":
    seed()
