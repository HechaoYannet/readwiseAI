"""GET /api/result/{request_id} – poll for processing results."""
from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.models.state import RequestStatus
from app.orchestrator.checkpoint import get_checkpoint_manager

router = APIRouter()


@router.get("/result/{request_id}")
async def get_result(request_id: str):
    """Poll for the result of a previously submitted request."""
    checkpoint_manager = get_checkpoint_manager()

    # Check for a saved final result first
    saved = checkpoint_manager.load_result(request_id)
    if saved is not None:
        return saved

    # Fall back to live checkpoint
    state = checkpoint_manager.load(request_id)
    if state is None:
        return JSONResponse(status_code=404, content={"status": "not_found"})

    if state.status == RequestStatus.COMPLETED:
        result = {
            "request_id": request_id,
            "status": "completed",
            "results": state.completed_results,
        }
        checkpoint_manager.save_result(request_id, result)
        checkpoint_manager.delete(request_id)
        return result

    if state.status == RequestStatus.FAILED:
        return {
            "request_id": request_id,
            "status": "failed",
            "error_log": state.error_log,
        }

    return {"request_id": request_id, "status": "processing"}
