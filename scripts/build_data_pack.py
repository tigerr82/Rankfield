"""Build rankfield_data_pack.zip from the monthly records.

Run by the deploy workflow just before the site is built, so every monthly and weekly publish
carries a pack that matches the data. The ZIP is generated, not committed.

Run: python scripts/build_data_pack.py [output.zip]
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from rankfield.config import DATA_DIR, HISTORY_DIR, SITE_PUBLIC_DATA, read_json
from rankfield.datapack import build_pack

PACK_NAME = "rankfield_data_pack.zip"


def main() -> int:
    records, unranked = {}, {}
    for path in sorted(HISTORY_DIR.glob("scores_*.json")):
        records[path.stem.replace("scores_", "")] = read_json(path)
    for path in sorted(HISTORY_DIR.glob("unranked_*.json")):
        unranked[path.stem.replace("unranked_", "")] = read_json(path)
    current = read_json(DATA_DIR / "scores_full.json")
    if not records or not current:
        print("no monthly records or no scores_full.json: nothing to pack", file=sys.stderr)
        return 1
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else SITE_PUBLIC_DATA / PACK_NAME
    target.parent.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    target.write_bytes(build_pack(records, unranked, current, stamp))
    print(f"{target}  {target.stat().st_size / 1e6:.2f} MB  ({len(records)} months)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
