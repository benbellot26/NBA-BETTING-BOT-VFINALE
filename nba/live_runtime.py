from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import date, datetime, timezone
import json
from pathlib import Path
from typing import Any

from .acquisition import fetch_nba_odds
from .injury_pdf import fetch_latest_report
from .live_inputs import acquire_stat_pack, team_id, team_metric_from_pack
from .odds_normalizer import normalize_game
from .pipeline import analyze_game
from .rotation_projection import project_rotation
from .schedule import fetch_schedule, games_on, season_for_date
from .schedule_context import build_game_context
from .snapshot_store import persist_snapshot
from .teams import canonical_team


def _phase(minutes: float) -> str:
    if 5 <= minutes <= 30: return "FINAL"
    if minutes <= 180: return "PREGAME"
    if minutes <= 720: return "MORNING"
    return "EARLY"


def _minutes_to(commence: str, now: datetime) -> float:
    if not commence: return 9999.0
    dt=datetime.fromisoformat(commence.replace("Z","+00:00"))
    if dt.tzinfo is None: dt=dt.replace(tzinfo=timezone.utc)
    return (dt.astimezone(timezone.utc)-now).total_seconds()/60


def _injury_map(report: dict[str,Any], team: str) -> dict[str,str]:
    return {str(r["player_name"]):str(r["status"]) for r in report.get("records") or [] if canonical_team(str(r.get("team") or ""))==canonical_team(team)}


def _line(books: list[dict[str,Any]], selection: str) -> float | None:
    pinnacle=[b for b in books if str(b.get("bookmaker") or "").lower()=="pinnacle"]
    search=pinnacle or books
    for book in search:
        for row in book.get("selections") or []:
            if row.get("selection")==selection and row.get("point") is not None:
                return float(row["point"])
    return None


def _match_odds(game, normalized: list[dict[str,Any]]) -> dict[str,Any] | None:
    for row in normalized:
        if canonical_team(row["home"])==canonical_team(game.home) and canonical_team(row["away"])==canonical_team(game.away):
            return row
    return None


def run(*, target_date: str, output: str, snapshot_root: str="runtime/snapshots") -> dict[str,Any]:
    now=datetime.now(timezone.utc); observed=now.isoformat(); season=season_for_date(target_date)
    result={"schema":"pulsar-nba-live-run-v1","target_date":target_date,"season":season,"generated_at":observed,"status":"OK","failures":[],"games":[]}
    try:
        schedule=fetch_schedule(); slate=games_on(schedule,target_date)
    except Exception as exc:
        result["status"]="NO_ANALYSIS"; result["failures"].append(f"schedule:{exc}"); schedule=[]; slate=[]
    if not slate:
        if result["status"]=="OK": result["status"]="NO_GAMES"
        Path(output).parent.mkdir(parents=True,exist_ok=True); Path(output).write_text(json.dumps(result,indent=2),encoding="utf-8"); return result
    try:
        raw_odds=fetch_nba_odds(); normalized=[normalize_game(x) for x in raw_odds]
        persist_snapshot(snapshot_root,kind="odds",observed_at=observed,payload=normalized,source="the-odds-api")
    except Exception as exc:
        result["status"]="NO_ANALYSIS"; result["failures"].append(f"odds:{exc}"); normalized=[]
    try:
        stats=acquire_stat_pack(season=season,observed_at=observed,snapshot_root=snapshot_root)
    except Exception as exc:
        result["status"]="NO_ANALYSIS"; result["failures"].append(f"stats:{exc}"); stats=None
    try:
        injuries=fetch_latest_report(season=season)
        persist_snapshot(snapshot_root,kind="injuries",observed_at=injuries["reported_at"],payload=injuries,source=injuries["source_url"])
    except Exception as exc:
        injuries={"records":[],"reported_at":None,"source_url":None}; result["failures"].append(f"injuries:{exc}")
    if stats is not None and normalized:
        for game in slate:
            odds=_match_odds(game,normalized)
            if not odds:
                result["failures"].append(f"{game.game_id}:odds_unmatched"); continue
            spread=_line(odds["markets"]["SPREAD"],"HOME"); total=_line(odds["markets"]["TOTAL"],"OVER")
            if spread is None or total is None:
                result["failures"].append(f"{game.game_id}:canonical_line_missing"); continue
            phase=_phase(_minutes_to(game.commence_time,now))
            context=build_game_context(game,schedule,analyzed_at=observed,phase=phase)
            home=team_metric_from_pack(game.home,stats,home=True); away=team_metric_from_pack(game.away,stats,home=False)
            try:
                hr=project_rotation(team_id(game.home),season_base=stats["player_season"],recent_base=stats["player_recent"],season_advanced=stats["player_advanced"],team_ortg=home.ortg,team_drtg=home.drtg,injury_status=_injury_map(injuries,game.home))
                ar=project_rotation(team_id(game.away),season_base=stats["player_season"],recent_base=stats["player_recent"],season_advanced=stats["player_advanced"],team_ortg=away.ortg,team_drtg=away.drtg,injury_status=_injury_map(injuries,game.away))
            except Exception as exc:
                result["failures"].append(f"{game.game_id}:rotation:{exc}"); continue
            analysis=analyze_game(home=home,away=away,context=context,spread_line=spread,total_line=total,books_by_market=odds["markets"],home_rotation=hr,away_rotation=ar,market_fresh=True)
            analysis["commence_time"]=game.commence_time; analysis["injury_report_at"]=injuries.get("reported_at"); analysis["rotation_home"]=[asdict(x) for x in hr]; analysis["rotation_away"]=[asdict(x) for x in ar]
            result["games"].append(analysis)
    if not result["games"] and result["status"]=="OK": result["status"]="NO_ANALYSIS"
    Path(output).parent.mkdir(parents=True,exist_ok=True); Path(output).write_text(json.dumps(result,indent=2),encoding="utf-8")
    return result


def main() -> None:
    p=argparse.ArgumentParser(); p.add_argument("--date",default=date.today().isoformat()); p.add_argument("--output",default="runtime/live_run.json"); p.add_argument("--snapshot-root",default="runtime/snapshots"); args=p.parse_args()
    out=run(target_date=args.date,output=args.output,snapshot_root=args.snapshot_root)
    print(json.dumps({"status":out["status"],"games":len(out["games"]),"failures":out["failures"]},indent=2))


if __name__=="__main__": main()
