# Validation: the oracles, ranked, and what was run

## The tier rule

Oracles rank by where their expected values came from:

1. **hardware-captured**: measured on a real chip;
2. **hardware-corrected**: written against hardware and fixed until it agreed;
3. **die-derived**: a transcription of the chip's silicon from die photographs;
4. **emulator-derived**: another emulator's output;
5. **documentation**.

A lower tier is used as a judge only where nothing above it covers the question. For
the YM2612's arithmetic nothing above die-derived exists: there is no YM2612
datasheet, no self-checking FM test program, and no capture of the DAC pins. That is
exactly the case the rule reserves for a die-derived judge. The recordings judge what
they reach through an analogue path. This is the family's rule, as megadrive-python
states it.

## The oracles

| Oracle | Tier | Role | Pinned |
| --- | --- | --- | --- |
| **Nuked-OPN2** (nukeykt), the YM3438 transcribed from its die, with a YM2612 output mode | die-derived | **the judge**: every internal cycle of MOL, MOR and status, both modes | `reference/src/Nuked-OPN2` @ 335747d, LGPL-2.1, built locally as `opn2_ref` |
| **YM2608-LLE** (nukeykt), `fmopna_2612.c`, the NMOS YM2612 from HardWareMan's die shot | die-derived | a detector for the discrete chip's output stage | `reference/src/YM2608-LLE` @ 7a2aca7, GPL-2.0, built locally as `lle2612_ref` |
| **Nuked-MD** (nukeykt et al.), the whole Mega Drive from its dies | die-derived | the /IC constants and the timer delay, measured through megadrive-python's board | megadrive-python `reference/src/Nuked-MD` @ 594ca2a |
| **Eke's BUSY measurements** (forum t=386 start=810) | hardware-captured | BUSY's length; which ports read it | cited |
| **Nemesis's MD1600 SSG-EG recording** | hardware-captured | SSG-EG's shapes and periods, by measurement | megadrive-python `tests/test_roms/nemesis` |
| **Aly James's `MD1_LADDER.wav`** | hardware-captured | the ladder's shape | megadrive-python `tests/test_roms/aly-james` |

The referees are fetched by `scripts/fetch_references.py` and built by
`sh validation/build_referees.sh`. They are never committed. The harnesses in
`validation/*.c` drive them and copy nothing. Their sources are read and cited by
file and line in `src/ym2612_python/chip.py`, never copied.

## Certification record

### The Nuked-OPN2 rung: every cycle, zero differences

`ym2612-python` at **92c9eaf**, CPython 3.14.4, gcc 15.2.0, run on 2026-10-11.
Nemesis's six test ROMs and five cartridges, as megadrive-python's board
(`efcc6bb`) fed them to its chip, exported by `scripts/export_board_streams.py`.

Every value of both DAC pins and of the status byte, on every internal cycle, in
both output modes against the matching variant:

| Streams | Internal cycles each variant | Result |
| --- | --- | --- |
| 7 synthetic: two random walks (4,000 writes each), channel 3's special mode and CSM, SSG-EG's eight shapes, the LFO at 8 speeds × 8 PMS × 4 AMS, both timers, the DAC | 6,124,839 | **identical** |
| Nemesis's six test ROMs: CSM, SSG-EG, attack and release, detune, multiplexing, frequency write order | 17,392,067 | **identical** |
| Five cartridges: Sonic the Hedgehog, Streets of Rage 2, Gunstar Heroes, Castlevania Bloodlines, Phantasy Star IV (5,500 to 133,630 port writes each) | 86,985,619 | **identical** |
| **All 18** | **110,502,525** | **663,015,150 values compared, 0 different** |

Commands:
```text
python scripts/fetch_references.py && sh validation/build_referees.sh
python scripts/run_fm_streams.py                       # synthetic, 7 streams
python scripts/export_board_streams.py --board ../megadrive-python --roms --games
python scripts/run_fm_streams.py --streams --only "<name>"   # one per stream, in parallel
```

The synthetic streams were also run on PyPy 7.3.20 at ebf5200: identical.

megadrive-python recorded the same comparison at 383992c, on its own board-embedded
chip: 524,264,898 values, 0 different. Today's streams are longer because the board
runs further now.

### The examples against Nuked-OPN2

The conformance examples' traces are checked against the referee too, not just
against this chip. `tests/test_conformance.py` replays every example Nuked-OPN2 can
model (generator on, no /IC, no timer delay) through `opn2_ref` and compares every
`C` line: 10 of the 13, identical.

### YM2608-LLE: a detector, with its differences classified

YM2608-LLE is a pin-level model at MCLK / 7 of the NMOS YM2612's own die. It cannot
be matched cycle for cycle, for two reasons megadrive-python measured and its owner
accepted on 2026-09-22 ("accepted as characterised, not chased"):

1. **A real difference.** The two die models place a channel's value differently
   among its four DAC cycles. LLE drives it first, then the sign on three. Nuked-OPN2
   drives the sign on three, then the value last. The 24 values of a sample are the
   same multiset either way. This core follows Nuked-OPN2 (see
   [claims.md](claims.md), Contested).
2. **A harness artefact.** `lle2612_ref` holds /CS and /WR low for 16 chip clocks,
   while Nuked latches an edge, so a write can land one internal cycle apart in the
   two.

So the comparison is made at the native sample rate, with one phase and one
whole-sample lag fitted. The result at this repository's commit is in
[the YM2608-LLE run](#the-ym2608-lle-run) below.

#### The YM2608-LLE run

`python scripts/run_fm_streams.py --lle`, at 92c9eaf, CPython 3.14.4. Each model's DAC
is summed over a sample, and one phase and one whole-sample lag are fitted per
stream:

| Stream | Samples differing at the native rate |
| --- | --- |
| SSG-EG, all eight shapes | **0** |
| both timers | **0** |
| the DAC | **0** |
| channel 3's special mode and CSM | 1 of 16,447 (0.01%) |
| the LFO, 8 × 8 × 4 (292 writes) | 3,111 of 102,690 (3.03%) |
| random walk, seed 1 (a write every 63 cycles on average) | 7,179 of 20,938 (34%) |
| random walk, seed 2 | 4,351 of 20,853 (21%) |

This is the pattern megadrive-python characterised. The streams written rarely are
identical. The densely written ones differ in bursts around writes, which the two
harnesses land a cycle apart, and then re-converge. The LFO stream reads 3.03% here
against 1.63% there because the board compared only its first 20,000 samples; this
run compares the whole stream.

### The recordings

- **The ladder** (`python scripts/run_fm_streams.py --ladder <MD1_LADDER.wav>`, at
  92c9eaf): one operator's total level walked from 0 to 127. The discrete variant's
  level stops falling 36-37 dB below its peak, Aly James's Model 1 at 33 dB, and the
  ASIC variant does not plateau (49 dB). The two ramps are differently made, so this
  is the shape, not a number:

  ```text
  discrete YM2612   0.0  -9.7 -18.5 -27.2 -34.0 -36.1 -37.1 -37.0 -40.4  -inf  -inf
  ASIC YM3438       0.0  -9.8 -18.7 -28.2 -37.9 -46.1 -49.0 -48.9 -52.4  -inf  -inf
  MD1_LADDER.wav    0.0  -9.5 -18.2 -25.7 -30.7 -32.8 -32.8 -33.0 -42.6 -61.1 -61.2
  ```
- **SSG-EG** against Nemesis's MD1600 recording is a measurement through a whole
  console's analogue path. It was made on megadrive-python's board
  (`scripts/run_ssg_eg.py`) and is not repeated here. Every note length agrees within
  one 50 ms block, every repetition period is identical, and the notes start 1.0-1.2%
  further apart on the MD1600, a rate difference accepted as the recorder's or the
  crystal's.

### The /IC constants and the timer delay

The core carries these from megadrive-python's measurements on Nuked-MD, each swept
through every position with a test cartridge on the whole console. The sweeps need
the board, so they stay there:
- `scripts/run_fm_ic.py`: where /IC restarts or pauses the slot counter, at four
  pulse lengths, and `--short` for the hold outlasting a short pulse.
- `scripts/run_fm_busy.py`: when BUSY clears after a data write.
- `scripts/run_fm_timer.py`: the Timer A flag under the two-cycle $27 delay.

`tests/test_chip.py` pins the outcomes, and the conformance example
`ic-pulses-ym2612` puts /IC at all 42 ticks of a cycle.

### Coverage

`coverage run --branch` over the fast suite (`pytest -m "not referee"`: the rules, the
tables, the thirteen examples) at this commit: **99% of `chip.py`'s statements, 98%
with branches**. What it does not reach:
- the test read's channel-accumulator form;
- a re-key while an envelope is still in attack;
- a sample owed while the hold outlasts a short /IC pulse;
- the operator's level clamp at 0x1FFF.

The clamp is unreachable: `LOG_SIN` peaks at 2,137 and an envelope at 4,092, which
sum to less. The die has the clamp, so the code keeps it.

### Seeded faults

`python scripts/mutation.py` breaks one rule at a time, 33 in all: BUSY, the timers,
pans, the ladder, the DAC, the multiplier, the sustain level, $A4, feedback, detune,
the LFO, SSG-EG, rate 31, CSM, channel 3's mode, the accumulator clamp, the status
decay and ports, /IC, the timer delay, and the log-sin table.
- **Examples plus the rule tests:** 33 caught.
- **Examples alone,** which is all a port has (`--examples-only`): 32 caught. The
  status decay needs 300,000 cycles without a read, too long for a committed trace.

Two of the 33 came from ym2612-rust's own seeded faults (2026-10-11): the slowest
LFO speed's reload and the order of key-on's operators 2 and 3. Until the examples
`lfo-slowest-ym2612` and `key-on-operators-ym3438` were added, a port that stopped at
the examples would have missed both; the synthetic streams always caught them.

### Speed

`python benchmarks/bench.py` at e3672d6. It runs the first seconds of the seed-1
random walk through `run()`, as a board does, best of three. The machine was shared,
with a load average of about 23 on 32 threads.

| Interpreter | Generator on | Quiet path (`enabled=False`) |
| --- | --- | --- |
| CPython 3.14.4 | 133,022 cycles/s, **0.104× real time** | 541,174 cycles/s, 0.423× |
| PyPy 7.3.20 (3.11.13) | 35,586 cycles/s, **0.028×** | 161,117 cycles/s, 0.126× |

Real time is 1,278,409 internal cycles a second (NTSC). PyPy runs *slower* than
CPython here. Its JIT gains only 2.2× over its own interpreter (16,520 cycles/s with
`--jit off`), and a larger trace limit makes it slower still (4,263 cycles/s at
`trace_limit=200000`). The one-cycle body is long and branchy, which this
interpreter's JIT handles badly. This is a reference core and correctness is the
goal; speed belongs to ym2612-rust and its `-fast` fork, measured against these
numbers.

## What is not available

- No capture of the DAC pins on real hardware, so the multiplexing order is
  die-derived and the two die models disagree on it.
- No self-checking FM test program.
- No hardware measurement of /IC's effect on the slot counter. Nuked-MD is the
  closest available.
