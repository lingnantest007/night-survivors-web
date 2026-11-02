"""Tests for the rules in rules.py only. They read the numbers from data/game.json."""

import json
import math
import os
import unittest

import rules

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT = os.path.dirname(HERE)
CFG_PATH = os.path.join(PROJECT, "data", "game.json")

with open(CFG_PATH, "r", encoding="utf-8") as handle:
    CFG = json.load(handle)

BIG_HP = 10 ** 6
FROZEN = -10 ** 9  # a timer this far back can never reach its interval


def make_game(seed=1, immortal=True):
    game = rules.Game(CFG, seed=seed)
    game.stop()
    if immortal:
        game.hero_hp = BIG_HP
        game.hero_max_hp = BIG_HP
    return game


def run(game, frames, auto_pick=False):
    for _ in range(frames):
        game.step(rules.DT)
        if game.game_over:
            return
        if auto_pick and game.level_up_pending:
            game.choose(0)


def put_bat(game, x=None, y=None):
    """One bat right next to the hero unless we say where."""
    stats = CFG["enemies"]["bat"]
    bat = rules.Enemy("bat", stats,
                      game.hero_x + 5 if x is None else x,
                      game.hero_y if y is None else y)
    game.enemies.append(bat)
    return bat


class SpawningTests(unittest.TestCase):
    def test_first_second_reaches_the_wave_minimum(self):
        game = make_game(seed=3)
        run(game, 60)
        # 12 are wanted, but only 8 may appear in one second
        self.assertEqual(len(game.enemies), CFG["spawn_max_per_check"])
        run(game, 60)  # the next 1 s check tops the count up to the minimum
        self.assertEqual(len(game.enemies), CFG["waves"][0]["min_alive"])

    def test_at_most_eight_new_enemies_per_second(self):
        game = make_game(seed=4)
        run(game, 60)
        game.enemies.clear()
        game.sparks.clear()
        run(game, 60)
        self.assertEqual(len(game.enemies), CFG["spawn_max_per_check"])

    def test_never_more_than_the_max_alive(self):
        crowded = json.loads(json.dumps(CFG))
        for wave in crowded["waves"]:
            wave["min_alive"] = crowded["max_alive_enemies"] + 50
        game = rules.Game(crowded, seed=5)
        game.hero_hp = BIG_HP
        game.hero_max_hp = BIG_HP
        game.wand_timer = FROZEN  # no kills, so only the alive cap matters
        game.stop()
        run(game, 60 * 40)
        self.assertEqual(len(game.enemies), CFG["max_alive_enemies"])

    def test_enemies_appear_on_the_circle_380_px_away(self):
        game = make_game(seed=6)
        run(game, 60)
        self.assertTrue(game.enemies)
        one_step = CFG["enemies"]["bat"]["speed"] * rules.DT
        for bat in game.enemies:
            d = math.hypot(bat.x - game.hero_x, bat.y - game.hero_y)
            self.assertLessEqual(d, CFG["spawn_circle_radius"] + 1e-6)
            self.assertGreaterEqual(d, CFG["spawn_circle_radius"] - one_step - 1e-6)

    def test_enemy_far_from_the_hero_is_removed(self):
        game = make_game(seed=7)
        game.spawn_timer = FROZEN
        game.enemies.clear()
        put_bat(game, x=game.hero_x + CFG["despawn_distance"] + 50)
        run(game, 5)
        self.assertEqual(game.enemies, [])


class ContactDamageTests(unittest.TestCase):
    def test_touching_enemy_damages_the_hero(self):
        game = make_game(seed=8, immortal=False)
        game.spawn_timer = FROZEN
        game.wand_timer = FROZEN
        game.enemies.clear()
        put_bat(game, x=game.hero_x, y=game.hero_y)
        run(game, 30)
        self.assertLess(game.hero_hp, CFG["hero"]["hp"])
        self.assertGreater(game.hero_hp, 0)

    def test_the_same_enemy_hurts_at_most_once_per_half_second(self):
        game = make_game(seed=9, immortal=False)
        game.spawn_timer = FROZEN
        game.wand_timer = FROZEN
        game.enemies.clear()
        put_bat(game, x=game.hero_x, y=game.hero_y)
        run(game, 1)
        after_one_hit = game.hero_hp
        self.assertEqual(after_one_hit, CFG["hero"]["hp"] - CFG["enemies"]["bat"]["damage"])
        run(game, 27)  # still inside the 0.5 s cooldown
        self.assertEqual(game.hero_hp, after_one_hit)
        run(game, 4)  # now the cooldown is over
        self.assertEqual(game.hero_hp, after_one_hit - CFG["enemies"]["bat"]["damage"])

    def test_hp_reaching_zero_ends_the_game(self):
        game = make_game(seed=10, immortal=False)
        game.spawn_timer = FROZEN
        game.wand_timer = FROZEN
        game.hero_hp = 1
        put_bat(game, x=game.hero_x, y=game.hero_y)
        run(game, 1)
        self.assertTrue(game.game_over)
        self.assertEqual(game.hero_hp, 0)


class SparkWandTests(unittest.TestCase):
    def test_wand_shoots_once_per_interval(self):
        game = make_game(seed=11)
        game.spawn_timer = FROZEN
        game.enemies.clear()
        put_bat(game, x=game.hero_x + 200)
        game.sparks.clear()
        run(game, 48)  # 0.8 s
        self.assertEqual(len(game.sparks), 1)
        spark = game.sparks[0]
        self.assertAlmostEqual(math.hypot(spark.vx, spark.vy),
                               CFG["weapons"]["spark_wand"]["speed"])

    def test_a_spark_kills_a_bat_and_counts_one_kill(self):
        game = make_game(seed=12)
        game.spawn_timer = FROZEN
        game.enemies.clear()
        bat = put_bat(game, x=game.hero_x + 30)
        run(game, 60)
        self.assertEqual(game.kills, 1)
        self.assertEqual(game.xp, CFG["enemies"]["bat"]["xp"])  # the gem reached him
        self.assertNotIn(bat, game.enemies)

    def test_no_enemies_means_no_sparks(self):
        game = make_game(seed=13)
        game.spawn_timer = FROZEN
        game.enemies.clear()
        run(game, 120)
        self.assertEqual(game.sparks, [])


class MovementTests(unittest.TestCase):
    def test_hero_walks_toward_the_target_at_his_speed(self):
        game = make_game(seed=14)
        game.spawn_timer = FROZEN
        game.set_target(240, 0)
        run(game, 60)
        self.assertAlmostEqual(game.hero_x, CFG["hero"]["speed"], places=4)

    def test_hero_stops_inside_the_deadzone(self):
        game = make_game(seed=15)
        game.spawn_timer = FROZEN
        game.set_target(CFG["hero"]["mouse_deadzone_px"] - 7, 0)
        run(game, 60)
        self.assertEqual(game.hero_x, 0.0)

    def test_hero_walks_straight_up_too(self):
        game = make_game(seed=16)
        game.spawn_timer = FROZEN
        game.set_target(0, 300)
        run(game, 60)
        self.assertAlmostEqual(game.hero_y, CFG["hero"]["speed"], places=4)


class GemTests(unittest.TestCase):
    def test_a_dead_enemy_drops_a_gem_worth_its_xp(self):
        game = make_game(seed=20)
        game.spawn_timer = FROZEN
        game.enemies.clear()
        bat = put_bat(game, x=game.hero_x + 200)
        game._damage(bat, 999)
        self.assertEqual(game.enemies, [])
        self.assertEqual(game.kills, 1)
        self.assertEqual(len(game.gems), 1)
        self.assertEqual(game.gems[0].xp, CFG["enemies"]["bat"]["xp"])
        self.assertEqual(game.gems[0].x, bat.x)

    def test_a_boss_drops_nothing(self):
        game = make_game(seed=20)
        game.spawn_timer = FROZEN
        game.enemies.clear()
        stats = CFG["enemies"]["demon"]
        boss = rules.Enemy("demon", stats, game.hero_x + 100, game.hero_y)
        game.enemies.append(boss)
        game._damage(boss, 10 ** 6)
        self.assertEqual(game.gems, [])
        self.assertEqual(game.kills, 1)

    def test_a_gem_in_the_magnet_radius_flys_to_the_hero(self):
        game = make_game(seed=21)
        game.spawn_timer = FROZEN
        game.enemies.clear()
        magnet = CFG["hero"]["magnet_radius"]
        game.gems.append(rules.Gem(game.hero_x + magnet - 5, game.hero_y, 1))
        run(game, 1)
        self.assertLess(abs(game.gems[0].x - game.hero_x), magnet - 5)

    def test_a_gem_outside_the_magnet_radius_stays(self):
        game = make_game(seed=22)
        game.spawn_timer = FROZEN
        game.enemies.clear()
        far = CFG["hero"]["magnet_radius"] + 40
        game.gems.append(rules.Gem(game.hero_x + far, game.hero_y, 1))
        run(game, 30)
        self.assertAlmostEqual(game.gems[0].x, game.hero_x + far, places=6)

    def test_a_reached_gem_adds_its_xp(self):
        game = make_game(seed=23)
        game.spawn_timer = FROZEN
        game.enemies.clear()
        game.gems.append(rules.Gem(game.hero_x, game.hero_y, 2))
        run(game, 1)
        self.assertEqual(game.gems, [])
        self.assertEqual(game.xp, 2)


class LevelUpTests(unittest.TestCase):
    def test_xp_needed_is_5_then_3_more_each_level(self):
        game = make_game(seed=24)
        self.assertEqual(game.xp_needed, CFG["level_up_xp_first"])
        first = game.xp_needed
        game._gain_xp(first)
        self.assertEqual(game.level, 2)
        self.assertEqual(game.xp_needed, first + CFG["level_up_xp_step"])

    def test_level_up_pauses_and_shows_three_cards(self):
        game = make_game(seed=25)
        game.spawn_timer = FROZEN
        game.enemies.clear()
        game.gems.append(rules.Gem(game.hero_x, game.hero_y, game.xp_needed))
        run(game, 1)
        self.assertTrue(game.level_up_pending)
        self.assertEqual(len(game.cards), 3)

    def test_step_does_nothing_while_a_card_is_open(self):
        game = make_game(seed=26)
        game.level_up_pending = True
        game.cards = [game._card("heal", None, None)] * 3
        before = (game.time, len(game.enemies))
        game.spawn_timer = FROZEN
        run(game, 60)
        self.assertEqual((game.time, len(game.enemies)), before)

    def test_choosing_a_card_starts_the_game_again(self):
        game = make_game(seed=27)
        game.level_up_pending = True
        game.cards = [game._card("heal", None, None)] * 3
        game.pending_level_ups = 1
        game.hero_hp = 10
        game.choose(0)
        self.assertFalse(game.level_up_pending)
        self.assertEqual(game.hero_hp, 10 + CFG["heal_card_amount"])

    def test_two_levels_at_once_need_two_choices(self):
        game = make_game(seed=28)
        game.level_up_pending = True
        game.cards = [game._card("heal", None, None)] * 3
        game.pending_level_ups = 2
        game.choose(0)
        self.assertTrue(game.level_up_pending)
        self.assertEqual(len(game.cards), 3)
        game.choose(0)
        self.assertFalse(game.level_up_pending)


class CardOfferTests(unittest.TestCase):
    def test_a_new_weapon_is_offered_only_below_three(self):
        game = make_game(seed=29)
        game.weapon_levels = {"spark_wand": 1, "spin_blades": 1, "holy_ring": 1}
        game._open_cards()
        self.assertEqual(len(game.weapon_levels), CFG["max_weapons"])
        for card in game.cards:
            self.assertNotIn(card["key"], [k for k in CFG["weapons"]
                                           if k not in game.weapon_levels])

    def test_nothing_is_offered_at_level_5(self):
        game = make_game(seed=30)
        max_level = CFG["max_item_level"]
        game.weapon_levels = {k: max_level for k in CFG["weapons"]}
        game.passive_levels = {k: max_level for k in CFG["passives"]}
        game._open_cards()
        for card in game.cards:
            self.assertEqual(card["kind"], "heal")

    def test_a_maxed_weapon_never_appears(self):
        game = make_game(seed=31)
        max_level = CFG["max_item_level"]
        game.weapon_levels = {"spark_wand": max_level, "spin_blades": 1}
        game._open_cards()
        for card in game.cards:
            if card["key"] == "spark_wand":
                self.fail("Spark Wand is already at level %d" % max_level)


class PassiveTests(unittest.TestCase):
    def test_swift_boots_make_the_hero_walk_faster(self):
        game = make_game(seed=32)
        base = game.hero_speed()
        game.passive_levels["swift_boots"] = 2
        pct = CFG["passives"]["swift_boots"]["speed_pct"]
        self.assertAlmostEqual(game.hero_speed(), base * (1 + 2 * pct))

    def test_magnet_widens_the_pick_up_radius(self):
        game = make_game(seed=33)
        base = game.magnet_radius()
        game.passive_levels["magnet"] = 3
        self.assertEqual(game.magnet_radius(),
                         base + 3 * CFG["passives"]["magnet"]["magnet_radius"])

    def test_big_heart_gives_more_hp_and_heals(self):
        game = make_game(seed=34, immortal=False)
        game.hero_hp = 30
        game.level_up_pending = True
        game.pending_level_ups = 1
        game.cards = [game._card("passive", "big_heart", 1)] * 3
        game.choose(0)
        heart = CFG["passives"]["big_heart"]
        self.assertEqual(game.hero_max_hp, CFG["hero"]["hp"] + heart["max_hp"])
        self.assertEqual(game.hero_hp, 30 + heart["heal"])


class WeaponTests(unittest.TestCase):
    def test_spark_wand_level_5_shoots_three_sparks(self):
        game = make_game(seed=35)
        game.spawn_timer = FROZEN
        game.enemies.clear()
        game.weapon_levels["spark_wand"] = 5
        for i in range(3):
            put_bat(game, x=game.hero_x + 600 + i * 20)
        game.sparks.clear()
        interval = game.weapon_stats("spark_wand")["interval"]
        run(game, int(round(interval / rules.DT)))
        self.assertEqual(len(game.sparks), 3)

    def test_spin_blades_hit_an_enemy_and_respect_their_cooldown(self):
        game = make_game(seed=36)
        game.spawn_timer = FROZEN
        game.enemies.clear()
        game.wand_timer = FROZEN
        game.weapon_levels["spin_blades"] = 1
        blades = game.weapon_stats("spin_blades")
        # park a bat on the blade circle and stop it moving
        bat = put_bat(game, x=game.hero_x + blades["orbit_radius"], y=game.hero_y)
        bat.speed = 0.0
        run(game, 90)  # one full turn is 1.5 s
        self.assertLess(bat.hp, CFG["enemies"]["bat"]["hp"])
        hp_after = bat.hp
        run(game, 20)
        self.assertEqual(bat.hp, hp_after)

    def test_spin_blades_gain_blades_at_levels_2_and_4(self):
        game = make_game(seed=37)
        game.weapon_levels["spin_blades"] = 1
        self.assertEqual(game.weapon_stats("spin_blades")["count"], 2)
        game.weapon_levels["spin_blades"] = 4
        self.assertEqual(game.weapon_stats("spin_blades")["count"], 4)

    def test_holy_ring_hurts_every_enemy_inside_it(self):
        game = make_game(seed=38)
        game.spawn_timer = FROZEN
        game.enemies.clear()
        game.wand_timer = FROZEN
        game.weapon_levels["holy_ring"] = 1
        ring = game.weapon_stats("holy_ring")
        bats = [put_bat(game, x=game.hero_x + ring["radius"] - 15, y=game.hero_y),
                put_bat(game, x=game.hero_x - ring["radius"] + 15, y=game.hero_y)]
        outside = put_bat(game, x=game.hero_x + ring["radius"] + 60, y=game.hero_y)
        outside.speed = 0.0
        for bat in bats:
            bat.speed = 0.0
        run(game, 30)  # 0.5 s, one pulse
        for bat in bats:
            self.assertEqual(bat.hp, CFG["enemies"]["bat"]["hp"] - ring["damage"])
        self.assertEqual(outside.hp, CFG["enemies"]["bat"]["hp"])


class WaveTests(unittest.TestCase):
    """The spawn table: which enemies, and how many, at each time."""

    def kinds_after(self, seconds, seed=40, frames=120):
        game = make_game(seed=seed)
        game.time = seconds
        game.enemies.clear()
        game.sparks.clear()
        run(game, frames)
        return {e.kind for e in game.enemies}, game

    def test_wave_one_is_only_bats(self):
        kinds, _ = self.kinds_after(0)
        self.assertEqual(kinds, {"bat"})

    def test_the_wave_types_change_with_the_time(self):
        for wave in CFG["waves"]:
            kinds, _ = self.kinds_after(wave["from"] + 1)
            allowed = set(wave["types"])
            if wave.get("boss"):
                allowed.add(wave["boss"])
            self.assertTrue(kinds, "no enemies in the wave at %ds" % wave["from"])
            self.assertTrue(kinds <= allowed,
                            "%s is not allowed at %ds (only %s)"
                            % (sorted(kinds - allowed), wave["from"], sorted(allowed)))

    def test_more_enemies_are_wanted_later(self):
        mins = [w["min_alive"] for w in CFG["waves"]]
        self.assertEqual(mins, sorted(mins))
        self.assertEqual(mins[0], 12)

    def test_slime_and_ghost_come_with_their_waves(self):
        _, game = self.kinds_after(31)
        self.assertTrue(any(e.kind == "slime" for e in game.enemies))
        _, game = self.kinds_after(46)
        self.assertTrue(any(e.kind == "ghost" for e in game.enemies))


class BossTests(unittest.TestCase):
    def test_the_boss_appears_once_at_its_time(self):
        game = make_game(seed=41)
        game.time = CFG["waves"][6]["from"]  # 1:30
        game.enemies.clear()
        run(game, 60)
        bosses = [e for e in game.enemies if e.boss]
        self.assertEqual(len(bosses), 1)
        self.assertEqual(bosses[0].kind, "demon")
        self.assertEqual(bosses[0].hp, CFG["enemies"]["demon"]["hp"])

    def test_the_boss_does_not_come_back_after_it_dies(self):
        game = make_game(seed=42)
        game.time = CFG["waves"][6]["from"]
        game.enemies.clear()
        run(game, 60)
        game.enemies = [e for e in game.enemies if not e.boss]
        run(game, 600)
        self.assertFalse(any(e.boss for e in game.enemies))

    def test_the_boss_is_pulled_back_instead_of_removed(self):
        game = make_game(seed=43)
        game.spawn_timer = FROZEN
        game.enemies.clear()
        boss = rules.Enemy("demon", CFG["enemies"]["demon"], 0, 0)
        game.enemies.append(boss)
        boss.x = game.hero_x + CFG["despawn_distance"] + 100  # past even the normal despawn line
        boss.speed = 0.0
        run(game, 1)
        self.assertIn(boss, game.enemies)
        d = math.hypot(boss.x - game.hero_x, boss.y - game.hero_y)
        self.assertAlmostEqual(d, CFG["spawn_circle_radius"], places=6)

    def test_a_boss_far_but_under_the_return_line_stays(self):
        game = make_game(seed=44)
        game.spawn_timer = FROZEN
        game.enemies.clear()
        boss = rules.Enemy("demon", CFG["enemies"]["demon"], 0, 0)
        boss.speed = 0.0
        game.enemies.append(boss)
        boss.x = game.hero_x + CFG["boss_return_distance"] - 50
        run(game, 5)
        self.assertIn(boss, game.enemies)
        self.assertGreater(boss.x, 0.0)


class WinAndLoseTests(unittest.TestCase):
    def test_surviving_to_the_goal_time_is_a_victory(self):
        game = make_game(seed=45)
        game.hero_hp = 10 ** 9
        game.hero_max_hp = 10 ** 9
        run(game, int(CFG["goal_time_seconds"] / rules.DT) + 5, auto_pick=True)
        self.assertTrue(game.victory)
        self.assertTrue(game.game_over)
        self.assertEqual(game.time, CFG["goal_time_seconds"])

    def test_losing_hp_is_a_defeat_not_a_victory(self):
        game = make_game(seed=46, immortal=False)
        game.hero_hp = 1
        put_bat(game, x=game.hero_x, y=game.hero_y)
        game.wand_timer = FROZEN
        run(game, 1)
        self.assertTrue(game.game_over)
        self.assertFalse(game.victory)

    def test_the_game_stops_after_a_victory(self):
        game = make_game(seed=47)
        game.time = CFG["goal_time_seconds"] - rules.DT
        game.enemies.clear()
        run(game, 3)
        self.assertTrue(game.victory)
        enemies_after = list(game.enemies)
        run(game, 60)
        self.assertEqual(game.enemies, enemies_after)


class RestartTests(unittest.TestCase):
    def test_reset_starts_a_new_run(self):
        game = make_game(seed=17, immortal=False)
        game.spawn_timer = FROZEN
        game.wand_timer = FROZEN
        game.hero_hp = 1
        put_bat(game, x=game.hero_x, y=game.hero_y)
        run(game, 1)
        self.assertTrue(game.game_over)
        game.reset()
        self.assertFalse(game.game_over)
        self.assertEqual(game.enemies, [])
        self.assertEqual(game.sparks, [])
        self.assertEqual(game.hero_hp, CFG["hero"]["hp"])
        self.assertEqual(game.time, 0.0)
        self.assertEqual(game.kills, 0)
        self.assertEqual(game.gems, [])
        self.assertEqual(game.xp, 0)
        self.assertEqual(game.level, 1)
        self.assertEqual(game.weapon_levels, {"spark_wand": 1})
        self.assertEqual(game.passive_levels, {})
        self.assertFalse(game.level_up_pending)
        self.assertFalse(game.victory)
        self.assertFalse(game.boss_spawned)


class EventTests(unittest.TestCase):
    """rules.py cannot use pygame, so it leaves a list of plain tuples instead.
    main.py turns that list into sounds and damage numbers."""

    def quiet_game(self, seed, immortal=True):
        game = make_game(seed=seed, immortal=immortal)
        game.spawn_timer = FROZEN
        game.wand_timer = FROZEN
        game.enemies.clear()
        return game

    def test_events_start_empty(self):
        self.quiet_game(60)
        self.assertEqual(self.quiet_game(60).events, [])

    def test_a_quiet_second_makes_no_events(self):
        game = self.quiet_game(61)
        run(game, 60)
        self.assertEqual(game.events, [])

    def test_a_hit_makes_a_damage_event_with_its_place(self):
        game = self.quiet_game(62)
        bat = put_bat(game, x=game.hero_x + 200)
        game.events.clear()
        game._damage(bat, 5)
        self.assertEqual(game.events, [("damage", bat.x, bat.y, 5)])

    def test_a_kill_adds_a_flash_event(self):
        game = self.quiet_game(63)
        bat = put_bat(game, x=game.hero_x + 200)
        game.events.clear()
        game._damage(bat, 999)
        self.assertEqual([e[0] for e in game.events], ["damage", "flash"])
        self.assertEqual(game.events[1], ("flash", bat.x, bat.y))

    def test_a_boss_death_flashes_but_drops_no_gem_event(self):
        game = self.quiet_game(64)
        stats = CFG["enemies"]["demon"]
        boss = rules.Enemy("demon", stats, game.hero_x + 100, game.hero_y)
        game.enemies.append(boss)
        game.events.clear()
        game._damage(boss, 10 ** 6)
        self.assertEqual([e[0] for e in game.events], ["damage", "flash"])

    def test_a_collected_gem_makes_a_gem_event(self):
        game = self.quiet_game(65)
        game.gems.append(rules.Gem(game.hero_x, game.hero_y, 2))
        run(game, 1)
        self.assertIn(("gem", 2), game.events)

    def test_a_level_up_makes_a_level_event(self):
        game = self.quiet_game(66)
        game._gain_xp(CFG["level_up_xp_first"])
        self.assertIn(("level", 2), game.events)

    def test_being_hurt_says_how_much(self):
        game = self.quiet_game(67, immortal=False)
        put_bat(game, x=game.hero_x, y=game.hero_y)
        run(game, 1)
        self.assertIn(("hurt", CFG["enemies"]["bat"]["damage"]), game.events)

    def test_dying_makes_an_end_event(self):
        game = self.quiet_game(68, immortal=False)
        game.hero_hp = 1
        put_bat(game, x=game.hero_x, y=game.hero_y)
        run(game, 1)
        self.assertTrue(game.game_over)
        self.assertIn(("end", False), game.events)

    def test_winning_makes_an_end_event(self):
        game = self.quiet_game(69)
        game.time = CFG["goal_time_seconds"] - rules.DT
        run(game, 2)
        self.assertIn(("end", True), game.events)

    def test_the_events_stay_until_the_caller_clears_them(self):
        game = self.quiet_game(70)
        bat = put_bat(game, x=game.hero_x + 200)
        game._damage(bat, 1)
        game.events.clear()
        self.assertEqual(game.events, [])

    def test_reset_clears_the_events(self):
        game = self.quiet_game(71)
        bat = put_bat(game, x=game.hero_x + 200)
        game._damage(bat, 1)
        self.assertNotEqual(game.events, [])
        game.reset()
        self.assertEqual(game.events, [])


if __name__ == "__main__":
    unittest.main()
