# ym2612-python

A readable, pure-Python reference core of the Yamaha **YM2612** (OPN2), the Mega
Drive's FM chip, and its CMOS successor the **YM3438**. It covers six FM channels,
channel 3's special mode, CSM, SSG-EG, the LFO, both timers, BUSY, the DAC, and the
discrete chip's ladder effect.

It is not a per-sample FM synthesiser. It is the chip's **pipeline**: one operator
served per internal cycle, 24 cycles to an output sample, with each stage the
number of cycles behind the others that the die has. On **every internal cycle** of
the 18 streams below, its two DAC pins and its status byte equal **Nuked-OPN2**, a
transcription of the YM3438's die, in both output modes.

It is a chip in the family's shape (chips are cores, boards compose cores), beside
[z80-python](https://github.com/alewman/z80-python) and
[m68000-python](https://github.com/alewman/m68000-python). It was extracted, with
its history, from
[megadrive-python](https://github.com/alewman/megadrive-python), which will depend
on it at a pinned commit. A Rust transcription proven equal to it through the
conformance kit is the next step.

## Validation

| What | Result | Tier |
| --- | --- | --- |
| Every cycle of MOL, MOR and status against Nuked-OPN2 @ 335747d, both variants: 7 synthetic streams, Nemesis's 6 test ROMs, 5 cartridges | **663,015,150 values, 0 different** (110.5 M cycles per variant) | die-derived (the judge) |
| The two ROM tables against the die's | all 256 + 256 entries equal; pinned by SHA-256 | die-derived |
| BUSY's length and ports | 32 cycles; port 0 only on the discrete chip | hardware-captured |
| The output stage against YM2608-LLE (the NMOS die) | identical at the native rate where the harnesses compare; one placement difference classified | die-derived (detector) |
| The ladder against a Model 1 recording | plateaus at 36-37 dB (hardware: 33 dB); the ASIC does not | hardware-captured (shape) |
| 31 seeded faults | 31 caught (30 by the conformance examples alone) | not an oracle |

What each result supports, and how strongly, is [docs/claims.md](docs/claims.md).
The runs, with commands and commits, are [docs/validation.md](docs/validation.md).

## Install

```text
git clone https://github.com/alewman/ym2612-python
cd ym2612-python
python -m pip install -e ".[dev]"
```

Python 3.11 or newer (the newest PyPy supports). No dependencies.

## Minimal host

```python
from ym2612_python import YM2612, YM2612_DISCRETE

chip = YM2612(YM2612_DISCRETE)
tick = 0


def write(register: int, value: int, part: int = 0) -> None:
    global tick
    for port, byte in ((part * 2, register), (part * 2 + 1, value)):
        chip.run(tick)  # bring the chip to the moment of the access
        chip.write(port, byte)
        tick += 24 * 42  # leave the chip a sample between writes


for register, value in (
    (0x30, 0x01),
    (0x40, 0x00),
    (0x50, 0x1F),
    (0x80, 0x0F),
    (0xB0, 0x07),
    (0xB4, 0xC0),
    (0xA4, 0x22),
    (0xA0, 0x69),
):
    write(register, value)
write(0x28, 0x10)  # key on operator 1 of channel 1

chip.run(tick + 53_693_175 // 10)  # a tenth of a second (ticks are the MD's MCLK)
samples = chip.take_samples()  # [(left, right), ...] at 53,267 Hz
```

The contract (the pins, the time unit, /IC, the switches, what belongs to the
board) is [docs/contract.md](docs/contract.md). In short:
- `run(t)` takes **ticks**, seven to an input clock, which on the Mega Drive is the
  master clock.
- `write(port, value)` and `read(port)` are the two ports.
- `reset_line(held, t, lag)` is /IC, and `irq()` is /IRQ.
- `mol` and `mor` are the DAC pins after the last cycle, and `take_samples()`
  returns their sums.

## For a port: the conformance kit

```text
python -m ym2612_python.conformance trace examples/conformance/voices-ym2612.json
python -m ym2612_python.conformance diff examples/conformance/voices-ym2612.json port.trace
```

A manifest names the variant and the timed writes, reads and /IC events. The trace
has a line for every internal cycle (the slot, both pins, status, IRQ, or *held*)
and one for every read. Eleven example manifests ship with reference traces, eight of
them checked against Nuked-OPN2 by the tests. See
[docs/conformance.md](docs/conformance.md).

## Reproducing

```text
python -m pytest -q -m "not referee"            # rules, tables, the kit (seconds)
python scripts/fetch_references.py              # Nuked-OPN2, YM2608-LLE (never committed)
sh validation/build_referees.sh
python -m pytest -q                             # plus the referee comparisons (minutes)
python scripts/run_fm_streams.py                # the synthetic streams, every cycle
python scripts/export_board_streams.py --board ../megadrive-python --roms --games
python scripts/run_fm_streams.py --streams      # the board's streams (needs the export)
python scripts/run_fm_streams.py --lle          # also YM2608-LLE (slow)
python scripts/mutation.py                      # the seeded faults
python benchmarks/bench.py                      # speed
```

The exported streams come from ROMs and stay local (`validation/streams/`,
ignored).

## Speed

This is a reference: correct first. At e3672d6 with the generator on, CPython 3.14
runs **0.104× real time** and PyPy 7.3.20 0.028×; PyPy's JIT does poorly on the long
cycle body. The quiet path (`enabled=False`: registers, timers and BUSY only) runs
0.42× on CPython. Making it fast is a job for the Rust transcription and its `-fast`
fork. See [docs/validation.md](docs/validation.md), "Speed".

## Licence

MIT. Nuked-OPN2 (LGPL-2.1) and YM2608-LLE (GPL-2.0) are read, cited by file and line,
and run as locally built referees. None of their code is in this repository.
