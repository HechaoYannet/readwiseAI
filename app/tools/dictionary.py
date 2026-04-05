"""有道词典 API wrapper.

If YOUDAO_APP_KEY and YOUDAO_APP_SECRET are set, calls the real Youdao API.
Otherwise falls back to a stub that returns a placeholder definition.
"""
from __future__ import annotations

import hashlib
import logging
import os
import time
from typing import Any, Dict

import httpx

logger = logging.getLogger(__name__)

_YOUDAO_BASE = "https://openapi.youdao.com/api"
_APP_KEY = os.getenv("YOUDAO_APP_KEY", "")
_APP_SECRET = os.getenv("YOUDAO_APP_SECRET", "")


def _sign(app_key: str, q: str, salt: str, cur_time: str, app_secret: str) -> str:
    input_str = app_key + _truncate(q) + salt + cur_time + app_secret
    return hashlib.sha256(input_str.encode("utf-8")).hexdigest()


def _truncate(q: str) -> str:
    if len(q) <= 20:
        return q
    return q[:10] + str(len(q)) + q[-10:]


async def lookup_word(word: str) -> Dict[str, Any]:
    """Return basic definition for a word."""
    if not _APP_KEY or not _APP_SECRET:
        return _stub_definition(word)

    salt = str(int(time.time() * 1000))
    cur_time = str(int(time.time()))
    sign = _sign(_APP_KEY, word, salt, cur_time, _APP_SECRET)

    params = {
        "q": word,
        "from": "en",
        "to": "zh-CHS",
        "appKey": _APP_KEY,
        "salt": salt,
        "sign": sign,
        "signType": "v3",
        "curtime": cur_time,
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(_YOUDAO_BASE, params=params)
            resp.raise_for_status()
            data = resp.json()
        ec = data.get("errorCode", "")
        if ec != "0":
            logger.warning("Youdao API error %s for word '%s'", ec, word)
            return _stub_definition(word)
        return _parse_youdao_response(word, data)
    except Exception as exc:
        logger.error("Youdao lookup failed: %s", exc)
        return _stub_definition(word)


def _parse_youdao_response(word: str, data: Dict[str, Any]) -> Dict[str, Any]:
    basic = data.get("basic", {})
    explains = basic.get("explains", [])
    phonetic = basic.get("phonetic", "")
    web = data.get("web", [])
    return {
        "word": word,
        "phonetic": phonetic,
        "definitions": explains,
        "web_translations": [w.get("value", []) for w in web[:3]],
    }


def _stub_definition(word: str) -> Dict[str, Any]:
    return {
        "word": word,
        "phonetic": "",
        "definitions": [f"[stub] {word}: definition not available (no API key)"],
        "web_translations": [],
    }
