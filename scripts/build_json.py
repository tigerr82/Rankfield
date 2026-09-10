"""Stage 5 - emit the site payloads.

Copies the generated data into site/public/data so the static build serves it.
Kept as its own stage so the scoring run and the publish step can fail
independently, and so the site can be rebuilt without re-scoring.

Run: python scripts/build_json.py
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from rankfield.config import DATA_DIR, SITE_PUBLIC_DATA, read_json

# The ranking table loads on page load; nothing else is fetched until a screen
# needs it. One giant payload would be tens of megabytes.
PAYLOADS = [
    "scores_full.json",
    "scores_public.json",
    "history_index.json",
    "coverage_report.json",
]


def main() -> int:
    SITE_PUBLIC_DATA.mkdir(parents=True, exist_ok=True)
    missing = [name for name in PAYLOADS if not (DATA_DIR / name).exists()]
    if missing:
        print(f"missing generated payloads: {', '.join(missing)} - run compute_scores.py first",
              file=sys.stderr)
        return 1

    total = 0
    for name in PAYLOADS:
        source = DATA_DIR / name
        shutil.copy2(source, SITE_PUBLIC_DATA / name)
        size = source.stat().st_size
        total += size
        print(f"  {name:<24} {size / 1e6:6.2f} MB")

    # A small universe file for anything that needs names without the scores.
    universe = read_json(DATA_DIR / "universe.json") or {}
    slim = {
        "generated_at": universe.get("generated_at"),
        "listings": [
            {
                "ticker": row["ticker"],
                "name": row["name"],
                "sector": row["sector"],
                "exchange": row["exchange"],
                "market_cap": row["market_cap"],
            }
            for row in universe.get("listings", [])
        ],
    }
    import json

    with open(SITE_PUBLIC_DATA / "universe.json", "w", encoding="utf-8") as fh:
        json.dump(slim, fh, separators=(",", ":"))
    size = (SITE_PUBLIC_DATA / "universe.json").stat().st_size
    total += size
    print(f"  {'universe.json':<24} {size / 1e6:6.2f} MB")
    print(f"published -> {SITE_PUBLIC_DATA}  ({total / 1e6:.2f} MB total)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
