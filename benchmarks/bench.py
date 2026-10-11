#!/usr/bin/env python
"""How fast this chip runs: internal cycles per second, and the fraction of real time.

    python benchmarks/bench.py [--seconds 2] [--repeat 3]

Runs the first ``--seconds`` of emulated time of the seed-1 random walk
(scripts/run_fm_streams.py) through ``run()``, as a board drives the chip, with the
generator on and then off (the quiet path). Real time is 7,670,454 / 6 = 1,278,409
internal cycles a second (NTSC: MCLK 53,693,175 / 42). Reports the best of
``--repeat`` runs, since the machine is shared.
"""

from __future__ import annotations

import argparse
import platform
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import run_fm_streams

from ym2612_python import YM2612, YM2612_DISCRETE
from ym2612_python.chip import MCLK_PER_CYCLE

REAL_TIME = 53_693_175 / MCLK_PER_CYCLE


def run(events, cycles: int, enabled: bool) -> float:
    chip = YM2612(YM2612_DISCRETE, enabled=enabled)
    started = time.perf_counter()
    for cycle, port, data in events:
        if cycle >= cycles:
            break
        chip.run(cycle * MCLK_PER_CYCLE)
        chip.write(port, data)
    chip.run(cycles * MCLK_PER_CYCLE)
    chip.take_samples()
    return time.perf_counter() - started


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--seconds", type=float, default=2.0)
    parser.add_argument("--repeat", type=int, default=3)
    args = parser.parse_args()
    cycles = int(REAL_TIME * args.seconds)
    events = run_fm_streams.stream_random(1, 40_000)
    print(f"{platform.python_implementation()} {platform.python_version()}, {cycles:,} cycles")
    for label, enabled in (("generator on", True), ("quiet path", False)):
        best = min(run(events, cycles, enabled) for _ in range(args.repeat))
        rate = cycles / best
        print(
            f"  {label:13s} {rate:12,.0f} cycles/s  {rate / REAL_TIME:6.3f}x real time"
            f"  ({best:.2f} s)"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
