"""Stage 5b - the monthly data-drift gate.

Reads data/drift_report.json (written by compute_scores.py) and:
  * prints a summary,
  * writes the markdown body for a GitHub issue when there is anything to review,
  * exposes `status` as a step output (ok / warn / block / baseline),
  * exits 2 on `block`, so the workflow stops before committing a ranking whose
    universe collapsed - usually an EDGAR taxonomy change, not a market event.

Run: python scripts/check_drift.py [--issue-body PATH]
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from rankfield.config import DATA_DIR, read_json
from rankfield.drift import render_issue


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--issue-body", default=None, help="where to write the issue markdown")
    args = parser.parse_args()

    report = read_json(DATA_DIR / "drift_report.json")
    if not report:
        print("data/drift_report.json missing - run compute_scores.py first", file=sys.stderr)
        return 1

    status = report["status"]
    print(f"drift status: {status}")
    print(f"  scored {report['scored_now']} (prior {report['scored_prior']}, change {report['scored_change_pct']}%)")
    print(f"  dropped out: {len(report['dropped_out'])}; metrics lost: {len(report['metrics_lost'])} "
          f"(plus {len(report['metrics_lost_economic'])} for economic reasons); "
          f"recently abandoned tags: {len(report['recently_abandoned_tags'])}")

    if args.issue_body and status in ("warn", "block"):
        Path(args.issue_body).write_text(render_issue(report), encoding="utf-8")
        print(f"  issue body -> {args.issue_body}")

    output = os.environ.get("GITHUB_OUTPUT")
    if output:
        with open(output, "a", encoding="utf-8") as fh:
            fh.write(f"status={status}\n")

    if status == "block":
        print("::error::Scored universe fell past the block threshold - publication stopped. "
              "See the drift issue.")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
