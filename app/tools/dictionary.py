"""有道词典 API wrapper.

If YOUDAO_APP_KEY and YOUDAO_APP_SECRET are set, calls the real Youdao API.
Otherwise falls back to a stub that returns a placeholder definition.
"""
from __future__ import annotations

import hashlib
import logging
import os
import time

import httpx
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)
#
# _YOUDAO_BASE = "https://openapi.youdao.com/api"
APP_KEY = os.getenv("YOUDAO_APP_KEY", "")
APP_SECRET = os.getenv("YOUDAO_APP_SECRET", "")

# # 在这里填入你的 API 密钥（没有就留空，会自动使用模拟数据）
# APP_KEY = "6938ceb25ba95258"  # 应用 ID
# APP_SECRET = "oCYG9DYmJj2oryILFgqRbvkOHJRN1l7Z"  # 应用密钥

API_URL = "https://openapi.youdao.com/api"


def _sign(q: str, salt: str, cur_time: str) -> str:
    """生成签名"""

    def truncate(s: str) -> str:
        return s if len(s) <= 20 else s[:10] + str(len(s)) + s[-10:]

    sign_str = APP_KEY + truncate(q) + salt + cur_time + APP_SECRET
    return hashlib.sha256(sign_str.encode()).hexdigest()


async def lookup_word(word: str):
    """查询单词"""
    # 无 API 密钥时使用模拟数据
    if not APP_KEY or not APP_SECRET:
        return {
            "word": word,
            "definitions": [f"[模拟] {word}: 请配置 API 密钥"],
            "translation": [f"[模拟] {word}: 请配置 API 密钥"],
            "success": False,
        }

    salt = str(int(time.time() * 1000))
    cur_time = str(int(time.time()))

    params = {
        "q": word,
        "from": "en",
        "to": "zh-CHS",
        "appKey": APP_KEY,
        "salt": salt,
        "sign": _sign(word, salt, cur_time),
        "signType": "v3",
        "curtime": cur_time,
    }

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(API_URL, params=params)
            data = resp.json()

        if data.get("errorCode") != "0":
            fallback = [f"[错误] {word}: API失败"]
            return {
                "word": word,
                "definitions": fallback,
                "translation": fallback,
                "success": False,
            }

        explains = data.get("translation", [])
        definitions = explains if isinstance(explains, list) else [str(explains)]
        first_translation = definitions[0] if definitions else ""
        return {
            "word": word,
            "definitions": definitions,
            "translation": first_translation,
            "success": True,
        }

    except Exception as e:
        fallback = [f"[异常] {word}: {e}"]
        return {
            "word": word,
            "definitions": fallback,
            "translation": fallback,
            "success": False,
        }





