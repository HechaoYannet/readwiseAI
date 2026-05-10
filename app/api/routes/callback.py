"""POST /internal/callback/{request_id} – sub-agent result callback."""
from __future__ import annotations

import logging
import os
import secrets

from fastapi import APIRouter, BackgroundTasks, Header, HTTPException, status
from pydantic import BaseModel

from app.config import is_production_env
from app.models.state import SubTaskStatus
from app.orchestrator.agent import get_orchestrator
from app.orchestrator.checkpoint import get_checkpoint_manager

router = APIRouter()
logger = logging.getLogger(__name__)
_DEFAULT_CALLBACK_SECRET = "readwise-dev-internal-callback-secret"
_CALLBACK_SECRET = os.getenv("INTERNAL_CALLBACK_SECRET", "")

if not _CALLBACK_SECRET:
    if is_production_env():
        raise RuntimeError("INTERNAL_CALLBACK_SECRET must be set in production")
    logger.warning(
        "INTERNAL_CALLBACK_SECRET is not set. Using the default dev secret – "
        "set INTERNAL_CALLBACK_SECRET in production."
    )
    _CALLBACK_SECRET = _DEFAULT_CALLBACK_SECRET


class CallbackPayload(BaseModel):
    task_id: str
    result: dict


@router.post("/callback/{request_id}")
async def subagent_callback(
    request_id: str,
    payload: CallbackPayload,
    background_tasks: BackgroundTasks,
    x_internal_callback_token: str | None = Header(default=None),
):
    """Called by a sub-agent when it has finished a task."""
    if not x_internal_callback_token or not secrets.compare_digest(
        x_internal_callback_token,
        _CALLBACK_SECRET,
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden",
        )
    checkpoint_manager = get_checkpoint_manager()
    state = checkpoint_manager.load(request_id)
    if state is None:
        return {"status": "not_found"}

    for sub_task in state.sub_tasks:
        if sub_task.sub_task_id == payload.task_id:
            sub_task.result = payload.result
            sub_task.status = SubTaskStatus.COMPLETED
            break

    checkpoint_manager.save(state)

    orchestrator = get_orchestrator()
    background_tasks.add_task(orchestrator.resume_processing, request_id)

    return {"status": "ok"}
