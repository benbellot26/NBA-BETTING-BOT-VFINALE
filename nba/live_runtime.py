from __future__ import annotations
import argparse,json
from dataclasses import asdict
from datetime import date,datetime,timezone
from pathlib import Path
from typing import Any
from .acquisition import fetch_nba_odds
from .injury_pdf import fetch_latest_report
from .live_inputs import acquire_stat_pack,team_id,team_metric_from_pack
from .odds_normalizer import normalize_game
from .pipeline import analyze_game
from .rotation_projection import project_rotation
from .schedule import fetch_schedule,games_on,season_for_date
from .schedule_context import build_game_context
from .snapshot_store import persist_snapshot
from .teams import canonical_team
from .timing import is_final_window

def _phase(minutes:float)->str:
    if 5<=minutes<=30:return "FINAL"
    if minutes<=180:return "PREGAME"
    if minutes<=720:return "MORNING"
    return "EARLY"
def _minutes_to(commence:str,now:datetime)->float:
    if not commence:return 9999
    dt=datetime.fromisoformat(commence.replace("Z","+00:00"));dt=dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    return (dt.astimezone(timezone.utc)-now).total_seconds()/60
def _injury_map(report:dict[str,Any],team:str)->dict[str,str]:
    return {str(r["player_name"]):str(r["status"]) for r in report.get("records") or [] if canonical_team(str(r.get("team") or ""))==canonical_team(team)}
def _line(books:list[dict[str,Any]],selection:str)->float|None:
    search=[b for b in books if str(b.get("bookmaker") or "").lower()=="pinnacle"] or books
    for b in search:
        for r in b.get("selections") or []:
            if r.get("selection")==selection and r.get("point") is not None:return float(r["point"])
    return None
def _match(game,rows):
    return next((r for r in rows if canonical_team(r["home"])==canonical_team(game.home) and canonical_team(r["away"])==canonical_team(game.away)),None)
def _load_cert(path:str)->dict[str,Any]:
    try:return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:return {"certified":False,"markets":{}}

def run(*,target_date:str,output:str,snapshot_root:str="runtime/snapshots",certification_path:str="data/nba_betting_certification.json")->dict[str,Any]:
    now=datetime.now(timezone.utc);observed=now.isoformat();season=season_for_date(target_date);out={"schema":"pulsar-nba-live-run-v1","target_date":target_date,"season":season,"generated_at":observed,"status":"OK","failures":[],"games":[]}
    try:schedule=fetch_schedule();slate=games_on(schedule,target_date)
    except Exception as exc:out["status"]="NO_ANALYSIS";out["failures"].append(f"schedule:{exc}");schedule=[];slate=[]
    if not slate:
        if out["status"]=="OK":out["status"]="NO_GAMES"
        Path(output).parent.mkdir(parents=True,exist_ok=True);Path(output).write_text(json.dumps(out,indent=2),encoding="utf-8");return out
    try:
        odds=[normalize_game(x) for x in fetch_nba_odds()];persist_snapshot(snapshot_root,kind="odds",observed_at=observed,payload=odds,source="the-odds-api")
    except Exception as exc:out["status"]="NO_ANALYSIS";out["failures"].append(f"odds:{exc}");odds=[]
    try:stats=acquire_stat_pack(season=season,observed_at=observed,snapshot_root=snapshot_root)
    except Exception as exc:out["status"]="NO_ANALYSIS";out["failures"].append(f"stats:{exc}");stats=None
    try:
        injuries=fetch_latest_report(season=season);persist_snapshot(snapshot_root,kind="injuries",observed_at=injuries["reported_at"],payload=injuries,source=injuries["source_url"])
        if not injuries.get("records"):raise RuntimeError("official injury report parsed zero player rows")
    except Exception as exc:out["status"]="NO_ANALYSIS";out["failures"].append(f"injuries:{exc}");injuries=None
    cert=_load_cert(certification_path)
    if stats is not None and odds and injuries is not None:
        for game in slate:
            market=_match(game,odds)
            if not market:out["failures"].append(f"{game.game_id}:odds_unmatched");continue
            spread=_line(market["markets"]["SPREAD"],"HOME");total=_line(market["markets"]["TOTAL"],"OVER")
            if spread is None or total is None:out["failures"].append(f"{game.game_id}:canonical_line_missing");continue
            phase=_phase(_minutes_to(game.commence_time,now));ctx=build_game_context(game,schedule,analyzed_at=observed,phase=phase);home=team_metric_from_pack(game.home,stats,home=True);away=team_metric_from_pack(game.away,stats,home=False)
            try:
                hr=project_rotation(team_id(game.home),season_base=stats["player_season"],recent_base=stats["player_recent"],season_advanced=stats["player_advanced"],team_ortg=home.ortg,team_drtg=home.drtg,injury_status=_injury_map(injuries,game.home));ar=project_rotation(team_id(game.away),season_base=stats["player_season"],recent_base=stats["player_recent"],season_advanced=stats["player_advanced"],team_ortg=away.ortg,team_drtg=away.drtg,injury_status=_injury_map(injuries,game.away))
            except Exception as exc:out["failures"].append(f"{game.game_id}:rotation:{exc}");continue
            timing=is_final_window(phase=phase,analyzed_at=observed,commence_time=game.commence_time)
            analysis=analyze_game(home=home,away=away,context=ctx,spread_line=spread,total_line=total,books_by_market=market["markets"],certification=cert,home_rotation=hr,away_rotation=ar,market_fresh=True,betting_window_ok=timing)
            analysis["commence_time"]=game.commence_time;analysis["injury_report_at"]=injuries["reported_at"];analysis["rotation_home"]=[asdict(x) for x in hr];analysis["rotation_away"]=[asdict(x) for x in ar];out["games"].append(analysis)
    if not out["games"] and out["status"]=="OK":out["status"]="NO_ANALYSIS"
    Path(output).parent.mkdir(parents=True,exist_ok=True);Path(output).write_text(json.dumps(out,indent=2),encoding="utf-8");return out

def main()->None:
    p=argparse.ArgumentParser();p.add_argument("--date",default=date.today().isoformat());p.add_argument("--output",default="runtime/live_run.json");p.add_argument("--snapshot-root",default="runtime/snapshots");p.add_argument("--certification",default="data/nba_betting_certification.json");a=p.parse_args();r=run(target_date=a.date,output=a.output,snapshot_root=a.snapshot_root,certification_path=a.certification);print(json.dumps({"status":r["status"],"games":len(r["games"]),"failures":r["failures"]},indent=2))
if __name__=="__main__":main()
