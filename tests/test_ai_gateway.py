

import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from game_ai.adapters.base import (
    PlanningRequest,
)
from game_ai.commands import CommandGateway
from game_ai.contracts import Command, CommandBatch
from game_ai.observation import build_observation
from tests.support.ai import _Player, _unit


class TestInformationBoundaryAndGateway(unittest.TestCase):
    @staticmethod
    def _colony_fixture(*, population=50, unit_count=1):
        from entities import Moon, Planet, PlanetType

        player = _Player(1, 1)
        units = [_unit(10 + index, player) for index in range(unit_count)]
        for unit in units:
            from geometry import Position
            unit.position = Position(2000, 0)  # Loading is pending travel in this fixture.
            unit.colony_component = SimpleNamespace(
                population_cargo=0,
                max_cargo=100,
            )
        source = Planet((0, 0), "Sol", next(iter(PlanetType)))
        source.owner = player
        source.population = population
        target = Moon((1, 0), "Sol")
        bodies = {source.id: source, target.id: target}

        class Galaxy:
            systems = {}

            def __init__(self):
                self.bodies = bodies

            def get_unit_by_id(self, unit_id):
                return next((unit for unit in units if unit.id == unit_id), None)

            def get_celestial_body_by_id(self, body_id):
                return self.bodies.get(body_id)

        game = SimpleNamespace(
            galaxy=Galaxy(),
            sidebar_needs_update=False,
            visibility_dirty=False,
        )
        return player, units, source, target, game

    @staticmethod
    def _inhibitor_fixture(
        *, positions=((0, 0),), active_ids=(), static_zones=()
    ):
        from geometry import Circle, Position
        from unit_components import HyperspaceInhibitionFieldEmitter

        player = _Player(1, 1)
        units = [_unit(10 + index, player) for index in range(len(positions))]
        for unit, position in zip(units, positions):
            unit.position = Position(*position)
            component = HyperspaceInhibitionFieldEmitter(unit, radius=100.0)
            unit.inhibitor_component = component
            unit.components = {HyperspaceInhibitionFieldEmitter: component}

        hex_obj = SimpleNamespace(
            boundary_circle=Circle(Position(0, 0), 500.0),
            static_inhibition_zones=list(static_zones),
            dynamic_inhibition_zones={},
            celestial_bodies=[],
            units=units,
            minefields=[],
        )
        hex_obj.get_all_inhibition_zones = lambda: (
            hex_obj.static_inhibition_zones
            + list(hex_obj.dynamic_inhibition_zones.values())
        )
        for unit in units:
            if unit.id in active_ids:
                unit.inhibitor_component.turn_on()
                hex_obj.dynamic_inhibition_zones[unit.id] = Circle(
                    unit.position, unit.inhibitor_component.radius
                )

        system = SimpleNamespace(
            position=Position(0, 0),
            radius=1,
            hexes={(0, 0): hex_obj},
        )

        class Galaxy:
            systems = {"Sol": system}
            system_graph = {"Sol": {}}

            @staticmethod
            def get_unit_by_id(unit_id):
                return next((unit for unit in units if unit.id == unit_id), None)

            @staticmethod
            def get_celestial_body_by_id(_body_id):
                return None

        game = SimpleNamespace(
            galaxy=Galaxy(),
            players=[player],
            turn_number=3,
            sidebar_needs_update=False,
            visibility_dirty=False,
        )
        return player, units, hex_obj, game

    def test_hidden_enemy_is_omitted_but_presence_is_retained(self):
        viewer = _Player(1, 1)
        enemy = _Player(2, 2)
        own_unit = _unit(10, viewer)
        hidden_unit = _unit(20, enemy)
        hex_obj = SimpleNamespace(
            celestial_bodies=[], units=[own_unit, hidden_unit], minefields=[]
        )
        system = SimpleNamespace(
            position=SimpleNamespace(x=1, y=2),
            radius=2,
            hexes={(0, 0): hex_obj},
        )
        galaxy = SimpleNamespace(systems={"Sol": system}, system_graph={"Sol": {}})
        game = SimpleNamespace(
            galaxy=galaxy,
            players=[viewer, enemy],
            turn_number=1,
        )
        snapshot = SimpleNamespace(
            visible_enemy_unit_ids=set(),
            presence_hexes={("Sol", (0, 0))},
        )
        with patch("visibility.VisibilityService.compute", return_value=snapshot):
            observation = build_observation(game, viewer)
        self.assertEqual([unit["id"] for unit in observation["units"]], [10])
        self.assertEqual(
            observation["undetailed_enemy_presence"],
            [{"system_name": "Sol", "hex_coord": [0, 0]}],
        )

    def test_batch_preflight_is_all_or_nothing(self):
        player = _Player(1, 1)
        unit = _unit(10, player)

        class Galaxy:
            def get_unit_by_id(self, unit_id):
                return unit if unit_id == 10 else None

        game = SimpleNamespace(galaxy=Galaxy(), sidebar_needs_update=False)
        batch = CommandBatch(
            commands=(
                Command(type="cancel_orders", unit_ids=(10,)),
                Command(type="cancel_orders", unit_ids=(999,)),
            )
        )
        result = CommandGateway(game).apply_batch(player, batch)
        self.assertFalse(result.accepted)
        self.assertEqual(unit.commander_component.clear_count, 0)

    def test_blocked_inhibitor_is_not_advertised_as_legal(self):
        from geometry import Circle, Position

        player, units, _hex_obj, game = self._inhibitor_fixture(
            static_zones=(Circle(Position(0, 0), 50.0),)
        )
        snapshot = SimpleNamespace(
            visible_enemy_unit_ids=set(),
            presence_hexes=set(),
        )
        with patch("visibility.VisibilityService.compute", return_value=snapshot):
            observation = build_observation(game, player)

        unit_view = observation["units"][0]
        inhibitor = unit_view["capability_details"]["inhibitor"]
        self.assertEqual(observation["schema_version"], 5)
        self.assertIn("toggle_inhibitor", unit_view["supported_commands"])
        self.assertNotIn("toggle_inhibitor", unit_view["legal_commands"])
        self.assertFalse(inhibitor["can_activate"])
        self.assertEqual(inhibitor["activation_blocker"], "inhibitor_overlap")
        self.assertEqual(
            unit_view["command_options"]["toggle_inhibitor"],
            {
                "current_state": "inactive",
                "resulting_state": "active",
                "available": False,
                "unavailable_reason": "inhibitor_overlap",
            },
        )

    def test_active_inhibitor_advertises_legal_deactivation(self):
        player, units, _hex_obj, game = self._inhibitor_fixture(active_ids=(10,))
        snapshot = SimpleNamespace(
            visible_enemy_unit_ids=set(),
            presence_hexes=set(),
        )
        with patch("visibility.VisibilityService.compute", return_value=snapshot):
            observation = build_observation(game, player)

        unit_view = observation["units"][0]
        inhibitor = unit_view["capability_details"]["inhibitor"]
        self.assertIn("toggle_inhibitor", unit_view["legal_commands"])
        self.assertTrue(inhibitor["is_active"])
        self.assertFalse(inhibitor["can_activate"])
        self.assertIsNone(inhibitor["activation_blocker"])
        self.assertEqual(
            unit_view["command_options"]["toggle_inhibitor"]["resulting_state"],
            "inactive",
        )

    def test_inhibitor_overlap_is_retryable_preflight_rejection(self):
        from geometry import Circle, Position

        player, units, _hex_obj, game = self._inhibitor_fixture(
            static_zones=(Circle(Position(0, 0), 50.0),)
        )
        result = CommandGateway(game).apply_batch(
            player,
            CommandBatch(
                commands=(
                    Command(type="cancel_orders", unit_ids=(units[0].id,)),
                    Command(type="toggle_inhibitor", unit_ids=(units[0].id,)),
                )
            ),
        )

        self.assertFalse(result.accepted)
        self.assertEqual(result.failure_stage, "preflight")
        self.assertTrue(result.retryable)
        self.assertEqual(result.errors[0].command_index, 1)
        self.assertEqual(result.errors[0].code, "inhibitor_overlap")
        self.assertEqual(units[0].commander_component.clear_count, 0)
        self.assertFalse(units[0].inhibitor_component.is_active)

    def test_projected_inhibitor_activations_cannot_overlap(self):
        player, units, _hex_obj, game = self._inhibitor_fixture(
            positions=((0, 0), (150, 0))
        )
        result = CommandGateway(game).apply_batch(
            player,
            CommandBatch(
                commands=(
                    Command(type="toggle_inhibitor", unit_ids=(units[0].id,)),
                    Command(type="toggle_inhibitor", unit_ids=(units[1].id,)),
                )
            ),
        )

        self.assertFalse(result.accepted)
        self.assertEqual(result.errors[0].command_index, 1)
        self.assertEqual(result.errors[0].code, "inhibitor_overlap")
        self.assertTrue(all(not unit.inhibitor_component.is_active for unit in units))

    def test_projected_deactivation_can_enable_later_activation(self):
        player, units, hex_obj, game = self._inhibitor_fixture(
            positions=((0, 0), (0, 0)), active_ids=(10,)
        )
        result = CommandGateway(game).apply_batch(
            player,
            CommandBatch(
                commands=(
                    Command(type="toggle_inhibitor", unit_ids=(units[0].id,)),
                    Command(type="toggle_inhibitor", unit_ids=(units[1].id,)),
                )
            ),
        )

        self.assertTrue(result.accepted)
        self.assertFalse(units[0].inhibitor_component.is_active)
        self.assertTrue(units[1].inhibitor_component.is_active)
        self.assertNotIn(units[0].id, hex_obj.dynamic_inhibition_zones)
        self.assertIn(units[1].id, hex_obj.dynamic_inhibition_zones)
        self.assertEqual(
            result.receipts,
            (
                "Deactivated inhibitor on U10.",
                "Activated inhibitor on U11.",
            ),
        )

    def test_colonist_load_can_feed_a_queued_colonize_command(self):
        player, units, source, target, game = self._colony_fixture()
        batch = CommandBatch(
            commands=(
                Command(
                    type="load_colonists",
                    unit_ids=(units[0].id,),
                    target_id=source.id,
                    amount=50,
                    queue=False,
                ),
                Command(
                    type="colonize",
                    unit_ids=(units[0].id,),
                    target_id=target.id,
                    queue=True,
                ),
            )
        )
        result = CommandGateway(game).apply_batch(player, batch)
        self.assertTrue(result.accepted)
        self.assertEqual(result.applied_count, 2)
        self.assertEqual(len(units[0].commander_component.orders_queue), 2)

    def test_existing_queued_load_can_feed_colonization(self):
        player, units, source, target, game = self._colony_fixture()
        units[0].commander_component.current_order = SimpleNamespace(
            order_type=SimpleNamespace(name="LOAD_COLONISTS"),
            status=SimpleNamespace(name="IN_PROGRESS"),
            parameters={"target_id": source.id, "amount": 40},
        )
        result = CommandGateway(game).apply_batch(
            player,
            CommandBatch(
                commands=(
                    Command(
                        type="colonize",
                        unit_ids=(units[0].id,),
                        target_id=target.id,
                        queue=True,
                    ),
                )
            ),
        )
        self.assertTrue(result.accepted)

    def test_cancellation_releases_projected_population_reservation(self):
        player, units, source, _target, game = self._colony_fixture(unit_count=2)
        batch = CommandBatch(
            commands=(
                Command(
                    type="load_colonists",
                    unit_ids=(units[0].id,),
                    target_id=source.id,
                    amount=50,
                    queue=False,
                ),
                Command(type="cancel_orders", unit_ids=(units[0].id,)),
                Command(
                    type="load_colonists",
                    unit_ids=(units[1].id,),
                    target_id=source.id,
                    amount=50,
                    queue=True,
                ),
            )
        )
        result = CommandGateway(game).apply_batch(player, batch)
        self.assertTrue(result.accepted)
        self.assertEqual(result.applied_count, 3)

    def test_colonize_without_cargo_or_preserved_load_is_rejected_atomically(self):
        player, units, source, target, game = self._colony_fixture()
        batch = CommandBatch(
            commands=(
                Command(
                    type="load_colonists",
                    unit_ids=(units[0].id,),
                    target_id=source.id,
                    amount=50,
                    queue=False,
                ),
                Command(
                    type="colonize",
                    unit_ids=(units[0].id,),
                    target_id=target.id,
                    queue=False,
                ),
            )
        )
        result = CommandGateway(game).apply_batch(player, batch)
        self.assertFalse(result.accepted)
        self.assertEqual(units[0].commander_component.clear_count, 0)
        self.assertIn("queue=true", result.errors[0].message)

    def test_colonist_population_is_reserved_across_multi_unit_command(self):
        player, units, source, _target, game = self._colony_fixture(
            population=50, unit_count=2
        )
        batch = CommandBatch(
            commands=(
                Command(
                    type="load_colonists",
                    unit_ids=tuple(unit.id for unit in units),
                    target_id=source.id,
                    amount=30,
                ),
            )
        )
        result = CommandGateway(game).apply_batch(player, batch)
        self.assertFalse(result.accepted)
        self.assertEqual(result.errors[0].code, "insufficient_population")
        self.assertTrue(all(unit.commander_component.clear_count == 0 for unit in units))

    def test_construction_credits_are_reserved_across_a_batch(self):
        player = _Player(1, 1)
        unit = _unit(10, player)
        buildable = SimpleNamespace(
            unit_template_name="SCOUT",
            cost_credits=6,
            time_to_build=1,
        )
        unit.constructor_component = SimpleNamespace(
            can_build=lambda name: buildable if name == "SCOUT" else None,
            buildable_units=[buildable],
        )

        class Galaxy:
            def get_unit_by_id(self, unit_id):
                return unit if unit_id == unit.id else None

        game = SimpleNamespace(galaxy=Galaxy(), sidebar_needs_update=False)
        command = Command(
            type="construct",
            unit_ids=(unit.id,),
            position=(0, 0),
            template_name="SCOUT",
            queue=True,
        )
        result = CommandGateway(game).apply_batch(
            player, CommandBatch(commands=(command, command))
        )
        self.assertFalse(result.accepted)
        self.assertEqual(result.errors[0].code, "insufficient_resources")
        self.assertEqual(unit.commander_component.clear_count, 0)

    def test_colony_sources_targets_and_capacity_are_validated_before_commit(self):
        from entities import Star, StarType

        def assert_rejected(configure, make_command, expected_code):
            player, units, source, target, game = self._colony_fixture()
            configure(player, units[0], source, target, game)
            command = make_command(units[0], source, target, game)
            result = CommandGateway(game).apply_batch(
                player, CommandBatch(commands=(command,))
            )
            self.assertFalse(result.accepted)
            self.assertEqual(result.errors[0].code, expected_code)
            self.assertEqual(units[0].commander_component.clear_count, 0)

        assert_rejected(
            lambda _player, _unit, source, _target, _game: setattr(
                source, "owner", _Player(2, 1)
            ),
            lambda unit, source, _target, _game: Command(
                type="load_colonists",
                unit_ids=(unit.id,),
                target_id=source.id,
                amount=10,
            ),
            "invalid_relation",
        )
        assert_rejected(
            lambda _player, unit, _source, _target, _game: setattr(
                unit.colony_component, "max_cargo", 5
            ),
            lambda unit, source, _target, _game: Command(
                type="load_colonists",
                unit_ids=(unit.id,),
                target_id=source.id,
                amount=10,
            ),
            "insufficient_capacity",
        )

        def add_star(_player, _unit, _source, _target, game):
            star = Star("Sol", next(iter(StarType)))
            game.galaxy.bodies[star.id] = star
            game.invalid_star = star

        assert_rejected(
            add_star,
            lambda unit, _source, _target, game: Command(
                type="load_colonists",
                unit_ids=(unit.id,),
                target_id=game.invalid_star.id,
                amount=10,
            ),
            "invalid_target",
        )
        assert_rejected(
            add_star,
            lambda unit, _source, _target, game: Command(
                type="colonize",
                unit_ids=(unit.id,),
                target_id=game.invalid_star.id,
            ),
            "invalid_target",
        )

    def test_observation_reports_colony_legality_and_capacity(self):
        player, units, source, target, game = self._colony_fixture()
        hex_obj = SimpleNamespace(
            celestial_bodies=[source, target], units=units, minefields=[]
        )
        system = SimpleNamespace(
            position=SimpleNamespace(x=1, y=2),
            radius=2,
            hexes={(0, 0): hex_obj},
        )
        game.galaxy.systems = {"Sol": system}
        game.galaxy.system_graph = {"Sol": {}}
        game.players = [player]
        game.turn_number = 1
        snapshot = SimpleNamespace(
            visible_enemy_unit_ids=set(),
            presence_hexes=set(),
        )
        with patch("visibility.VisibilityService.compute", return_value=snapshot):
            observation = build_observation(game, player)
        unit_view = observation["units"][0]
        self.assertEqual(observation["schema_version"], 5)
        self.assertNotIn("celestial_bodies", observation)
        self.assertIn("colonize", unit_view["supported_commands"])
        self.assertNotIn("colonize", unit_view["legal_commands"])
        self.assertIn("load_colonists", unit_view["legal_commands"])
        self.assertEqual(
            unit_view["capability_details"]["colony"]["maximum_cargo"],
            100.0,
        )
        self.assertEqual(unit_view["command_options"]["colonize"]["target_ids"], [target.id])
        self.assertEqual(unit_view["conditional_commands"][0]["type"], "colonize")

    def test_hybrid_observation_summarizes_remote_neutral_bodies(self):
        from entities import Moon, Planet, PlanetType, Star, StarType

        player = _Player(1, 1)
        unit = _unit(10, player)
        planet_type = next(iter(PlanetType))
        star_type = next(iter(StarType))

        def make_system(name, bodies, units=()):
            return SimpleNamespace(
                position=SimpleNamespace(x=0, y=0),
                radius=4,
                hexes={
                    (0, 0): SimpleNamespace(
                        celestial_bodies=bodies,
                        units=list(units),
                        minefields=[],
                    )
                },
            )

        sol_star = Star("Sol", star_type)
        sol_target = Moon((0, 0), "Sol")
        vega_star = Star("Vega", star_type)
        vega_target = Planet((0, 0), "Vega", planet_type)
        sirius_star = Star("Sirius", star_type)
        remote_neutral = Planet((0, 0), "Sirius", planet_type)
        remote_colony = Planet((0, 0), "Sirius", planet_type)
        remote_colony.owner = player
        remote_colony.population = 20
        galaxy = SimpleNamespace(
            systems={
                "Sol": make_system("Sol", [sol_star, sol_target], [unit]),
                "Vega": make_system("Vega", [vega_star, vega_target]),
                "Sirius": make_system(
                    "Sirius", [sirius_star, remote_neutral, remote_colony]
                ),
            },
            system_graph={
                "Sol": {"Vega": SimpleNamespace(value="huge")},
                "Vega": {"Sol": SimpleNamespace(value="huge")},
                "Sirius": {},
            },
        )
        game = SimpleNamespace(galaxy=galaxy, players=[player], turn_number=1)
        snapshot = SimpleNamespace(
            visible_enemy_unit_ids=set(), presence_hexes=set()
        )
        with patch("visibility.VisibilityService.compute", return_value=snapshot):
            observation = build_observation(game, player)

        systems = {system["name"]: system for system in observation["systems"]}
        self.assertEqual(systems["Sol"]["detail_level"], "full")
        self.assertEqual(systems["Vega"]["detail_level"], "full")
        self.assertEqual(systems["Sirius"]["detail_level"], "summary")
        notable_ids = {body["id"] for body in systems["Sirius"]["notable_bodies"]}
        self.assertIn(sirius_star.id, notable_ids)
        self.assertIn(remote_colony.id, notable_ids)
        self.assertNotIn(remote_neutral.id, notable_ids)
        self.assertEqual(
            systems["Sirius"]["body_summary"]["neutral_colonizable_count"], 1
        )
        self.assertNotIn(
            remote_neutral.id,
            observation["action_catalogs"]["colonization_target_ids"],
        )

    def test_large_hybrid_observation_stays_below_character_budget(self):
        from entities import Planet, PlanetType, Star, StarType

        player = _Player(1, 1)
        unit = _unit(10, player)
        planet_type = next(iter(PlanetType))
        star_type = next(iter(StarType))
        systems = {}
        graph = {}
        remaining_planets = 785
        for index in range(15):
            name = f"System {index}"
            count = remaining_planets // (15 - index)
            remaining_planets -= count
            bodies = [Star(name, star_type)] + [
                Planet((0, 0), name, planet_type) for _ in range(count)
            ]
            systems[name] = SimpleNamespace(
                position=SimpleNamespace(x=index, y=0),
                radius=4,
                hexes={
                    (0, 0): SimpleNamespace(
                        celestial_bodies=bodies,
                        units=[unit] if index == 0 else [],
                        minefields=[],
                    )
                },
            )
            graph[name] = {}
        graph["System 0"]["System 1"] = SimpleNamespace(value="huge")
        graph["System 1"]["System 0"] = SimpleNamespace(value="huge")
        galaxy = SimpleNamespace(systems=systems, system_graph=graph)
        game = SimpleNamespace(galaxy=galaxy, players=[player], turn_number=1)
        snapshot = SimpleNamespace(
            visible_enemy_unit_ids=set(), presence_hexes=set()
        )
        with patch("visibility.VisibilityService.compute", return_value=snapshot):
            observation = build_observation(game, player)
        payload = json.dumps(
            PlanningRequest("campaign", "agent", "AI", 1, observation, {}).to_dict(),
            separators=(",", ":"),
        )
        self.assertLess(len(payload), 75_000)

    @staticmethod
    def _combat_fixture():
        from geometry import Position
        from unit_components import Engines, Weapons, Hyperdrive, HyperdriveType

        player = _Player(1, 1)
        enemy_player = _Player(2, 2)

        my_unit = _unit(10, player)
        my_unit.engines_component = Engines(my_unit, speed=50.0)
        my_unit.weapons_component = Weapons(my_unit)
        from unit_components import Turret, TurretType
        my_unit.weapons_component.add_turret(Turret(TurretType.MASS_DRIVER, 20, 300, 1, my_unit))
        my_unit.components = {
            Engines: my_unit.engines_component,
            Weapons: my_unit.weapons_component,
        }

        enemy_unit = _unit(20, enemy_player)
        enemy_unit.engines_component = Engines(enemy_unit, speed=50.0)
        enemy_unit.weapons_component = Weapons(enemy_unit)
        enemy_unit.hyperdrive_component = Hyperdrive(
            enemy_unit, drive_type=HyperdriveType.BASIC, jump_range=5
        )
        enemy_unit.components = {
            Engines: enemy_unit.engines_component,
            Weapons: enemy_unit.weapons_component,
            Hyperdrive: enemy_unit.hyperdrive_component,
        }

        units = [my_unit, enemy_unit]
        units_by_id = {u.id: u for u in units}

        class Galaxy:
            systems = {
                "Sol": SimpleNamespace(
                    position=Position(0, 0),
                    radius=1,
                    hexes={(0, 0): SimpleNamespace(units=units, celestial_bodies=[])},
                )
            }
            system_graph = {"Sol": {}}

            @staticmethod
            def get_unit_by_id(unit_id):
                return units_by_id.get(unit_id)

            @staticmethod
            def get_celestial_body_by_id(_body_id):
                return None

        game = SimpleNamespace(
            galaxy=Galaxy(),
            players=[player, enemy_player],
            sidebar_needs_update=False,
            visibility_dirty=False,
            turn_number=1,
        )
        return player, enemy_player, my_unit, enemy_unit, game

    def test_attack_with_subsystem_targeting(self):
        player, enemy_player, my_unit, enemy_unit, game = self._combat_fixture()
        snapshot = SimpleNamespace(
            visible_enemy_unit_ids={enemy_unit.id}, presence_hexes=set()
        )
        with patch("visibility.VisibilityService.compute", return_value=snapshot):
            batch = CommandBatch(
                commands=(
                    Command(
                        type="attack",
                        unit_ids=(my_unit.id,),
                        target_id=enemy_unit.id,
                        target_component="Engines",
                    ),
                )
            )
            result = CommandGateway(game).apply_batch(player, batch)
            self.assertTrue(result.accepted)
            self.assertEqual(result.receipts, ("attack issued for unit 10.",))

            self.assertEqual(len(my_unit.commander_component.orders_queue), 1)
            order = my_unit.commander_component.orders_queue[0]
            self.assertEqual(order.parameters["target_component_type"], "Engines")

        with patch("visibility.VisibilityService.compute", return_value=snapshot):
            batch_alias = CommandBatch(
                commands=(
                    Command(
                        type="attack",
                        unit_ids=(my_unit.id,),
                        target_id=enemy_unit.id,
                        target_component="hyperdrive",
                    ),
                )
            )
            result_alias = CommandGateway(game).apply_batch(player, batch_alias)
            self.assertTrue(result_alias.accepted)
            self.assertEqual(result_alias.receipts, ("attack issued for unit 10.",))

    def test_destroyed_engines_are_not_advertised_and_reject_move_preflight(self):
        player, _enemy_player, my_unit, enemy_unit, game = self._combat_fixture()
        my_unit.engines_component.current_hit_points = 0
        snapshot = SimpleNamespace(
            visible_enemy_unit_ids={enemy_unit.id}, presence_hexes=set()
        )

        with patch("visibility.VisibilityService.compute", return_value=snapshot):
            observation = build_observation(game, player)

        unit_view = next(unit for unit in observation["units"] if unit["id"] == my_unit.id)
        for command_type in ("move", "patrol", "protect", "defend"):
            self.assertIn(command_type, unit_view["supported_commands"])
            self.assertNotIn(command_type, unit_view["legal_commands"])
        self.assertEqual(
            unit_view["capability_details"]["engines"],
            {"speed": 50.0, "effective_speed": 0.0, "destroyed": True},
        )

        result = CommandGateway(game).apply_batch(
            player,
            CommandBatch(
                commands=(
                    Command(
                        type="move",
                        unit_ids=(my_unit.id,),
                        system_name="Sol",
                        hex_coord=(0, 0),
                        position=(50.0, 50.0),
                    ),
                )
            ),
        )
        self.assertFalse(result.accepted)
        self.assertEqual(result.errors[0].code, "capability_unavailable")

    def test_attack_subsystem_targeting_rejections(self):
        player, enemy_player, my_unit, enemy_unit, game = self._combat_fixture()
        snapshot = SimpleNamespace(
            visible_enemy_unit_ids={enemy_unit.id}, presence_hexes=set()
        )
        # 1. Non-existent component on enemy unit
        with patch("visibility.VisibilityService.compute", return_value=snapshot):
            batch_invalid_target = CommandBatch(
                commands=(
                    Command(
                        type="attack",
                        unit_ids=(my_unit.id,),
                        target_id=enemy_unit.id,
                        target_component="ColonyComponent",
                    ),
                )
            )
            result = CommandGateway(game).apply_batch(player, batch_invalid_target)
            self.assertFalse(result.accepted)
            self.assertEqual(result.errors[0].code, "target_unavailable")

        # 2. Bogus / unresolvable component name
        with patch("visibility.VisibilityService.compute", return_value=snapshot):
            batch_bogus = CommandBatch(
                commands=(
                    Command(
                        type="attack",
                        unit_ids=(my_unit.id,),
                        target_id=enemy_unit.id,
                        target_component="laser_cannon_mk2",
                    ),
                )
            )
            result = CommandGateway(game).apply_batch(player, batch_bogus)
            self.assertFalse(result.accepted)
            self.assertEqual(result.errors[0].code, "target_unavailable")

    def test_defend_command_execution(self):
        player, enemy_player, my_unit, enemy_unit, game = self._combat_fixture()
        # 1. Valid defend command with coordinates
        batch_valid = CommandBatch(
            commands=(
                Command(
                    type="defend",
                    unit_ids=(my_unit.id,),
                    system_name="Sol",
                    hex_coord=(0, 0),
                    position=(50.0, 50.0),
                ),
            )
        )
        result = CommandGateway(game).apply_batch(player, batch_valid)
        self.assertTrue(result.accepted)
        self.assertEqual(result.receipts, ("defend issued for unit 10.",))
        self.assertEqual(len(my_unit.commander_component.orders_queue), 1)

        # 2. Missing coordinate fields
        batch_missing = CommandBatch(
            commands=(
                Command(
                    type="defend",
                    unit_ids=(my_unit.id,),
                    system_name="Sol",
                ),
            )
        )
        result_missing = CommandGateway(game).apply_batch(player, batch_missing)
        self.assertFalse(result_missing.accepted)
        self.assertEqual(result_missing.errors[0].code, "invalid_command_contract")

        # 3. Unit without weapons cannot perform defend
        my_unit.weapons_component = None
        result_no_weapons = CommandGateway(game).apply_batch(player, batch_valid)
        self.assertFalse(result_no_weapons.accepted)
        self.assertEqual(result_no_weapons.errors[0].code, "capability_unavailable")
