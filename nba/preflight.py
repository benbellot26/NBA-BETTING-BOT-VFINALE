from __future__ import annotations
import importlib
MODULES=("nba.model","nba.team_strength","nba.pace","nba.rotations","nba.player_availability","nba.matchup","nba.context","nba.structural","nba.distribution","nba.market","nba.uncertainty","nba.decision","nba.staking","nba.certification","nba.pipeline","nba.provider_http","nba.schedule","nba.nba_stats_api","nba.team_inputs","nba.injury_pdf","nba.rotation_projection","nba.live_runtime","nba.prospective","nba.close_runtime","nba.performance_runtime","nba.provider_smoke","nba.odds_smoke","nba.v2_shadow","nba.replay_export","nba.pit_bundle","nba.lineage","nba.evidence_audit","nba.provider_contract","nba.providers","nba.fixture_provider","nba.e2e_dryrun","nba.v2_gate","nba.preseason_check","nba.preseason_rehearsal","nba.health_report","nba.automation_window","nba.market_smoke","nba.full_rehearsal","nba.health_gate","nba.odds_budget","nba.readiness_gate","nba.runner_probe")
def run()->dict:
    failures=[]
    for name in MODULES:
        try:importlib.import_module(name)
        except Exception as exc:failures.append(f"{name}: {exc}")
    return {"ok":not failures,"failures":failures,"modules_checked":len(MODULES)}
if __name__=="__main__":
    result=run()
    if not result["ok"]:raise SystemExit("\n".join(result["failures"]))
    print(f"preflight ok: {result['modules_checked']} modules")
