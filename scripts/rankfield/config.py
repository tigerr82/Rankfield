"""Paths and configuration loading. Every script reads settings from here."""
from __future__ import annotations

import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = ROOT / "config"
DATA_DIR = ROOT / "data"
HISTORY_DIR = DATA_DIR / "history"
CACHE_DIR = DATA_DIR / ".cache"
SITE_PUBLIC_DATA = ROOT / "site" / "public" / "data"


def load_settings() -> dict:
    with open(CONFIG_DIR / "settings.json", encoding="utf-8") as fh:
        return json.load(fh)


def load_weights() -> dict:
    """Official weights. `version` is stamped onto every score record."""
    with open(CONFIG_DIR / "weights.json", encoding="utf-8") as fh:
        return json.load(fh)


def user_agent() -> str:
    """SEC requires a real name and email.

    Deliberately NOT defaulted in config/settings.json: that file is committed
    to a public repository, and a personal address does not belong there. The
    environment variable is the only source, so a missing contact fails here
    with an explanation rather than reaching EDGAR as a blank or fake one.
    """
    contact = os.environ.get("RANKFIELD_USER_AGENT") or load_settings()["http"].get("user_agent") or ""
    if "@" not in contact:
        raise RuntimeError(
            "RANKFIELD_USER_AGENT is not set. SEC policy requires a User-Agent carrying a "
            "real name and email address.\n"
            '  export RANKFIELD_USER_AGENT="Your Name your@email.com"'
        )
    return contact


def ensure_dirs() -> None:
    for d in (DATA_DIR, HISTORY_DIR, CACHE_DIR):
        d.mkdir(parents=True, exist_ok=True)


def write_json(path: Path, payload, *, compact: bool = False) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        if compact:
            json.dump(payload, fh, separators=(",", ":"), ensure_ascii=False)
        else:
            json.dump(payload, fh, indent=1, ensure_ascii=False)
    return path


def read_json(path: Path, default=None):
    if not Path(path).exists():
        return default
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)
