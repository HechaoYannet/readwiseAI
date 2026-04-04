"""WorkingMemory – 会话级工作记忆管理.

存储当前会话的上下文信息，包括当前文章、当前题目和对话历史。
数据持久化到 data/working/sessions/{session_id}.json。
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

_SESSIONS_DIR = Path(__file__).parent.parent.parent / "data" / "working" / "sessions"


class WorkingMemory(BaseModel):
    """Session-level working memory.

    Attributes:
        session_id: Unique identifier for the session.
        user_id: The user this session belongs to.
        current_article: Full metadata and content of the article being studied.
        current_questions: List of questions generated for the current article.
        conversation_history: Ordered list of user/assistant message pairs.
        created_at: ISO timestamp when the session was created.
        updated_at: ISO timestamp of the most recent modification.
    """

    session_id: str
    user_id: str
    current_article: Dict[str, Any] = Field(default_factory=dict)
    current_questions: List[Dict[str, Any]] = Field(default_factory=list)
    conversation_history: List[Dict[str, str]] = Field(default_factory=list)
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now().isoformat())

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def save(self) -> None:
        """Persist this working memory to disk."""
        _SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
        self.updated_at = datetime.now().isoformat()
        path = _SESSIONS_DIR / f"{self.session_id}.json"
        path.write_text(self.model_dump_json(indent=2), encoding="utf-8")

    @classmethod
    def load(cls, session_id: str) -> Optional["WorkingMemory"]:
        """Load working memory from disk.  Returns None if not found."""
        path = _SESSIONS_DIR / f"{session_id}.json"
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return cls(**data)
        except Exception as exc:
            logger.error("Failed to load working memory %s: %s", session_id, exc)
            return None

    @classmethod
    def get_or_create(cls, session_id: str, user_id: str) -> "WorkingMemory":
        """Load existing session or create a new one."""
        existing = cls.load(session_id)
        if existing is not None:
            return existing
        wm = cls(session_id=session_id, user_id=user_id)
        wm.save()
        return wm

    # ------------------------------------------------------------------
    # Mutators
    # ------------------------------------------------------------------

    def set_article(self, article: Dict[str, Any]) -> None:
        """Replace the current article and clear stale question state."""
        self.current_article = article
        self.current_questions = []
        self.save()

    def set_questions(self, questions: List[Dict[str, Any]]) -> None:
        """Store generated questions for the current article."""
        self.current_questions = questions
        self.save()

    def add_message(self, role: str, content: str) -> None:
        """Append a message to the conversation history.

        Args:
            role: "user" or "assistant".
            content: The message text.
        """
        self.conversation_history.append({"role": role, "content": content})
        # Keep only the last 20 turns to avoid unbounded growth
        if len(self.conversation_history) > 40:
            self.conversation_history = self.conversation_history[-40:]
        self.save()

    # ------------------------------------------------------------------
    # Read helpers
    # ------------------------------------------------------------------

    def get_article_content(self) -> str:
        """Return the full text of the current article, or an empty string."""
        return self.current_article.get("content", "")

    def get_article_title(self) -> str:
        """Return the title of the current article, or a placeholder."""
        return self.current_article.get("title", "（无当前文章）")
