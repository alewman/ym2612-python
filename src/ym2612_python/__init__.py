"""ym2612-python: a readable, pure-Python YM2612 / YM3438 (OPN2) reference core.

The chip is :class:`YM2612`; its two variants are :data:`YM2612_DISCRETE` (the NMOS
part, with the ladder) and :data:`YM3438_ASIC`. The contract -- the pins, the time
unit, the outputs -- is docs/contract.md.
"""

from ym2612_python.chip import EXP, LOG_SIN, YM2612, YM2612_DISCRETE, YM3438_ASIC, FMVariant

__all__ = ["EXP", "LOG_SIN", "YM2612", "YM2612_DISCRETE", "YM3438_ASIC", "FMVariant"]
__version__ = "0.1.0.dev0"
