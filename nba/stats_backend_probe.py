"""Discover public backend hints referenced by the reachable NBA Stats frontend.

NETWORK_DIAGNOSTIC_ONLY: this module reads public NBA.com HTML/JS bundles and
persists only hashes, counts and whitelisted endpoint markers. It never stores
bundle source and cannot authorize a predictive provider.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
from typing import Any
from urllib.parse import urljoin, urlsplit

from .provider_http import get_text
from .provider_smoke import _previous
from .schedule import season_for_date

SCRIPT_RE=re.compile(r"<script[^>]+src=[\"']([^\"']+)[\"']",re.I)
BACKEND_URL_RE=re.compile(
    r"https?://(?:stats\\.nba\\.com|api-hub\\.nba\\.com)"
    r"(?:/[A-Za-z0-9._~!()*+,;=:@%/-]{0,180})?",
    re.I,
)
ROUTE_RE=re.compile(
    r"/(?:stats|api)/[A-Za-z0-9._~!()*+,;=:@%/-]{1,160}",
    re.I,
)
MARKERS={
    "stats_nba_host":"stats.nba.com",
    "api_hub_host":"api-hub.nba.com",
    "league_dash_team":"leaguedashteamstats",
    "league_dash_player":"leaguedashplayerstats",
    "cume_stats_team":"cumestatsteam",
    "cume_stats_player":"cumestatsplayer",
    "boxscore_traditional":"boxscoretraditional",
    "graphql":"graphql",
    "stats_path":"/stats/",
}


def _safe_url(value:str)->str:
    parsed=urlsplit(value)
    return f"{parsed.scheme}://{parsed.netloc}{parsed.path}"


def _scan_text(text:str)->dict[str,int]:
    lowered=text.casefold()
    return {
        name:lowered.count(marker.casefold())
        for name,marker in MARKERS.items()
    }


def _backend_urls(text:str)->list[str]:
    normalized=str(text).replace("\\/", "/")
    return sorted({
        _safe_url(match.group(0))
        for match in BACKEND_URL_RE.finditer(normalized)
    })[:50]


def _route_candidates(text:str)->list[str]:
    normalized=str(text).replace("\\/", "/")
    routes=set()
    for match in ROUTE_RE.finditer(normalized):
        route=match.group(0).rstrip("/.,;:")
        if "_next/" in route.casefold():
            continue
        routes.add(route)
    return sorted(routes)[:100]


def run(*,season:str|None=None,max_scripts:int=20)->dict[str,Any]:
    if max_scripts<1 or max_scripts>30:
        raise ValueError("max_scripts must be between 1 and 30")
    now=datetime.now(timezone.utc)
    probe_season=season or _previous(season_for_date(now))
    page=(
        "https://www.nba.com/stats/teams/advanced"
        f"?Season={probe_season}&SeasonType=Regular%20Season"
    )
    html=get_text(page,headers={"Accept":"text/html,*/*"},timeout=12.0,retries=0)
    scripts=list(dict.fromkeys(
        urljoin(page,src.replace("\\/","/"))
        for src in SCRIPT_RE.findall(html)
        if "_next/" in src or "nba.com" in src
    ))
    selected=scripts[:max_scripts]
    rows=[]
    aggregate={key:0 for key in MARKERS}
    discovered_urls=set(_backend_urls(html))
    discovered_routes=set(_route_candidates(html))
    for url in selected:
        try:
            source=get_text(
                url,
                headers={"Accept":"application/javascript,text/javascript,*/*"},
                timeout=12.0,retries=0,
            )
            encoded=source.encode("utf-8")
            counts=_scan_text(source)
            for key,value in counts.items():
                aggregate[key]+=value
            backend_urls=_backend_urls(source)
            route_candidates=_route_candidates(source)
            discovered_urls.update(backend_urls)
            discovered_routes.update(route_candidates)
            row={
                "url":_safe_url(url),
                "ok":True,
                "bytes":len(encoded),
                "sha256":hashlib.sha256(encoded).hexdigest(),
                "marker_counts":counts,
            }
            if backend_urls:
                row["backend_urls"]=backend_urls
            if route_candidates:
                row["route_candidates"]=route_candidates
            rows.append(row)
        except Exception as exc:
            rows.append({
                "url":_safe_url(url),
                "ok":False,
                "error_type":type(exc).__name__,
                "error":str(exc),
            })
    backend_hints=[]
    if aggregate["stats_nba_host"]:
        backend_hints.append("stats.nba.com")
    if aggregate["api_hub_host"]:
        backend_hints.append("api-hub.nba.com")
    endpoint_hints=[
        name for name in (
            "league_dash_team","league_dash_player","cume_stats_team",
            "cume_stats_player","boxscore_traditional","graphql"
        ) if aggregate[name]
    ]
    return {
        "schema":"pulsar-nba-stats-backend-discovery-v1",
        "checked_at":now.isoformat(),
        "season":probe_season,
        "role":"NETWORK_DIAGNOSTIC_ONLY",
        "predictive_evidence_eligible":False,
        "production_provider_authorized":False,
        "odds_api_requests":0,
        "page":{
            "url":_safe_url(page),
            "bytes":len(html.encode("utf-8")),
            "sha256":hashlib.sha256(html.encode("utf-8")).hexdigest(),
            "script_src_count":len(scripts),
            "marker_counts":_scan_text(html),
        },
        "scripts_requested":len(selected),
        "scripts_reachable":sum(row.get("ok") is True for row in rows),
        "aggregate_marker_counts":aggregate,
        "backend_hints":backend_hints,
        "endpoint_hints":endpoint_hints,
        "backend_urls":sorted(discovered_urls),
        "route_candidates":sorted(discovered_routes)[:200],
        "scripts":rows,
    }


def main()->None:
    p=argparse.ArgumentParser()
    p.add_argument("--season")
    p.add_argument("--max-scripts",type=int,default=20)
    p.add_argument("--output",default="runtime/stats_backend_probe.json")
    a=p.parse_args()
    result=run(season=a.season,max_scripts=a.max_scripts)
    target=Path(a.output);target.parent.mkdir(parents=True,exist_ok=True)
    target.write_text(json.dumps(result,indent=2,sort_keys=True),encoding="utf-8")
    print(json.dumps(result,indent=2,sort_keys=True))


if __name__=="__main__":
    main()
