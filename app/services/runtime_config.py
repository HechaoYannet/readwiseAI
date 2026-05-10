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
        "api_key": "",
    }
}


def _ensure_parent() -> None:
    _CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)


def load_runtime_config() -> Dict[str, Any]:
    """Load runtime config from disk, falling back to defaults on errors."""
    _ensure_parent()
    if not _CONFIG_FILE.exists():
        return json.loads(json.dumps(_DEFAULT_CONFIG))
    try:
        data = json.loads(_CONFIG_FILE.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return json.loads(json.dumps(_DEFAULT_CONFIG))
        merged = json.loads(json.dumps(_DEFAULT_CONFIG))
        merged.update(data)
        if not isinstance(merged.get("llm"), dict):
            merged["llm"] = json.loads(json.dumps(_DEFAULT_CONFIG["llm"]))
        else:
            llm = json.loads(json.dumps(_DEFAULT_CONFIG["llm"]))
            llm.update(merged["llm"])
            merged["llm"] = llm
        return merged
    except Exception:
        return json.loads(json.dumps(_DEFAULT_CONFIG))


def save_runtime_config(config: Dict[str, Any]) -> Dict[str, Any]:
    """Persist runtime config atomically."""
    _ensure_parent()
    with _LOCK:
        _CONFIG_FILE.write_text(
            json.dumps(config, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    return config


def update_runtime_config(section: str, values: Dict[str, Any]) -> Dict[str, Any]:
    """Merge and persist one runtime config section."""
    with _LOCK:
        config = load_runtime_config()
        section_data = config.get(section, {})
        if not isinstance(section_data, dict):
            section_data = {}
        section_data.update(values)
        config[section] = section_data
        _CONFIG_FILE.write_text(
            json.dumps(config, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return config
