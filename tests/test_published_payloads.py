"""The site serves its own copy of the data, so the copy must match the record.

Methodology 1.7 and 1.8 were both scored, committed and deployed while the
site kept serving the 1.6 payload: `compute_scores.py` writes `data/`, and it
is `build_json.py` that copies the payloads into `site/public/data/`. The
monthly workflow runs both; a manual regeneration is one command away from
publishing nothing. These tests fail that commit instead of the reader finding
out - run `python scripts/build_json.py` and commit again.
"""
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
PUBLISHED = ROOT / "site" / "public" / "data"
PAYLOADS = ["scores_full.json", "scores_public.json", "history_index.json", "coverage_report.json"]

pytestmark = pytest.mark.skipif(
    not (DATA / "scores_full.json").exists(),
    reason="no scoring run in this checkout",
)


def load(directory: Path, name: str):
    path = directory / name
    if not path.exists():
        pytest.fail(f"{path.relative_to(ROOT)} is missing - run python scripts/build_json.py")
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


@pytest.mark.parametrize("name", PAYLOADS)
def test_the_published_payload_is_the_one_that_was_scored(name):
    generated, published = load(DATA, name), load(PUBLISHED, name)
    assert published == generated, (
        f"site/public/data/{name} is not the file compute_scores.py produced - "
        "run python scripts/build_json.py and commit the result"
    )


def test_the_site_serves_the_current_methodology_version():
    generated = load(DATA, "scores_full.json")["meta"]
    published = load(PUBLISHED, "scores_full.json")["meta"]
    assert published["weights_version"] == generated["weights_version"]
    assert published["scoring_date"] == generated["scoring_date"]
    assert published["generated_at"] == generated["generated_at"]
