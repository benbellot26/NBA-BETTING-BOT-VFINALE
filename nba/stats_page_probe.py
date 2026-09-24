"""Inspect reachable www.nba.com/stats HTML for embedded structured-data signals.

This is NETWORK_DIAGNOSTIC_ONLY. It stores hashes/counts, never page HTML, and
cannot become a predictive input or authorize a provider automatically.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import re
from pathlib import Path
from typing import Any

from .provider_http import get_text
from .provider_smoke import _previous
from .schedule import season_for_date

MARKERS = (
    "OFF_RATING", "DEF_RATING", "PACE", "GP", "TEAM_NAME", "PLAYER_NAME",
    "rowSet", "resultSet", "resultSets", "__NEXT_DATA__", "self.__next_f.push",
)
STRUCTURED_MARKERS = ("rowSet", "resultSet", "resultSets", "__NEXT_DATA__", "self.__next_f.push")

def _scan(html: str) -> dict[str, Any]:
    encoded=html.encode("utf-8")
    marker_counts={marker:html.count(marker) for marker in MARKERS}
    script_ids=sorted(set(re.findall(
        r"<script[^>]+id=[\"']([^\"']+)[\"']", html, flags=re.I)))
    json_scripts=len(re.findall(
        r"<script[^>]+type=[\"']application/(?:ld\+json|json)[\"']",html,flags=re.I))
    next_chunks=html.count("self.__next_f.push")
    structured=any(marker_counts[name] > 0 for name in STRUCTURED_MARKERS)
    basketball_fields=sum(marker_counts[name] for name in (
        "OFF_RATING","DEF_RATING","PACE","TEAM_NAME","PLAYER_NAME"))
    return {
        "bytes":len(encoded),
        "sha256":hashlib.sha256(encoded).hexdigest(),
        "marker_counts":marker_counts,
        "script_ids":script_ids[:30],
        "json_script_tags":json_scripts,
        "next_stream_chunks":next_chunks,
        "structured_payload_signal":structured,
        "basketball_field_signal":basketball_fields > 0,
    }

def run(*, season: str | None = None) -> dict[str, Any]:
    now=datetime.now(timezone.utc)
    probe_season=season or _previous(season_for_date(now))
    urls={
        "teams_advanced":f"https://www.nba.com/stats/teams/advanced?Season={probe_season}&SeasonType=Regular%20Season",
        "teams_traditional":f"https://www.nba.com/stats/teams/traditional?Season={probe_season}&SeasonType=Regular%20Season",
        "players_advanced":f"https://www.nba.com/stats/players/advanced?Season={probe_season}&SeasonType=Regular%20Season",
        "players_traditional":f"https://www.nba.com/stats/players/traditional?Season={probe_season}&SeasonType=Regular%20Season",
    }
    pages={}
    for name,url in urls.items():
        try:
            html=get_text(url,headers={"Accept":"text/html,*/*"},timeout=12.0,retries=0)
            pages[name]={"ok":True,**_scan(html)}
        except Exception as exc:
            pages[name]={"ok":False,"error_type":type(exc).__name__,"error":str(exc)}
    usable_candidate=all(
        row.get("ok") and row.get("structured_payload_signal")
        for row in pages.values()
    )
    return {
        "schema":"pulsar-nba-www-stats-structure-probe-v1",
        "checked_at":now.isoformat(),
        "season":probe_season,
        "role":"NETWORK_DIAGNOSTIC_ONLY",
        "predictive_evidence_eligible":False,
        "production_provider_authorized":False,
        "odds_api_requests":0,
        "all_pages_reachable":all(row.get("ok") for row in pages.values()),
        "structured_candidate_for_reference_parser":bool(usable_candidate),
        "pages":pages,
    }

def main()->None:
    p=argparse.ArgumentParser()
    p.add_argument("--season")
    p.add_argument("--output",default="runtime/www_stats_probe.json")
    a=p.parse_args()
    result=run(season=a.season)
    target=Path(a.output);target.parent.mkdir(parents=True,exist_ok=True)
    target.write_text(json.dumps(result,indent=2),encoding="utf-8")
    print(json.dumps(result,indent=2))

if __name__=="__main__":main()
