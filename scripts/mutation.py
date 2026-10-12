#!/usr/bin/env python
"""Seed faults into the chip, one at a time, and check the fast gate catches each.

    python scripts/mutation.py                    # examples and the rule tests
    python scripts/mutation.py --examples-only    # what a port's gate alone catches

A gate that cannot fail proves nothing. Each mutant changes one place in
``src/ym2612_python/chip.py`` -- a rule the chip is known to have, broken the way a
port might break it -- and the gate is the conformance examples
(``examples/conformance/``), which a port runs, plus this chip's own rule tests
(``tests/test_chip.py`` without the referee): what fails first when a rule is broken.
A mutant the gate misses is listed.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CHIP = ROOT / "src" / "ym2612_python" / "chip.py"

#: (what is broken, the exact text, its replacement)
MUTANTS = [
    ("BUSY lasts 31 cycles", "self.write_busy_cnt + self.write_busy) & 0x1F",
     "self.write_busy_cnt + self.write_busy) & 0x1E"),
    ("an address write sets BUSY", "if (self.write_busy and self.write_busy_cnt != 0) or self.write_d_en",
     "if (self.write_busy and self.write_busy_cnt != 0) or self.write_d_en or self.write_a_en"),
    ("timer A steps on cycle 2", "if (self.cycles == 1 and self.timer_a_load_lock)",
     "if (self.cycles == 2 and self.timer_a_load_lock)"),
    ("timer B every 8 samples", "if (self.timer_b_subcnt == 0x10 and self.timer_b_load_lock)",
     "if (self.timer_b_subcnt == 0x08 and self.timer_b_load_lock)"),
    ("timer A flag ignores enable", "self.timer_a_overflow_flag |= self.timer_a_overflow & self.timer_a_enable",
     "self.timer_a_overflow_flag |= self.timer_a_overflow"),
    ("pans swapped", "self.pan_l[channel] = (data >> 7) & 1", "self.pan_l[channel] = (data >> 6) & 1"),
    ("no ladder +1", "                out += 1\n                sign += 1", "                sign += 1"),
    ("ASIC drives all four cycles", "out_en = (cycles & 3) != 0 or test_dac", "out_en = True"),
    ("DAC ninth bit lost", "self.dacdata = (self.dacdata & 0x1FE) | self.mode_test_2c[3]",
     "self.dacdata = self.dacdata & 0x1FE"),
    ("DAC sign not flipped", "(((data ^ 0x80) << 1) & 0x1FE)", "(((data) << 1) & 0x1FE)"),
    ("multiplier 0 means 0", "(data & 0x0F) << 1 if data & 0x0F else 1", "(data & 0x0F) << 1"),
    ("SL 15 not all the way down", "self.sl[slot] = level | ((level + 1) & 0x10)", "self.sl[slot] = level"),
    ("$A4 written straight through", "fnum = (data & 0xFF) | ((self.reg_a4 & 7) << 8)",
     "fnum = (data & 0xFF) | ((data & 7) << 8)"),
    ("feedback one step stronger", "mod = (mod >> (10 - fb)) if fb else 0", "mod = (mod >> (9 - fb)) if fb else 0"),
    ("detune sign ignored", "basefreq = (basefreq - detune if dt & 4 else basefreq + detune) & 0x1FFFF",
     "basefreq = (basefreq + detune) & 0x1FFFF"),
    ("LFO AM depth off by one", "EG_AM_SHIFT = (7, 3, 1, 0)", "EG_AM_SHIFT = (7, 3, 2, 0)"),
    ("LFO speed table", "LFO_CYCLES = (108, 77, 71, 67, 62, 44, 8, 5)",
     "LFO_CYCLES = (108, 77, 71, 67, 62, 44, 9, 5)"),
    ("slowest LFO reloads a sample late", "LFO_CYCLES = (108, 77, 71, 67, 62, 44, 8, 5)",
     "LFO_CYCLES = (109, 77, 71, 67, 62, 44, 8, 5)"),
    ("key-on operators 2 and 3 swapped",
     "self.mode_kon[channel + 12] = operator[1]\n            self.mode_kon[channel + 6] = operator[2]",
     "self.mode_kon[channel + 12] = operator[2]\n            self.mode_kon[channel + 6] = operator[1]"),
    ("SSG-EG runs at normal speed", "                        inc <<= 2  # SSG-EG runs the envelope four times as fast",
     "                        pass"),
    ("SSG-EG inversion ignored", "            ssg_level = (512 - level) & 0x3FF", "            ssg_level = level"),
    ("attack rate 31 not instant", "                nextlevel = 0  # a rate of 31 attacks in one step",
     "                pass"),
    ("CSM keys channel 4", "if self.channel == 2 and self.mode_kon_csm:", "if self.channel == 3 and self.mode_kon_csm:"),
    ("ch3 mode operator slot", "            if slot == 7:\n                self.pg_fnum = self.fnum_3ch[0]",
     "            if slot == 8:\n                self.pg_fnum = self.fnum_3ch[0]"),
    ("accumulator clamps at 254", "        if total > 255:\n            total = 255",
     "        if total > 254:\n            total = 254"),
    ("status never decays on the YM2612", "STATUS_TIME = (300_000, 40_000_000)", "STATUS_TIME = (40_000_000, 40_000_000)"),
    ("discrete status on every port", "if (port & 3) == 0 or self.variant.busy_on_all_ports:", "if True:"),
    ("/IC pauses at another position", "IC_PAUSE_POSITIONS = (0, 4, 5)", "IC_PAUSE_POSITIONS = (0, 3, 5)"),
    ("/IC hold two cycles", "IC_FSM_HOLD = 3", "IC_FSM_HOLD = 2"),
    ("/IC hold ends at release", "IC_HOLD_PAST_RELEASE = 1", "IC_HOLD_PAST_RELEASE = 0"),
    ("writes accepted under /IC", "        if self.in_reset:\n            return\n        port &= 3",
     "        port &= 3"),
    ("timer control delay one short", "                self._pending_27 = [data, self.control_delay - 1]",
     "                self._pending_27 = [data, self.control_delay - 2]"),
    ("log-sin table rounded down", "round(-math.log2(math.sin((i + 0.5) * math.pi / 512)) * 256)",
     "int(-math.log2(math.sin((i + 0.5) * math.pi / 512)) * 256)"),
]  # fmt: skip


def gate(src: Path, python: str, examples_only: bool = False) -> bool:
    """True when the gate passes (the mutant survives)."""
    rules = ["tests/test_chip.py::test_the_tables_are_the_pinned_integers"]
    if not examples_only:
        rules = ["tests/test_chip.py"]
    env = dict(os.environ, PYTHONPATH=str(src))
    result = subprocess.run(
        # -o pythonpath: pyproject puts the real src first; the mutated copy must win.
        [python, "-m", "pytest", "-q", "-x", "-p", "no:cacheprovider", "-o", "pythonpath=tests scripts",
         "-m", "not referee",
         "tests/test_conformance.py::test_each_example_reproduces_its_committed_trace",
         *rules],
        cwd=ROOT, env=env, capture_output=True, text=True,
    )  # fmt: skip
    return result.returncode == 0


def main() -> int:
    examples_only = "--examples-only" in sys.argv[1:]
    python = sys.executable
    original = CHIP.read_text()
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / "src"
        shutil.copytree(ROOT / "src", src)
        target = src / "ym2612_python" / "chip.py"
        if not gate(src, python):
            print("the unmutated chip fails the gate")
            return 2
        survivors = []
        for name, old, new in MUTANTS:
            if original.count(old) != 1:
                print(f"{name}: the text to mutate is not found exactly once")
                return 2
            target.write_text(original.replace(old, new))
            survived = gate(src, python, examples_only)
            print(f"{'SURVIVED' if survived else 'caught  '}  {name}")
            if survived:
                survivors.append(name)
        print(f"\n{len(MUTANTS) - len(survivors)} of {len(MUTANTS)} mutants caught")
    return 1 if survivors else 0


if __name__ == "__main__":
    sys.exit(main())
