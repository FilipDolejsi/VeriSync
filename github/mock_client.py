"""
MockGitHubClient — full pipeline testing without a real GitHub repo.

PR #1 covers: security (SQL injection), style (bad naming), logic (off-by-one)
PR #2 covers: architecture (bloated class), test-coverage (new test file)
"""

MOCK_PRS: dict[int, dict] = {
    1: {
        "number": 1,
        "title": "Add user login endpoint",
        "url": "https://github.com/mock/repo/pull/1",
        "diff": """\
diff --git a/auth/login.py b/auth/login.py
--- a/auth/login.py
+++ b/auth/login.py
@@ -1,4 +1,10 @@
+import sqlite3
+
 def get_user(user_id):
-    pass
+    conn = sqlite3.connect("users.db")
+    cursor = conn.cursor()
+    query = "SELECT * FROM users WHERE id = " + user_id
+    cursor.execute(query)
+    return cursor.fetchone()
diff --git a/auth/utils.py b/auth/utils.py
--- a/auth/utils.py
+++ b/auth/utils.py
@@ -1,3 +1,7 @@
-def validateToken(t):
-    return t != None
+def validate_token(token: str) -> bool:
+    return token is not None and len(token) > 0
+
+def ParseUserName(raw):
+    return raw.strip().lower()
diff --git a/auth/session.py b/auth/session.py
--- /dev/null
+++ b/auth/session.py
@@ -0,0 +1,10 @@
+SESSION_STORE = {}
+
+def create_session(user_id: str) -> str:
+    import random, string
+    token = ''.join(random.choices(string.ascii_letters, k=16))
+    SESSION_STORE[token] = user_id
+    return token
+
+def get_session_user(token: str):
+    items = list(SESSION_STORE.items())
+    for i in range(len(items) + 1):
+        if items[i][0] == token:
+            return items[i][1]
""",
    },
    2: {
        "number": 2,
        "title": "Refactor pipeline into modules",
        "url": "https://github.com/mock/repo/pull/2",
        "diff": """\
diff --git a/pipeline/runner.py b/pipeline/runner.py
--- /dev/null
+++ b/pipeline/runner.py
@@ -0,0 +1,18 @@
+class PipelineRunner:
+    def __init__(self):
+        self.stages = []
+        self.results = []
+        self.errors = []
+        self.metadata = {}
+        self.config = {}
+        self.state = {}
+        self.cache = {}
+        self.logger = None
+        self.hooks = []
+        self.plugins = []
+
+    def run(self, chunks):
+        for chunk in chunks:
+            for stage in self.stages:
+                chunk = stage.process(chunk)
+            self.results.append(chunk)
diff --git a/pipeline/tests/test_runner.py b/pipeline/tests/test_runner.py
--- /dev/null
+++ b/pipeline/tests/test_runner.py
@@ -0,0 +1,5 @@
+from pipeline.runner import PipelineRunner
+
+def test_runner_empty_chunks():
+    result = PipelineRunner().run([])
+    assert result == []
""",
    },
}


class MockGitHubClient:
    """Drop-in for the real PyGithub client. Import as GitHubClient for testing."""

    def get_user_repos(self, token: str = "") -> list[dict]:
        return [
            {"full_name": "mock/repo", "private": False},
            {"full_name": "mock/private-repo", "private": True},
        ]

    def register_webhook(self, repo_full_name: str, github_token: str) -> tuple[int, str]:
        return 99999, "mock_secret_" + repo_full_name.replace("/", "_")

    def delete_webhook(self, repo_full_name: str, github_token: str, hook_id: int):
        pass

    def fetch_pr_diff(self, repo_full_name: str, pr_number: int, github_token: str = "") -> dict:
        pr = MOCK_PRS.get(pr_number)
        if not pr:
            raise ValueError(f"Mock PR #{pr_number} not found. Available: {list(MOCK_PRS.keys())}")
        return pr

    def fetch_push_diff(self, repo_full_name: str, before_sha: str, after_sha: str, github_token: str = "") -> dict:
        return MOCK_PRS[1] | {"title": f"Direct push {after_sha[:7]}", "number": None}

    def post_review_comment(self, repo_full_name: str, pr_number: int, findings: list, github_token: str = ""):
        print(f"\n[MockGitHub] Posting {len(findings)} finding(s) on {repo_full_name}#{pr_number}:")
        for f in findings:
            print(f"  [{f.get('severity','?').upper()}] line {f.get('line_number','?')}: {f.get('description','')}")
