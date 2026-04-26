import sys
import pytest
import asyncio
from unittest.mock import patch, MagicMock

from models import PRChunk, ModelEntry
from pipeline.graph import run_chunk_review, run_pr_review

# Mock data
mock_registry = [
    ModelEntry(
        id="llama3-8b",
        name="llama3:8b",
        provider="qrok-api",
        cost_sats=5,
        endpoint_url="http://localhost:8000/worker/llama3-8b",
        capability_tags=["style", "classify"]
    ),
    ModelEntry(
        id="mistral-7b",
        name="mistral:7b",
        provider="qrok-api",
        cost_sats=10,
        endpoint_url="http://localhost:8000/worker/mistral-7b",
        capability_tags=["logic"]
    )
]

mock_chunk = PRChunk(
    id="chunk-123",
    pr_id="pr-999",
    file_path="src/utils.py",
    hunk_index=0,
    language="python",
    diff_text="def test():\n+    pass\n",
    lines_changed=2
)


@pytest.mark.asyncio
@patch("pipeline.nodes.Groq")
@patch("pipeline.nodes.httpx.Client")
@patch("pipeline.nodes.genai.Client")
async def test_run_chunk_review(mock_genai, mock_httpx, mock_groq):
    # Evict any mocks injected by test_auth.py so the real db.store is used
    for _k in list(sys.modules.keys()):
        if _k in ("db", "db.store"):
            del sys.modules[_k]

    import db.store
    db.store.DB_PATH = "./test_verisync.db"
    from db.store import init_db
    import aiosqlite
    await init_db()

    # Clear table if it exists
    async with aiosqlite.connect(db.store.DB_PATH) as db_conn:
        await db_conn.execute("DELETE FROM episodes")
        await db_conn.commit()

    # 1. Setup Groq mock (classifier)
    mock_groq_instance = MagicMock()
    mock_groq.return_value = mock_groq_instance
    mock_choice = MagicMock()
    mock_choice.message.content = "logic\n"
    mock_groq_instance.chat.completions.create.return_value.choices = [mock_choice]

    # 2. Setup httpx mock (reviewer)
    mock_httpx_instance = MagicMock()
    mock_httpx.return_value.__enter__.return_value = mock_httpx_instance
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "findings": [{"issue": "Test issue", "severity": "minor", "line_number": 1, "suggestion": "Fix it"}]
    }
    mock_httpx_instance.post.return_value = mock_response

    # 3. Setup genai mock (verifier)
    mock_genai_instance = MagicMock()
    mock_genai.return_value = mock_genai_instance
    mock_genai_response = MagicMock()
    mock_genai_response.text = "accept"
    mock_genai_instance.models.generate_content.return_value = mock_genai_response

    # Run the pipeline
    final_state = await run_chunk_review(
        chunk=mock_chunk,
        user_id="user-1",
        registry=mock_registry,
        budget=100
    )

    # Assertions
    assert final_state.classifier_tag == "logic"
    assert final_state.status == "done"
    assert final_state.verifier_accepted is True
    assert len(final_state.findings) == 1
    assert final_state.findings[0].description == "Test issue"
    
    # Assert DB actually recorded the episode
    import db.store
    async with aiosqlite.connect(db.store.DB_PATH) as db_conn:
        async with db_conn.execute("SELECT * FROM episodes") as cur:
            rows = await cur.fetchall()
            assert len(rows) == 1
            assert rows[0][1] == mock_chunk.id  # chunk_id is column 1


@pytest.mark.asyncio
@patch("pipeline.nodes.Groq")
@patch("pipeline.nodes.httpx.Client")
@patch("pipeline.nodes.genai.Client")
async def test_run_pr_review(mock_genai, mock_httpx, mock_groq):
    # Evict any mocks injected by test_auth.py
    for _k in list(sys.modules.keys()):
        if _k in ("db", "db.store"):
            del sys.modules[_k]

    import db.store
    db.store.DB_PATH = "./test_verisync.db"
    from db.store import init_db
    import aiosqlite
    await init_db()
    # 1. Setup Groq mock (classifier)
    mock_groq_instance = MagicMock()
    mock_groq.return_value = mock_groq_instance
    mock_choice = MagicMock()
    mock_choice.message.content = "style\n"
    mock_groq_instance.chat.completions.create.return_value.choices = [mock_choice]

    # 2. Setup httpx mock (reviewer)
    mock_httpx_instance = MagicMock()
    mock_httpx.return_value.__enter__.return_value = mock_httpx_instance
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "findings": [{"issue": "Style issue", "severity": "minor", "line_number": 1, "suggestion": "Fix format"}]
    }
    mock_httpx_instance.post.return_value = mock_response

    # 3. Setup genai mock (verifier and synthesiser)
    mock_genai_instance = MagicMock()
    mock_genai.return_value = mock_genai_instance
    mock_genai_response = MagicMock()
    mock_genai_response.text = "accept\nSUMMARY: This PR fixes format issues.\nPRIORITY_ACTIONS: [{\"action\": \"Fix indentation\"}]"
    mock_genai_instance.models.generate_content.return_value = mock_genai_response

    # Run PR review with multiple chunks
    report = await run_pr_review(
        pr_id="pr-999",
        chunks=[mock_chunk, mock_chunk],
        user_id="user-1",
        registry=mock_registry,
        budget=100
    )

    assert report.pr_id == "pr-999"
    assert report.total_chunks > 0
    # The report findings might be aggregated, but we can verify it contains the expected text
    assert len(report.priority_actions) == 1
    assert report.priority_actions[0]["action"] == "Fix indentation"
    
    import db.store
    # Assert DB recorded the multiple chunks
    async with aiosqlite.connect(db.store.DB_PATH) as db_conn:
        async with db_conn.execute("SELECT * FROM episodes") as cur:
            rows = await cur.fetchall()
            assert len(rows) >= 2
