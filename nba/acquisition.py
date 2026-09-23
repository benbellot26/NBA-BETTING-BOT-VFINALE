from __future__ import annotations
import os
from typing import Any
from urllib.parse import urlencode
from .provider_http import get_json, get_json_with_headers

ODDS_API_BASE="https://api.the-odds-api.com/v4"

def _key(api_key:str|None)->str:
    key=api_key or os.environ.get("ODDS_API_KEY")
    if not key:raise RuntimeError("ODDS_API_KEY is required for odds acquisition")
    return key

def fetch_nba_odds(*,api_key:str|None=None,regions:str="eu,us",markets:str="h2h,spreads,totals",bookmakers:str|None=None)->list[dict[str,Any]]:
    params={"apiKey":_key(api_key),"markets":markets,"oddsFormat":"decimal","dateFormat":"iso"}
    if bookmakers:params["bookmakers"]=bookmakers
    else:params["regions"]=regions
    data=get_json(f"{ODDS_API_BASE}/sports/basketball_nba/odds/?{urlencode(params)}")
    if not isinstance(data,list):raise RuntimeError("unexpected odds provider payload")
    return data

def fetch_historical_nba_odds(*,date_iso:str,api_key:str|None=None,regions:str="eu,us",markets:str="h2h,spreads,totals",bookmakers:str="pinnacle")->dict[str,Any]:
    params={"apiKey":_key(api_key),"markets":markets,"oddsFormat":"decimal","dateFormat":"iso","date":date_iso}
    if bookmakers:params["bookmakers"]=bookmakers
    else:params["regions"]=regions
    data=get_json(f"{ODDS_API_BASE}/historical/sports/basketball_nba/odds?{urlencode(params)}")
    if not isinstance(data,dict) or not isinstance(data.get("data"),list):raise RuntimeError("unexpected historical odds payload")
    return data

def load_fixture(path:str)->Any:
    import json
    with open(path,"r",encoding="utf-8") as fh:return json.load(fh)


def fetch_nba_odds_diagnostic(*, api_key: str | None = None,
                              regions: str = "eu,us",
                              markets: str = "h2h,spreads,totals",
                              bookmakers: str | None = "pinnacle") -> dict[str, Any]:
    """One current NBA odds request plus scrubbed quota telemetry."""
    params={"apiKey":_key(api_key),"markets":markets,"oddsFormat":"decimal","dateFormat":"iso"}
    if bookmakers: params["bookmakers"]=bookmakers
    else: params["regions"]=regions
    data, headers=get_json_with_headers(
        f"{ODDS_API_BASE}/sports/basketball_nba/odds/?{urlencode(params)}")
    if not isinstance(data,list): raise RuntimeError("unexpected odds provider payload")
    usage={}
    for source,target in (
        ("x-requests-remaining","remaining"),
        ("x-requests-used","used"),
        ("x-requests-last","last_cost"),
    ):
        if source in headers:
            try: usage[target]=int(headers[source])
            except ValueError: usage[target]=headers[source]
    return {"events":data,"usage":usage}
