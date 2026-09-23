from __future__ import annotations
from datetime import datetime,timezone
import argparse
from pathlib import Path
import json
from .injury_pdf import fetch_latest_report
from .nba_stats_api import team_stats
from .schedule import fetch_schedule,season_for_date

def _previous(season:str)->str:
    start=int(season[:4])-1
    return f"{start}-{str(start+1)[-2:]}"

def run()->dict:
    now=datetime.now(timezone.utc);season=season_for_date(now)
    result={"schema":"pulsar-nba-provider-smoke-v1","checked_at":now.isoformat(),"season":season,"providers":{},"ok":True}
    try:
        games=fetch_schedule()
        if len(games)<1000:raise RuntimeError(f"unexpected schedule size {len(games)}")
        result["providers"]["schedule"]={"ok":True,"games":len(games)}
    except Exception as exc:
        result["providers"]["schedule"]={"ok":False,"error":str(exc)};result["ok"]=False
    stats_season=season
    try:
        rows=team_stats(season=stats_season,last_n_games=0,measure_type="Advanced")
        if len(rows)<25:
            stats_season=_previous(season);rows=team_stats(season=stats_season,last_n_games=0,measure_type="Advanced")
        if len(rows)<25:raise RuntimeError(f"unexpected team-stat row count {len(rows)}")
        result["providers"]["stats"]={"ok":True,"season":stats_season,"teams":len(rows)}
    except Exception as exc:
        result["providers"]["stats"]={"ok":False,"error":str(exc)};result["ok"]=False
    injury_season=season
    try:
        try:report=fetch_latest_report(season=injury_season)
        except Exception:
            injury_season=_previous(season);report=fetch_latest_report(season=injury_season)
        if int(report.get("record_count") or 0)<=0:raise RuntimeError("injury report parsed zero player rows")
        result["providers"]["injuries"]={"ok":True,"season":injury_season,"records":report["record_count"],"reported_at":report["reported_at"]}
    except Exception as exc:
        result["providers"]["injuries"]={"ok":False,"error":str(exc)};result["ok"]=False
    return result

def main()->None:
    parser=argparse.ArgumentParser()
    parser.add_argument("--output")
    args=parser.parse_args()
    result=run()
    payload=json.dumps(result,indent=2)
    if args.output:
        target=Path(args.output);target.parent.mkdir(parents=True,exist_ok=True);target.write_text(payload,encoding="utf-8")
    print(payload)
    if not result["ok"]:raise SystemExit(1)
if __name__=="__main__":main()
