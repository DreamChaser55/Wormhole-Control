from types import SimpleNamespace
from unittest.mock import Mock

from geometry import Position
from turn_processor import TurnProcessor
from constants import HullSize
from unit_components import AntimatterStorage, Turret, TurretType, TurretVariant, UnitStance
from unit_components.enums import SabotageType
from unit_orders import AttackOrder, Order, OrderStatus, OrderType, ProtectOrder, ReachWaypointOrder

from tests.test_stance_visibility import create_combat_ship, create_test_galaxy


def test_stance_owns_attack_movement_tree_and_explicit_orders_take_priority():
    galaxy, player, enemy_player = create_test_galaxy()
    attacker = create_combat_ship(
        galaxy, player, "Guard", (0, 0), pos=(0, 0), short_range=2000.0
    )
    target = create_combat_ship(
        galaxy, enemy_player, "Raider", (0, 0), pos=(1000, 0), short_range=500.0
    )
    commander = attacker.commander_component

    commander.set_stance(UnitStance.ATTACK_SAME_SECTOR)
    commander.update()

    attack = commander.standing_order.active_attack
    assert commander.current_order is None
    assert attack is not None
    assert attack.parameters["target_unit_id"] == target.id
    assert attack.sub_orders[0].order_type == OrderType.MOVE
    assert attack.sub_orders[0].sub_orders[0].order_type == OrderType.REACH_WAYPOINT
    assert attacker.engines_component.move_target_order_id == attack.sub_orders[0].sub_orders[0].order_id

    explicit = Order(attacker, OrderType.TOGGLE_INHIBITOR)
    commander.add_order(explicit)
    assert commander.current_order is explicit
    assert commander.standing_order.active_attack is None
    assert attacker.engines_component.move_target is None

    queued = Order(attacker, OrderType.TOGGLE_INHIBITOR)
    commander.add_order(queued)
    assert list(commander.orders_queue) == [queued]

    commander.set_stance(UnitStance.ATTACK_WEAPON_RANGE)
    assert commander.current_order is explicit
    commander.clear_explicit_orders()
    commander.update()
    assert commander.current_order is None
    assert commander.stance == UnitStance.ATTACK_WEAPON_RANGE


def test_stop_and_idle_clears_both_layers_and_component_state():
    galaxy, player, enemy_player = create_test_galaxy()
    attacker = create_combat_ship(
        galaxy, player, "Guard", (0, 0), pos=(0, 0), short_range=2000.0
    )
    create_combat_ship(
        galaxy, enemy_player, "Raider", (0, 0), pos=(1000, 0), short_range=500.0
    )
    commander = attacker.commander_component
    commander.set_stance(UnitStance.ATTACK_SAME_SECTOR)
    commander.update()
    assert commander.standing_order.active_attack is not None

    commander.stop_and_idle()

    assert commander.stance == UnitStance.DO_NOTHING
    assert commander.current_order is None
    assert not commander.orders_queue
    assert commander.standing_order.active_attack is None
    assert attacker.engines_component.move_target is None
    assert attacker.hyperdrive_component.hex_jump_target is None
    assert attacker.weapons_component.turrets[0].target is None


def test_stance_scope_is_checked_before_movement_and_antimatter_spend():
    galaxy, player, enemy_player = create_test_galaxy()
    attacker = create_combat_ship(
        galaxy, player, "Pursuer", (0, 0), pos=(0, 0), short_range=2000.0
    )
    attacker.add_component(AntimatterStorage(attacker, max_capacity=100.0))
    target = create_combat_ship(
        galaxy, enemy_player, "Runner", (0, 0), pos=(1000, 0), short_range=500.0
    )
    commander = attacker.commander_component
    commander.set_stance(UnitStance.ATTACK_SAME_SECTOR)
    commander.update()
    assert attacker.engines_component.move_target is not None

    origin_position = Position(attacker.position.x, attacker.position.y)
    antimatter_before = attacker.antimatter_component.current_amount
    galaxy.systems["Sol"].hexes[(0, 0)].units.remove(target)
    target.in_hex = (0, 1)
    galaxy.systems["Sol"].hexes[(0, 1)].units.append(target)

    TurnProcessor(SimpleNamespace(galaxy=galaxy))._process_movement(player)

    assert attacker.position == origin_position
    assert attacker.antimatter_component.current_amount == antimatter_before
    assert commander.standing_order.active_attack is None
    assert attacker.engines_component.move_target is None
    assert attacker.engines_component.move_target_order_id is None
    assert attacker.hyperdrive_component.hex_jump_target is None
    assert attacker.weapons_component.turrets[0].target is None


def test_waypoint_cancellation_only_clears_the_target_it_owns():
    galaxy, player, _ = create_test_galaxy()
    unit = create_combat_ship(galaxy, player, "Courier", (0, 0))
    old = ReachWaypointOrder(unit, {})
    new = ReachWaypointOrder(unit, {})

    unit.engines_component.set_move_target(Position(10, 0), old.order_id)
    unit.engines_component.set_move_target(Position(20, 0), new.order_id)
    old.cancel()
    assert unit.engines_component.move_target == Position(20, 0)
    assert unit.engines_component.move_target_order_id == new.order_id

    new.cancel()
    assert unit.engines_component.move_target is None
    assert unit.engines_component.move_target_order_id is None


def test_prepare_for_movement_rejects_orphaned_targets():
    galaxy, player, _ = create_test_galaxy()
    unit = create_combat_ship(galaxy, player, "Courier", (0, 0))
    unit.engines_component.set_move_target(Position(50, 0), 999_999)

    unit.commander_component.prepare_for_movement()

    assert unit.engines_component.move_target is None
    assert unit.engines_component.move_target_order_id is None


def test_stances_and_direct_attacks_reject_allies():
    galaxy, player, _ = create_test_galaxy()
    ally = type(player)(name="Ally", color=(0, 255, 0), team_id=player.team_id)
    attacker = create_combat_ship(galaxy, player, "Guard", (0, 0), short_range=2000.0)
    allied_ship = create_combat_ship(
        galaxy, ally, "Allied Ship", (0, 0), pos=(100, 0), short_range=500.0
    )

    attacker.commander_component.set_stance(UnitStance.ATTACK_SAME_SECTOR)
    attacker.commander_component.update()
    assert attacker.commander_component.standing_order.active_attack is None

    attack = AttackOrder(attacker, {"target_unit_id": allied_ship.id})
    attack.execute(galaxy)
    assert attack.status == OrderStatus.FAILED
    assert attacker.weapons_component.turrets[0].target is None


def test_protect_accepts_an_allied_target():
    galaxy, player, _ = create_test_galaxy()
    ally = type(player)(name="Ally", color=(0, 255, 0), team_id=player.team_id)
    protector = create_combat_ship(galaxy, player, "Escort", (0, 0))
    allied_ship = create_combat_ship(galaxy, ally, "Ally", (0, 0), pos=(50, 0))

    order = ProtectOrder(protector, {"target_unit_id": allied_ship.id})
    order.execute(galaxy)

    assert order.status == OrderStatus.IN_PROGRESS


def test_attack_range_and_standoff_use_only_eligible_turrets():
    galaxy, player, enemy_player = create_test_galaxy()
    attacker = create_combat_ship(galaxy, player, "Mixed Battery", (0, 0))
    target = create_combat_ship(
        galaxy, enemy_player, "Fighters", (0, 0), pos=(150, 0)
    )
    target.hull_size = HullSize.STRIKECRAFT_WING
    weapons = attacker.weapons_component
    weapons.turrets = [
        Turret(TurretType.MASS_DRIVER, 10, 1000.0, 2, attacker, TurretVariant.STANDARD),
        Turret(TurretType.MASS_DRIVER, 10, 100.0, 2, attacker, TurretVariant.ANTI_STRIKECRAFT),
    ]

    attack = AttackOrder(attacker, {"target_unit_id": target.id})
    attack.execute(galaxy)

    assert attack.status == OrderStatus.IN_PROGRESS
    assert len(attack.sub_orders) == 1
    assert attack.sub_orders[0].parameters["standoff_distance"] == 95.0
    assert weapons.turrets[0].target is None
    assert weapons.turrets[1].target is target


def test_sabotaged_hyperdrive_removes_jump_stances_and_resets_policy():
    galaxy, player, _ = create_test_galaxy()
    unit = create_combat_ship(galaxy, player, "Hunter", (0, 0))
    unit.commander_component.set_stance(UnitStance.ATTACK_SAME_SYSTEM)
    unit.is_sabotaged = lambda sabotage_type: sabotage_type == SabotageType.HYPERDRIVE

    unit.commander_component.prepare_for_movement()

    assert unit.commander_component.stance == UnitStance.DO_NOTHING
    assert UnitStance.ATTACK_SAME_SYSTEM not in unit.commander_component.get_allowed_stances()


def test_loaded_explicit_movement_rebinds_new_waypoint_ownership():
    from save_manager import deserialize_order, serialize_order
    from unit_orders import MoveOrder

    galaxy, player, _ = create_test_galaxy()
    unit = create_combat_ship(galaxy, player, "Courier", (0, 0))
    commander = unit.commander_component
    move = MoveOrder(unit, {
        "destination_system_name": "Sol",
        "destination_hex_coord": (0, 0),
        "destination_position": Position(500, 0),
    })
    commander.add_order(move)
    old_waypoint = move.sub_orders[0]
    assert unit.engines_component.move_target_order_id == old_waypoint.order_id

    payload = serialize_order(move)
    commander.clear_explicit_orders()
    restored = deserialize_order(payload, unit, galaxy.game)
    commander.restore_explicit_orders(restored, [], galaxy)

    new_waypoint = restored.sub_orders[0]
    assert new_waypoint.order_id != old_waypoint.order_id
    assert unit.engines_component.move_target == Position(500, 0)
    assert unit.engines_component.move_target_order_id == new_waypoint.order_id


def test_loaded_explicit_attack_rebinds_weapon_authority_without_execute():
    from save_manager import deserialize_order, serialize_order

    galaxy, player, enemy_player = create_test_galaxy()
    attacker = create_combat_ship(galaxy, player, "Gunship", (0, 0))
    target = create_combat_ship(galaxy, enemy_player, "Target", (0, 0), pos=(100, 0))
    commander = attacker.commander_component
    attack = AttackOrder(attacker, {"target_unit_id": target.id})
    commander.add_order(attack)
    payload = serialize_order(attack)
    commander.clear_explicit_orders()
    assert attacker.weapons_component.turrets[0].target is None

    restored = deserialize_order(payload, attacker, galaxy.game)
    commander.restore_explicit_orders(restored, [], galaxy)

    assert commander.current_order is restored
    assert commander.get_active_attack_order() is restored
    assert attacker.weapons_component.turrets[0].target is target


def test_restoring_queue_only_resumes_in_progress_order_without_replaying_startup():
    galaxy, player, _ = create_test_galaxy()
    unit = create_combat_ship(galaxy, player, "Builder", (0, 0))
    order = Order(unit, OrderType.CONSTRUCT)
    order.status = OrderStatus.IN_PROGRESS
    order.execute = Mock()
    order.resume = Mock()
    order.update = Mock()

    unit.commander_component.restore_explicit_orders(None, [order], galaxy)

    assert unit.commander_component.current_order is order
    order.execute.assert_not_called()
    order.resume.assert_called_once_with(galaxy_ref=galaxy)


def test_stance_pursuit_waypoints_are_rendered_as_current_through_all_levels():
    from rendering.sector_renderer.sector_overlay_renderer import SectorOverlayRenderer
    from unit_orders import MoveOrder

    galaxy, player, enemy_player = create_test_galaxy()
    attacker = create_combat_ship(galaxy, player, "Guard", (0, 0), short_range=2000.0)
    create_combat_ship(galaxy, enemy_player, "Raider", (0, 0), pos=(1000, 0))
    commander = attacker.commander_component
    commander.set_stance(UnitStance.ATTACK_SAME_SECTOR)
    commander.update()
    renderer = SectorOverlayRenderer.__new__(SectorOverlayRenderer)

    waypoints = renderer.collect_all_waypoints(attacker)

    assert waypoints
    assert all(wp["is_current"] for wp in waypoints)
    assert all(wp["order_type"] == OrderType.REACH_WAYPOINT for wp in waypoints)

    queued = MoveOrder(attacker, {
        "destination_system_name": "Sol",
        "destination_hex_coord": (0, 0),
        "destination_position": Position(800, 0),
    })
    queued_waypoints = []
    renderer.collect_waypoints_from_order(queued, attacker, queued_waypoints, False)
    assert queued_waypoints
    assert not any(wp["is_current"] for wp in queued_waypoints)


def test_observation_and_sidebar_keep_standing_and_explicit_sections_compatible():
    from game_ai.order_view import order_layers

    galaxy, player, enemy_player = create_test_galaxy()
    attacker = create_combat_ship(galaxy, player, "Guard", (0, 0), short_range=2000.0)
    create_combat_ship(galaxy, enemy_player, "Raider", (0, 0), pos=(100, 0))
    commander = attacker.commander_component
    commander.set_stance(UnitStance.ATTACK_WEAPON_RANGE)
    commander.update()

    observed = order_layers(attacker, "self", set(), set())
    assert observed["current_order"] is None
    assert observed["standing_order"]["engagement"]["type"] == "attack"
    assert observed["standing_order"]["engagement"]["status"] == "in_progress"
    assert observed["standing_order"]["engagement"]["origin"] == "stance"

    gui = SimpleNamespace(is_section_expanded=lambda _key: False)
    game = SimpleNamespace(
        players=[player],
        current_player_index=0,
        gui=gui,
        _generate_order_data_recursive=lambda order, _indent: order.order_type.name,
    )
    sidebar = commander.get_sidebar_data(game)
    labels = [item.get("text") for item in sidebar if item.get("type") == "label"]
    assert "Stance Order:" in labels
    assert "Current Order: None" in labels
    assert "Queued Orders" in labels

    commander.add_order(Order(attacker, OrderType.TOGGLE_INHIBITOR))
    sidebar = commander.get_sidebar_data(game)
    labels = [item.get("text") for item in sidebar if item.get("type") == "label"]
    assert "Current Order:" in labels
