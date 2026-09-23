from __future__ import annotations

import hashlib
from pathlib import Path

from . import MODEL_GENERATION, PROBABILITY_POLICY_ID

PREDICTIVE_FILES = (
    "nba/model.py", "nba/team_strength.py", "nba/pace.py", "nba/rotations.py",
    "nba/player_availability.py", "nba/matchup.py", "nba/context.py",
    "nba/structural.py", "nba/distribution.py",
)


def file_sha256(path: str | Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def build_manifest(root: str | Path = ".") -> dict:
    root=Path(root)
    files={name:file_sha256(root/name) for name in PREDICTIVE_FILES}
    identity="\n".join(f"{k}:{v}" for k,v in sorted(files.items())).encode()
    return {"model_generation":MODEL_GENERATION,"probability_policy_id":PROBABILITY_POLICY_ID,"files":files,"manifest_sha256":hashlib.sha256(identity).hexdigest()}
