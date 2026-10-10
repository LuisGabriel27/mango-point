"""Run controlled sensitivity experiments and the transparent BPI recheck."""

import argparse
import json
from pathlib import Path
from core.config import SIMULATION_MODEL_VERSION
from validation.revision_audit import input_audit, run_sensitivity, run_bpi, export_figures, export_daylight_response


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    revision = SIMULATION_MODEL_VERSION.rsplit("-", 1)[-1]
    parser.add_argument("--output", type=Path, default=Path(f"outputs/revision-{revision}-audit"))
    parser.add_argument("--seeds", type=int, default=30, help="Repeated seeds per sensitivity scenario/engine")
    parser.add_argument("--monte-carlo", type=int, default=10, help="BPI realizations per weather window")
    parser.add_argument("--windows", type=int, default=4)
    parser.add_argument("--workers", type=int, default=1, help="Independent BPI simulation processes")
    parser.add_argument("--part", choices=["all", "sensitivity", "bpi", "bpi_tree_graph", "light"], default="all")
    args = parser.parse_args()
    if min(args.seeds, args.monte_carlo, args.windows, args.workers) < 1:
        parser.error("Seed, Monte Carlo, window and worker counts must be positive")
    root = Path(__file__).resolve().parents[1]
    output = args.output.resolve(); output.mkdir(parents=True, exist_ok=True)
    audit = input_audit(root)
    (output / "input_audit.json").write_text(json.dumps(audit, indent=2), encoding="utf-8")
    print(json.dumps(audit, indent=2), flush=True)
    export_daylight_response(output)
    summary = run_sensitivity(output, list(range(1000, 1000 + args.seeds))) if args.part in ["all", "sensitivity"] else None
    if args.part in ["all", "bpi"]:
        run_bpi(output, root, args.monte_carlo, args.windows, args.workers)
    if args.part in ["all", "bpi_tree_graph"]:
        run_bpi(output, root, args.monte_carlo, args.windows, args.workers, mode="tree_graph")
    export_figures(output, summary)
    print(f"Artifacts saved to {output}", flush=True)


if __name__ == "__main__":
    main()
