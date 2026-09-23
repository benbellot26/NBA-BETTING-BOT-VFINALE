from __future__ import annotations

import json
import time
from typing import Any
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/153 Safari/537.36",
    "Accept": "application/json,text/plain,*/*",
    "Accept-Language": "en-US,en;q=0.9",
}

NBA_BROWSER_HEADERS = {
    "Origin": "https://www.nba.com",
    "Referer": "https://www.nba.com/",
}


def headers_for(url: str, overrides: dict[str, str] | None = None) -> dict[str, str]:
    """Use provider-specific headers instead of leaking NBA browser headers everywhere."""
    merged = dict(DEFAULT_HEADERS)
    host = (urlsplit(url).hostname or "").lower()
    if host == "nba.com" or host.endswith(".nba.com"):
        merged.update(NBA_BROWSER_HEADERS)
    if overrides:
        merged.update(overrides)
    return merged


class ProviderError(RuntimeError):
    pass


def _safe_endpoint(url: str) -> str:
    parsed = urlsplit(url)
    return f"{parsed.scheme}://{parsed.netloc}{parsed.path}"


def get_bytes(url: str, *, headers: dict[str, str] | None = None,
              timeout: float = 20.0, retries: int = 2) -> bytes:
    merged = headers_for(url, headers)
    error: Exception | None = None
    for attempt in range(retries + 1):
        try:
            request = Request(url, headers=merged)
            with urlopen(request, timeout=timeout) as response:  # nosec B310: explicit provider URLs
                return response.read()
        except Exception as exc:
            error = exc
            if attempt < retries:
                time.sleep(0.5 * (2 ** attempt))
    code = getattr(error, "code", None)
    detail = f"HTTP {code}" if isinstance(code, int) else type(error).__name__
    # Never include the query string or exception's string: URLs may contain apiKey.
    raise ProviderError(f"GET {_safe_endpoint(url)} failed: {detail}") from None


def get_text(url: str, **kwargs: Any) -> str:
    return get_bytes(url, **kwargs).decode("utf-8", errors="replace")


def get_json(url: str, **kwargs: Any) -> Any:
    try:
        return json.loads(get_text(url, **kwargs))
    except json.JSONDecodeError:
        raise ProviderError(f"invalid JSON from {_safe_endpoint(url)}") from None
