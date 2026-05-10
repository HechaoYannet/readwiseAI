"""Simple in-memory login rate limiter."""
from __future__ import annotations

import threading
import time
from collections import defaultdict, deque
from typing import Deque, Dict, Tuple

_WINDOW_SECONDS = 15 * 60
_MAX_FAILURES = 10
_LOCK = threading.Lock()
_FAILURES: Dict[str, Deque[float]] = defaultdict(deque)


def _key(client_ip: str, login_id: str) -> str:
    return f"{client_ip.strip().lower()}::{login_id.strip().lower()}"


def _prune(bucket: Deque[float], now: float) -> None:
    while bucket and (now - bucket[0]) > _WINDOW_SECONDS:
        bucket.popleft()


def check_allowed(client_ip: str, login_id: str) -> Tuple[bool, int]:
    now = time.time()
    with _LOCK:
        bucket = _FAILURES[_key(client_ip, login_id)]
        _prune(bucket, now)
        if len(bucket) < _MAX_FAILURES:
            return True, 0
        retry_after = int(max(1, _WINDOW_SECONDS - (now - bucket[0])))
        return False, retry_after


def record_failure(client_ip: str, login_id: str) -> None:
    now = time.time()
    with _LOCK:
        bucket = _FAILURES[_key(client_ip, login_id)]
        _prune(bucket, now)
        bucket.append(now)


def clear_failures(client_ip: str, login_id: str) -> None:
    with _LOCK:
        _FAILURES.pop(_key(client_ip, login_id), None)
