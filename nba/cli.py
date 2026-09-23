from __future__ import annotations

import argparse
import json
from pathlib import Path

from .pipeline import analyze_game
from .model import GameContext, TeamMetrics


def main() -> None:
    parser=argparse.ArgumentParser(description="Pulsar NBA research runtime")
    parser.add_argument("fixture", help="JSON fixture containing home/away/context/lines")
    args=parser.parse_args()
    data=json.loads(Path(args.fixture).read_text(encoding="utf-8"))
    result=analyze_game(
        home=TeamMetrics(**data["home"]), away=TeamMetrics(**data["away"]),
        context=GameContext(**data["context"]), spread_line=float(data["spread_line"]), total_line=float(data["total_line"]),
    )
    print(json.dumps(result, indent=2, sort_keys=True))

if __name__ == "__main__": main()
