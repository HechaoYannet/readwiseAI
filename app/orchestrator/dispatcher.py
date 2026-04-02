"""Dispatcher – routes sub-tasks to the appropriate sub-agent and executes them."""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from app.models.state import OrchestratorState, SubTask, SubTaskStatus

logger = logging.getLogger(__name__)


def _get_sub_agent(name: str) -> Optional[Any]:
    """Lazy-import sub-agents to avoid circular imports."""
    if name == "diagnosis_expert":
        from app.sub_agents.diagnosis import DiagnosisExpert

        return DiagnosisExpert()
    if name == "corpus_expert":
        from app.sub_agents.corpus import CorpusExpert

        return CorpusExpert()
    if name == "question_expert":
        from app.sub_agents.question import QuestionExpert

        return QuestionExpert()
    if name == "qa_expert":
        from app.sub_agents.qa import QAExpert

        return QAExpert()
    return None


class Dispatcher:
    async def dispatch_all_pending(
        self, state: OrchestratorState
    ) -> OrchestratorState:
        """Execute all PENDING sub-tasks whose dependencies are satisfied."""
        for task in state.sub_tasks:
            if task.status != SubTaskStatus.PENDING:
                continue
            if not self._deps_satisfied(task, state):
                continue
            state = await self._execute_task(task, state)
        return state

    def _deps_satisfied(self, task: SubTask, state: OrchestratorState) -> bool:
        for dep_id in task.depends_on:
            dep = next((t for t in state.sub_tasks if t.sub_task_id == dep_id), None)
            if dep is None or dep.status != SubTaskStatus.COMPLETED:
                return False
        return True

    async def _execute_task(
        self, task: SubTask, state: OrchestratorState
    ) -> OrchestratorState:
        agent = _get_sub_agent(task.assigned_to)
        if agent is None:
            task.status = SubTaskStatus.FAILED
            task.error_message = f"Unknown agent: {task.assigned_to}"
            state.error_log.append(task.error_message)
            return state

        task.status = SubTaskStatus.RUNNING
        try:
            context: Dict[str, Any] = {
                "user_id": state.user_id,
                "completed_results": state.completed_results,
            }
            result = await agent.execute(task.input, context)
            task.result = result
            # Mark as completed here so verifier can inspect it
            task.status = SubTaskStatus.COMPLETED
            logger.info("Task %s completed by %s", task.sub_task_id, task.assigned_to)
        except Exception as exc:
            task.status = SubTaskStatus.FAILED
            task.error_message = str(exc)
            state.error_log.append(
                f"Task {task.sub_task_id} raised exception: {exc}"
            )
            logger.error("Task %s failed: %s", task.sub_task_id, exc)

        return state
