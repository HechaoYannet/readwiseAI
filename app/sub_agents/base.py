"""Base class for all Sub-agents."""
from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod
from typing import Any, Dict

from app.services.llm_service import llm_json_call

logger = logging.getLogger(__name__)


class BaseSubAgent(ABC):
    name: str = "base"
    description: str = ""

    @abstractmethod
    async def execute(self, input: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        """Execute the sub-task and return a result dict."""

    async def _call_llm(self, prompt: str) -> Dict[str, Any]:
        """Convenience wrapper around the shared LLM service."""
        return await llm_json_call(prompt)

    def _timed(self, start: float) -> int:
        return int((time.time() - start) * 1000)
