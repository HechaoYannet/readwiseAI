"""Orchestrator – main control loop that coordinates Planner, Dispatcher, and Verifier."""
from __future__ import annotations

import logging
from typing import Any, Dict, List

from app.models.state import OrchestratorState, RequestStatus, SubTask, SubTaskStatus
from app.orchestrator.checkpoint import get_checkpoint_manager
from app.orchestrator.dispatcher import Dispatcher
from app.orchestrator.planner import Planner
from app.orchestrator.verifier import Verifier

logger = logging.getLogger(__name__)


class Orchestrator:
    def __init__(self):
        self.planner = Planner()
        self.verifier = Verifier()
        self.dispatcher = Dispatcher()
        self.checkpoint = get_checkpoint_manager()

    async def process_request(
        self, request_id: str, user_request: Dict[str, Any]
    ) -> None:
        """Entry point called by BackgroundTasks."""
        state = self.checkpoint.load(request_id)
        if state is None:
            logger.error("No checkpoint found for %s", request_id)
            return

        await self._run(state)

    async def resume_processing(self, request_id: str) -> None:
        """Resume after a sub-agent callback."""
        state = self.checkpoint.load(request_id)
        if state is None:
            return
        await self._run(state)

    async def _run(self, state: OrchestratorState) -> None:
        for _iteration in range(20):  # guard against infinite loops
            if state.status == RequestStatus.PENDING:
                state.status = RequestStatus.PLANNING
                state = await self.planner.plan(state)
                if not state.sub_tasks:
                    state.status = RequestStatus.FAILED
                    break
                state.status = RequestStatus.WAITING

            elif state.status == RequestStatus.WAITING:
                # Dispatch any pending tasks
                state = await self.dispatcher.dispatch_all_pending(state)

                # Look for a completed-but-not-yet-verified task
                unverified = next(
                    (
                        t
                        for t in state.sub_tasks
                        if t.status == SubTaskStatus.COMPLETED
                        and t.sub_task_id not in state.completed_results
                    ),
                    None,
                )

                if unverified:
                    state = await self.verifier.verify(state, unverified)
                    if unverified.status == SubTaskStatus.FAILED:
                        # Check if the whole request should be failed
                        if not self._any_retryable(state):
                            state.status = RequestStatus.FAILED
                    elif unverified.status == SubTaskStatus.RETRY:
                        state.status = RequestStatus.RETRY
                    else:
                        # Inject any new sub-tasks emitted by this task
                        state = self._inject_new_tasks(state, unverified)
                        if self._all_tasks_done(state):
                            state.status = RequestStatus.COMPLETED
                else:
                    # All tasks either completed or failed
                    if self._all_tasks_done(state):
                        if self._any_failed(state):
                            state.status = RequestStatus.FAILED
                        else:
                            state.status = RequestStatus.COMPLETED
                    # else still waiting – save checkpoint and exit
                    else:
                        self.checkpoint.save(state)
                        return

            elif state.status == RequestStatus.RETRY:
                retry_task = next(
                    (t for t in state.sub_tasks if t.status == SubTaskStatus.RETRY),
                    None,
                )
                if retry_task:
                    state = await self.planner.replan(state, retry_task)
                state.status = RequestStatus.WAITING

            elif state.status in (RequestStatus.COMPLETED, RequestStatus.FAILED):
                break

        self._finalize(state)

    # ------------------------------------------------------------------
    # Dynamic task injection (Plan A – LangChain-style flexibility)
    # ------------------------------------------------------------------

    def _inject_new_tasks(
        self, state: OrchestratorState, completed_task: SubTask
    ) -> OrchestratorState:
        """Inject sub-tasks emitted by a completed task into the state.

        When a corpus_expert planning task returns ``new_sub_tasks`` in its
        result, those tasks are appended to ``state.sub_tasks`` so the
        Dispatcher will pick them up on the next iteration.  This implements
        the Plan A "high-flexibility main LLM" behaviour without requiring an
        upfront full plan.
        """
        new_tasks_data: List[Dict[str, Any]] = completed_task.result.get(
            "new_sub_tasks", []
        )
        if not new_tasks_data:
            return state

        existing_ids = {t.sub_task_id for t in state.sub_tasks}
        injected = 0
        for task_data in new_tasks_data:
            tid = task_data.get("sub_task_id", "")
            if not tid or tid in existing_ids:
                continue
            try:
                state.sub_tasks.append(SubTask(**task_data))
                existing_ids.add(tid)
                injected += 1
            except Exception as exc:
                logger.warning("Could not inject task %s: %s", tid, exc)

        if injected:
            logger.info(
                "Injected %d new sub-tasks from %s", injected, completed_task.sub_task_id
            )
        return state

    # ------------------------------------------------------------------
    def _all_tasks_done(self, state: OrchestratorState) -> bool:
        terminal = {SubTaskStatus.COMPLETED, SubTaskStatus.FAILED}
        return all(t.status in terminal for t in state.sub_tasks)

    def _any_failed(self, state: OrchestratorState) -> bool:
        return any(t.status == SubTaskStatus.FAILED for t in state.sub_tasks)

    def _any_retryable(self, state: OrchestratorState) -> bool:
        return state.retry_count < 2

    def _finalize(self, state: OrchestratorState) -> None:
        result = self._assemble_result(state)
        self.checkpoint.save_result(state.request_id, state.user_id, result)
        self.checkpoint.delete(state.request_id)
        logger.info(
            "Request %s finalized with status %s", state.request_id, state.status
        )

    def _assemble_result(self, state: OrchestratorState) -> dict:
        return {
            "request_id": state.request_id,
            "status": state.status,
            "results": state.completed_results,
            "error_log": state.error_log,
        }


# Singleton
_orchestrator: Orchestrator | None = None


def get_orchestrator() -> Orchestrator:
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = Orchestrator()
    return _orchestrator
