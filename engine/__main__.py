"""CLI.  python -m engine run            full discovery + refresh
          python -m engine run --seed f    also process a list you supply
          python -m engine run --seed f --only-seed   just that list (fast, for a new input)
          python -m engine report          print the last run report"""

import argparse
import json
import logging
import os
import sys

from . import export
from .pipeline import Pipeline, SimulatedFailure

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load_config(path):
    with open(path, encoding="utf-8-sig") as f:  # tolerate the BOM Windows editors add
        return json.load(f)


def paths_for(root):
    data = os.path.join(root, "data")
    os.makedirs(os.path.join(data, "cache"), exist_ok=True)
    os.makedirs(os.path.join(root, "output", "logs"), exist_ok=True)
    return {"db": os.path.join(data, "state.sqlite"), "cache": os.path.join(data, "cache"),
            "output": os.path.join(root, "output"), "outreach": os.path.join(root, "outreach"),
            "logs": os.path.join(root, "output", "logs"), "registry": os.path.join(root, "lead_ids.csv")}


def setup_logging(logdir, verbose):
    from datetime import datetime
    fmt = logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s", "%H:%M:%S")
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    h = logging.StreamHandler(sys.stdout)
    h.setFormatter(fmt)
    h.setLevel(logging.INFO if verbose else logging.WARNING)
    fh = logging.FileHandler(os.path.join(logdir, f"run_{datetime.now():%Y%m%d_%H%M%S}.log"), encoding="utf-8")
    fh.setFormatter(fmt)
    root.addHandler(h)
    root.addHandler(fh)
    # progress lines always reach the console
    logging.getLogger("engine").setLevel(logging.INFO)
    if not verbose:
        p = logging.StreamHandler(sys.stdout)
        p.setFormatter(fmt)
        p.addFilter(lambda r: r.name == "engine")
        root.addHandler(p)


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python -m engine")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="discover, verify, score and export")
    r.add_argument("--config", default=os.path.join(ROOT, "config.json"))
    r.add_argument("--seed", help="txt/csv of Apple Podcasts URLs, RSS feed URLs or show names")
    r.add_argument("--only-seed", action="store_true", help="skip discovery; process only the seed list")
    r.add_argument("--no-discover", action="store_true", help="re-verify known candidates without new searches")
    r.add_argument("--refetch", action="store_true", help="ignore the feed cache and re-check every feed")
    r.add_argument("--simulate-failure", type=int, metavar="N", help="crash after N feeds (recovery demo)")
    r.add_argument("--verbose", action="store_true")
    sub.add_parser("report", help="show the last run report")
    a = ap.parse_args(argv)

    paths = paths_for(ROOT)
    if a.cmd == "report":
        with open(os.path.join(paths["output"], "run_report.json"), encoding="utf-8") as f:
            print(f.read())
        return 0

    setup_logging(paths["logs"], a.verbose)
    # http.client complains while finalising responses we stopped reading early; that is harmless
    sys.unraisablehook = lambda u: None if isinstance(u.exc_value, ValueError) else sys.__unraisablehook__(u)
    cfg = load_config(a.config)
    p = Pipeline(cfg, paths)
    p.stats["mode"] = "seed-only" if a.only_seed else ("refresh" if a.no_discover else "full")
    try:
        rep = p.run(discover=not a.no_discover, seed=a.seed, fail_after=a.simulate_failure,
                    force_refetch=a.refetch, only_seed=a.only_seed)
    except SimulatedFailure as e:
        logging.getLogger("engine").error("%s", e)
        export.record_failure(paths, p.stats, p.errors, str(e))
        print(f"\nRun stopped: {e}\nProgress is saved in data/state.sqlite. Run the same command again to resume.")
        return 2
    except KeyboardInterrupt:
        print("\nInterrupted. Progress is saved; rerun the same command to resume.")
        return 130
    keys = ["qualified", "rejected", "reserve_country_cap", "duplicates_removed", "feed_errors",
            "runtime_min", "direct_cost_usd", "countries", "priority", "best_channels"]
    print("\n=== run summary ===")
    for k in keys:
        print(f"{k:>22}: {rep[k]}")
    if rep.get("seed_results"):
        print("\nseed results:")
        for s in rep["seed_results"]:
            print(f"  {s['lead_id'] or '-':7} {s['status']:9} {s['show'][:50]:50} {s['reason'][:90]}")
    print(f"\nWrote output/leads.csv ({rep['qualified']} leads), output/run_report.json, outreach/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
