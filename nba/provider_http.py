from __future__ import annotations

import json
import time
from typing import Any
from urllib.request import Request, urlopen


DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/153 Safari/537.36",
    "Accept": "application/json,text/plain,*/*",
    "Accept-Language": "en-US,en;q=0.9",
    "Origin": "https://www.nba.com",
    "Referer": "https://www.nba.com/",
}


class ProviderError(RuntimeError):
    pass


def get_bytes(url: str, *, headers: dict[str, str] | None = None, timeout: float = 20.0, retries: int = 2) -> bytes:
    merged = dict(DEFAULT_HEADERS)
    if headers:
        merged.update(headers)
    error: Exception | None = None
    for attempt in range(retries + 1):
        try:
            req = Request(url, headers=merged)
            with urlopen(req, timeout=timeout) as response:  # nosec B310 - provider URLs are explicit/configured
                return response.read()
        except Exception as exc:
            error = exc
            if attempt < retries:
                time.sleep(0.5 * (2 ** attempt))
    raise ProviderError(f"GET failed after {retries + 1} attempts: {url}: {error}")


def get_text(url: str, **kwargs: Any) -> str:
    return get_bytes(url, **kwargs).decode("utf-8", errors="replace")


def get_json(url: str, **kwargs: Any) -> Any:
    try:
        return json.loads(get_text(url, **kwargs))
    except json.JSONDecodeError as exc:
        raise ProviderError(f"provider returned invalid JSON: {url}") from exc
