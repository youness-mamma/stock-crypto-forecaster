"""Daily-resetting per-user rate limiting backed by a local JSON file."""

from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_LIMIT = 5
DEFAULT_STORE = Path(__file__).resolve().parent / ".usage.json"
_LOCK = threading.Lock()


def _today_key() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _load(store: Path) -> dict:
    if not store.exists():
        return {}
    try:
        with store.open("r", encoding="utf-8") as fh:
            return json.load(fh)
    except (json.JSONDecodeError, OSError):
        return {}


def _save(store: Path, data: dict) -> None:
    tmp = store.with_suffix(store.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        json.dump(data, fh)
    os.replace(tmp, store)


def get_usage(user_id: str, store: Path = DEFAULT_STORE) -> int:
    """Return today's usage count for a user."""
    today = _today_key()
    with _LOCK:
        data = _load(store)
        record = data.get(user_id)
        if not record or record.get("date") != today:
            return 0
        return int(record.get("count", 0))


def check_limit(user_id: str, limit: int = DEFAULT_LIMIT, store: Path = DEFAULT_STORE) -> tuple[bool, int]:
    """Return (allowed, used_so_far)."""
    used = get_usage(user_id, store=store)
    return (used < limit, used)


def increment(user_id: str, limit: int = DEFAULT_LIMIT, store: Path = DEFAULT_STORE) -> tuple[bool, int]:
    """Increment today's count atomically. Returns (allowed, new_count).

    If already at limit, does not increment and returns (False, current_count).
    """
    today = _today_key()
    with _LOCK:
        data = _load(store)
        record = data.get(user_id)
        if not record or record.get("date") != today:
            count = 0
        else:
            count = int(record.get("count", 0))

        if count >= limit:
            return False, count

        count += 1
        data[user_id] = {"date": today, "count": count}
        _save(store, data)
        return True, count


def remaining(user_id: str, limit: int = DEFAULT_LIMIT, store: Path = DEFAULT_STORE) -> int:
    return max(0, limit - get_usage(user_id, store=store))
