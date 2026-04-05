"""LLM service – thin wrapper around ChatOpenAI (or any compatible backend).

Set OPENAI_API_KEY (or DEEPSEEK_API_KEY + DEEPSEEK_BASE_URL) in environment.
If no key is set, a stub implementation is used so the rest of the system can
still be exercised in tests without real LLM calls.
"""
from __future__ import annotations

import json
import logging
import os
from dotenv import load_dotenv
from typing import Any, Dict, Optional

load_dotenv()
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# LLM backend selection
# ---------------------------------------------------------------------------

OPENAI_KEY = os.getenv("OPENAI_API_KEY", "")
DEEPSEEK_KEY = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_DEEPSEEK_BASE = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")
MODEL = os.getenv("LLM_MODEL", "gpt-4o-mini")
TEMPERATURE = float(os.getenv("LLM_TEMPERATURE", "0.2"))


class _StubLLM:
    """Stub LLM used when no API key is configured (useful for unit tests)."""

    async def ainvoke(self, prompt: str) -> "_StubMessage":
        logger.warning("StubLLM.ainvoke called – returning empty JSON object")
        return _StubMessage("{}")


class _StubMessage:
    def __init__(self, content: str):
        self.content = content


def _build_llm():
    if OPENAI_KEY:
        try:
            from langchain_openai import ChatOpenAI  # type: ignore

            return ChatOpenAI(model=MODEL, api_key=OPENAI_KEY)
        except Exception as exc:
            logger.warning("Failed to build ChatOpenAI: %s – falling back to stub", exc)
    elif DEEPSEEK_KEY:
        try:
            from langchain_openai import ChatOpenAI  # type: ignore

            return ChatOpenAI(
                model=MODEL,
                api_key=DEEPSEEK_KEY,
                base_url=DEEPSEEK_BASE_DEEPSEEK_BASE,
                temperature=TEMPERATURE
            )
        except Exception as exc:
            logger.warning("Failed to build DeepSeek LLM: %s – falling back to stub", exc)
    return _StubLLM()


# Singleton
_llm_instance: Optional[Any] = None


def get_llm() -> Any:
    global _llm_instance
    if _llm_instance is None:
        _llm_instance = _build_llm()
    return _llm_instance


async def llm_json_call(prompt: str) -> Dict[str, Any]:
    """Call LLM and parse the response as JSON.

    Returns an empty dict on parse failure so callers can handle gracefully.
    """
    llm = get_llm()
    try:
        response = await llm.ainvoke(prompt)
        content = response.content if hasattr(response, "content") else str(response)
        # Strip Markdown code fences if present
        content = content.strip()
        if content.startswith("```"):
            lines = content.splitlines()
            content = "\n".join(lines[1:-1]) if len(lines) > 2 else content
        return json.loads(content)
    except json.JSONDecodeError as exc:
        logger.error("LLM response is not valid JSON: %s", exc)
        return {}
    except Exception as exc:
        logger.error("LLM call failed: %s", exc)
        return {}
