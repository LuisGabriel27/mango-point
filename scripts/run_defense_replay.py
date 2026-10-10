"""Replay the saved enhanced BPI defense with both current simulation engines."""

import argparse
from pathlib import Path
from core.config import SIMULATION_MODEL_VERSION

from validation.defense_replay import run_replay


def main():
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    revision = SIMULATION_MODEL_VERSION.rsplit("-", 1)[-1]
    parser.add_argument("--output", type=Path, default=root / f"outputs/validation_defense_{revision}")
    parser.add_argument("--reference", type=Path, default=root / "docs/v16-defense-legacy-reference.csv")
    parser.add_argument("--monte-carlo", type=int, default=30)
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    if min(args.monte_carlo, args.workers) < 1:
        parser.error("Realization and worker counts must be positive")
    _, summary = run_replay(root, args.output.resolve(), args.reference.resolve(), args.monte_carlo, args.workers)
    print(summary[(summary.split == "testing") & (summary.pest == "both")].to_string(index=False), flush=True)
    print(f"Artifacts saved to {args.output.resolve()}", flush=True)


if __name__ == "__main__":
    main()
