from __future__ import annotations

import json
import os
from urllib.parse import urlencode

from .acquisition import ODDS_API_BASE
from .provider_http import get_json


def check_auth(*, api_key: str | None = None) -> dict[str, object]:
    """One low-cost authenticated /sports request. Never prints or returns key or URL."""
    key = api_key or os.environ.get("ODDS_API_KEY")
    if not key:
        raise RuntimeError("ODDS_API_KEY GitHub secret is missing")
    url = f"{ODDS_API_BASE}/sports/?{urlencode({'apiKey': key})}"
    sports = get_json(url, timeout=20.0, retries=0)
    if not isinstance(sports, list):
        raise RuntimeError("sports endpoint returned an unexpected response")
    return {"authorized": True, "sport_count": len(sports)}


def main() -> None:
    try:
        result = check_auth()
    except Exception as exc:
        print(json.dumps({"authorized": False, "error_type": type(exc).__name__}))
        raise SystemExit(1) from None
    print(json.dumps(result))


if __name__ == "__main__":
    main()
