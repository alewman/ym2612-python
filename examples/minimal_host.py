"""The README's minimal host: one operator keyed on for a tenth of a second."""

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

if __name__ == "__main__":
    loudest = max(abs(left) for left, _right in samples)
    print(f"{len(samples)} samples, loudest {loudest}")
