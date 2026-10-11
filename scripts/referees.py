"""Running the two FM referees, and reading and writing register streams.

The referees are C programs built from the pinned die-derived sources by
``sh validation/build_referees.sh`` into ``reference/build-referees/`` (ignored):

* ``opn2_ref``    -- Nuked-OPN2 (the YM3438 from its die, with a YM2612 output mode)
* ``lle2612_ref`` -- YM2608-LLE's ``fmopna_2612.c`` (the NMOS YM2612 from its die)

Each takes a binary event file of ``{u64 clock; u8 port; u8 data}`` records and
writes a binary output file; the clock unit differs per referee and is documented
in the corresponding ``validation/*.c``. This module builds those files, runs the
program and decodes the result, so the run scripts stay short. The same event file
is how a board hands this repository a register stream (``scripts/
export_board_streams.py``): ``clock`` is then the chip's internal cycle, the unit
``opn2_ref`` takes.
"""

from __future__ import annotations

import os
import struct
import subprocess
import sys
from array import array
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REFEREES = ROOT / "reference" / "build-referees"

EVENT = struct.Struct("<QBB")

#: Two of these running at once in the same directory -- two pytest workers, a run
#: beside a test -- must not write each other's event and output files, so every
#: name carries the process id.
_PID = os.getpid()


def referee(name: str) -> Path:
    path = REFEREES / name
    if not path.exists():
        raise SystemExit(
            f"{path} is missing: run `python scripts/fetch_references.py` and "
            "`sh validation/build_referees.sh` first"
        )
    return path


def write_events(path: Path, events: list[tuple[int, int, int]]) -> None:
    """``(clock, port, data)`` records, sorted, into an event file."""
    with path.open("wb") as handle:
        for clock, port, data in sorted(events):
            handle.write(EVENT.pack(clock, port & 0xFF, data & 0xFF))


def read_events(path: Path) -> list[tuple[int, int, int]]:
    """An event file's ``(clock, port, data)`` records, in file order."""
    raw = path.read_bytes()
    if len(raw) % EVENT.size:
        raise ValueError(f"{path}: not a whole number of {EVENT.size}-byte records")
    return list(EVENT.iter_unpack(raw))


def _run(program: Path, args: list[str]) -> None:
    result = subprocess.run([str(program), *args], capture_output=True)
    if result.returncode != 0:
        sys.stderr.write(result.stderr.decode(errors="replace"))
        raise SystemExit(f"{program.name} failed ({result.returncode})")


def run_opn2(
    events: list[tuple[int, int, int]],
    cycles: int,
    tmp: Path,
    *,
    variant: str = "ym2612",
    every: int = 1,
) -> tuple[array, array, array]:
    """Nuked-OPN2 over ``cycles`` internal cycles; returns (mol, mor, status)."""
    event_file, out_file = tmp / f"opn2-events-{_PID}.bin", tmp / f"opn2-out-{_PID}.bin"
    write_events(event_file, events)
    _run(referee("opn2_ref"), [str(event_file), str(out_file), str(cycles), variant, str(every)])
    triples = array("h")
    triples.frombytes(out_file.read_bytes())
    if sys.byteorder == "big":
        triples.byteswap()
    event_file.unlink()
    out_file.unlink()
    return triples[0::3], triples[1::3], triples[2::3]


def run_lle(
    events: list[tuple[int, int, int]], clocks: int, tmp: Path, *, every: int = 1
) -> tuple[array, array]:
    """YM2608-LLE's YM2612 over ``clocks`` chip clocks; returns (o_mol, o_mor)."""
    event_file, out_file = tmp / f"lle-events-{_PID}.bin", tmp / f"lle-out-{_PID}.bin"
    write_events(event_file, events)
    _run(referee("lle2612_ref"), [str(event_file), str(out_file), str(clocks), str(every)])
    both = array("h")
    both.frombytes(out_file.read_bytes())
    if sys.byteorder == "big":
        both.byteswap()
    event_file.unlink()
    out_file.unlink()
    return both[0::2], both[1::2]
