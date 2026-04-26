import os
import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel

from models import ModelEntry
from payments.wallet import get_wallet
from workers.handler import dispatch

logger = logging.getLogger(__name__)

USE_MOCK_WALLET = os.environ.get("USE_MOCK_WALLET", "true").lower() == "true"


class WorkerRequest(BaseModel):
    task: str
    chunk_id: str
    user_id: str
    wallet_id: str


class WorkerResponse(BaseModel):
    response: str
    model_id: str
    cost_sats: int
    chunk_id: str


def _make_payment_dep(model_entry: ModelEntry):
    """
    Returns a FastAPI dependency that handles payment before the worker runs.
    Mock mode: deducts from MockWallet.
    Real mode: swap this for L402 middleware when MDK is available.
    """
    async def payment_dep(body: WorkerRequest) -> WorkerRequest:
        if USE_MOCK_WALLET:
            wallet = get_wallet()
            try:
                wallet.pay(
                    from_wallet_id=body.wallet_id,
                    to_wallet_id=f"model_{model_entry.id}",
                    amount_sats=model_entry.cost_sats,
                )
            except Exception as e:
                raise HTTPException(status_code=402, detail=str(e))
        return body

    return payment_dep


def create_worker_router(registry: list[ModelEntry]) -> APIRouter:
    router = APIRouter(prefix="/worker")

    for model_entry in registry:
        _register_route(router, model_entry)

    logger.info(f"Registered {len(registry)} worker endpoint(s): "
                f"{[m.id for m in registry]}")
    return router


def _register_route(router: APIRouter, model_entry: ModelEntry):
    payment_dep = _make_payment_dep(model_entry)

    async def endpoint(
        body: Annotated[WorkerRequest, Depends(payment_dep)],
    ) -> WorkerResponse:
        logger.info(f"Worker [{model_entry.id}] handling chunk {body.chunk_id}")
        try:
            response_text = await dispatch(body.task, model_entry)
        except Exception as e:
            logger.error(f"Worker [{model_entry.id}] failed: {e}")
            raise HTTPException(status_code=500, detail=str(e))

        return WorkerResponse(
            response=response_text,
            model_id=model_entry.id,
            cost_sats=model_entry.cost_sats,
            chunk_id=body.chunk_id,
        )

    # Unique name required — FastAPI uses function name for route identification
    endpoint.__name__ = f"worker_{model_entry.id}"

    router.add_api_route(
        f"/{model_entry.id}",
        endpoint,
        methods=["POST"],
        response_model=WorkerResponse,
    )
