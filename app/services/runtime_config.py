"""Runtime configuration storage for admin-managed settings."""
from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any, Dict

_CONFIG_FILE = Path(__file__).parent.parent.parent / "data" / "admin" / "runtime_config.json"
_LOCK = threading.Lock()

_DEFAULT_CONFIG: Dict[str, Any] = {
    "llm": {
        "provider": "",
        "model": "",
        "temperature": None,
        "base_url": "",
    }
}

_ALLOWED_LLM_KEYS = {"provider", "model", "temperature", "base_url"}


def _ensure_parent() -> None:
    _CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)


def _sanitize_config(config: Dict[str, Any]) -> Dict[str, Any]:
    sanitized = json.loads(json.dumps(_DEFAULT_CONFIG))
    llm_config = config.get("llm", {})
    if isinstance(llm_config, dict):
        for key in _ALLOWED_LLM_KEYS:
            if key in llm_config:
                sanitized["llm"][key] = llm_config[key]
    return sanitized


def load_runtime_config() -> Dict[str, Any]:
    """Load runtime config from disk, falling back to defaults on errors."""
    _ensure_parent()
    if not _CONFIG_FILE.exists():
        return json.loads(json.dumps(_DEFAULT_CONFIG))
    try:
        data = json.loads(_CONFIG_FILE.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return json.loads(json.dumps(_DEFAULT_CONFIG))
        return _sanitize_config(data)
    except Exception:
        return json.loads(json.dumps(_DEFAULT_CONFIG))


def save_runtime_config(config: Dict[str, Any]) -> Dict[str, Any]:
    """Persist runtime config atomically."""
    _ensure_parent()
    sanitized = _sanitize_config(config)
    with _LOCK:
        _CONFIG_FILE.write_text(
            json.dumps(sanitized, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    return sanitized


def update_runtime_config(section: str, values: Dict[str, Any]) -> Dict[str, Any]:
    """Merge and persist one runtime config section."""
    with _LOCK:
        config = load_runtime_config()
        section_data = config.get(section, {})
        if not isinstance(section_data, dict):
            section_data = {}
        section_data.update(values)
        config[section] = section_data
        sanitized = _sanitize_config(config)
        _CONFIG_FILE.write_text(json.dumps(sanitized, ensure_ascii=False, indent=2), encoding="utf-8")
        return sanitized
