"""Makes the game pictures from raw_art/. Run this on your computer:

    python make_assets.py

It writes 3x bigger copies (no blurring) into assets/, plus two coloured gems.
raw_art/ is never changed. main.py only reads the finished files in assets/.
"""

import os

from PIL import Image, ImageOps

HERE = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(HERE, "raw_art")
OUT = os.path.join(HERE, "assets")

SCALE = 3

SPRITES = ["hero.png", "bat.png", "slime.png", "ghost.png", "demon.png",
           "sword.png", "floor.png"]

# (out name, dark colour at the bottom, bright colour at the top)
GEMS = [
    ("gem_blue.png", (24, 64, 180), (150, 220, 255)),   # worth 1 XP
    ("gem_pink.png", (150, 24, 130), (255, 170, 245)),  # worth 2 XP
]


def upscale(image):
    """3x bigger with hard edges, so the pixels stay crisp."""
    return image.resize((image.width * SCALE, image.height * SCALE), Image.NEAREST)


def copy_sprite(name):
    src = Image.open(os.path.join(RAW, name)).convert("RGBA")
    out = upscale(src)
    out.save(os.path.join(OUT, name))
    print(name, src.size, "->", out.size)


def make_gem(out_name, dark, light):
    """Re-colour gem.png: keep its shape and alpha, paint a bright crystal."""
    src = Image.open(os.path.join(RAW, "gem.png")).convert("RGBA")
    alpha = src.getchannel("A")
    shape = src.convert("L")
    tinted = ImageOps.colorize(shape, black=dark, white=light)
    tinted.putalpha(alpha)
    out = upscale(tinted)
    out.save(os.path.join(OUT, out_name))
    print(out_name, src.size, "->", out.size)


def main():
    os.makedirs(OUT, exist_ok=True)
    for name in SPRITES:
        copy_sprite(name)
    for out_name, dark, light in GEMS:
        make_gem(out_name, dark, light)
    print("done: %d files in %s" % (len(os.listdir(OUT)), OUT))


if __name__ == "__main__":
    main()
