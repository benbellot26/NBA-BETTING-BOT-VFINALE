"""One-shot checks of publicly accessible NBA data endpoints from GitHub Actions.

This probe never supplies odds credentials or promotes an alternate feed as
equivalent to the official NBA report. Results are schema metadata only.
"""
from __future__ import annotations

import json
from .provider_http import get_json

ESPN_SCOREBOARD = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard?dates=20260401&limit=50"
ESPN_SUMMARY = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/summary?event="
NBA_CDN_BOXSCORE = "https://cdn.nba.com/static/json/liveData/boxscore/boxscore_0022000181.json"


def check() -> dict:
    result = {"schema": "pulsar-nba-alternate-probe-v1", "providers": {}}
    try:
        board = get_json(ESPN_SCOREBOARD, timeout=12, retries=0)
        events = board.get("events") or []
        if not isinstance(events, list) or not events:
            raise ValueError("no scoreboard events in control date")
        event = next((row for row in events if row.get("id")), None)
        if not event:
            raise ValueError("no ESPN event ID")
        result["providers"]["espn_scoreboard"] = {
            "ok": True, "events": len(events),
            "competition_keys": sorted((event.get("competitions") or [{}])[0].keys()),
        }
        try:
            summary = get_json(ESPN_SUMMARY + str(event["id"]), timeout=12, retries=0)
            boxscore = summary.get("boxscore") or {}
            result["providers"]["espn_summary"] = {
                "ok": True,
                "boxscore_keys": sorted(boxscore.keys()),
                "team_statistics_count": len(boxscore.get("teams") or []),
                "player_statistics_count": len(boxscore.get("players") or []),
                "header_keys": sorted((summary.get("header") or {}).keys()),
            }
        except Exception as exc:
            result["providers"]["espn_summary"] = {
                "ok": False, "error_type": type(exc).__name__,
                "error": str(exc) if type(exc).__name__ == "ProviderError" else "",
            }
    except Exception as exc:
        result["providers"]["espn_scoreboard"] = {
            "ok": False, "error_type": type(exc).__name__,
            "error": str(exc) if type(exc).__name__ == "ProviderError" else "",
        }
    try:
        box = get_json(NBA_CDN_BOXSCORE, timeout=12, retries=0)
        game = box.get("game") or {}
        result["providers"]["nba_cdn_boxscore"] = {
            "ok": bool(game.get("gameId")), "has_team_stats": bool(
                ((game.get("homeTeam") or {}).get("statistics"))),
            "has_player_stats": bool(((game.get("homeTeam") or {}).get("players"))),
        }
    except Exception as exc:
        result["providers"]["nba_cdn_boxscore"] = {
            "ok": False, "error_type": type(exc).__name__,
            "error": str(exc) if type(exc).__name__ == "ProviderError" else "",
        }
    return result


def main() -> None:
    result = check()
    print(json.dumps(result, indent=2))
    if not any(row.get("ok") for row in result["providers"].values()):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
