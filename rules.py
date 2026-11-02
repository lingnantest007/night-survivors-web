"""The game rules, one fixed time step at a time. No pygame in this file."""

import math
import random

DT = 1.0 / 60.0
EPS = 1e-9  # 60 steps of DT can add up to just under 1.0


def _dist(ax, ay, bx, by):
    return math.hypot(bx - ax, by - ay)


class Enemy:
    def __init__(self, kind, stats, x, y):
        self.kind = kind
        self.hp = stats["hp"]
        self.speed = stats["speed"]
        self.damage = stats["damage"]
        self.radius = stats.get("radius", 10)
        self.xp = stats.get("xp", 0)
        self.boss = bool(stats.get("boss"))
        self.x = x
        self.y = y
        self.contact_ready = 0.0
        self.blade_ready = []  # one cooldown per blade, so a blade cannot hit twice in one frame


class Spark:
    def __init__(self, x, y, vx, vy, damage, radius):
        self.x = x
        self.y = y
        self.vx = vx
        self.vy = vy
        self.damage = damage
        self.radius = radius


class Gem:
    def __init__(self, x, y, xp):
        self.x = x
        self.y = y
        self.xp = xp


class Game:
    """All the rules. main.py only draws what this object says."""

    def __init__(self, config, seed=None):
        self.config = config
        self.rng = random.Random(seed)
        self.reset()

    def reset(self):
        cfg = self.config
        hero = cfg["hero"]
        self.time = 0.0
        self.hero_x = 0.0
        self.hero_y = 0.0
        self.hero_hp = float(hero["hp"])
        self.hero_max_hp = float(hero["hp"])
        self.target_x = None
        self.target_y = None
        self.enemies = []
        self.sparks = []
        self.gems = []
        self.kills = 0
        self.game_over = False
        self.victory = False
        self.spawn_timer = 0.0
        self.last_hit = 0.0
        self.boss_spawned = False

        # growth
        self.xp = 0
        self.level = 1
        self.xp_needed = cfg["level_up_xp_first"]
        self.weapon_levels = {"spark_wand": 1}
        self.passive_levels = {}
        self.pending_level_ups = 0
        self.level_up_pending = False
        self.cards = []

        # weapons
        self.wand_timer = 0.0
        self.blade_angle = 0.0
        self.blade_positions = []
        self.ring_timer = 0.0
        self.ring_flash = -1.0  # time of the last pulse, for drawing

        # what happened this step, for main.py to draw and play
        self.events = []

    # --- input -------------------------------------------------------------
    def set_target(self, x, y):
        self.target_x = x
        self.target_y = y

    def stop(self):
        self.target_x = None
        self.target_y = None

    def choose(self, index):
        """Take card number index from the level-up screen and start walking again."""
        if not self.level_up_pending:
            return
        card = self.cards[index]
        kind = card["kind"]
        if kind == "heal":
            self.hero_hp = min(self.hero_max_hp,
                               self.hero_hp + self.config["heal_card_amount"])
        elif kind == "weapon":
            self.weapon_levels[card["key"]] = card["level"]
        else:
            old = self.passive_levels.get(card["key"], 0)
            self.passive_levels[card["key"]] = card["level"]
            heart = self.config["passives"]["big_heart"]
            if card["key"] == "big_heart":
                gained = card["level"] - old
                self.hero_max_hp += heart["max_hp"] * gained
                self.hero_hp = min(self.hero_max_hp, self.hero_hp + heart["heal"] * gained)
        self.pending_level_ups -= 1
        if self.pending_level_ups > 0:
            self._open_cards()
        else:
            self.level_up_pending = False
            self.cards = []

    # --- numbers that come from levels and items ---------------------------
    def hero_speed(self):
        boots = self.passive_levels.get("swift_boots", 0)
        pct = self.config["passives"]["swift_boots"]["speed_pct"]
        return float(self.config["hero"]["speed"]) * (1.0 + pct * boots)

    def magnet_radius(self):
        magnet = self.passive_levels.get("magnet", 0)
        extra = self.config["passives"]["magnet"]["magnet_radius"]
        return float(self.config["hero"]["magnet_radius"]) + extra * magnet

    def weapon_stats(self, name):
        """The weapon's numbers at the level the hero has it at."""
        base = self.config["weapons"][name]
        level = self.weapon_levels.get(name, 0)
        up = base.get("level_up", {})
        stats = dict(base)
        stats["level"] = level
        extra = sum(1 for at in up.get("extra_count_at_levels", []) if level >= at)
        if "count" in base:
            stats["count"] = base["count"] + extra
        if "damage" in base and "damage" in up:
            stats["damage"] = base["damage"] + up["damage"] * (level - 1)
        if "interval" in base and "interval" in up:
            stats["interval"] = base["interval"] + up["interval"] * (level - 1)
        if "radius" in base and "radius" in up:
            stats["radius"] = base["radius"] + up["radius"] * (level - 1)
        return stats

    # --- one step ----------------------------------------------------------
    def step(self, dt=DT):
        if self.game_over or self.level_up_pending:
            return
        self.time += dt
        if self.time >= self.config["goal_time_seconds"]:
            # you made it to 2:00
            self.time = self.config["goal_time_seconds"]
            self.victory = True
            self.game_over = True
            self.events.append(("end", True))
            return
        self._move_hero(dt)
        self._spawn(dt)
        self._move_enemies(dt)
        self._move_sparks(dt)
        self._update_wand(dt)
        self._update_blades(dt)
        self._update_ring(dt)
        self._move_gems(dt)

    def _move_hero(self, dt):
        if self.target_x is None:
            return
        dx = self.target_x - self.hero_x
        dy = self.target_y - self.hero_y
        d = math.hypot(dx, dy)
        deadzone = self.config["hero"]["mouse_deadzone_px"]
        if d <= deadzone:
            return
        step = self.hero_speed() * dt
        if step >= d:
            self.hero_x, self.hero_y = self.target_x, self.target_y
        else:
            self.hero_x += dx / d * step
            self.hero_y += dy / d * step

    def _current_wave(self):
        wave = self.config["waves"][0]
        for w in self.config["waves"]:
            if self.time >= w["from"]:
                wave = w
        return wave

    def _spawn(self, dt):
        self.spawn_timer += dt
        if self.spawn_timer + EPS < self.config["spawn_check_interval"]:
            return
        self.spawn_timer = 0.0
        wave = self._current_wave()
        stats = self.config["enemies"]
        if wave.get("boss") and not self.boss_spawned:
            self.boss_spawned = True
            self.enemies.append(self._new_enemy(wave["boss"], stats))
        types = wave["types"]
        to_spawn = min(wave["min_alive"] - len(self.enemies),
                       self.config["spawn_max_per_check"],
                       self.config["max_alive_enemies"] - len(self.enemies))
        for _ in range(max(0, to_spawn)):
            kind = types[self.rng.randrange(len(types))]
            self.enemies.append(self._new_enemy(kind, stats))

    def _point_on_spawn_circle(self):
        angle = self.rng.random() * 2 * math.pi
        r = self.config["spawn_circle_radius"]
        return self.hero_x + math.cos(angle) * r, self.hero_y + math.sin(angle) * r

    def _new_enemy(self, kind, stats):
        """A fresh enemy of this kind on the circle just outside the screen."""
        x, y = self._point_on_spawn_circle()
        return Enemy(kind, stats[kind], x, y)

    def _move_enemies(self, dt):
        hero_r = self.config["hero"]["hit_radius"]
        interval = self.config["contact_damage_cooldown"]
        despawn = self.config["despawn_distance"]
        kept = []
        for e in self.enemies:
            e.contact_ready = max(0.0, e.contact_ready - dt)
            e.blade_ready = [max(0.0, t - dt) for t in e.blade_ready]
            d = _dist(e.x, e.y, self.hero_x, self.hero_y)
            if e.boss:
                # the boss is never removed: it is pulled back to the spawn circle
                if d > self.config["boss_return_distance"]:
                    e.x, e.y = self._point_on_spawn_circle()
                    d = _dist(e.x, e.y, self.hero_x, self.hero_y)
            elif d > despawn:
                continue
            if d > 0.0001:
                move = e.speed * dt
                if move >= d:
                    e.x, e.y = self.hero_x, self.hero_y
                    d = 0.0
                else:
                    e.x += (self.hero_x - e.x) / d * move
                    e.y += (self.hero_y - e.y) / d * move
            if d <= hero_r + e.radius and e.contact_ready <= EPS:
                self.hero_hp -= e.damage
                e.contact_ready = interval
                self.last_hit = self.time
                self.events.append(("hurt", e.damage))
                if self.hero_hp <= 0:
                    self.hero_hp = 0.0
                    self.game_over = True
                    self.events.append(("end", False))
            kept.append(e)
        self.enemies = kept

    def _damage(self, enemy, amount):
        enemy.hp -= amount
        self.events.append(("damage", enemy.x, enemy.y, amount))
        if enemy.hp <= 0 and enemy in self.enemies:
            self.enemies.remove(enemy)
            self.kills += 1
            self.events.append(("flash", enemy.x, enemy.y))
            if enemy.xp > 0:
                self.gems.append(Gem(enemy.x, enemy.y, enemy.xp))

    def _update_wand(self, dt):
        if "spark_wand" not in self.weapon_levels:
            return
        wand = self.weapon_stats("spark_wand")
        self.wand_timer += dt
        if self.wand_timer + EPS < wand["interval"]:
            return
        if not self.enemies:
            return
        self.wand_timer = 0.0
        by_distance = sorted(self.enemies,
                             key=lambda e: _dist(e.x, e.y, self.hero_x, self.hero_y))
        for i in range(wand["count"]):
            target = by_distance[i % len(by_distance)]
            d = _dist(target.x, target.y, self.hero_x, self.hero_y)
            if d < 0.0001:
                dx, dy = 1.0, 0.0
            else:
                dx, dy = (target.x - self.hero_x) / d, (target.y - self.hero_y) / d
            self.sparks.append(Spark(self.hero_x, self.hero_y,
                                     dx * wand["speed"], dy * wand["speed"],
                                     wand["damage"], wand["radius"]))

    def _update_blades(self, dt):
        if "spin_blades" not in self.weapon_levels:
            self.blade_positions = []
            return
        blades = self.weapon_stats("spin_blades")
        self.blade_angle = (self.blade_angle + 2 * math.pi / blades["turn_seconds"] * dt) \
            % (2 * math.pi)
        count = blades["count"]
        positions = []
        for i in range(count):
            angle = self.blade_angle + i * 2 * math.pi / count
            bx = self.hero_x + math.cos(angle) * blades["orbit_radius"]
            by = self.hero_y + math.sin(angle) * blades["orbit_radius"]
            positions.append((bx, by))
            for e in list(self.enemies):
                if len(e.blade_ready) <= i:
                    e.blade_ready.extend([0.0] * (i + 1 - len(e.blade_ready)))
                if e.blade_ready[i] > EPS:
                    continue
                if _dist(bx, by, e.x, e.y) <= blades["radius"] + e.radius:
                    e.blade_ready[i] = blades["hit_cooldown"]
                    self._damage(e, blades["damage"])
        self.blade_positions = positions

    def _update_ring(self, dt):
        if "holy_ring" not in self.weapon_levels:
            return
        ring = self.weapon_stats("holy_ring")
        self.ring_timer += dt
        if self.ring_timer + EPS < ring["interval"]:
            return
        self.ring_timer = 0.0
        self.ring_flash = self.time
        for e in list(self.enemies):
            if _dist(e.x, e.y, self.hero_x, self.hero_y) <= ring["radius"] + e.radius:
                self._damage(e, ring["damage"])

    def _move_sparks(self, dt):
        live = []
        for s in self.sparks:
            s.x += s.vx * dt
            s.y += s.vy * dt
            hit = None
            for e in self.enemies:
                if _dist(s.x, s.y, e.x, e.y) <= s.radius + e.radius:
                    hit = e
                    break
            if hit is None:
                live.append(s)
                continue
            self._damage(hit, s.damage)
        self.sparks = live

    def _move_gems(self, dt):
        magnet = self.magnet_radius()
        speed = self.config["gem_speed"]
        pick_up = self.config["hero"]["hit_radius"]
        kept = []
        for g in self.gems:
            d = _dist(g.x, g.y, self.hero_x, self.hero_y)
            if d > magnet:
                kept.append(g)
                continue
            if d <= pick_up:
                self.events.append(("gem", g.xp))
                self._gain_xp(g.xp)
                continue
            move = min(speed * dt, d)
            g.x += (self.hero_x - g.x) / d * move
            g.y += (self.hero_y - g.y) / d * move
            kept.append(g)
        self.gems = kept

    # --- XP and cards ------------------------------------------------------
    def _gain_xp(self, amount):
        self.xp += amount
        while self.xp >= self.xp_needed:
            self.xp -= self.xp_needed
            self.level += 1
            self.xp_needed += self.config["level_up_xp_step"]
            self.pending_level_ups += 1
            self.events.append(("level", self.level))
        if self.pending_level_ups and not self.level_up_pending:
            self._open_cards()

    def _card(self, kind, key, level):
        if kind == "heal":
            return {"kind": "heal", "key": None, "level": None,
                    "name": "Heal",
                    "text": "Heal %d HP" % self.config["heal_card_amount"]}
        item = self.config["weapons"][key] if kind == "weapon" else self.config["passives"][key]
        return {"kind": kind, "key": key, "level": level,
                "name": item["name"], "text": item["card_text"]}

    def _open_cards(self):
        options = []
        max_level = self.config["max_item_level"]
        for key in self.config["weapons"]:
            level = self.weapon_levels.get(key)
            if level is None:
                if len(self.weapon_levels) < self.config["max_weapons"]:
                    options.append(self._card("weapon", key, 1))
            elif level < max_level:
                options.append(self._card("weapon", key, level + 1))
        for key in self.config["passives"]:
            level = self.passive_levels.get(key, 0)
            if level < max_level:
                options.append(self._card("passive", key, level + 1))
        self.rng.shuffle(options)
        self.cards = options[:3]
        while len(self.cards) < 3:
            self.cards.append(self._card("heal", None, None))
        self.level_up_pending = True
