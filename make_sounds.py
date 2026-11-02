"""Makes the short game sounds. Run this on your computer:

    python make_sounds.py

It writes small .wav files into sounds/ using only Python's standard library.
main.py only plays the finished files (it never imports wave).
"""

import math
import os
import struct
import wave

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "sounds")

RATE = 22050      # samples per second
VOLUME = 0.30     # keep it quiet enough that five sounds at once do not clip
CLIP = 32767


def add_tone(samples, freq, seconds, volume=VOLUME, shape="sine", slide_to=None,
             decay=True, offset=0.0):
    """Append one simple beep to the sample list."""
    count = int(RATE * seconds)
    edge = max(1, int(RATE * 0.02))  # a short fade in and out, so there is no click
    for i in range(count):
        t = i / RATE
        f = freq if slide_to is None else freq + (slide_to - freq) * (i / max(1, count - 1))
        x = 2 * math.pi * f * t + offset
        if shape == "sine":
            value = math.sin(x)
        elif shape == "square":
            value = 1.0 if math.sin(x) >= 0 else -1.0
        else:  # saw: used for the hurt sound, it sounds rougher
            value = 2.0 * ((x / (2 * math.pi)) % 1.0) - 1.0
        if decay:
            value *= math.exp(-4.0 * (i / count))
        else:
            if i < edge:
                value *= i / edge
            elif i > count - edge:
                value *= (count - i) / edge
        samples.append(value * volume)


def add_rest(samples, seconds):
    samples.extend([0.0] * int(RATE * seconds))


def write(name, samples):
    path = os.path.join(OUT, name)
    with wave.open(path, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(RATE)
        handle.writeframes(b"".join(
            struct.pack("<h", int(max(-1.0, min(1.0, s)) * CLIP)) for s in samples))
    print(name, "%.2f s" % (len(samples) / RATE))


def make_hit():
    """A spark landing: one short, dry blip."""
    samples = []
    add_tone(samples, 1100, 0.05, volume=0.22, shape="square")
    return samples


def make_gem():
    """A gem picked up: two quick rising notes."""
    samples = []
    add_tone(samples, 880, 0.05, volume=0.18)
    add_tone(samples, 1320, 0.07, volume=0.18)
    return samples


def make_level_up():
    """Level up: a small three-note run up."""
    samples = []
    for freq in (523, 659, 784):
        add_tone(samples, freq, 0.09, volume=0.22)
    add_tone(samples, 1046, 0.16, volume=0.22)
    return samples


def make_hurt():
    """The hero is hit: a rough drop in pitch."""
    samples = []
    add_tone(samples, 320, 0.16, volume=0.26, shape="saw", slide_to=120)
    return samples


def make_end():
    """The run is over: two low notes fading out."""
    samples = []
    add_tone(samples, 196, 0.5, volume=0.22, decay=False)
    add_rest(samples, 0.02)
    add_tone(samples, 147, 0.6, volume=0.22, decay=False)
    return samples


def main():
    os.makedirs(OUT, exist_ok=True)
    write("hit.wav", make_hit())
    write("gem.wav", make_gem())
    write("level_up.wav", make_level_up())
    write("hurt.wav", make_hurt())
    write("end.wav", make_end())
    print("done: %d files in %s" % (len(os.listdir(OUT)), OUT))


if __name__ == "__main__":
    main()
