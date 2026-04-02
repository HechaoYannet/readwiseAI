"""Checkpoint Manager – persists OrchestratorState to the local filesystem."""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional

from app.models.state import OrchestratorState

logger = logging.getLogger(__name__)

CHECKPOINT_DIR = Path("data/checkpoints")
RESULTS_DIR = Path("data/results")


class CheckpointManager:
    def __init__(
        self,
        checkpoint_dir: Path = CHECKPOINT_DIR,
        results_dir: Path = RESULTS_DIR,
    ):
        self.checkpoint_dir = checkpoint_dir
        self.results_dir = results_dir
        self.checkpoint_dir.mkdir(parents=True, exist_ok=True)
        self.results_dir.mkdir(parents=True, exist_ok=True)

    def save(self, state: OrchestratorState) -> None:
        """Persist state as JSON."""
        path = self.checkpoint_dir / f"{state.request_id}.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(state.model_dump(mode="json"), f, ensure_ascii=False, indent=2)
        logger.debug("Checkpoint saved for %s", state.request_id)

    def load(self, request_id: str) -> Optional[OrchestratorState]:
        """Load state from JSON; returns None if not found."""
        path = self.checkpoint_dir / f"{request_id}.json"
        if not path.exists():
            return None
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return OrchestratorState(**data)

    def delete(self, request_id: str) -> None:
        """Remove checkpoint file after completion."""
        path = self.checkpoint_dir / f"{request_id}.json"
        if path.exists():
            path.unlink()

    def save_result(self, request_id: str, result: dict) -> None:
        """Persist final result."""
        path = self.results_dir / f"{request_id}.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)

    def load_result(self, request_id: str) -> Optional[dict]:
        """Load cached final result."""
        path = self.results_dir / f"{request_id}.json"
        if not path.exists():
            return None
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)


# Singleton
_checkpoint_manager: Optional[CheckpointManager] = None


def get_checkpoint_manager() -> CheckpointManager:
    global _checkpoint_manager
    if _checkpoint_manager is None:
        _checkpoint_manager = CheckpointManager()
    return _checkpoint_manager
