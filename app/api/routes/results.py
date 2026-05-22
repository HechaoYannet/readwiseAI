"""GET /api/result/{request_id} – poll for processing results."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from app.auth.dependencies import get_current_user
from app.auth.models import TokenData
from app.models.state import RequestStatus, SubTaskStatus
from app.orchestrator.checkpoint import get_checkpoint_manager

router = APIRouter()


def _build_progress(state) -> dict:
    """Extract progress info from orchestrator state for polling consumers."""
    if not state.sub_tasks:
        # Planning phase – no sub-tasks yet; report 0% with the latest status hint.
        current_task = state.status_history[-1] if state.status_history else "正在规划..."
        return {
            "total_tasks": 0,
            "completed_tasks": 0,
            "failed_tasks": 0,
            "current_task": current_task,
            "percentage": 0,
            "steps": [],
        }

    total = len(state.sub_tasks)
    completed = sum(1 for t in state.sub_tasks if t.status == SubTaskStatus.COMPLETED)
    running = [t.description for t in state.sub_tasks if t.status == SubTaskStatus.RUNNING]
    failed = sum(1 for t in state.sub_tasks if t.status == SubTaskStatus.FAILED)

    steps = []
    for t in state.sub_tasks:
        step = {"id": t.sub_task_id, "description": t.description, "status": t.status.value}
        if t.error_message:
            step["error"] = t.error_message
        steps.append(step)

    return {
        "total_tasks": total,
        "completed_tasks": completed,
        "failed_tasks": failed,
        "current_task": running[0] if running else None,
        "percentage": round((completed + failed) * 100 / total) if total > 0 else 0,
        "steps": steps,
    }


@router.get("/result/{request_id}")
async def get_result(
        request_id: str,
        token_data: TokenData = Depends(get_current_user),
):
    """Poll for the result of a previously submitted request.

    Requires a valid JWT Bearer token.  Returns 403 if the request belongs to
    a different user, or ``{"status": "not_found"}`` if the request_id is
    unknown (to avoid leaking whether a request exists).
    """
    user_id = token_data.user_id
    checkpoint_manager = get_checkpoint_manager()

    # Ownership check: verify that the request belongs to the authenticated user.
    stored_user_id = checkpoint_manager.lookup_user_id(request_id)
    if stored_user_id is None:
        return JSONResponse(status_code=200, content={"status": "not_found"})
    if stored_user_id != user_id:
        return JSONResponse(status_code=403, content={"error": "Forbidden"})

    # Check for a saved final result first.
    saved = checkpoint_manager.load_result(request_id, user_id)
    if saved is not None:
        return saved

    # Fall back to live checkpoint.
    state = checkpoint_manager.load(request_id)
    if state is None:
        return JSONResponse(status_code=200, content={"status": "not_found"})

    if state.status == RequestStatus.COMPLETED:
        result = {
            "request_id": request_id,
            "session_id": state.session_id,
            "status": "completed",
            "status_history": state.status_history,
            "results": state.completed_results,
            "error_log": state.error_log,
        }
        # Reload working memory to grab the latest agent_information
        try:
            from app.models.working_memory import WorkingMemory
            wm = WorkingMemory.load(session_id=state.session_id or "", user_id=user_id)
            if wm and wm.agent_information:
                result["agent_information"] = wm.agent_information
        except Exception:
            pass
        checkpoint_manager.save_result(request_id, user_id, result)
        checkpoint_manager.delete(request_id)
        return result

    if state.status == RequestStatus.FAILED:
        return {
            "request_id": request_id,
            "status": "failed",
            "status_history": state.status_history,
            "error_log": state.error_log,
        }

    # Include progress info during processing
    return {
        "request_id": request_id,
        "status": state.status,
        "status_history": state.status_history,
        "progress": _build_progress(state),
    }
