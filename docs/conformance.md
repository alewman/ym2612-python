# Conformance: proving another core is the same chip

This page is for someone writing a YM2612 core in another language, ym2612-rust
first, who wants to use this one as the reference. It covers three things: what
"the same chip" means here, the manifest and trace formats, and what a port may
claim after each rung. The tooling is `ym2612_python.conformance`. The shape is the
family's: z80-python's and m68000-python's kits certified z80-rust and m68000-rust.

## What must match

On every internal cycle, all of:

- whether the chip **ran or was held** (under /IC);
- the **slot** it served, or, when held, where its slot counter stands;
- both **DAC pins**, MOL and MOR, exactly as `mol`/`mor` hold them (the YM2612's ×3
  included);
- the **status byte** as the chip holds it (BUSY, timer B, timer A), with no read
  side effect;
- the **/IRQ** pin.

On every read, the **value returned**, including the decay of the driven value and
the discrete chip's silence on ports 1-3.

The two ROM tables, which a port checks by hash ([contract.md](contract.md), "The
tables").

## The manifest

```json
{
  "version": 1,
  "name": "status-reads-ym2612",
  "variant": "ym2612",
  "enabled": true,
  "control_delay": 0,
  "ticks": 387839,
  "events": [
    {"t": 336, "kind": "write", "port": 0, "data": 36},
    {"t": 840, "kind": "write", "port": 1, "data": 255},
    {"t": 1557, "kind": "read", "port": 1},
    {"t": 99437, "kind": "ic", "held": true, "lag": 3}
  ]
}
```

| Key | Meaning |
| --- | --- |
| `variant` | `ym2612` (`YM2612_DISCRETE`) or `ym3438` (`YM3438_ASIC`). |
| `enabled` | The generator switch (default `true`). |
| `control_delay` | Register $27's timer delay in cycles (default 0). |
| `ticks` | Run to this tick. |
| `events` | In tick order. `write` (`port`, `data`) and `read` (`port`) are the ports. `ic` (`held`, `lag`, default 3) is `reset_line(held, t, lag)`. Before each event the chip is run to its `t`. |

Seven ticks are one input clock and 42 one internal cycle. An event at a tick inside
a cycle is seen by the cycle under way, because `run(t)` completes only the cycles
that end by `t`.

## The trace

Plain text, one record per line:

```text
# ym2612-trace 1
# status-reads-ym2612 ym2612
C 0 3 3 0 0          a cycle ran: slot, mol, mor, status, irq
R 1 0                a read: port, value
H 17                 a cycle held under /IC: where the slot counter now stands
# end 9234 cycles 102 writes
```

The header line names the format version; a trace of another version is refused
rather than misread. Lines starting `#` other than the header are comments, but they
are compared too, so a port writes them exactly. A port writes its trace in this
form and runs:

```text
python -m ym2612_python.conformance diff manifest.json port.trace
```

which reports `traces are identical` (exit 0) or the first differing line with both
versions (exit 1). `python -m ym2612_python.conformance trace manifest.json` writes
the reference trace.

## The examples

`examples/conformance/` holds fifteen manifests with their reference traces, written by
`scripts/make_examples.py`. `tests/test_conformance.py` checks two things. First,
that this chip still writes every trace. Second, with the referee built, that the
twelve examples Nuked-OPN2 can model (generator on, no /IC, no timer delay) agree with
it on every `C` line. The examples are therefore themselves referee-checked, not
just this chip's say-so.

| Manifest | Aimed at |
| --- | --- |
| `random-walk-ym2612`, `random-walk-ym3438` | every register, both output stages, 250 writes each |
| `voices-ym2612`, `voices-ym3438` | six sounding channels: every algorithm and feedback, both detune signs, a multiplier of 0, a sustain level of 15, every pan, LFO AM and PM at two speeds, channel 3's own frequencies, an accumulator that clamps |
| `corners-ym2612`, `corners-ym3438` | the LSI test registers $21 and $2C (and the test read), the SSG's absent $00-$0F, key-on bytes naming no channel, re-keys, reads on every port |
| `dac-ym2612` | the DAC enable, a value ramp, the ninth bit |
| `ssg-eg-ym3438` | SSG-EG's eight shapes |
| `lfo-slowest-ym2612` | the LFO's slowest speed (its counter reload of 108), PMS 7 and AMS 3, and a switch to the next speed and back |
| `key-on-operators-ym3438` | each of $28's operator bits alone and in pairs, on four carriers at different multipliers: which operator each bit keys (the slots run 1, 3, 2, 4) |
| `status-reads-ym2612`, `status-reads-ym3438` | BUSY and both timer flags read on every port at ticks inside cycles (the variants differ on ports 1-3) |
| `timer-control-delay-ym2612` | the same with register $27 delayed two cycles (megadrive-python's die-figures machine) |
| `ic-pulses-ym2612` | /IC asserted at all 42 ticks of a cycle, both lags, pulses of 1, 3, 10 and 60 cycles, a write ignored while held |
| `quiet-timers-ym3438` | the quiet path: timers, flags and reads with the generator off |

## Certification ladder for a port

| Rung | What | Claim after it |
| --- | --- | --- |
| 1 | The two tables' SHA-256 equal [contract.md](contract.md)'s | the ROMs are the chip's |
| 2 | Every example in `examples/conformance/` diffs identical | the pins, /IC and the reads, on the examples |
| 3 | The seven synthetic streams of `scripts/run_fm_streams.py` as manifests, identical, both variants (about 5.6 M cycles each) | equivalent to this core over the synthetic streams, and therefore equal to Nuked-OPN2 on them |
| 4 | The exported board streams (Nemesis's six test ROMs, five cartridges) as manifests, identical | equivalent on real drivers' register traffic |
| 5 | Seeded random manifests with /IC and reads in lockstep, both variants | equivalence where no fixed stream reaches |

Rung 3 and up do not need a port to talk to the referee. Equivalence to this core
and this core's equality to Nuked-OPN2 ([validation.md](validation.md)) compose.

## What this does not cover

- The **analogue path**: filtering, the ladder's audible depth, mixing. Those are
  the board's.
- **Bus timing**: when a host's access reaches the chip is the host's (the `lag`,
  the arbiter).
- The **test registers** ($21, $2C) beyond what the random walks write. Nemesis's
  test ROMs use some of them, through rung 4.
