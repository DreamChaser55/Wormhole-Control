import pytest
from unittest.mock import MagicMock
from geometry import Position
from entities import Unit
from constants import HullSize
from unit_components import AbilityComponent, AbilityType, Engines, AntimatterStorage
from unit_orders import UseAbilityOrder, OrderStatus, OrderType
from tests.test_unit_components import MockPlayer
from custom_unit_templates import CustomUnitTemplate, ComponentConfig


class DummyGame:
    def __init__(self):
        self.galaxy = MagicMock()
        self.selected_objects = []
        self.players = []
        self.current_player_index = 0


def test_drain_antimatter_success():
    player_caster = MockPlayer("Caster Player")
    player_target = MockPlayer("Target Player")
    player_target.id = 2
    game = DummyGame()

    caster = Unit(owner=player_caster, position=Position(0, 0), in_hex=(0, 0), in_system="Sol", name="Caster", hull_size=HullSize.MEDIUM, game=game)
    target = Unit(owner=player_target, position=Position(100, 0), in_hex=(0, 0), in_system="Sol", name="Target", hull_size=HullSize.MEDIUM, game=game)
    target.id = 999

    game.galaxy.get_unit_by_id.return_value = target

    caster_am = AntimatterStorage(caster, max_capacity=100.0)
    caster_am.current_amount = 20.0
    caster.add_component(caster_am)

    target_am = AntimatterStorage(target, max_capacity=100.0)
    target_am.current_amount = 50.0
    target.add_component(target_am)

    ability_comp = AbilityComponent(caster, [AbilityType.DRAIN_ANTIMATTER])
    caster.add_component(ability_comp)

    order = UseAbilityOrder(caster, {
        "ability_type": "drain_antimatter",
        "target_unit_id": target.id
    })

    order.execute(game.galaxy)
    assert order.status == OrderStatus.COMPLETED
    assert target_am.current_amount == 20.0  # 50 - 30
    assert caster_am.current_amount == 50.0  # 20 + 30


def test_drain_antimatter_partial():
    player_caster = MockPlayer("Caster Player")
    player_target = MockPlayer("Target Player")
    player_target.id = 2
    game = DummyGame()

    caster = Unit(owner=player_caster, position=Position(0, 0), in_hex=(0, 0), in_system="Sol", name="Caster", hull_size=HullSize.MEDIUM, game=game)
    target = Unit(owner=player_target, position=Position(100, 0), in_hex=(0, 0), in_system="Sol", name="Target", hull_size=HullSize.MEDIUM, game=game)
    target.id = 999

    game.galaxy.get_unit_by_id.return_value = target

    caster_am = AntimatterStorage(caster, max_capacity=100.0)
    caster_am.current_amount = 10.0
    caster.add_component(caster_am)

    target_am = AntimatterStorage(target, max_capacity=100.0)
    target_am.current_amount = 12.5  # Less than max drain cap (30.0)
    target.add_component(target_am)

    ability_comp = AbilityComponent(caster, [AbilityType.DRAIN_ANTIMATTER])
    caster.add_component(ability_comp)

    order = UseAbilityOrder(caster, {
        "ability_type": "drain_antimatter",
        "target_unit_id": target.id
    })

    order.execute(game.galaxy)
    assert order.status == OrderStatus.COMPLETED
    assert target_am.current_amount == 0.0
    assert caster_am.current_amount == 22.5


def test_drain_antimatter_out_of_range():
    player_caster = MockPlayer("Caster Player")
    player_target = MockPlayer("Target Player")
    player_target.id = 2
    game = DummyGame()

    caster = Unit(owner=player_caster, position=Position(0, 0), in_hex=(0, 0), in_system="Sol", name="Caster", hull_size=HullSize.MEDIUM, game=game)
    target = Unit(owner=player_target, position=Position(500, 0), in_hex=(0, 0), in_system="Sol", name="Target", hull_size=HullSize.MEDIUM, game=game)
    target.id = 999

    engines = Engines(caster, speed=50.0)
    caster.add_component(engines)

    caster_am = AntimatterStorage(caster, max_capacity=100.0)
    caster_am.current_amount = 20.0
    caster.add_component(caster_am)

    target_am = AntimatterStorage(target, max_capacity=100.0)
    target_am.current_amount = 50.0
    target.add_component(target_am)

    game.galaxy.get_unit_by_id.return_value = target

    ability_comp = AbilityComponent(caster, [AbilityType.DRAIN_ANTIMATTER])
    caster.add_component(ability_comp)

    # Range of DRAIN_ANTIMATTER is 300.0, target is at 500.0 distance
    order = UseAbilityOrder(caster, {
        "ability_type": "drain_antimatter",
        "target_unit_id": target.id
    })

    order.execute(game.galaxy)
    assert order.status == OrderStatus.IN_PROGRESS
    assert len(order.sub_orders) == 2
    assert order.sub_orders[0].order_type == OrderType.MOVE
    assert order.sub_orders[1].order_type == OrderType.USE_ABILITY


def test_drain_antimatter_fails_friendly_target():
    player = MockPlayer()
    game = DummyGame()

    caster = Unit(owner=player, position=Position(0, 0), in_hex=(0, 0), in_system="Sol", name="Caster", hull_size=HullSize.MEDIUM, game=game)
    target = Unit(owner=player, position=Position(50, 0), in_hex=(0, 0), in_system="Sol", name="Target", hull_size=HullSize.MEDIUM, game=game)
    target.id = 999

    caster_am = AntimatterStorage(caster, max_capacity=100.0)
    caster_am.current_amount = 20.0
    caster.add_component(caster_am)

    target_am = AntimatterStorage(target, max_capacity=100.0)
    target_am.current_amount = 50.0
    target.add_component(target_am)

    game.galaxy.get_unit_by_id.return_value = target

    ability_comp = AbilityComponent(caster, [AbilityType.DRAIN_ANTIMATTER])
    caster.add_component(ability_comp)

    order = UseAbilityOrder(caster, {
        "ability_type": "drain_antimatter",
        "target_unit_id": target.id
    })

    order.execute(game.galaxy)
    assert order.status == OrderStatus.FAILED
    assert target_am.current_amount == 50.0
    assert caster_am.current_amount == 20.0


def test_drain_antimatter_fails_no_antimatter_target():
    player_caster = MockPlayer("Caster Player")
    player_target = MockPlayer("Target Player")
    player_target.id = 2
    game = DummyGame()

    caster = Unit(owner=player_caster, position=Position(0, 0), in_hex=(0, 0), in_system="Sol", name="Caster", hull_size=HullSize.MEDIUM, game=game)
    target = Unit(owner=player_target, position=Position(50, 0), in_hex=(0, 0), in_system="Sol", name="Target", hull_size=HullSize.MEDIUM, game=game)
    target.id = 999

    caster_am = AntimatterStorage(caster, max_capacity=100.0)
    caster_am.current_amount = 20.0
    caster.add_component(caster_am)

    # Target has AntimatterStorage with 0 current amount
    target_am = AntimatterStorage(target, max_capacity=100.0)
    target_am.current_amount = 0.0
    target.add_component(target_am)

    game.galaxy.get_unit_by_id.return_value = target

    ability_comp = AbilityComponent(caster, [AbilityType.DRAIN_ANTIMATTER])
    caster.add_component(ability_comp)

    order = UseAbilityOrder(caster, {
        "ability_type": "drain_antimatter",
        "target_unit_id": target.id
    })

    order.execute(game.galaxy)
    assert order.status == OrderStatus.FAILED


def test_drain_antimatter_unit_editor_validation():
    # Design without Antimatter Storage equipping drain_antimatter should fail validation
    invalid_template = CustomUnitTemplate(
        display_name="Siphon Ship",
        hull_size=HullSize.MEDIUM,
        components=ComponentConfig(
            has_engine=True,
            has_ability_component=True,
            abilities=["drain_antimatter"],
            has_antimatter_storage=False,
        )
    )
    errors = invalid_template.validate()
    assert any("has_antimatter_storage" in err for err in errors)

    # Valid design with Antimatter Storage
    valid_template = CustomUnitTemplate(
        display_name="Siphon Ship Valid",
        hull_size=HullSize.MEDIUM,
        components=ComponentConfig(
            has_engine=True,
            has_ability_component=True,
            abilities=["drain_antimatter"],
            has_antimatter_storage=True,
        )
    )
    errors_valid = valid_template.validate()
    assert not any("has_antimatter_storage" in err for err in errors_valid)
