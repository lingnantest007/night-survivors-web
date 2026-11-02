"""Night Survivors - window, drawing, sound and input. The rules live in rules.py."""

import asyncio
import json
import math
import os

import pygame

import rules

HERE = os.path.dirname(os.path.abspath(__file__))
CFG_PATH = os.path.join(HERE, "data", "game.json")
ASSETS = os.path.join(HERE, "assets")
SOUNDS = os.path.join(HERE, "sounds")

# which sound each rule event plays
EVENT_SOUND = {"damage": "hit", "gem": "gem", "level": "level_up",
               "hurt": "hurt", "end": "end"}


def load_config():
    with open(CFG_PATH, "r", encoding="utf-8") as handle:
        return json.load(handle)


def load_sounds(cfg):
    """Load the finished files from sounds/ (.ogg or .wav, whichever is there).
    No wave module here: make_sounds.py already made them on my computer."""
    if not os.path.isdir(SOUNDS):
        raise SystemExit("sounds/ is missing - run:  python make_sounds.py")
    if pygame.mixer.get_init() is None:
        # this computer cannot play sound - the game still runs, just quietly
        return {}
    sounds = {}
    for name in cfg["sounds"]:
        for ext in (".ogg", ".wav"):
            path = os.path.join(SOUNDS, name + ext)
            if os.path.exists(path):
                try:
                    sounds[name] = pygame.mixer.Sound(path)
                except (pygame.error, OSError):
                    # a browser may not read this audio file - one missing sound
                    # must not stop the game, so that sound is simply skipped
                    pass
                break
    return sounds


def load_pictures(cfg):
    """Load the finished pictures from assets/ and size them. No Pillow here:
    make_assets.py already made these files on my computer."""
    if not os.path.isdir(ASSETS):
        raise SystemExit("assets/ is missing - run:  python make_assets.py")
    pictures = {}
    for key, name in cfg["pictures"].items():
        path = os.path.join(ASSETS, name)
        try:
            image = pygame.image.load(path).convert_alpha()
        except pygame.error as error:
            raise SystemExit("cannot read %s (%s) - run:  python make_assets.py"
                             % (name, error))
        size = int(cfg["picture_px"][key])
        pictures[key] = pygame.transform.scale(image, (size, size))
    return pictures


def blit_center(surface, image, x, y):
    surface.blit(image, (int(x - image.get_width() / 2), int(y - image.get_height() / 2)))


class Effects:
    """The short-lived things that make the game feel alive: damage numbers,
    a flash when an enemy dies and a small shake when the hero is hurt.
    Everything here is only for the screen - rules.py knows nothing about it."""

    def __init__(self, cfg):
        feel = cfg["feel"]
        self.shake_px = feel["shake_px"]
        self.shake_seconds = feel["shake_seconds"]
        self.number_life = feel["number_life_seconds"]
        self.number_rise = feel["number_rise_px"]
        self.flash_life = feel["flash_life_seconds"]
        self.flash_radius = feel["flash_radius_px"]
        self.max_numbers = feel["max_numbers"]
        self.numbers = []    # (world x, world y, text, born, is_hurt)
        self.flashes = []    # (world x, world y, born)
        self.hurt_at = None  # when the hero was last hurt

    def reset(self):
        self.numbers.clear()
        self.flashes.clear()
        self.hurt_at = None

    def add_number(self, x, y, text, born, is_hurt=False):
        self.numbers.append((x, y, text, born, is_hurt))
        if len(self.numbers) > self.max_numbers:
            # drop the oldest ones so the screen does not fill up
            del self.numbers[:len(self.numbers) - self.max_numbers]

    def add_flash(self, x, y, born):
        self.flashes.append((x, y, born))

    def add_hurt(self, born):
        self.hurt_at = born

    def shake(self, now):
        """How far the camera moves this frame: strongest just after a hit, gone after shake_seconds."""
        if self.hurt_at is None:
            return 0.0, 0.0
        age = now - self.hurt_at
        if age < 0 or age >= self.shake_seconds:
            return 0.0, 0.0
        # two different waves, so the camera jitters instead of sliding
        amount = self.shake_px * (1.0 - age / self.shake_seconds)
        return (amount * math.sin(now * 91.0), amount * math.cos(now * 73.0))

    def clean(self, now):
        self.numbers = [n for n in self.numbers if now - n[3] < self.number_life]
        self.flashes = [f for f in self.flashes if now - f[2] < self.flash_life]


def handle_events(game, sounds, effects, now):
    """Turn the events rules.py left in game.events into sounds and pictures.
    A sound plays at most once per frame: 100 enemies dying together must not
    start 100 copies of the same noise."""
    played = set()
    for event in game.events:
        kind = event[0]
        name = EVENT_SOUND.get(kind)
        if name is not None and name in sounds and name not in played:
            sounds[name].play()
            played.add(name)
        if kind == "damage":
            effects.add_number(event[1], event[2], str(int(event[3])), now)
        elif kind == "flash":
            effects.add_flash(event[1], event[2], now)
        elif kind == "hurt":
            effects.add_number(game.hero_x, game.hero_y, "-%d" % int(event[1]), now, True)
            effects.add_hurt(now)
    game.events.clear()


def draw_effects_numbers(surface, cfg, font, effects, cam_x, cam_y, now):
    colors = cfg["colors"]
    for x, y, text, born, is_hurt in effects.numbers:
        age = (now - born) / effects.number_life
        sx, sy = world_to_screen(cfg, x, y, cam_x, cam_y)
        y_pos = sy - 20 - effects.number_rise * age
        image = font.render(text, True, colors["number_hurt" if is_hurt else "number"])
        image.set_alpha(int(255 * (1.0 - age)))
        shadow = font.render(text, True, (0, 0, 0))
        shadow.set_alpha(int(200 * (1.0 - age)))
        w = image.get_width()
        surface.blit(shadow, (int(sx - w / 2) + 1, int(y_pos) + 1))
        surface.blit(image, (int(sx - w / 2), int(y_pos)))


def draw_effects_flashes(surface, cfg, effects, cam_x, cam_y, now):
    color = cfg["colors"]["flash"]
    for x, y, born in effects.flashes:
        age = (now - born) / effects.flash_life
        radius = int(effects.flash_radius * (0.4 + age))
        sx, sy = world_to_screen(cfg, x, y, cam_x, cam_y)
        size = radius * 2 + 2
        blob = pygame.Surface((size, size), pygame.SRCALPHA)
        pygame.draw.circle(blob, tuple(color) + (int(255 * (1.0 - age)),),
                           (size // 2, size // 2), radius)
        surface.blit(blob, (int(sx - size / 2), int(sy - size / 2)))


def screen_to_world(cfg, sx, sy, cam_x, cam_y):
    """A point on the screen becomes a point in the endless world."""
    half_w = cfg["screen"]["width"] / 2.0
    half_h = cfg["screen"]["height"] / 2.0
    return cam_x + (sx - half_w), cam_y + (sy - half_h)


def world_to_screen(cfg, wx, wy, cam_x, cam_y):
    half_w = cfg["screen"]["width"] / 2.0
    half_h = cfg["screen"]["height"] / 2.0
    return wx - cam_x + half_w, wy - cam_y + half_h


def draw_floor(surface, cfg, cam_x, cam_y, tile_image):
    """One tile repeated forever, so the map has no edges."""
    tile = tile_image.get_width()
    w = cfg["screen"]["width"]
    h = cfg["screen"]["height"]
    x0 = math.floor((cam_x - w / 2.0) / tile) * tile
    y0 = math.floor((cam_y - h / 2.0) / tile) * tile
    y = y0
    while y < cam_y + h / 2.0 + tile:
        x = x0
        while x < cam_x + w / 2.0 + tile:
            sx, sy = world_to_screen(cfg, x, y, cam_x, cam_y)
            surface.blit(tile_image, (int(sx), int(sy)))
            x += tile
        y += tile


def draw_bar(surface, x, y, w, h, ratio, fill, back):
    pygame.draw.rect(surface, back, pygame.Rect(x, y, w, h))
    filled = int(w * max(0.0, min(1.0, ratio)))
    if filled > 0:
        pygame.draw.rect(surface, fill, pygame.Rect(x, y, filled, h))


def fmt_time(seconds):
    return "%d:%02d" % (int(seconds) // 60, int(seconds) % 60)


def draw_text(surface, font, text, pos, colors, big=False, center=False):
    """Text with a dark shadow, so it stays readable on the bright floor tile."""
    f = pygame.font.Font(None, 46) if big else font
    x, y = pos
    if center:
        x = surface.get_width() // 2 - f.size(text)[0] // 2
    image = f.render(text, True, colors["text"])
    shadow = f.render(text, True, (0, 0, 0))
    surface.blit(shadow, (x + 1, y + 1))
    surface.blit(image, (x, y))
    return image


def card_rects(cfg):
    """Where the three level-up cards are on the screen."""
    w = cfg["screen"]["width"]
    card_w = w - 50
    card_h = 120
    gap = 16
    top = cfg["screen"]["height"] // 2 - (3 * card_h + 2 * gap) // 2
    return [pygame.Rect(25, top + i * (card_h + gap), card_w, card_h) for i in range(3)]


def pick_card(cfg, game, pos):
    """A click or tap on one of the level-up cards. True when it chose something."""
    if not game.level_up_pending:
        return False
    for i, rect in enumerate(card_rects(cfg)):
        if rect.collidepoint(pos):
            game.choose(i)
            return True
    return False


def inventory_line(cfg, game):
    parts = []
    for key, level in game.weapon_levels.items():
        parts.append("%s %d" % (cfg["weapons"][key]["short"], level))
    for key, level in game.passive_levels.items():
        parts.append("%s %d" % (cfg["passives"][key]["short"], level))
    return "  ".join(parts)


def draw_cards(surface, cfg, game, font):
    colors = cfg["colors"]
    overlay = pygame.Surface((cfg["screen"]["width"], cfg["screen"]["height"]), pygame.SRCALPHA)
    overlay.fill(tuple(colors["overlay"]) + (190,))
    surface.blit(overlay, (0, 0))
    draw_text(surface, font, "LEVEL UP - pick one", (0, 40), colors, big=True, center=True)
    for rect, card in zip(card_rects(cfg), game.cards):
        pygame.draw.rect(surface, colors["card"], rect)
        pygame.draw.rect(surface, colors["card_border"], rect, 3)
        title = card["name"] if card["level"] is None else "%s  Lv %d" % (card["name"], card["level"])
        draw_text(surface, font, title, (rect.x + 16, rect.y + 18), colors)
        draw_text(surface, font, card["text"], (rect.x + 16, rect.y + 52), colors)


def draw_game(surface, cfg, game, font, pictures, effects, now, shake=(0.0, 0.0)):
    colors = cfg["colors"]
    # the camera follows the hero, and shakes a little when he is hurt
    cam_x = game.hero_x + shake[0]
    cam_y = game.hero_y + shake[1]
    draw_floor(surface, cfg, cam_x, cam_y, pictures["floor"])

    for g in game.gems:
        sx, sy = world_to_screen(cfg, g.x, g.y, cam_x, cam_y)
        blit_center(surface, pictures["gem_1" if g.xp == 1 else "gem_2"], sx, sy)

    for e in game.enemies:
        sx, sy = world_to_screen(cfg, e.x, e.y, cam_x, cam_y)
        blit_center(surface, pictures[e.kind], sx, sy)

    for s in game.sparks:
        sx, sy = world_to_screen(cfg, s.x, s.y, cam_x, cam_y)
        pygame.draw.circle(surface, colors["spark"], (int(sx), int(sy)), int(s.radius))

    if "holy_ring" in game.weapon_levels:
        ring = game.weapon_stats("holy_ring")
        hx, hy = world_to_screen(cfg, game.hero_x, game.hero_y, cam_x, cam_y)
        fresh = (game.time - game.ring_flash) < 0.15
        pygame.draw.circle(surface, colors["ring_flash" if fresh else "ring"],
                           (int(hx), int(hy)), int(ring["radius"]), 3)

    hx, hy = world_to_screen(cfg, game.hero_x, game.hero_y, cam_x, cam_y)
    blit_center(surface, pictures["hero"], hx, hy)

    for bx, by in game.blade_positions:
        sx, sy = world_to_screen(cfg, bx, by, cam_x, cam_y)
        angle = math.degrees(math.atan2(by - game.hero_y, bx - game.hero_x))
        blade = pygame.transform.rotate(pictures["sword"], -(angle + 90))
        blit_center(surface, blade, sx, sy)

    draw_effects_flashes(surface, cfg, effects, cam_x, cam_y, now)
    draw_effects_numbers(surface, cfg, font, effects, cam_x, cam_y, now)

    draw_bar(surface, 10, 10, 130, 12, game.hero_hp / game.hero_max_hp,
             colors["hp_fill"], colors["hp_back"])
    draw_bar(surface, 10, 26, 130, 8, game.xp / game.xp_needed,
             colors["xp_fill"], colors["xp_back"])
    draw_text(surface, font, "Lv %d" % game.level, (10, 38), colors)

    right = cfg["screen"]["width"] - 10
    timer_text = "%s / %s" % (fmt_time(game.time), fmt_time(cfg["goal_time_seconds"]))
    kills_text = "kills %d" % game.kills
    draw_text(surface, font, timer_text,
              (right - font.size(timer_text)[0], 10), colors)
    draw_text(surface, font, kills_text,
              (right - font.size(kills_text)[0], 28), colors)

    draw_text(surface, font, inventory_line(cfg, game),
              (10, cfg["screen"]["height"] - 24), colors)

    if game.level_up_pending:
        draw_cards(surface, cfg, game, font)
    elif game.game_over:
        draw_end(surface, cfg, game, font)


def draw_end(surface, cfg, game, font):
    overlay = pygame.Surface((cfg["screen"]["width"], cfg["screen"]["height"]), pygame.SRCALPHA)
    overlay.fill(tuple(cfg["colors"]["overlay"]) + (200,))
    surface.blit(overlay, (0, 0))
    colors = cfg["colors"]
    lines = ["VICTORY" if game.victory else "GAME OVER",
             "%s   kills %d   Lv %d" % (fmt_time(game.time), game.kills, game.level),
             "Click or tap to play again"]
    y = cfg["screen"]["height"] // 2 - 60
    for i, line in enumerate(lines):
        draw_text(surface, font, line, (0, y), colors, big=(i == 0), center=True)
        y += 46 if i == 0 else 34


async def main():
    cfg = load_config()
    pygame.init()
    screen = pygame.display.set_mode((cfg["screen"]["width"], cfg["screen"]["height"]))
    clock = pygame.time.Clock()
    font = pygame.font.Font(None, 22)
    pictures = load_pictures(cfg)
    sounds = load_sounds(cfg)
    effects = Effects(cfg)
    game = rules.Game(cfg, seed=os.environ.get("NS_SEED"))

    paused = False
    pointer = None  # where the mouse or finger is on the screen, or None
    running = True
    carry = 0.0

    while running:
        now = pygame.time.get_ticks() / 1000.0
        shake = effects.shake(now)
        cam_x = game.hero_x + shake[0]
        cam_y = game.hero_y + shake[1]

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_p:
                    paused = not paused
                elif event.key == pygame.K_ESCAPE:
                    running = False
            elif event.type in (pygame.MOUSEMOTION, pygame.MOUSEBUTTONDOWN):
                if event.type == pygame.MOUSEBUTTONDOWN and pick_card(cfg, game, event.pos):
                    pointer = None
                    continue
                pointer = (event.pos[0], event.pos[1])
                if game.game_over and event.type == pygame.MOUSEBUTTONDOWN:
                    game.reset()
                    effects.reset()
                    pointer = None
            elif event.type in (pygame.FINGERDOWN, pygame.FINGERMOTION):
                pos = (event.x * cfg["screen"]["width"], event.y * cfg["screen"]["height"])
                if event.type == pygame.FINGERDOWN and pick_card(cfg, game, pos):
                    pointer = None
                    continue
                pointer = pos
                if game.game_over and event.type == pygame.FINGERDOWN:
                    game.reset()
                    effects.reset()
                    pointer = None
            elif event.type == pygame.FINGERUP:
                # the hero stops when the finger leaves the screen
                pointer = None

        if not paused:
            if pointer is not None:
                # walk where the pointer is now, not where it was when it moved
                game.set_target(*screen_to_world(cfg, pointer[0], pointer[1], cam_x, cam_y))
            else:
                game.stop()
            # keep the rules on the fixed step, even when the frame rate wobbles
            carry += clock.tick(60) / 1000.0
            steps = 0
            while carry >= rules.DT and steps < 5:
                game.step(rules.DT)
                carry -= rules.DT
                steps += 1
        else:
            clock.tick(60)

        # what just happened in the rules becomes sound and "feel" on screen
        handle_events(game, sounds, effects, now)
        effects.clean(now)

        draw_game(screen, cfg, game, font, pictures, effects, now, shake)
        pygame.display.flip()

        await asyncio.sleep(0)


asyncio.run(main())
