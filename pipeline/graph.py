import asyncio
from typing import List, Dict, Any

from langgraph.graph import StateGraph, START, END

from models import ChunkReviewState, PRChunk, ModelEntry
from pipeline.nodes import (
    classifier_node,
    router_node,
    reviewer_node,
    verifier_node,
    escalate_node,
    synthesiser_node,
    done_node,
    failed_node,
    ReviewReport,
)


def should_escalate(state: ChunkReviewState) -> str:
    """
    Returns 'done' if verifier_accepted=True, 'escalate' if retries remain and budget ok, else 'failed'.
    """
    if state.verifier_accepted:
        return "done"
    
    if state.retry_count < state.max_retries and state.budget_remaining_sats > 0:
        return "escalate"
    
    return "failed"


def build_graph():
    """
    Constructs the LangGraph graph with all nodes and edges.
    """
    workflow = StateGraph(ChunkReviewState)

    # In a real system, these dependencies would be injected or instantiated here.
    # We provide dummy classes to adapt the node signatures in nodes.py to LangGraph.
    
    from router.router import Router
    from db.store import DBStore
    from registry.registry import Registry



    def _classifier(state: ChunkReviewState):
        return classifier_node(state)
        
    def _router(state: ChunkReviewState):
        # wrap the registry for get_tier / get_next_tier methods expected by nodes.py
        reg = Registry(state.registry)
        router_instance = Router()
        return router_node(state, registry=reg, router=router_instance)
        
    def _reviewer(state: ChunkReviewState):
        worker_url = "http://localhost:8000"
        return reviewer_node(state, worker_url=worker_url)
        
    def _verifier(state: ChunkReviewState):
        db_store = DBStore()
        return verifier_node(state, db_store=db_store)
        
    def _escalate(state: ChunkReviewState):
        reg = Registry(state.registry)
        return escalate_node(state, registry=reg)

    def _done(state: ChunkReviewState):
        return done_node(state)

    def _failed(state: ChunkReviewState):
        return failed_node(state)

    workflow.add_node("classifier", _classifier)
    workflow.add_node("router", _router)
    workflow.add_node("reviewer", _reviewer)
    workflow.add_node("verifier", _verifier)
    workflow.add_node("escalate", _escalate)
    workflow.add_node("done", _done)
    workflow.add_node("failed", _failed)

    workflow.add_edge(START, "classifier")
    workflow.add_edge("classifier", "router")
    workflow.add_edge("router", "reviewer")
    workflow.add_edge("reviewer", "verifier")

    workflow.add_conditional_edges(
        "verifier",
        should_escalate,
        {
            "done": "done",
            "escalate": "escalate",
            "failed": "failed",
        }
    )

    workflow.add_edge("escalate", "router")
    workflow.add_edge("done", END)
    workflow.add_edge("failed", END)

    return workflow.compile()


# Global graph instance
graph = build_graph()


async def run_chunk_review(chunk: PRChunk, user_id: str, registry: List[ModelEntry], budget: int) -> ChunkReviewState:
    """
    Entry point per chunk. Initializes state and invokes the graph.
    """
    initial_state = ChunkReviewState(
        chunk=chunk,
        user_id=user_id,
        registry=registry,
        budget_remaining_sats=budget,
        current_model_id=""
    )
    
    # If state is a BaseModel, LangGraph accepts and returns a dictionary or dict-like object
    # depending on how StateGraph is configured. LangGraph ainvoke processes the graph async.
    result = await graph.ainvoke(initial_state)
    
    if isinstance(result, dict):
        return ChunkReviewState(**result)
    return result


async def run_pr_review(pr_id: str, chunks: List[PRChunk], user_id: str, registry: List[ModelEntry], budget: int) -> ReviewReport:
    """
    Orchestrates all chunks for a PR concurrently using asyncio.gather.
    After all chunks are done, synthesises the final report.
    """
    # Create coroutines for each chunk
    tasks = [
        run_chunk_review(chunk, user_id, registry, budget)
        for chunk in chunks
    ]
    
    # Run all reviews concurrently
    final_states = await asyncio.gather(*tasks)
    
    # Gather findings
    all_findings = []
    for state in final_states:
        if state.findings:
            all_findings.extend(state.findings)
            
    # Call synthesiser node
    report = synthesiser_node(pr_id, all_findings)
    
    return report
