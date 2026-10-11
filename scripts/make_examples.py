#!/usr/bin/env python
"""Write the example manifests in examples/conformance/ and their reference traces.

    python scripts/make_examples.py

Each manifest is short enough to commit with its trace and aimed at one part of the
contract (docs/conformance.md, "The examples"). The traces are this chip's, at the
commit that wrote them; tests/test_conformance.py checks the chip still writes them,
and, with the referee built, checks every ``C`` line against Nuked-OPN2.
"""

from __future__ import annotations

import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import run_fm_streams

from ym2612_python.chip import MCLK_PER_CYCLE
from ym2612_python.conformance import manifest_from_dict, trace_manifest

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "examples" / "conformance"
TICK = MCLK_PER_CYCLE


def _writes(stream: list[tuple[int, int, int]], scale: int = 1) -> list[dict]:
    """A run_fm_streams stream (internal cycles) as write events at cycle starts."""
    return [
        {"t": cycle * scale * TICK, "kind": "write", "port": port, "data": data}
        for cycle, port, data in sorted(stream)
    ]


def _write(events: list[dict], t: int, register: int, value: int) -> int:
    part = 2 if register >= 0x100 else 0
    events.append({"t": t, "kind": "write", "port": part, "data": register & 0xFF})
    events.append({"t": t + 12 * TICK, "kind": "write", "port": part + 1, "data": value & 0xFF})
    return t + 24 * TICK


def random_walk(seed: int, count: int) -> list[dict]:
    return _writes(run_fm_streams.stream_random(seed, count))


def dac() -> list[dict]:
    stream = [e for e in run_fm_streams.stream_dac() if e[0] < 24 * 120]
    return _writes(stream)


def ssg_eg_short() -> list[dict]:
    events: list[dict] = []
    t = 8 * TICK
    for register, value in (
        (0x30, 0x01), (0x40, 0x00), (0x50, 0x1F), (0x60, 0x1C), (0x70, 0x1C), (0x80, 0xFF),
        (0xB0, 0x07), (0xB4, 0xC0), (0xA4, 0x22), (0xA0, 0x69),
    ):  # fmt: skip
        t = _write(events, t, register, value)
    for shape in range(8):
        t = _write(events, t, 0x90, 0x08 | shape)
        t = _write(events, t, 0x28, 0xF0)
        t += 24 * 150 * TICK
        t = _write(events, t, 0x28, 0x00)
        t += 24 * 30 * TICK
    return events


def status_reads() -> list[dict]:
    """BUSY after data writes, both timers' flags, read on every port, at odd ticks."""
    events: list[dict] = []
    t = 8 * TICK
    for register, value in ((0x24, 0xFF), (0x25, 0x00), (0x26, 0xFE), (0x27, 0x3F)):
        t = _write(events, t, register, value)
        events.extend(
            {"t": t + offset, "kind": "read", "port": (offset // TICK) & 3}
            for offset in range(0, 40 * TICK, 5 * TICK + 3)
        )
        t += 40 * TICK
    for _ in range(40):
        t += 24 * 9 * TICK + 17
        events.extend({"t": t + port, "kind": "read", "port": port} for port in range(4))
    t = _write(events, t, 0x27, 0x30)
    events.extend({"t": t + 50 * TICK + port, "kind": "read", "port": port} for port in range(4))
    return events


def ic_pulses() -> list[dict]:
    """/IC asserted at every tick of a cycle with both lags, long and short pulses."""
    rng = random.Random(7)
    events: list[dict] = []
    t = 8 * TICK
    for register, value in ((0xB0, 0x07), (0xB4, 0xC0), (0xA4, 0x22), (0xA0, 0x69)):
        t = _write(events, t, register, value)
    for position in range(42):
        t = _write(events, t, 0x28, 0xF0)
        t += 24 * 4 * TICK + position
        lag = 0 if position % 2 else 3
        length = rng.choice((TICK, 3 * TICK, 10 * TICK, 60 * TICK))
        events.append({"t": t, "kind": "ic", "held": True, "lag": lag})
        events.append({"t": t + 20, "kind": "write", "port": 0, "data": 0x28})  # ignored
        events.append({"t": t + length, "kind": "ic", "held": False, "lag": lag})
        t += length + 24 * 3 * TICK - position
    return events


def quiet_timers() -> list[dict]:
    """The quiet path: registers, timers and BUSY only, with the generator off."""
    events: list[dict] = []
    t = 8 * TICK
    for register, value in ((0x24, 0xFC), (0x25, 0x00), (0x26, 0xFE), (0x27, 0x3F)):
        t = _write(events, t, register, value)
    for index in range(60):
        t += 24 * 3 * TICK + 11
        events.append({"t": t, "kind": "read", "port": index & 3})
        if index % 10 == 9:
            t = _write(events, t, 0x27, 0x3F)  # reset both flags, keep both running
    return events


MANIFESTS = [
    ("random-walk-ym2612", "ym2612", lambda: random_walk(3, 250), {}),
    ("random-walk-ym3438", "ym3438", lambda: random_walk(4, 250), {}),
    ("dac-ym2612", "ym2612", dac, {}),
    ("ssg-eg-ym3438", "ym3438", ssg_eg_short, {}),
    ("status-reads-ym2612", "ym2612", status_reads, {}),
    ("status-reads-ym3438", "ym3438", status_reads, {}),
    ("timer-control-delay-ym2612", "ym2612", status_reads, {"control_delay": 2}),
    ("ic-pulses-ym2612", "ym2612", ic_pulses, {}),
    ("quiet-timers-ym3438", "ym3438", quiet_timers, {"enabled": False}),
]


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    for name, variant, build, extra in MANIFESTS:
        events = sorted(build(), key=lambda e: e["t"])
        ticks = events[-1]["t"] + 24 * 10 * TICK
        document = {
            "version": 1,
            "name": name,
            "variant": variant,
            **extra,
            "ticks": ticks,
            "events": events,
        }
        manifest = manifest_from_dict(document)
        path = OUT / f"{name}.json"
        path.write_text(json.dumps(document, indent=1) + "\n", encoding="utf-8")
        lines = list(trace_manifest(manifest))
        (OUT / f"{name}.trace").write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(f"{name}: {len(events)} events, {ticks:,} ticks, {len(lines):,} trace lines")
    return 0


if __name__ == "__main__":
    sys.exit(main())
