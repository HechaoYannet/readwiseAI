"""LLM service – provider selection with runtime admin overrides."""
from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict, Optional

from dotenv import load_dotenv

from app.services.runtime_config import update_runtime_config, load_runtime_config

load_dotenv()
logger = logging.getLogger(__name__)

_DEFAULT_MODEL = os.getenv("LLM_MODEL", "gpt-4o-mini")
_DEFAULT_TEMPERATURE = float(os.getenv("LLM_TEMPERATURE", "1.3"))
_DEFAULT_DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")


class _StubLLM:
    """Stub LLM used when no API key is configured (useful for unit tests)."""

    async def ainvoke(self, prompt: str) -> "_StubMessage":
        logger.warning("StubLLM.ainvoke called – returning empty JSON object")
        return _StubMessage("{}")


class _StubMessage:
    def __init__(self, content: str):
        self.content = content


def _normalize_provider(provider: str) -> str:
    value = (provider or "").strip().lower()
    return value if value in {"openai", "deepseek", "stub"} else ""


def _build_effective_config() -> Dict[str, Any]:
    runtime_config = load_runtime_config().get("llm", {})
    provider = _normalize_provider(runtime_config.get("provider", ""))
    if not provider:
        if os.getenv("OPENAI_API_KEY", "").strip():
            provider = "openai"
        elif os.getenv("DEEPSEEK_API_KEY", "").strip():
            provider = "deepseek"
        else:
            provider = "stub"

    model = (runtime_config.get("model") or os.getenv("LLM_MODEL") or _DEFAULT_MODEL).strip()
    base_url = (runtime_config.get("base_url") or "").strip()
    temperature = runtime_config.get("temperature")
    if temperature is None:
        temperature = _DEFAULT_TEMPERATURE

    api_key = (runtime_config.get("api_key") or "").strip()
    if provider == "openai":
        api_key = api_key or os.getenv("OPENAI_API_KEY", "").strip()
    elif provider == "deepseek":
        api_key = api_key or os.getenv("DEEPSEEK_API_KEY", "").strip()
        if not base_url:
            base_url = _DEFAULT_DEEPSEEK_BASE_URL
    else:
        api_key = ""
        base_url = ""

    return {
        "provider": provider,
        "model": model or _DEFAULT_MODEL,
        "temperature": float(temperature),
        "base_url": base_url.rstrip("/"),
        "api_key": api_key,
    }


def get_public_runtime_llm_config() -> Dict[str, Any]:
    """Return a sanitized config view for admin API responses."""
    effective = _build_effective_config()
    runtime_llm = load_runtime_config().get("llm", {})
    return {
        "provider": effective["provider"],
        "model": effective["model"],
        "temperature": effective["temperature"],
        "base_url": effective["base_url"],
        "has_api_key": bool(effective["api_key"]),
        "api_key_source": "runtime" if bool(runtime_llm.get("api_key")) else ("environment" if bool(effective["api_key"]) else "unset"),
        "runtime_overrides": {
            "provider": bool(runtime_llm.get("provider")),
            "model": bool(runtime_llm.get("model")),
            "temperature": runtime_llm.get("temperature") is not None,
            "base_url": bool(runtime_llm.get("base_url")),
        },
    }


def update_runtime_llm_config(
    *,
    provider: str,
    model: Optional[str] = None,
    temperature: Optional[float] = None,
    base_url: Optional[str] = None,
    api_key: Optional[str] = None,
) -> Dict[str, Any]:
    """Update persisted runtime LLM config and reset the singleton."""
    current = load_runtime_config().get("llm", {})
    new_values = {
        "provider": _normalize_provider(provider),
        "model": model.strip() if isinstance(model, str) else current.get("model", ""),
        "temperature": float(temperature) if temperature is not None else current.get("temperature"),
        "base_url": (base_url or "").strip().rstrip("/") if base_url is not None else current.get("base_url", ""),
        "api_key": (api_key or "").strip() if api_key is not None else current.get("api_key", ""),
    }
    update_runtime_config("llm", new_values)
    reset_llm()
    return get_public_runtime_llm_config()


def _build_llm():
    config = _build_effective_config()
    provider = config["provider"]
    if provider == "openai" and config["api_key"]:
        try:
            from langchain_openai import ChatOpenAI  # type: ignore

            return ChatOpenAI(
                model=config["model"],
                api_key=config["api_key"],
                temperature=config["temperature"],
                base_url=config["base_url"] or None,
            )
        except Exception as exc:
            logger.warning("Failed to build ChatOpenAI: %s – falling back to stub", exc)
    elif provider == "deepseek" and config["api_key"]:
        try:
            from langchain_openai import ChatOpenAI  # type: ignore

            return ChatOpenAI(
                model=config["model"],
                api_key=config["api_key"],
                base_url=config["base_url"] or _DEFAULT_DEEPSEEK_BASE_URL,
                temperature=config["temperature"],
            )
        except Exception as exc:
            logger.warning("Failed to build DeepSeek LLM: %s – falling back to stub", exc)
    return _StubLLM()


# Singleton
_llm_instance: Optional[Any] = None


def reset_llm() -> None:
    global _llm_instance
    _llm_instance = None


def get_llm() -> Any:
    global _llm_instance
    if _llm_instance is None:
        _llm_instance = _build_llm()
    return _llm_instance


async def llm_json_call(prompt: str) -> Dict[str, Any]:
    """Call LLM and parse the response as JSON.

    Returns an empty dict on parse failure so callers can handle gracefully.
    Automatically writes a structured Markdown log entry via llm_logger when
    a request context is active (request_id set via contextvars).
    """
    import time as _time
    from app.services import llm_logger

    llm = get_llm()
    raw_content = ""
    parsed: Dict[str, Any] = {}
    error_msg = ""
    success = False
    t0 = _time.monotonic()

    try:
        response = await llm.ainvoke(prompt)
        raw_content = response.content if hasattr(response, "content") else str(response)
        # Strip Markdown code fences if present
        content = raw_content.strip()
        if content.startswith("```"):
            lines = content.splitlines()
            content = "\n".join(lines[1:-1]) if len(lines) > 2 else content
        parsed = json.loads(content)
        success = True
        return parsed
    except json.JSONDecodeError as exc:
        error_msg = f"JSON parse error: {exc}"
        logger.error("LLM response is not valid JSON: %s", exc)
        return {}
    except Exception as exc:
        error_msg = str(exc)
        logger.error("LLM call failed: %s", exc)
        return {}
    finally:
        latency_ms = int((_time.monotonic() - t0) * 1000)
        try:
            llm_logger.log_llm_call(
                prompt=prompt,
                raw_response=raw_content,
                parsed=parsed,
                latency_ms=latency_ms,
                success=success,
                error=error_msg,
            )
        except Exception as log_exc:  # pragma: no cover
            logger.warning("LLM logger error: %s", log_exc)
