"""The chip's rules, its two ROM tables, and the chip against Nuked-OPN2.

The judges are **Nuked-OPN2** and **YM2608-LLE**: no hardware capture or
hardware-corrected test covers the chip's arithmetic (there is no YM2612 datasheet
and no self-checking FM test ROM), so the tier rule makes a die-derived model the
judge (docs/validation.md). They are C programs built from the pinned sources by
``sh validation/build_referees.sh``; a test skips when they are not built.

The long runs -- the exported board streams, YM2608-LLE -- are
``scripts/run_fm_streams.py --streams --lle`` and are recorded in docs/validation.md;
what is here is the part that runs in minutes.
"""

from __future__ import annotations

import hashlib
import re
import struct
import subprocess
import sys
from pathlib import Path

import pytest
from conftest import ROOT

from ym2612_python import EXP, LOG_SIN, YM2612, YM3438_ASIC
from ym2612_python import YM2612_DISCRETE as FM_DISCRETE

REFEREES = ROOT / "reference" / "build-referees"
NUKED_OPN2 = ROOT / "reference" / "src" / "Nuked-OPN2" / "ym3438.c"


def _table(source: Path, name: str) -> list[int]:
    text = source.read_text()
    body = re.search(rf"{name}\[\d+\] = \{{(.*?)\}};", text, re.S)
    assert body, f"{name} not found in {source}"
    return [int(value, 16) for value in re.findall(r"0x([0-9a-fA-F]+)", body.group(1))]


# -- the chip's ROMs, generated here, pinned by hash and checked against the die's ----

#: SHA-256 of each table as 256 little-endian unsigned 16-bit integers: the contract a
#: port in any language checks its own tables against (docs/contract.md, "The tables"),
#: rather than trusting its libm at a rounding boundary.
LOG_SIN_SHA256 = "a099b16dd3aa2f56cabc1fee590db31ee412ee361da4f0c67497092cf57c4776"
EXP_SHA256 = "a0ca448cb3178dd131cd23425b2adc8ee155d1905f2fa083d570954a47f3ede0"


def _sha256(table: tuple[int, ...]) -> str:
    return hashlib.sha256(struct.pack("<256H", *table)).hexdigest()


def test_the_tables_are_the_pinned_integers() -> None:
    assert len(LOG_SIN) == len(EXP) == 256
    assert _sha256(LOG_SIN) == LOG_SIN_SHA256
    assert _sha256(EXP) == EXP_SHA256


def test_the_tables_hash_would_notice_one_entry_off() -> None:
    """A gate that cannot fail proves nothing: one entry out by one changes the hash."""
    for table, digest in ((LOG_SIN, LOG_SIN_SHA256), (EXP, EXP_SHA256)):
        wrong = list(table)
        wrong[15] += 1
        assert _sha256(tuple(wrong)) != digest


@pytest.mark.skipif(not NUKED_OPN2.exists(), reason="Nuked-OPN2 is not fetched")
def test_log_sin_rom_matches_the_die() -> None:
    """All 256 entries of the generated quarter-sine table equal the ones read off the
    YM3438's die (``ym3438.c`` ``logsinrom``)."""
    assert list(LOG_SIN) == _table(NUKED_OPN2, "logsinrom")


@pytest.mark.skipif(not NUKED_OPN2.exists(), reason="Nuked-OPN2 is not fetched")
def test_exp_rom_matches_the_die() -> None:
    assert list(EXP) == _table(NUKED_OPN2, "exprom")


# -- the chips' own rules --------------------------------------------------------------


def test_busy_lasts_32_internal_cycles() -> None:
    """Eke's measurement: BUSY is set by a *data* write and lasts 32 internal clocks,
    which are 6 68000 cycles each (forum t=386 start=810; docs/timing.md)."""
    chip = YM2612(FM_DISCRETE)
    chip.write(0, 0x22)  # an address write: no BUSY
    for _ in range(4):
        chip.cycle()
    assert chip.busy == 0
    chip.write(1, 0x00)  # a data write
    chip.cycle()
    assert chip.busy == 0  # it appears on the cycle after the strobe
    high = 0
    for _ in range(64):
        chip.cycle()
        high += chip.busy
    assert high == 32
    assert chip.busy == 0


def test_ym2612_busy_reads_on_port_0_only_on_the_discrete_chip() -> None:
    """The ASIC answers on every port, the discrete YM2612 on port 0 (Eke)."""
    for variant, ports in ((FM_DISCRETE, [0]), (YM3438_ASIC, [0, 1, 2, 3])):
        chip = YM2612(variant)
        chip.write(1, 0x00)
        for _ in range(3):
            chip.cycle()
        assert chip.busy == 1
        for port in range(4):
            expected = 0x80 if port in ports else 0x00
            assert chip.read(port) & 0x80 == expected or port not in ports


def test_ym2612_timer_a_overflows_after_its_reload() -> None:
    """Timer A counts one per output sample and overflows at 1024 - reload
    (the Manual; ``ym3438.c`` ``OPN2_DoTimerA``)."""
    chip = YM2612(FM_DISCRETE)
    reload_value = 1000
    for register, value in ((0x24, reload_value >> 2), (0x25, reload_value & 3), (0x27, 0x05)):
        chip.write(0, register)
        chip.cycle()
        chip.cycle()
        chip.write(1, value)
        for _ in range(4):
            chip.cycle()
    samples = 0
    while not chip.timer_a_overflow_flag and samples < 200:
        for _ in range(24):
            chip.cycle()
        samples += 1
    assert chip.timer_a_overflow_flag
    assert 1024 - reload_value - 2 <= samples <= 1024 - reload_value + 2


def test_the_driven_status_decays_after_its_hold() -> None:
    """The value a read drives is held for 300,000 cycles on the YM2612 and 40,000,000
    on the YM3438, then reads 0 (``ym3438.c`` ``OPN2_Read``, ``status_time``). On the
    discrete chip it shows through ports 1-3, which return the held value without
    driving a new one; on the ASIC every port drives afresh, so only the hold shows.
    Run on the quiet path, which keeps the timers and the decay."""
    for cycles, expected in ((299_990, 0x80), (300_000, 0x00)):
        chip = YM2612(FM_DISCRETE, enabled=False)
        chip.write(1, 0x00)  # a data write: BUSY
        chip.run(3 * 42)
        assert chip.read(0) == 0x80
        chip.run(chip.mclk + cycles * 42)
        assert chip.read(1) == expected, cycles
    chip = YM2612(YM3438_ASIC, enabled=False)
    chip.read(2)
    assert chip.status_time == 40_000_000


def test_ladder_is_a_variant_field_and_changes_the_output() -> None:
    """The discrete chip drives the sign in the gaps and multiplies by three; the ASIC
    drives zero and does not (``ym3438.c`` ``OPN2_ChOutput``)."""
    silent_discrete = YM2612(FM_DISCRETE)
    silent_asic = YM2612(YM3438_ASIC)
    for _ in range(96):
        silent_discrete.cycle()
        silent_asic.cycle()
    assert silent_asic.mol == 0
    assert silent_discrete.mol == 3  # +1 sign, amplified
    assert FM_DISCRETE.ladder and not YM3438_ASIC.ladder


def test_the_chip_ignores_writes_while_ic_is_held() -> None:
    """On the Mega Drive /IC is the Z80's reset: "For as long as the Z80 is reset, the
    YM2612 cannot be used" (CMD 2.2)."""
    chip = YM2612(FM_DISCRETE)
    chip.reset_line(True)
    chip.write(0, 0x28)
    chip.write(1, 0xF0)
    assert chip.writes == 0
    chip.reset_line(False)
    chip.write(0, 0x28)
    assert chip.writes == 1


def test_an_ic_write_restarts_the_slot_counter_only_7_to_27_mclk_into_a_slot() -> None:
    """Nuked-MD (megadrive-python scripts/run_fm_ic.py, docs/worklog.md "The FM's
    restart, swept"): an /IC driven by a write to $A11200 (lag 0, the board's
    ``IC_WRITE_SLOT_LAG``) whose bus cycle begins 7-27 MCLK into the FM's slot
    restarts the slot counter at 0; at 0-6 and 28-41 it only pauses it, the count going
    on."""
    for position in range(42):
        chip = YM2612(FM_DISCRETE)
        chip.mclk, chip.cycles = 4200, 10
        chip.reset_line(True, 4200 + position, 0)
        restarted = chip.cycles == 0
        assert restarted == (7 <= position < 28), position


def test_a_short_ic_pulse_leaves_the_chip_where_a_long_one_does() -> None:
    """Nuked-MD (megadrive-python scripts/run_fm_ic.py --short, docs/worklog.md "The busy
    flag"): /IC
    stops the chip for three cycles after the assertion, and released sooner it stays
    stopped for the rest of them -- a 1-cycle pulse and a 10-cycle one leave the slot
    counter at the same place."""
    counts = {}
    for length in (1, 10):
        chip = YM2612(FM_DISCRETE)
        chip.mclk, chip.cycles = 4200, 10
        chip.reset_line(True, 4200, 0)
        chip.run(4200 + length * 42)
        chip.reset_line(False, 4200 + length * 42)
        chip.run(4200 + 20 * 42)
        counts[length] = chip.cycles
    assert counts[1] == counts[10]


# -- against the referees ---------------------------------------------------------------


@pytest.mark.referee
@pytest.mark.skipif(
    not (REFEREES / "opn2_ref").exists(), reason="run `sh validation/build_referees.sh`"
)
def test_ym2612_matches_nuked_opn2() -> None:
    """The synthetic streams of ``scripts/run_fm_streams.py``: every internal cycle of
    both DAC pins and the status byte, in both chip variants."""
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "run_fm_streams.py")],
        capture_output=True, text=True, check=False,
    )  # fmt: skip
    assert result.returncode == 0, result.stdout + result.stderr
    assert "0 comparisons not identical" in result.stdout
