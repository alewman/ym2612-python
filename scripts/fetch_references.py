#!/usr/bin/env python
"""Fetch the two die-derived referees' sources at their pinned commits.

    python scripts/fetch_references.py            # fetch what is missing
    python scripts/fetch_references.py --verify   # only check what is there

Into ``reference/src/`` (ignored): they are (L)GPL, read and run as referees here,
never copied into this repository (docs/referees.md).
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "reference" / "src"

#: The pins, the same as megadrive-python's scripts/pinned_repos.json.
REPOS = [
    {
        "path": "Nuked-OPN2",
        "url": "https://github.com/nukeykt/Nuked-OPN2",
        "rev": "335747d78cb0abbc3b55b004e62dad9763140115",
        "why": "The YM3438 transcribed from its die, with a YM2612 output mode: the judge. "
        "LGPL-2.1.",
    },
    {
        "path": "YM2608-LLE",
        "url": "https://github.com/nukeykt/YM2608-LLE",
        "rev": "7a2aca7b6830b96e48e3a4e1a40d15525993fa60",
        "why": "Die-derived low-level models; fmopna_2612.c is the NMOS YM2612: a detector. "
        "GPL-2.0.",
    },
]


def head(path: Path) -> str | None:
    if not (path / ".git").exists():
        return None
    result = subprocess.run(
        ["git", "-C", str(path), "rev-parse", "HEAD"], capture_output=True, text=True
    )
    return result.stdout.strip() or None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--verify", action="store_true", help="check, do not fetch")
    args = parser.parse_args(argv)
    bad = 0
    for entry in REPOS:
        path = SRC / entry["path"]
        if head(path) == entry["rev"]:
            print(f"{entry['path']}: at {entry['rev'][:7]}")
            continue
        if args.verify:
            print(f"{entry['path']}: missing or not at {entry['rev'][:7]}")
            bad += 1
            continue
        path.mkdir(parents=True, exist_ok=True)
        git = ["git", "-C", str(path)]
        if not (path / ".git").exists():
            subprocess.run([*git, "init", "-q"], check=True)
        subprocess.run(
            [*git, "fetch", "-q", "--depth", "1", entry["url"], entry["rev"]], check=True
        )
        subprocess.run([*git, "checkout", "-q", "--detach", "FETCH_HEAD"], check=True)
        if head(path) != entry["rev"]:
            print(f"{entry['path']}: fetched the wrong revision")
            bad += 1
            continue
        print(f"{entry['path']}: fetched {entry['rev'][:7]}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
