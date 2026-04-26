"""
router/seed.py — Generate synthetic training episodes for the router.

Run once before a demo to give the router enough data to train on:

    python -m router.seed

Produces ~80 episode rows spread realistically across all 6 model tiers,
then calls train_router() so the model file is ready immediately.
"""

import asyncio
import os
import sqlite3
import sys
import uuid
from datetime import datetime, timezone
from typing import List

# ── Registry metadata mirrors registry.yaml ───────────────────────────────────
# Tier 0: llama3-8b (5 sats)   — style, classify
# Tier 1: mistral-7b (10 sats) — style, logic, classify
# Tier 2: gemma2-9b (12 sats)  — logic, test-coverage
# Tier 3: llama3-70b (18 sats) — logic, architecture, test-coverage
# Tier 4: gemini-flash (40 sats) — logic, security, architecture
# Tier 5: gemini-pro (150 sats) — security, architecture, logic

# ── Synthetic users / repos ────────────────────────────────────────────────────
# alice  → fintech security work  → skews tier 4-5
# bob    → personal blog          → skews tier 0-1
# charlie → backend services      → skews tier 2-3

_USER_REPO_BY_TIER = {
    0: ("user_bob",     "bob/personal-blog"),
    1: ("user_bob",     "bob/personal-blog"),
    2: ("user_charlie", "charlie/backend-api"),
    3: ("user_charlie", "charlie/backend-api"),
    4: ("user_alice",   "alice/fintech-app"),
    5: ("user_alice",   "alice/fintech-app"),
}

# ── Diff texts: EASY (tier 0-1) — style & simple refactors ───────────────────

EASY_TASKS: List[dict] = [
    {
        "diff_text": (
            "--- a/utils.py\n+++ b/utils.py\n@@ -1,4 +1,4 @@\n"
            "-def GetUserName(id):\n+def get_user_name(user_id):\n"
            "     \"\"\"Return display name.\"\"\"\n-    return db.query(id)\n"
            "+    return db.query(user_id)\n"
        ),
        "language": "python",
        "lines_changed": 4,
        "classifier_tag": "style",
        "tier": 0,
    },
    {
        "diff_text": (
            "--- a/config.js\n+++ b/config.js\n@@ -3,7 +3,9 @@\n"
            " const PORT = 3000;\n-const host='localhost'\n+const host = 'localhost';\n"
            "+\n+// Default timeout in ms\n const TIMEOUT = 5000;\n"
        ),
        "language": "javascript",
        "lines_changed": 3,
        "classifier_tag": "style",
        "tier": 0,
    },
    {
        "diff_text": (
            "--- a/models.py\n+++ b/models.py\n@@ -10,6 +10,8 @@\n"
            " class User:\n+    \"\"\"Represents an authenticated user.\"\"\"\n"
            "     id: str\n     name: str\n"
        ),
        "language": "python",
        "lines_changed": 2,
        "classifier_tag": "style",
        "tier": 0,
    },
    {
        "diff_text": (
            "--- a/helpers.ts\n+++ b/helpers.ts\n@@ -1,5 +1,5 @@\n"
            "-import {foo} from './foo'\n-import {bar} from './bar'\n"
            "+import { foo } from './foo';\n+import { bar } from './bar';\n"
            " export { foo, bar };\n"
        ),
        "language": "typescript",
        "lines_changed": 4,
        "classifier_tag": "style",
        "tier": 0,
    },
    {
        "diff_text": (
            "--- a/main.py\n+++ b/main.py\n@@ -5,7 +5,6 @@\n"
            " import os\n-import sys  # unused\n import json\n"
            " import logging\n"
        ),
        "language": "python",
        "lines_changed": 1,
        "classifier_tag": "style",
        "tier": 0,
    },
    {
        "diff_text": (
            "--- a/server.go\n+++ b/server.go\n@@ -12,6 +12,6 @@\n"
            "-func Handle( w http.ResponseWriter, r *http.Request){\n"
            "+func Handle(w http.ResponseWriter, r *http.Request) {\n"
            "     w.WriteHeader(http.StatusOK)\n }\n"
        ),
        "language": "go",
        "lines_changed": 2,
        "classifier_tag": "style",
        "tier": 1,
    },
    {
        "diff_text": (
            "--- a/api.py\n+++ b/api.py\n@@ -20,8 +20,8 @@\n"
            "-def list_items( page=1,limit=20 ):\n"
            "+def list_items(page: int = 1, limit: int = 20) -> list:\n"
            "     \"\"\"Paginated item list.\"\"\"\n"
            "-    return Item.query.paginate(page,limit)\n"
            "+    return Item.query.paginate(page, limit)\n"
        ),
        "language": "python",
        "lines_changed": 3,
        "classifier_tag": "style",
        "tier": 1,
    },
    {
        "diff_text": (
            "--- a/routes.rb\n+++ b/routes.rb\n@@ -4,6 +4,6 @@\n"
            " Rails.application.routes.draw do\n"
            "-  get '/users', to: 'users#index'\n"
            "+  resources :users, only: [:index, :show]\n"
            " end\n"
        ),
        "language": "ruby",
        "lines_changed": 2,
        "classifier_tag": "style",
        "tier": 1,
    },
    {
        "diff_text": (
            "--- a/logger.py\n+++ b/logger.py\n@@ -1,6 +1,7 @@\n"
            " import logging\n+\n"
            "-logging.basicConfig(level=logging.DEBUG)\n"
            "+logging.basicConfig(\n+    level=logging.INFO,\n"
            "+    format='%(asctime)s %(levelname)s %(message)s',\n+)\n"
        ),
        "language": "python",
        "lines_changed": 6,
        "classifier_tag": "style",
        "tier": 0,
    },
    {
        "diff_text": (
            "--- a/constants.java\n+++ b/constants.java\n@@ -2,5 +2,5 @@\n"
            " public class Constants {\n"
            "-    public static int RETRY_COUNT = 3;\n"
            "+    public static final int RETRY_COUNT = 3;\n"
            " }\n"
        ),
        "language": "java",
        "lines_changed": 2,
        "classifier_tag": "style",
        "tier": 1,
    },
    {
        "diff_text": (
            "--- a/utils.py\n+++ b/utils.py\n@@ -8,6 +8,6 @@\n"
            " def chunk_list(lst, n):\n"
            "-    return [lst[i:i + n] for i in range(0, len(lst), n)]\n"
            "+    return [lst[i : i + n] for i in range(0, len(lst), n)]\n"
        ),
        "language": "python",
        "lines_changed": 2,
        "classifier_tag": "style",
        "tier": 0,
    },
    {
        "diff_text": (
            "--- a/types.ts\n+++ b/types.ts\n@@ -1,6 +1,8 @@\n"
            "-export type Status = 'active'|'inactive'|'pending'\n"
            "+export type Status = 'active' | 'inactive' | 'pending';\n"
            "+\n+export type UserId = string;\n"
        ),
        "language": "typescript",
        "lines_changed": 3,
        "classifier_tag": "style",
        "tier": 1,
    },
]

# ── MEDIUM tasks (tier 2-3) — logic, architecture, test-coverage ──────────────

MEDIUM_TASKS: List[dict] = [
    {
        "diff_text": (
            "--- a/processor.py\n+++ b/processor.py\n@@ -14,10 +14,13 @@\n"
            " def process_batch(items):\n"
            "-    results = []\n-    for item in items:\n"
            "-        results.append(transform(item))\n-    return results\n"
            "+    if not items:\n+        return []\n"
            "+    return [transform(item) for item in items]\n"
        ),
        "language": "python",
        "lines_changed": 7,
        "classifier_tag": "logic",
        "tier": 2,
    },
    {
        "diff_text": (
            "--- a/cache.go\n+++ b/cache.go\n@@ -22,12 +22,16 @@\n"
            " func (c *Cache) Get(key string) (interface{}, bool) {\n"
            "+    c.mu.RLock()\n+    defer c.mu.RUnlock()\n"
            "     val, ok := c.data[key]\n"
            "-    if ok {\n-        c.hits++\n-    }\n"
            "+    if ok { c.hits.Add(1) }\n"
            "     return val, ok\n }\n"
        ),
        "language": "go",
        "lines_changed": 8,
        "classifier_tag": "logic",
        "tier": 2,
    },
    {
        "diff_text": (
            "--- a/queue.py\n+++ b/queue.py\n@@ -30,14 +30,19 @@\n"
            " class TaskQueue:\n+    def __init__(self, maxsize=100):\n"
            "+        self._q = asyncio.Queue(maxsize=maxsize)\n"
            "-    async def push(self, task):\n+    async def push(self, task, timeout=5.0):\n"
            "         try:\n"
            "-            self._q.put_nowait(task)\n"
            "+            await asyncio.wait_for(self._q.put(task), timeout)\n"
            "+        except asyncio.TimeoutError:\n"
            "+            raise QueueFullError(f'Queue full after {timeout}s')\n"
            "         except asyncio.QueueFull:\n"
            "             raise QueueFullError('Queue is full')\n"
        ),
        "language": "python",
        "lines_changed": 10,
        "classifier_tag": "logic",
        "tier": 3,
    },
    {
        "diff_text": (
            "--- a/user_service.java\n+++ b/user_service.java\n"
            "@@ -45,9 +45,14 @@\n"
            " public User findById(Long id) {\n"
            "-    return userRepo.findById(id).get();\n"
            "+    return userRepo.findById(id)\n"
            "+        .orElseThrow(() -> new UserNotFoundException(\n"
            "+            \"User not found: \" + id));\n"
            " }\n"
        ),
        "language": "java",
        "lines_changed": 5,
        "classifier_tag": "logic",
        "tier": 2,
    },
    {
        "diff_text": (
            "--- a/test_api.py\n+++ b/test_api.py\n@@ -0,0 +1,24 @@\n"
            "+import pytest\n+from fastapi.testclient import TestClient\n"
            "+from main import app\n+\n"
            "+client = TestClient(app)\n+\n"
            "+def test_health():\n+    r = client.get('/health')\n"
            "+    assert r.status_code == 200\n+\n"
            "+def test_create_user_missing_field():\n"
            "+    r = client.post('/users', json={})\n"
            "+    assert r.status_code == 422\n"
        ),
        "language": "python",
        "lines_changed": 14,
        "classifier_tag": "tests",
        "tier": 2,
    },
    {
        "diff_text": (
            "--- a/retry.ts\n+++ b/retry.ts\n@@ -5,14 +5,20 @@\n"
            " async function withRetry<T>(fn: () => Promise<T>,\n"
            "-                           retries = 3): Promise<T> {\n"
            "+                           retries = 3,\n"
            "+                           backoff = 1000): Promise<T> {\n"
            "     let lastErr: Error;\n"
            "     for (let i = 0; i < retries; i++) {\n"
            "         try { return await fn(); }\n"
            "-        catch (e) { lastErr = e as Error; }\n"
            "+        catch (e) {\n+            lastErr = e as Error;\n"
            "+            await sleep(backoff * 2 ** i);\n+        }\n"
            "     }\n     throw lastErr!;\n }\n"
        ),
        "language": "typescript",
        "lines_changed": 9,
        "classifier_tag": "logic",
        "tier": 3,
    },
    {
        "diff_text": (
            "--- a/service.go\n+++ b/service.go\n@@ -60,8 +60,12 @@\n"
            " func (s *Service) ProcessOrder(ctx context.Context, o Order) error {\n"
            "+    if err := o.Validate(); err != nil {\n"
            "+        return fmt.Errorf('invalid order: %w', err)\n+    }\n"
            "     tx, err := s.db.BeginTx(ctx, nil)\n"
            "-    if err != nil { return err }\n"
            "+    if err != nil { return fmt.Errorf('begin tx: %w', err) }\n"
            "     defer tx.Rollback()\n"
        ),
        "language": "go",
        "lines_changed": 7,
        "classifier_tag": "logic",
        "tier": 3,
    },
    {
        "diff_text": (
            "--- a/test_models.py\n+++ b/test_models.py\n@@ -0,0 +1,30 @@\n"
            "+import pytest\n+from models import Order, User\n+\n"
            "+@pytest.fixture\n+def sample_order():\n"
            "+    return Order(id='o1', user_id='u1', amount=100)\n+\n"
            "+class TestOrder:\n+    def test_total_with_tax(self, sample_order):\n"
            "+        assert sample_order.total_with_tax(0.2) == 120\n+\n"
            "+    def test_negative_amount_raises(self):\n"
            "+        with pytest.raises(ValueError):\n"
            "+            Order(id='o2', user_id='u1', amount=-1)\n"
        ),
        "language": "python",
        "lines_changed": 15,
        "classifier_tag": "tests",
        "tier": 2,
    },
    {
        "diff_text": (
            "--- a/router.py\n+++ b/router.py\n@@ -10,12 +10,18 @@\n"
            " class Router:\n-    def route(self, chunk, tag):\n"
            "+    def route(self, chunk, tag, registry):\n"
            "         \"\"\"Select model tier for this chunk.\"\"\"\n"
            "-        return registry[0]\n"
            "+        scores = [\n+            self._score(chunk, m, tag)\n"
            "+            for m in registry\n+        ]\n"
            "+        return registry[scores.index(max(scores))]\n+\n"
            "+    def _score(self, chunk, model, tag):\n"
            "+        return int(tag in model.capability_tags)\n"
        ),
        "language": "python",
        "lines_changed": 12,
        "classifier_tag": "logic",
        "tier": 3,
    },
    {
        "diff_text": (
            "--- a/data_pipeline.rs\n+++ b/data_pipeline.rs\n@@ -20,10 +20,16 @@\n"
            " fn process_records(records: &[Record]) -> Vec<ProcessedRecord> {\n"
            "-    records.iter().map(|r| process(r)).collect()\n"
            "+    records\n+        .par_iter()\n"
            "+        .filter(|r| r.is_valid())\n"
            "+        .map(|r| process(r))\n"
            "+        .collect()\n }\n"
        ),
        "language": "rust",
        "lines_changed": 7,
        "classifier_tag": "performance",
        "tier": 3,
    },
    {
        "diff_text": (
            "--- a/api_client.py\n+++ b/api_client.py\n@@ -8,14 +8,20 @@\n"
            " class APIClient:\n-    def get(self, url):\n+    def get(self, url, timeout=10):\n"
            "-        resp = requests.get(url)\n"
            "+        resp = requests.get(url, timeout=timeout)\n"
            "         resp.raise_for_status()\n         return resp.json()\n+\n"
            "+    def post(self, url, data, timeout=10):\n"
            "+        resp = requests.post(url, json=data, timeout=timeout)\n"
            "+        resp.raise_for_status()\n+        return resp.json()\n"
        ),
        "language": "python",
        "lines_changed": 9,
        "classifier_tag": "logic",
        "tier": 2,
    },
    {
        "diff_text": (
            "--- a/EventBus.java\n+++ b/EventBus.java\n@@ -15,12 +15,18 @@\n"
            " public class EventBus {\n"
            "-    private List<EventListener> listeners = new ArrayList<>();\n"
            "+    private final CopyOnWriteArrayList<EventListener> listeners\n"
            "+        = new CopyOnWriteArrayList<>();\n+\n"
            "     public void publish(Event e) {\n"
            "-        for (EventListener l : listeners) l.onEvent(e);\n"
            "+        listeners.forEach(l -> l.onEvent(e));\n"
            "     }\n }\n"
        ),
        "language": "java",
        "lines_changed": 7,
        "classifier_tag": "logic",
        "tier": 3,
    },
]

# ── HARD tasks (tier 4-5) — security & complex architecture ───────────────────

HARD_TASKS: List[dict] = [
    {
        "diff_text": (
            "--- a/runner.py\n+++ b/runner.py\n@@ -5,6 +5,6 @@\n"
            " def run_command(user_input):\n"
            "-    result = subprocess.run(user_input, shell=True, capture_output=True)\n"
            "+    args = shlex.split(user_input)\n"
            "+    result = subprocess.run(args, shell=False, capture_output=True)\n"
            "     return result.stdout.decode()\n"
        ),
        "language": "python",
        "lines_changed": 3,
        "classifier_tag": "security",
        "tier": 4,
    },
    {
        "diff_text": (
            "--- a/db.py\n+++ b/db.py\n@@ -10,6 +10,7 @@\n"
            " def get_user(username):\n"
            "-    query = f\"SELECT * FROM users WHERE username = '{username}'\"\n"
            "+    query = 'SELECT * FROM users WHERE username = ?'\n"
            "     cursor.execute(query)\n+    # Use parameterised query to prevent SQL injection\n"
        ),
        "language": "python",
        "lines_changed": 3,
        "classifier_tag": "security",
        "tier": 4,
    },
    {
        "diff_text": (
            "--- a/config.py\n+++ b/config.py\n@@ -1,6 +1,8 @@\n"
            "-SECRET_KEY = 'hardcoded_secret_abc123'\n"
            "-DB_PASSWORD = 'hunter2'\n"
            "+import os\n+SECRET_KEY = os.environ['SECRET_KEY']\n"
            "+DB_PASSWORD = os.environ['DB_PASSWORD']\n"
        ),
        "language": "python",
        "lines_changed": 4,
        "classifier_tag": "security",
        "tier": 5,
    },
    {
        "diff_text": (
            "--- a/deserializer.py\n+++ b/deserializer.py\n@@ -4,6 +4,10 @@\n"
            " def load_payload(data: bytes):\n"
            "-    return pickle.loads(data)  # deserialise user-supplied bytes\n"
            "+    try:\n+        obj = json.loads(data.decode('utf-8'))\n"
            "+    except (json.JSONDecodeError, UnicodeDecodeError) as e:\n"
            "+        raise ValueError(f'Invalid payload: {e}') from e\n"
            "+    return obj\n"
        ),
        "language": "python",
        "lines_changed": 6,
        "classifier_tag": "security",
        "tier": 5,
    },
    {
        "diff_text": (
            "--- a/auth.go\n+++ b/auth.go\n@@ -30,12 +30,16 @@\n"
            " func ValidateJWT(tokenStr string) (*Claims, error) {\n"
            "-    token, _ := jwt.Parse(tokenStr, func(t *jwt.Token) (interface{}, error) {\n"
            "-        return []byte('secret'), nil\n-    })\n"
            "+    token, err := jwt.ParseWithClaims(\n"
            "+        tokenStr, &Claims{},\n"
            "+        func(t *jwt.Token) (interface{}, error) {\n"
            "+            if _, ok := t.Method.(*jwt.SigningMethodHMAC); !ok {\n"
            "+                return nil, fmt.Errorf('unexpected signing method: %v', t.Header['alg'])\n"
            "+            }\n+            return jwtSecret, nil\n"
            "+        },\n"
            "+    )\n+    if err != nil { return nil, err }\n"
        ),
        "language": "go",
        "lines_changed": 14,
        "classifier_tag": "security",
        "tier": 4,
    },
    {
        "diff_text": (
            "--- a/upload.py\n+++ b/upload.py\n@@ -12,9 +12,15 @@\n"
            " def save_upload(filename, content):\n"
            "-    path = f'/uploads/{filename}'\n"
            "+    safe_name = os.path.basename(filename)\n"
            "+    if '..' in safe_name or safe_name.startswith('/'):\n"
            "+        raise ValueError('Path traversal detected')\n"
            "+    allowed = {'.jpg', '.png', '.pdf'}\n"
            "+    if os.path.splitext(safe_name)[1].lower() not in allowed:\n"
            "+        raise ValueError('File type not permitted')\n"
            "+    path = os.path.join('/uploads', safe_name)\n"
            "     with open(path, 'wb') as f:\n         f.write(content)\n"
        ),
        "language": "python",
        "lines_changed": 10,
        "classifier_tag": "security",
        "tier": 5,
    },
    {
        "diff_text": (
            "--- a/gateway.ts\n+++ b/gateway.ts\n@@ -40,16 +40,24 @@\n"
            " export class APIGateway {\n"
            "-    async forward(req: Request): Promise<Response> {\n"
            "+    async forward(req: Request, opts: ForwardOpts = {}): Promise<Response> {\n"
            "         const target = this.resolver.resolve(req.path);\n"
            "+        if (!target) throw new NotFoundError(req.path);\n"
            "+        const allowed = this.acl.check(req.user, target);\n"
            "+        if (!allowed) throw new ForbiddenError(req.user, target);\n"
            "         return this.http.proxy(req, target);\n"
            "     }\n }\n"
        ),
        "language": "typescript",
        "lines_changed": 8,
        "classifier_tag": "security",
        "tier": 4,
    },
    {
        "diff_text": (
            "--- a/PaymentService.java\n+++ b/PaymentService.java\n"
            "@@ -55,18 +55,28 @@\n"
            " public PaymentResult charge(long userId, BigDecimal amount) {\n"
            "+    if (amount.compareTo(BigDecimal.ZERO) <= 0)\n"
            "+        throw new IllegalArgumentException('Amount must be positive');\n"
            "     try (var conn = ds.getConnection()) {\n"
            "+        conn.setAutoCommit(false);\n"
            "         var stmt = conn.prepareStatement(\n"
            "             'SELECT balance FROM wallets WHERE user_id = ? FOR UPDATE');\n"
            "         stmt.setLong(1, userId);\n"
            "         var rs = stmt.executeQuery();\n"
            "+        if (!rs.next()) throw new UserNotFoundException(userId);\n"
            "         var bal = rs.getBigDecimal('balance');\n"
            "-        if (bal.compareTo(amount) < 0) throw new InsufficientFundsException();\n"
            "+        if (bal.compareTo(amount) < 0)\n"
            "+            throw new InsufficientFundsException(bal, amount);\n"
            "+        conn.commit();\n"
        ),
        "language": "java",
        "lines_changed": 12,
        "classifier_tag": "security",
        "tier": 5,
    },
    {
        "diff_text": (
            "--- a/crypto.rs\n+++ b/crypto.rs\n@@ -10,10 +10,14 @@\n"
            " fn encrypt(plaintext: &[u8], key: &[u8]) -> Vec<u8> {\n"
            "-    // ECB mode — deterministic, leaks patterns\n"
            "-    aes::Aes256::new(key).encrypt(plaintext)\n"
            "+    use aes_gcm::{Aes256Gcm, KeyInit, aead::{Aead, OsRng, rand_core::RngCore}};\n"
            "+    let cipher = Aes256Gcm::new_from_slice(key).expect('valid key');\n"
            "+    let mut nonce_bytes = [0u8; 12];\n"
            "+    OsRng.fill_bytes(&mut nonce_bytes);\n"
            "+    let nonce = Nonce::from_slice(&nonce_bytes);\n"
            "+    cipher.encrypt(nonce, plaintext).expect('encryption failure')\n"
            " }\n"
        ),
        "language": "rust",
        "lines_changed": 8,
        "classifier_tag": "security",
        "tier": 5,
    },
    {
        "diff_text": (
            "--- a/auth_middleware.go\n+++ b/auth_middleware.go\n"
            "@@ -18,14 +18,20 @@\n"
            " func AuthMiddleware(next http.Handler) http.Handler {\n"
            "     return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {\n"
            "-        token := r.Header.Get('Authorization')\n"
            "+        raw := r.Header.Get('Authorization')\n"
            "+        if !strings.HasPrefix(raw, 'Bearer ') {\n"
            "+            http.Error(w, 'missing bearer token', 401)\n"
            "+            return\n+        }\n"
            "+        token := strings.TrimPrefix(raw, 'Bearer ')\n"
            "         claims, err := validateToken(token)\n"
            "         if err != nil {\n"
            "-            w.WriteHeader(http.StatusUnauthorized)\n"
            "+            http.Error(w, err.Error(), http.StatusUnauthorized)\n"
            "             return\n         }\n"
        ),
        "language": "go",
        "lines_changed": 10,
        "classifier_tag": "security",
        "tier": 4,
    },
    {
        "diff_text": (
            "--- a/ratelimit.py\n+++ b/ratelimit.py\n@@ -5,14 +5,22 @@\n"
            " class RateLimiter:\n"
            "-    def __init__(self):\n-        self.counts = {}\n"
            "+    def __init__(self, limit=100, window=60):\n"
            "+        self.limit  = limit\n+        self.window = window\n"
            "+        self.counts: dict[str, list[float]] = {}\n"
            "+        self._lock  = threading.Lock()\n+\n"
            "     def is_allowed(self, key: str) -> bool:\n"
            "+        now = time.time()\n"
            "+        with self._lock:\n"
            "-        count = self.counts.get(key, 0)\n"
            "-        if count >= 100:\n-            return False\n"
            "-        self.counts[key] = count + 1\n-        return True\n"
            "+            hits = [t for t in self.counts.get(key, []) if t > now - self.window]\n"
            "+            self.counts[key] = hits\n"
            "+            if len(hits) >= self.limit:\n+                return False\n"
            "+            self.counts[key].append(now)\n"
            "+            return True\n"
        ),
        "language": "python",
        "lines_changed": 18,
        "classifier_tag": "security",
        "tier": 4,
    },
    {
        "diff_text": (
            "--- a/session.py\n+++ b/session.py\n@@ -8,10 +8,14 @@\n"
            " def create_session(user_id: str) -> str:\n"
            "-    token = str(user_id)  # predictable token\n"
            "+    token = secrets.token_urlsafe(32)\n"
            "     sessions[token] = {\n"
            "         'user_id': user_id,\n"
            "+        'created_at': datetime.utcnow().isoformat(),\n"
            "+        'expires_at': (datetime.utcnow() + timedelta(hours=1)).isoformat(),\n"
            "     }\n     return token\n"
        ),
        "language": "python",
        "lines_changed": 5,
        "classifier_tag": "security",
        "tier": 5,
    },
]


# ── Episode generation ─────────────────────────────────────────────────────────

def generate_episodes(registry, n_per_tier: int = 10) -> list[dict]:
    """
    Build synthetic episode + chunk rows from EASY / MEDIUM / HARD task lists.
    Returns a flat list of dicts, each containing both chunk and episode fields.
    """
    all_tasks = EASY_TASKS + MEDIUM_TASKS + HARD_TASKS
    episodes = []
    now = datetime.now(timezone.utc).isoformat()

    for task in all_tasks:
        tier = task["tier"]
        if tier >= len(registry):
            tier = len(registry) - 1

        model = registry[tier]
        chunk_id   = str(uuid.uuid4())
        episode_id = str(uuid.uuid4())
        pr_id      = str(uuid.uuid4())  # synthetic PR

        user_id, repo_full_name = _USER_REPO_BY_TIER.get(tier, ("user_charlie", "charlie/backend-api"))

        episodes.append({
            # chunk fields
            "chunk_id":        chunk_id,
            "pr_id":           pr_id,
            "file_path":       f"src/file_{chunk_id[:8]}.{task['language'][:2]}",
            "hunk_index":      0,
            "language":        task["language"],
            "lines_changed":   task["lines_changed"],
            "diff_text":       task["diff_text"],
            "classifier_tag":  task["classifier_tag"],
            # episode fields
            "episode_id":      episode_id,
            "user_id":         user_id,
            "repo_full_name":  repo_full_name,
            "model_id":        model.id,
            "tier_index":      tier,
            "cost_sats":       model.cost_sats,
            "verifier_pass":   1,
            "finding_count":   1,
            "timestamp":       now,
        })

    return episodes


# ── Database seeding ───────────────────────────────────────────────────────────

def seed_database(registry, db_path: str) -> int:
    """
    Insert synthetic chunk + episode rows into SQLite synchronously.
    Returns the number of episodes inserted.
    """
    episodes = generate_episodes(registry)

    with sqlite3.connect(db_path) as conn:
        inserted = 0
        for ep in episodes:
            pr_id    = ep["pr_id"]
            chunk_id = ep["chunk_id"]

            # Minimal pull_request row to satisfy the FK constraint on chunks
            conn.execute(
                """
                INSERT OR IGNORE INTO pull_requests
                    (id, user_id, repo_full_name, pr_number, pr_title, pr_url,
                     trigger_type, status, started_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (pr_id, ep["user_id"], ep["repo_full_name"], 0,
                 "Seed PR", "", "seed", "done", ep["timestamp"]),
            )

            conn.execute(
                """
                INSERT OR IGNORE INTO chunks
                    (id, pr_id, file_path, hunk_index, language, lines_changed, diff_text)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    chunk_id, pr_id,
                    ep["file_path"], ep["hunk_index"],
                    ep["language"], ep["lines_changed"], ep["diff_text"],
                ),
            )

            conn.execute(
                """
                INSERT OR IGNORE INTO episodes
                    (id, chunk_id, user_id, repo_full_name, model_id, tier_index,
                     classifier_tag, verifier_pass, cost_sats, finding_count,
                     diff_text, timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    ep["episode_id"], chunk_id,
                    ep["user_id"], ep["repo_full_name"],
                    ep["model_id"], ep["tier_index"],
                    ep["classifier_tag"], ep["verifier_pass"],
                    ep["cost_sats"], ep["finding_count"],
                    ep["diff_text"][:2000], ep["timestamp"],
                ),
            )
            inserted += 1

        conn.commit()

    return inserted


# ── CLI entry point ────────────────────────────────────────────────────────────

def main() -> None:
    from registry.loader import load_registry
    from router.router import train_router

    db_path = os.environ.get("DATABASE_PATH", "./verisync.db")

    print(f"Loading registry …")
    registry = load_registry()
    print(f"  {len(registry)} models loaded (tiers 0–{len(registry)-1})")

    print(f"Seeding database at {db_path} …")
    n = seed_database(registry, db_path)
    print(f"  {n} episodes inserted.")

    print("Training router …")
    accuracy = train_router(registry)
    if accuracy:
        print("  Per-class accuracy:")
        for tier, acc in sorted(accuracy.items()):
            print(f"    tier {tier}: {acc:.1%}")
    else:
        print("  Training skipped (not enough data or single class).")

    print("Done. Router model saved to", os.environ.get("ROUTER_MODEL_PATH", "./router_model.joblib"))


if __name__ == "__main__":
    main()
