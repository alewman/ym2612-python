"""The conformance kit: what a port of this chip must reproduce, cycle by cycle.

Two entry points, also ``python -m ym2612_python.conformance`` (or ``ym2612-conformance``):

* :func:`trace_manifest` runs a manifest on this chip and yields the reference trace,
  one line per internal cycle and one per read.
* :func:`diff_traces` compares an external trace with the reference and returns the
  first difference, or ``None``.

The manifest and trace formats are docs/conformance.md. The module depends only on the
standard library and :mod:`ym2612_python.chip`.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import TextIO

from ym2612_python.chip import (
    IC_HOLD_PAST_RELEASE,
    MCLK_PER_CYCLE,
    YM2612,
    YM2612_DISCRETE,
    YM3438_ASIC,
    FMVariant,
)

__all__ = [
    "MANIFEST_SCHEMA_VERSION",
    "TRACE_HEADER",
    "Event",
    "Manifest",
    "TraceDifference",
    "diff_traces",
    "load_manifest",
    "main",
    "manifest_from_dict",
    "trace_manifest",
]

MANIFEST_SCHEMA_VERSION = 1
#: The first line of every trace, so a trace of another version is refused, not misread.
TRACE_HEADER = "# ym2612-trace 1"

VARIANTS: dict[str, FMVariant] = {"ym2612": YM2612_DISCRETE, "ym3438": YM3438_ASIC}
KINDS = ("write", "read", "ic")


@dataclass(frozen=True)
class Event:
    """One thing the host does to the chip, at tick ``t``.

    ``write``: ``write(port, data)``. ``read``: ``read(port)``, whose value is traced.
    ``ic``: ``reset_line(held, t, lag)``. Before an event the chip is brought to ``t``
    with ``run(t)``, which completes every internal cycle that *ends* by ``t``; so an
    event at a tick inside a cycle is seen by that cycle, the one under way.
    """

    t: int
    kind: str
    port: int = 0
    data: int = 0
    held: bool = False
    lag: int = 3

    def __post_init__(self) -> None:
        if self.kind not in KINDS:
            raise ValueError(f"unknown event kind {self.kind!r}")
        if self.t < 0 or not 0 <= self.port <= 3 or not 0 <= self.data <= 0xFF:
            raise ValueError(f"event out of range: {self}")


@dataclass(frozen=True)
class Manifest:
    """A run: the variant, the events in tick order, and how many ticks to run."""

    name: str
    variant: str
    events: tuple[Event, ...]
    ticks: int
    enabled: bool = True
    control_delay: int = 0

    def __post_init__(self) -> None:
        if self.variant not in VARIANTS:
            raise ValueError(f"unknown variant {self.variant!r} (ym2612 or ym3438)")
        if any(b.t < a.t for a, b in zip(self.events, self.events[1:], strict=False)):
            raise ValueError("events must be in tick order")
        if self.events and self.events[-1].t > self.ticks:
            raise ValueError("an event falls after the end of the run")


@dataclass(frozen=True)
class TraceDifference:
    """The first line where two traces differ (1-based), and both lines."""

    line: int
    reference: str
    external: str

    def __str__(self) -> str:
        return (
            f"traces differ at line {self.line}\n"
            f"  reference: {self.reference}\n  external:  {self.external}"
        )


def _status(chip: YM2612) -> int:
    """The status byte as the chip holds it, without a read's side effect."""
    return (chip.busy << 7) | (chip.timer_b_overflow_flag << 1) | chip.timer_a_overflow_flag


def _cycle_line(chip: YM2612) -> str:
    # ``cycles`` has already moved on to the next slot; the line names the slot the
    # cycle served, as the referee's harness numbers them.
    return f"C {(chip.cycles - 1) % 24} {chip.mol} {chip.mor} {_status(chip)} {int(chip.irq())}"


def trace_manifest(manifest: Manifest) -> Iterator[str]:
    """Run ``manifest`` on this chip, yielding the trace's lines (without newlines).

    ``C slot mol mor status irq`` after every internal cycle the chip runs; ``H slot``
    after every cycle it is held instead (/IC low, or the brief hold after an /IC
    assertion that outlasts a short pulse), ``slot`` being where its slot counter then
    stands; ``R port value`` for every read. So a port must agree on which cycles are
    held and on where /IC leaves the slot counter, as well as on every pin.
    """
    chip = YM2612(VARIANTS[manifest.variant], enabled=manifest.enabled)
    chip.control_delay = manifest.control_delay
    yield TRACE_HEADER
    yield f"# {manifest.name} {manifest.variant}"

    def advance(t: int) -> Iterator[str]:
        while chip.mclk + MCLK_PER_CYCLE <= t:
            held = chip.in_reset or bool(chip._ic_hold and IC_HOLD_PAST_RELEASE)
            chip.run(chip.mclk + MCLK_PER_CYCLE)
            yield f"H {chip.cycles}" if held else _cycle_line(chip)

    for event in manifest.events:
        yield from advance(event.t)
        if event.kind == "write":
            chip.write(event.port, event.data)
        elif event.kind == "read":
            yield f"R {event.port} {chip.read(event.port)}"
        else:
            chip.reset_line(event.held, event.t, event.lag)
    yield from advance(manifest.ticks)
    yield f"# end {chip.cycles_run} cycles {chip.writes} writes"


def diff_traces(reference: Iterable[str], external: Iterable[str]) -> TraceDifference | None:
    """The first line where ``external`` differs from ``reference``, or ``None``."""
    line = 0
    ref_iter, ext_iter = iter(reference), iter(external)
    while True:
        line += 1
        ref = next(ref_iter, None)
        ext = next(ext_iter, None)
        if ref is None and ext is None:
            return None
        ref = None if ref is None else ref.rstrip("\n")
        ext = None if ext is None else ext.rstrip("\n")
        if ref != ext:
            return TraceDifference(line, ref or "(end of trace)", ext or "(end of trace)")


def manifest_from_dict(value: object) -> Manifest:
    """A manifest from its JSON form (docs/conformance.md), strictly checked."""
    if not isinstance(value, dict):
        raise ValueError("a manifest is a JSON object")
    allowed = {"version", "name", "variant", "enabled", "control_delay", "events", "ticks"}
    unknown = set(value) - allowed
    if unknown:
        raise ValueError(f"unknown manifest keys: {sorted(unknown)}")
    if value.get("version") != MANIFEST_SCHEMA_VERSION:
        raise ValueError(f"unsupported manifest version {value.get('version')!r}")
    events = []
    for index, item in enumerate(value.get("events", [])):
        if not isinstance(item, dict):
            raise ValueError(f"event {index} is not an object")
        extra = set(item) - {"t", "kind", "port", "data", "held", "lag"}
        if extra:
            raise ValueError(f"event {index}: unknown keys {sorted(extra)}")
        events.append(Event(**item))
    return Manifest(
        name=str(value["name"]),
        variant=str(value["variant"]),
        events=tuple(events),
        ticks=int(value["ticks"]),
        enabled=bool(value.get("enabled", True)),
        control_delay=int(value.get("control_delay", 0)),
    )


def load_manifest(path: str | Path) -> Manifest:
    return manifest_from_dict(json.loads(Path(path).read_text(encoding="utf-8")))


def main(argv: list[str] | None = None, *, stdout: TextIO | None = None) -> int:
    """``trace`` writes the reference trace; ``diff`` reports the first difference.

    Exit status: 0 on success or equal traces, 1 on a difference, 2 on bad input.
    """
    out = stdout or sys.stdout
    parser = argparse.ArgumentParser(prog="ym2612-conformance", description=main.__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    trace_cmd = commands.add_parser("trace", help="write the reference trace of a manifest")
    trace_cmd.add_argument("manifest")
    trace_cmd.add_argument("--out", help="file to write (default: stdout)")
    diff_cmd = commands.add_parser("diff", help="compare an external trace with the reference")
    diff_cmd.add_argument("manifest")
    diff_cmd.add_argument("trace", help="trace path, or '-' for stdin")
    args = parser.parse_args(argv)
    try:
        manifest = load_manifest(args.manifest)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"error: {exc}", file=out)
        return 2
    if args.command == "trace":
        lines = trace_manifest(manifest)
        if args.out:
            with open(args.out, "w", encoding="utf-8") as handle:
                for line in lines:
                    handle.write(line + "\n")
        else:
            for line in lines:
                out.write(line + "\n")
        return 0
    try:
        handle = sys.stdin if args.trace == "-" else open(args.trace, encoding="utf-8")  # noqa: SIM115
    except OSError as exc:
        print(f"error: {exc}", file=out)
        return 2
    with handle:
        difference = diff_traces(trace_manifest(manifest), handle)
    if difference is None:
        print(f"{manifest.name}: traces are identical", file=out)
        return 0
    print(f"{manifest.name}: {difference}", file=out)
    return 1


if __name__ == "__main__":
    sys.exit(main())
