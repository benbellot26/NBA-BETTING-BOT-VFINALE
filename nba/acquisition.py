from __future__ import annotations

import json
import os
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ODDS_API_BASE = "https://api.the-odds-api.com/v4"


def _get_json(url: str, *, timeout: float = 20.0) -> Any:
    req=Request(url, headers={"User-Agent":"Pulsar-NBA/1.0"})
    with urlopen(req, timeout=timeout) as response:  # nosec B310 - fixed https provider URL
        return json.loads(response.read().decode("utf-8"))


def fetch_nba_odds(*, api_key: str | None = None, regions: str = "eu,us", markets: str = "h2h,spreads,totals") -> list[dict[str, Any]]:
    key=api_key or os.environ.get("ODDS_API_KEY")
    if not key:
        raise RuntimeError("ODDS_API_KEY is required for live odds acquisition")
    query=urlencode({"apiKey":key,"regions":regions,"markets":markets,"oddsFormat":"decimal","dateFormat":"iso"})
    data=_get_json(f"{ODDS_API_BASE}/sports/basketball_nba/odds/?{query}")
    if not isinstance(data,list):
        raise RuntimeError("unexpected odds provider payload")
    return data


def load_fixture(path: str) -> Any:
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)
