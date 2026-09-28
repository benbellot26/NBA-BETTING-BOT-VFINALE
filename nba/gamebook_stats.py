"""Official-gamebook-derived NBA stat pack.

This is an alternate REFERENCE source for parity research while stats.nba.com
is inaccessible from the runner. It is deliberately not production-authorized:
promotion requires a separate parity gate against the canonical stat pack.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Callable

from .communications_schedule import ReferenceScheduleGame, fetch_reference_schedule
from .gamebook import gamebook_url, parse_gamebook_pdf
from .provider_http import get_bytes
from .rotation_projection import normalized_player_name
from .teams import TEAMS, team_info

WINDOWS = (0, 30, 15, 10, 5)
ROLE = "ALTERNATE_REFERENCE_ONLY"
SOURCE = "NBA_OFFICIAL_SCORERS_REPORT"


def _safe_div(a: float, b: float, default: float = 0.0) -> float:
    return float(a) / float(b) if abs(float(b)) > 1e-12 else float(default)


def _player_id(team: str, name: str) -> int:
    raw = f"{team_info(team).team_id}|{normalized_player_name(name)}".encode()
    value = int.from_bytes(hashlib.sha256(raw).digest()[:4], "big") & 0x7FFFFFFF
    return value or 1


def _poss(totals: dict[str, Any]) -> float:
    return (
        float(totals["FGA"])
        + 0.44 * float(totals["FTA"])
        - float(totals["OREB"])
        + float(totals["TOV"])
    )


def _cache_path(root: str | Path, reference_id: str) -> Path:
    clean = "".join(ch for ch in str(reference_id) if ch.isalnum() or ch in "-_")
    return Path(root) / "gamebooks" / f"{clean}.json"


def _validate_cached(payload: dict[str, Any]) -> dict[str, Any]:
    if payload.get("schema") != "pulsar-nba-gamebook-cache-v1":
        raise ValueError("unsupported gamebook cache schema")
    if payload.get("source") != SOURCE:
        raise ValueError("gamebook cache source mismatch")
    parsed = payload.get("parsed")
    if not isinstance(parsed, dict) or parsed.get("source") != SOURCE:
        raise ValueError("gamebook cache parsed payload invalid")
    return payload


def _candidate_orders(game: ReferenceScheduleGame) -> list[tuple[str, str]]:
    if game.away and game.home:
        return [(game.away, game.home)]
    # Neutral-site Communications rows do not designate home/away. The
    # official gamebook URL does, so try both schedule identities and accept
    # only the order whose PDF parses against the expected teams.
    return [(game.team1, game.team2), (game.team2, game.team1)]


def fetch_gamebook(
    game: ReferenceScheduleGame,
    *,
    cache_root: str | Path,
    fetcher: Callable[..., bytes] = get_bytes,
) -> dict[str, Any]:
    path = _cache_path(cache_root, game.reference_id)
    if path.exists():
        return _validate_cached(json.loads(path.read_text(encoding="utf-8")))

    errors: list[str] = []
    for away, home in _candidate_orders(game):
        url = gamebook_url(game_date=game.game_date, away=away, home=home)
        try:
            data = fetcher(
                url,
                headers={"Accept": "application/pdf"},
                timeout=15.0,
                retries=1,
            )
            parsed = parse_gamebook_pdf(
                data, expected_away=away, expected_home=home
            )
            payload = {
                "schema": "pulsar-nba-gamebook-cache-v1",
                "source": SOURCE,
                "role": ROLE,
                "reference_id": game.reference_id,
                "game_date": game.game_date,
                "away": away,
                "home": home,
                "pdf_sha256": hashlib.sha256(data).hexdigest(),
                "parsed": parsed,
            }
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                json.dumps(payload, sort_keys=True, separators=(",", ":")),
                encoding="utf-8",
            )
            return payload
        except Exception as exc:
            errors.append(f"{away}@{home}:{type(exc).__name__}:{exc}")
    raise RuntimeError(
        f"official gamebook unavailable for {game.reference_id}: "
        + " | ".join(errors)
    )


def collect_gamebooks(
    *,
    season: str,
    target_date: str,
    cache_root: str | Path,
    schedule: list[ReferenceScheduleGame] | None = None,
    fetcher: Callable[..., bytes] = get_bytes,
    max_network_games: int | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    cutoff = date.fromisoformat(target_date)
    rows = schedule if schedule is not None else fetch_reference_schedule(season=season)
    eligible = sorted(
        (row for row in rows if date.fromisoformat(row.game_date) < cutoff),
        key=lambda row: (row.game_date, row.schedule_number),
    )
    collected: list[dict[str, Any]] = []
    missing: list[dict[str, str]] = []
    network_used = 0
    for game in eligible:
        cached = _cache_path(cache_root, game.reference_id).exists()
        if not cached and max_network_games is not None and network_used >= max_network_games:
            missing.append({
                "reference_id": game.reference_id,
                "game_date": game.game_date,
                "reason": "network_limit",
            })
            continue
        try:
            collected.append(fetch_gamebook(
                game, cache_root=cache_root, fetcher=fetcher
            ))
            if not cached:
                network_used += 1
        except Exception as exc:
            if not cached:
                network_used += 1
            missing.append({
                "reference_id": game.reference_id,
                "game_date": game.game_date,
                "reason": f"{type(exc).__name__}:{exc}",
            })
    return collected, missing


def _team_games(gamebooks: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    out = {name: [] for name in TEAMS}
    for record in gamebooks:
        parsed = record["parsed"]
        away = str(record["away"])
        home = str(record["home"])
        out[away].append({
            "date": record["game_date"],
            "team": parsed["away"],
            "opponent": parsed["home"],
        })
        out[home].append({
            "date": record["game_date"],
            "team": parsed["home"],
            "opponent": parsed["away"],
        })
    for rows in out.values():
        rows.sort(key=lambda row: row["date"])
    return out


def _aggregate_team(team: str, games: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not games:
        return None
    team_pts = opp_pts = own_poss = opp_poss = 0.0
    pace_sum = 0.0
    fgm = fga = fg3m = fg3a = ftm = fta = oreb = dreb = tov = 0.0
    opp_oreb = opp_dreb = 0.0
    for game in games:
        own = game["team"]
        opp = game["opponent"]
        ot = own["totals"]
        pt = opp["totals"]
        p_own = _poss(ot)
        p_opp = _poss(pt)
        own_poss += p_own
        opp_poss += p_opp
        team_pts += float(ot["PTS"])
        opp_pts += float(pt["PTS"])
        game_minutes = float(own["minutes_seconds"]) / 5.0 / 60.0
        pace_sum += ((p_own + p_opp) / 2.0) * 48.0 / max(1.0, game_minutes)
        fgm += float(ot["FG"])
        fga += float(ot["FGA"])
        fg3m += float(ot["FG3M"])
        fg3a += float(ot["FG3A"])
        ftm += float(ot["FT"])
        fta += float(ot["FTA"])
        oreb += float(ot["OREB"])
        dreb += float(ot["DREB"])
        tov += float(ot["TOV"])
        opp_oreb += float(pt["OREB"])
        opp_dreb += float(pt["DREB"])
    gp = len(games)
    return {
        "TEAM_ID": team_info(team).team_id,
        "TEAM_NAME": team,
        "GP": gp,
        "OFF_RATING": 100.0 * _safe_div(team_pts, own_poss, 1.0),
        "DEF_RATING": 100.0 * _safe_div(opp_pts, opp_poss, 1.0),
        "PACE": pace_sum / gp,
        "EFG_PCT": _safe_div(fgm + 0.5 * fg3m, fga, 0.55),
        "TM_TOV_PCT": 100.0 * _safe_div(tov, fga + 0.44 * fta + tov, 0.13),
        "OREB_PCT": _safe_div(oreb, oreb + opp_dreb, 0.25),
        "FGA": fga / gp,
        "FTA": fta / gp,
        "FG3A": fg3a / gp,
        "PTS": team_pts / gp,
        "source": SOURCE,
    }


def _advanced_windows(team_games: dict[str, list[dict[str, Any]]]) -> dict[int, list[dict[str, Any]]]:
    result: dict[int, list[dict[str, Any]]] = {}
    for window in WINDOWS:
        rows: list[dict[str, Any]] = []
        for team, games in team_games.items():
            selected = games if window == 0 else games[-window:]
            row = _aggregate_team(team, selected)
            if row is not None:
                rows.append(row)
        result[window] = rows
    return result


def _player_rows(
    team_games: dict[str, list[dict[str, Any]]],
    *,
    last_n: int | None,
    advanced: bool,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for team, games in team_games.items():
        selected = games if not last_n else games[-last_n:]
        if not selected:
            continue
        team_summary = _aggregate_team(team, selected)
        assert team_summary is not None
        team_fga = team_fta = team_tov = 0.0
        appearances: dict[str, dict[str, Any]] = {}
        for game in selected:
            own = game["team"]
            totals = own["totals"]
            team_fga += float(totals["FGA"])
            team_fta += float(totals["FTA"])
            team_tov += float(totals["TOV"])
            for player in own.get("players") or []:
                name = str(player["name"])
                key = normalized_player_name(name)
                bucket = appearances.setdefault(key, {
                    "name": name, "minutes": 0.0, "games": 0,
                    "FGA": 0.0, "FTA": 0.0, "TOV": 0.0,
                })
                bucket["minutes"] += float(player["minutes_seconds"]) / 60.0
                bucket["games"] += 1
                stats = player["stats"]
                bucket["FGA"] += float(stats["FGA"])
                bucket["FTA"] += float(stats["FTA"])
                bucket["TOV"] += float(stats["TOV"])
        team_usage_den = team_fga + 0.44 * team_fta + team_tov
        for bucket in appearances.values():
            minutes = float(bucket["minutes"])
            if minutes <= 0:
                continue
            player_actions = (
                float(bucket["FGA"]) + 0.44 * float(bucket["FTA"]) + float(bucket["TOV"])
            )
            usage = 100.0 * _safe_div(
                player_actions * (len(selected) * 48.0),
                minutes * team_usage_den,
                0.0,
            )
            row = {
                "PLAYER_ID": _player_id(team, bucket["name"]),
                "TEAM_ID": team_info(team).team_id,
                "PLAYER_NAME": bucket["name"],
                "GP": int(bucket["games"]),
                "MIN": minutes / max(1, int(bucket["games"])),
                "USG_PCT": usage,
                "source": SOURCE,
            }
            if advanced:
                # Gamebooks do not provide player on/off possessions. Use team
                # efficiency as a conservative neutral impact baseline rather
                # than inventing player-specific ratings.
                row["OFF_RATING"] = float(team_summary["OFF_RATING"])
                row["DEF_RATING"] = float(team_summary["DEF_RATING"])
            rows.append(row)
    return rows


def build_reference_stat_pack(
    *,
    season: str,
    target_date: str,
    gamebooks: list[dict[str, Any]],
    missing: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    team_games = _team_games(gamebooks)
    advanced = _advanced_windows(team_games)
    base_season = [dict(row) for row in advanced[0]]
    player_season = _player_rows(team_games, last_n=None, advanced=False)
    player_recent = _player_rows(team_games, last_n=10, advanced=False)
    player_advanced = _player_rows(team_games, last_n=None, advanced=True)
    teams_with_games = sum(bool(rows) for rows in team_games.values())
    expected = len(gamebooks) + len(missing or [])
    completeness = _safe_div(len(gamebooks), expected, 0.0) if expected else 0.0
    return {
        "schema": "pulsar-nba-gamebook-stat-pack-v1",
        "role": ROLE,
        "production_provider_authorized": False,
        "source": SOURCE,
        "season": season,
        "date_to": (date.fromisoformat(target_date) - timedelta(days=1)).strftime("%m/%d/%Y"),
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "advanced_windows": advanced,
        "base_season": base_season,
        "player_season": player_season,
        "player_recent": player_recent,
        "player_advanced": player_advanced,
        "gamebooks": len(gamebooks),
        "missing_gamebooks": list(missing or []),
        "gamebook_completeness": completeness,
        "teams_with_games": teams_with_games,
        "player_rating_method": "team_efficiency_neutral_baseline",
    }


def run(
    *,
    season: str,
    target_date: str,
    cache_root: str = "runtime/gamebook_reference",
    output: str = "runtime/gamebook_reference/stat_pack.json",
    max_network_games: int | None = None,
) -> dict[str, Any]:
    gamebooks, missing = collect_gamebooks(
        season=season,
        target_date=target_date,
        cache_root=cache_root,
        max_network_games=max_network_games,
    )
    pack = build_reference_stat_pack(
        season=season, target_date=target_date,
        gamebooks=gamebooks, missing=missing,
    )
    target = Path(output)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(pack, indent=2, sort_keys=True), encoding="utf-8")
    return pack


def main() -> None:
    parser = argparse.ArgumentParser(description="Build reference stats from official NBA gamebooks")
    parser.add_argument("--season", required=True)
    parser.add_argument("--date", required=True)
    parser.add_argument("--cache-root", default="runtime/gamebook_reference")
    parser.add_argument("--output", default="runtime/gamebook_reference/stat_pack.json")
    parser.add_argument("--max-network-games", type=int)
    args = parser.parse_args()
    result = run(
        season=args.season,
        target_date=args.date,
        cache_root=args.cache_root,
        output=args.output,
        max_network_games=args.max_network_games,
    )
    print(json.dumps({
        "role": result["role"],
        "production_provider_authorized": False,
        "gamebooks": result["gamebooks"],
        "missing_gamebooks": len(result["missing_gamebooks"]),
        "gamebook_completeness": result["gamebook_completeness"],
        "teams_with_games": result["teams_with_games"],
    }, indent=2))


if __name__ == "__main__":
    main()
