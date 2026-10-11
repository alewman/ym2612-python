# The contract: the chip's pins, as this core has them

This is what a host can rely on and what a port must reproduce. Everything here is
checked by `tests/` or by the conformance kit ([conformance.md](conformance.md));
how strongly each behaviour is known is [claims.md](claims.md).

## One chip, two variants

```python
from ym2612_python import YM2612, YM2612_DISCRETE, YM3438_ASIC

chip = YM2612(YM2612_DISCRETE)  # or YM3438_ASIC
chip = YM2612(YM3438_ASIC, enabled=False)  # the quiet path, below
```

The variant is a constructor argument, an `FMVariant` with two fields. A variant is
a value, not a subclass, so a host can build its own.

| Field | `YM2612_DISCRETE` (NMOS YM2612) | `YM3438_ASIC` (the YM3438-like core) | Evidence |
| --- | --- | --- | --- |
| `busy_on_all_ports` | `False`: the status reads on port 0 only | `True`: on every port | Eke's counting program on a VA4 Model 1 and a VA0 Model 2 (hardware-captured) |
| `ladder` | `True`: the DAC's crossover step, the value ×3 | `False` | HardWareMan's oscilloscope traces, Aly James's recording (hardware-captured); the model is Nuked-OPN2's YM2612 mode |

## Time

The chip runs from one input clock (φM). On the Mega Drive that is MCLK / 7, about
7.67 MHz. The chip divides φM by 6 into its **internal cycle**, and 24 internal
cycles make one output sample.

The core counts time in **ticks**, and **seven ticks are one input clock**. On the
Mega Drive a tick is the master clock, so `run(mclk)` takes the board's own count.
A host whose chip has its own oscillator counts seven ticks per input clock.

| Unit | Ticks |
| --- | --- |
| input clock (φM) | 7 |
| internal cycle (`MCLK_PER_CYCLE`) | 42 |
| output sample (`CYCLES_PER_SAMPLE` cycles) | 1,008 |

The tick is finer than the input clock for one reason: where an /IC assertion falls
inside a slot was measured on Nuked-MD to the master clock, and some of those
constants are not whole input clocks (below).

- **`run(t)`** completes every internal cycle that *ends* by tick `t`. A remainder
  waits for the next call. `mclk` is the tick the next cycle starts at, and
  `cycles_run` counts the cycles run since power-on.
- **The host owns the conversion.** It brings the chip up to the moment of each port
  access with `run(t)` before calling `write`, `read` or `reset_line`. An access at
  a tick inside a cycle is therefore seen by the cycle under way.
- A host may set `mclk` once, before the first `run`, to place the chip's divider
  against its own clock. megadrive-python does this for its power-on phase.

## The pins

| Pin | API | Behaviour |
| --- | --- | --- |
| A1, A0, D7-D0, /WR | `write(port, value)` | Ports 0 and 2 latch an address in part I or part II; ports 1 and 3 latch data. The write is taken up by the next internal cycle, and a register changes only when its slot comes round. Ignored while /IC is held. |
| /RD | `read(port)` -> int | The status byte: bit 7 BUSY, bit 1 timer B, bit 0 timer A. The discrete chip answers only on port 0; on the other ports it returns its last driven value, decayed. What an undriven bus reads is the host's business (the Mega Drive's 68000 sees its prefetch). The driven value decays to 0 after 300,000 cycles without a read on the YM2612, 40,000,000 on the YM3438. |
| /IC | `reset_line(held, t, lag)` | See below. |
| /IRQ | `irq()` -> bool | Either timer's overflow flag. The Mega Drive leaves it unconnected. |
| MOL, MOR | `mol`, `mor` | The two DAC pins after the cycle just run, with the six channels multiplexed four cycles each. YM2612: the value on one cycle of the four and the sign on three, all ×3. YM3438: the value on three and 0 on one. |
| (sample) | `take_samples()` -> list | One `(left, right)` per 24 cycles: that sample's 24 MOL and MOR values summed. These are what a mixer averages; the analogue filter belongs to the board. |

### /IC

`reset_line(held, t, lag)` asserts or releases /IC at tick `t`.

**Asserting it** resets every register, envelope and phase. It does not reset the
sample queue: samples already made belong to the host. It also restarts the clock
divider from `t`.

The slot counter is either restarted at 0 or only paused, depending on where in the
slot /IC is *sampled*:
- **`lag`** is the number of ticks between `t` and the moment /IC reaches the chip.
  It is a property of the board's wiring, so the board supplies it.
- megadrive-python passes 3 for the reset button and 0 for a write to $A11200. Those
  are the lags `IC_SLOT_LAG` and the measured constants were fitted with. `lag`
  defaults to `IC_SLOT_LAG`, the button's.

The chip then stands still for `IC_FSM_HOLD` (3) cycles. It stays still for all of
them even if /IC is released sooner (`IC_HOLD_PAST_RELEASE`). After that the slot
counter runs on while /IC stays low, the outputs silent and owing zero samples.
**Releasing it** resets nothing.

The constants are die-derived. They come from Nuked-MD measured through every
position (megadrive-python `scripts/run_fm_ic.py`, `docs/worklog.md` "The FM's
restart" and "The busy flag").

## Switches

- **`enabled`** (constructor, default `True`): with it off, the chip runs the bus,
  the register file, the timers, BUSY and key-on, and nothing else (`_quiet_cycle`).
  `mol` and `mor` stay 0 and the samples are silent. A game polling BUSY or the
  timers sees what it would. Turning it back on mid-run resumes from stale envelopes
  and phases, so set it once.
- **`control_delay`** (attribute, default 0): register $27's timer bits take effect
  this many cycles late. megadrive-python sets 2 (`TIMER_CONTROL_DELAY_CYCLES`) on
  its die-figures machine, where Nuked-MD's Timer A flag rises in all 325 loads of a
  swept test cartridge. Nuked-OPN2 has no such delay, so the referee comparison runs
  with 0.

## The tables

The chip's two ROMs are generated, not transcribed:
- **`LOG_SIN`:** `round(-log2(sin((i + 0.5) * pi / 512)) * 256)`, the quarter sine
  in the log domain, 12 bits.
- **`EXP`:** `round((2 ** (i / 256) - 1) * 1024)`, 10 bits.

Both are 256 entries. A port must produce the same integers. It checks this with the
SHA-256 of each table packed as 256 little-endian unsigned 16-bit integers:

| Table | SHA-256 |
| --- | --- |
| `LOG_SIN` | `a099b16dd3aa2f56cabc1fee590db31ee412ee361da4f0c67497092cf57c4776` |
| `EXP` | `a0ca448cb3178dd131cd23425b2adc8ee155d1905f2fa083d570954a47f3ede0` |

No entry is near a rounding boundary. The closest are `LOG_SIN[15]`, 3.1 × 10⁻⁴
from .5, and `EXP[191]`, 7.5 × 10⁻⁴. A libm within a few ulps cannot round
differently, but the hash is what a port proves. Both tables also equal the ones
read off the YM3438's die, entry for entry (`ym3438.c` `logsinrom`, `exprom`;
`tests/test_chip.py`, with Nuked-OPN2 fetched).

## What belongs to the board, not the chip

- **Where an access lands in time.** The bus arbitration, the 68000's and Z80's
  waits, and when /IC reaches the pin (the `lag` the board passes). In
  megadrive-python these are `IC_SLOT_LAG`, `IC_WRITE_SLOT_LAG`, and the
  `M68K_FM_WRITE_MCLK` and `M68K_FM_READ_MCLK` offsets.
- **What an undriven read returns.**
- **Mixing with the PSG, resampling, and the analogue filter** (megadrive-python's
  `audio.py`).
- **Which variant a console model has.**

## Stability

Before 1.0 the public surface is the package exports, the `YM2612` methods and
attributes named above, and the conformance manifest and trace formats. The private
pipeline state (`eg_*`, `pg_*`, `fm_*` and the rest) is readable, so a debugger or
test may look at it, but it is not a contract and may change shape.
