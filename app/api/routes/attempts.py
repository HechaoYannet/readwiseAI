"""POST /api/attempt – submit an answer attempt for processing."""
from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, BackgroundTasks

from app.models.state import AttemptRequest, OrchestratorState, RequestStatus
from app.orchestrator.agent import get_orchestrator
from app.orchestrator.checkpoint import get_checkpoint_manager

router = APIRouter()


def _generate_request_id() -> str:
    return "req_" + uuid.uuid4().hex[:12]


@router.post("/attempt")
async def submit_attempt(
    attempt: AttemptRequest,
    background_tasks: BackgroundTasks,
):
    """Submit a user attempt; returns a request_id for later polling."""
    request_id = _generate_request_id()
    now = datetime.now()

    state = OrchestratorState(
        request_id=request_id,
        user_id=attempt.user_id,
        status=RequestStatus.PENDING,
        original_request=attempt.model_dump(),
        created_at=now,
        updated_at=now,
    )

    checkpoint_manager = get_checkpoint_manager()
    checkpoint_manager.save(state)

    orchestrator = get_orchestrator()
    background_tasks.add_task(
        orchestrator.process_request,
        request_id,
        attempt.model_dump(),
    )

    return {
        "request_id": request_id,
        "status": "processing",
        "result_url": f"/api/result/{request_id}",
    }
