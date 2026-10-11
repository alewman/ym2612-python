#!/usr/bin/env python
"""Export the register streams a board's YM2612 receives, as event files.

    python scripts/export_board_streams.py --board ../megadrive-python --roms --games

The stream is the board's own: every write that reached the chip, at the internal cycle
the board's chip was at when it arrived, so a replay into a fresh chip sees each write on
the cycle the board's did (scripts/run_fm_streams.py ``--streams``). Writes made while
/IC is held never reach the chip and are not recorded. The generator is off for the
capture: the register stream does not depend on it.

This needs megadrive-python (``--board``: a checkout; its ``src`` goes on the path) and
the ROMs. The files land in ``validation/streams/`` (ignored), each with a ``.json``
beside it: the image's SHA-256, the frames run, the buttons, and the cycle count. They
are derived from ROMs and are never committed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import referees

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "validation" / "streams"

#: The five cartridges megadrive-python's milestones are measured on, with the buttons,
#: the frames each is pressed at and the run's length: what each needs to get its sound
#: driver going. Gunstar Heroes wants Start twice -- title, then mode select.
GAMES = [
    ("Sonic The Hedgehog (USA, Europe).zip", "start", (120,), 720),
    ("Streets of Rage 2 (USA).zip", "start", (240,), 720),
    ("Gunstar Heroes (USA).zip", "start", (200, 400, 600), 1200),
    ("Castlevania - Bloodlines (USA).zip", "start", (240,), 720),
    ("Phantasy Star IV (USA).zip", "start", (240,), 720),
]

#: Nemesis's YM2612 test ROMs, each run 400 frames with Start pressed at frame 120.
TEST_ROMS = [
    "ym2612csmmode.bin",
    "ym2612ssg-eg.bin",
    "ym2612attackandrelease.bin",
    "ym2612detune.bin",
    "ym2612multiplexing.bin",
    "ym2612FrequencyWriteOrder.bin",
]


def load_image(path: Path) -> bytes:
    if path.suffix.lower() == ".zip":
        with zipfile.ZipFile(path) as archive:
            for name in archive.namelist():
                if Path(name).suffix.lower() in (".md", ".gen", ".bin", ".smd"):
                    return archive.read(name)
    return path.read_bytes()


def capture(
    image: bytes, frames: int, *, press: int, press_at: tuple[int, ...], hold: int = 8
) -> tuple[list[tuple[int, int, int]], int]:
    """Run a cartridge on the board; return the FM's writes and its final cycle count.

    Each press is held for ``hold`` frames, so that a game reading edges sees one.
    """
    from megadrive_python.cartridge import Cartridge
    from megadrive_python.machine import MACHINES
    from megadrive_python.system import System

    system = System(MACHINES["genesis"], Cartridge(image))
    board = system.board
    fm = board.fm
    fm.enabled = False
    writes: list[tuple[int, int, int]] = []
    fm_write = fm.write

    def spy(port: int, value: int) -> None:
        if not fm.in_reset:
            writes.append((fm.cycles_run, port & 3, value & 0xFF))
        fm_write(port, value)

    fm.write = spy  # type: ignore[method-assign]
    pad = board.io.ports[0].device
    for frame in range(frames):
        pressed = any(at <= frame < at + hold for at in press_at)
        pad.pressed = press if pressed else 0
        system.run_frame()
        fm.take_samples()
        board.psg.take_samples()
    return writes, fm.cycles_run


def export(name: str, image: bytes, frames: int, button: str, press_at: tuple[int, ...]) -> None:
    from megadrive_python.io import BUTTONS

    writes, cycles = capture(image, frames, press=BUTTONS[button], press_at=press_at)
    stem = Path(name).stem
    OUT.mkdir(parents=True, exist_ok=True)
    referees.write_events(OUT / f"{stem}.bin", writes)
    meta = {
        "name": name,
        "sha256": hashlib.sha256(image).hexdigest(),
        "frames": frames,
        "press": button,
        "press_at": list(press_at),
        "writes": len(writes),
        "cycles": cycles,
    }
    (OUT / f"{stem}.json").write_text(json.dumps(meta, indent=2) + "\n")
    print(f"{name}: {len(writes):,} writes over {cycles:,} cycles -> validation/streams/{stem}.bin")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--board", type=Path, required=True, help="a megadrive-python checkout")
    parser.add_argument("--roms", action="store_true", help="Nemesis's six test ROMs")
    parser.add_argument("--games", action="store_true", help="the five cartridges")
    parser.add_argument("--carts", type=Path, default=Path("/data/emu/roms/megadrive"))
    args = parser.parse_args(argv)
    sys.path.insert(0, str(args.board.resolve() / "src"))
    commit = subprocess.run(
        ["git", "-C", str(args.board), "rev-parse", "--short", "HEAD"],
        capture_output=True,
        text=True,
    ).stdout.strip()
    print(f"board: megadrive-python {commit or '(not a git checkout)'}")
    if args.roms:
        for name in TEST_ROMS:
            path = args.board / "tests" / "test_roms" / "nemesis" / name
            if not path.exists():
                print(f"{name}: missing (megadrive-python scripts/fetch_references.py)")
                continue
            export(name, path.read_bytes(), 400, "start", (120,))
    if args.games:
        for name, button, press_at, frames in GAMES:
            path = args.carts / name
            if not path.exists():
                print(f"{name}: missing")
                continue
            export(name, load_image(path), frames, button, press_at)
    return 0


if __name__ == "__main__":
    sys.exit(main())
