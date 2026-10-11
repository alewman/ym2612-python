# Claims: what this core claims, how strongly, and where it stops

The YM2612 has no datasheet beyond Yamaha's register manual, and no self-checking
test program. Two transcriptions of real dies exist: Nuked-OPN2 (the YM3438) and
YM2608-LLE (the NMOS YM2612). So the strongest judge of the chip's arithmetic is
**die-derived**. Hardware captures exist only for a few behaviours, and recordings
judge only what can be measured through an analogue path. Each behaviour below
carries a status set by the best evidence that reaches it; where the evidence runs
out, this page says so. The evidence itself is [validation.md](validation.md).

## The strands of evidence

| Lineage | Sources | Tier | Reach |
| --- | --- | --- | --- |
| **Real Mega Drives** | Eke's BUSY counting program (VA4 Model 1, VA0 Model 2); HardWareMan's DAC oscilloscope traces; Aly James's ladder recording; Nemesis's MD1600 SSG-EG recording | hardware-captured | BUSY's length and ports; that the discrete DAC has a crossover step; SSG-EG's shapes and periods (by measurement through the analogue path) |
| **The YM3438's die** | Nuked-OPN2 @ 335747d, run as a referee | die-derived | every internal cycle of both DAC pins and the status byte, both output modes; the two ROM tables entry for entry |
| **The NMOS YM2612's die** | YM2608-LLE @ 7a2aca7, `fmopna_2612.c`, run as a referee | die-derived (a detector here) | the discrete chip's output stage at the native sample rate |
| **The Mega Drive's die** | Nuked-MD, through megadrive-python's swept test cartridges | die-derived | where /IC lands in a slot, the hold after it, register $27's delay on the die-figures machine |
| **Yamaha** | the register manual (via the Sega and community documents megadrive-python pins) | documentation | the register map |
| **The suite itself** | the tests, the conformance examples, the seeded faults | not an oracle | shows a gate would notice a wrong value |

Agreement counts once per lineage. The two Nuked transcriptions are separate dies
transcribed separately.

## Status levels

| Status | Meaning |
| --- | --- |
| **Verified** | Hardware-captured evidence covers it and the core matches. |
| **Strong** | A die-derived model agrees on every cycle over broad streams, and nothing closer to silicon disagrees. |
| **Provisional** | One die-derived lineage or one measurement supports it, over a narrow domain. |
| **Contested** | Credible sources disagree; the core's choice is named. |
| **Undecidable here** | Nothing available tells the candidates apart. |
| **Outside the contract** | Not claimed, by decision. |

## The claims

### Verified

- **BUSY lasts 32 internal cycles after a data write, and an address write does not
  set it.** Eke's counting program on hardware; `tests/test_chip.py`.
- **The discrete chip's status reads on port 0 only; the ASIC's on every port.**
  Eke; the variant field.

### Strong

- **Every internal cycle of MOL, MOR and the status byte**, both variants, over the
  seven synthetic streams (every register, channel 3's mode, CSM, SSG-EG, the LFO at
  every speed and depth, both timers, the DAC) and over the register traffic of
  Nemesis's six test ROMs and five cartridges, equals Nuked-OPN2. The numbers are in
  [validation.md](validation.md).
- **The two ROM tables** equal the die's, entry for entry. Ports pin them by hash.
- **The discrete chip's output stage at the native sample rate** equals YM2608-LLE's
  on the SSG-EG, timer and DAC streams. A second die agrees where the harnesses can
  be compared (see Contested).

### Provisional

- **SSG-EG against hardware.** Nemesis's MD1600 recording and the core agree on
  every note length (within one 50 ms block) and every repetition period. The notes
  start 1.0-1.2% further apart on the MD1600, which megadrive-python accepted as the
  recorder's or the crystal's rate. This is a measurement through an analogue path
  of one console, made on the board (megadrive-python `scripts/run_ssg_eg.py`).
- **The ladder's depth.** The discrete variant's level stops falling 36-37 dB below
  its peak; a Model 1 recording stops at 33 dB. The two ramps differ, so this shows
  the shape, not a number.
- **/IC: where in a slot an assertion restarts or pauses the slot counter, the
  three-cycle hold, and that the hold outlasts a short pulse.** The constants were
  measured on Nuked-MD at every position, through megadrive-python's board, and
  this core's tests pin them. Nuked-OPN2 has no /IC timing to compare. One open
  item: a 56-tick pulse is still 28 ticks off the die's (megadrive-python
  `docs/worklog.md`, "The busy flag").
- **Register $27's two-cycle delay** (opt-in `control_delay`). It matches Nuked-MD's
  Timer A flag in all 325 loads of a swept cartridge. Resets still show on the die
  20-60 ticks later than here.

### Contested

- **Where a channel's value sits among its four DAC cycles on the discrete chip.**
  YM2608-LLE drives the value on the first of the four and the sign on three.
  Nuked-OPN2's YM2612 mode, whose own comment calls it "not verified", drives the
  sign on three and the value on the last. **The core follows Nuked-OPN2**, because
  the cycle-exact comparison anchors there (megadrive-python, decision 2026-09-22).
  The sum over a sample, which is what is heard, is the same multiset either way.

### Undecidable here

- **Anything finer than the die transcriptions.** Analogue behaviour inside the DAC,
  and anything the two transcriptions model identically and wrongly.
- **The YM3438 discrete part against the ASIC cores.** The ASIC variant is
  Nuked-OPN2's YM3438. Whether every Sega ASIC's core behaves exactly so is not
  measured here.

### Outside the contract

- The analogue path, mixing and resampling (the board's).
- When a host's access reaches the pins (the board's arbitration and the `lag`).
- The YM2612's SSG part, which it does not have: writes to $00-$0F are dropped, as on
  the chip.
- The rest of the OPN family (YM2203, YM2608, YM2610). They share the design but are
  not modelled.

## The claim, in one paragraph

ym2612-python is the YM2612 and its ASIC successor as a cycle-level pipeline. On
every internal cycle, its two DAC pins and its status byte equal Nuked-OPN2, a
transcription of the YM3438's die, in both output modes. That holds over synthetic
streams covering every register and over real drivers' traffic. Its two ROMs are
pinned integers. Its /IC timing and one register delay are fitted to Nuked-MD, and
the few behaviours hardware has measured agree with it. It does not claim the
analogue path, and it says which of the two die models it follows where they
disagree.
