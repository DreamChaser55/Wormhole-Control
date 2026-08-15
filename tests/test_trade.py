import unittest
from unittest.mock import MagicMock

from constants import (
    HullSize, RED, TRADE_BASE_HULL_COST, TRADE_BASE_INCOME,
    TRADE_INCOME_PER_DISTANCE_UNIT, TRADE_INTERSYSTEM_HOP_DISTANCE
)
from entities import Player, Unit, Planet
from geometry import Position
from galaxy import Galaxy, StarSystem
from unit_components import (
    TradeComponent, CivilianHabitatComponent, Engines, Hyperdrive,
    instantiate_unit_from_template
)
from unit_orders import (
    OrderStatus, OrderType, TradeOrder, ContinuousTradeOrder
)
from custom_unit_templates import CustomUnitTemplate, ComponentConfig, HULL_RESTRICTIONS
from gui.unit_editor_gui.catalog import COMPONENT_ROWS, COMPONENT_DESCRIPTIONS
from save_manager import serialize_unit, deserialize_unit, serialize_order, deserialize_order


class TestTradeComponent(unittest.TestCase):
    def setUp(self):
        self.player = Player(name="Test Trader", color=RED, is_human=True)
        self.player.credits = 500.0

        self.galaxy = Galaxy()
        self.system_a = StarSystem(name="Alpha", position=None, radius=4)
        self.system_b = StarSystem(name="Beta", position=None, radius=4)
        for h in list(self.system_a.hexes.values()) + list(self.system_b.hexes.values()):
            h.celestial_bodies.clear()
            h.units.clear()

        self.galaxy.systems["Alpha"] = self.system_a
        self.galaxy.systems["Beta"] = self.system_b
        self.galaxy.system_graph = {
            "Alpha": {"Beta": HullSize.HUGE},
            "Beta": {"Alpha": HullSize.HUGE}
        }

        # Habitat 1 in Alpha (0, 0)
        self.planet_a = Planet(in_hex=(0, 0), in_system="Alpha", planet_type=None)
        self.planet_a.owner = self.player
        self.planet_a.population = 100.0
        self.system_a.add_celestial_body(self.planet_a)

        self.habitat_unit_a = Unit(
            owner=self.player,
            position=Position(100.0, 100.0),
            in_hex=(0, 0),
            in_system="Alpha",
            name="Habitat Alpha",
            hull_size=HullSize.MEDIUM,
            game=MagicMock(galaxy=self.galaxy)
        )
        self.system_a.add_unit(self.habitat_unit_a)
        self.habitat_comp_a = CivilianHabitatComponent(self.habitat_unit_a, economic_bonus=50.0)
        self.habitat_unit_a.add_component(self.habitat_comp_a)

        # Habitat 2 in Alpha (3, 0) - Different sector, same system
        self.planet_a2 = Planet(in_hex=(3, 0), in_system="Alpha", planet_type=None)
        self.planet_a2.owner = self.player
        self.planet_a2.population = 100.0
        self.system_a.add_celestial_body(self.planet_a2)

        self.habitat_unit_a2 = Unit(
            owner=self.player,
            position=Position(100.0, 100.0),
            in_hex=(3, 0),
            in_system="Alpha",
            name="Habitat Alpha-2",
            hull_size=HullSize.MEDIUM,
            game=MagicMock(galaxy=self.galaxy)
        )
        self.system_a.add_unit(self.habitat_unit_a2)
        self.habitat_comp_a2 = CivilianHabitatComponent(self.habitat_unit_a2, economic_bonus=50.0)
        self.habitat_unit_a2.add_component(self.habitat_comp_a2)

        # Habitat 3 in Beta (1, 1) - Different system
        self.planet_b = Planet(in_hex=(1, 1), in_system="Beta", planet_type=None)
        self.planet_b.owner = self.player
        self.planet_b.population = 100.0
        self.system_b.add_celestial_body(self.planet_b)

        self.habitat_unit_b = Unit(
            owner=self.player,
            position=Position(100.0, 100.0),
            in_hex=(1, 1),
            in_system="Beta",
            name="Habitat Beta",
            hull_size=HullSize.MEDIUM,
            game=MagicMock(galaxy=self.galaxy)
        )
        self.system_b.add_unit(self.habitat_unit_b)
        self.habitat_comp_b = CivilianHabitatComponent(self.habitat_unit_b, economic_bonus=50.0)
        self.habitat_unit_b.add_component(self.habitat_comp_b)

        # Trade Ship
        self.trade_unit = Unit(
            owner=self.player,
            position=Position(100.0, 100.0),
            in_hex=(0, 0),
            in_system="Alpha",
            name="Merchantman",
            hull_size=HullSize.MEDIUM,
            game=MagicMock(galaxy=self.galaxy)
        )
        self.system_a.add_unit(self.trade_unit)
        self.trade_comp = TradeComponent(self.trade_unit, hull_cost=TRADE_BASE_HULL_COST)
        self.trade_unit.add_component(self.trade_comp)
        self.trade_unit.add_component(Engines(self.trade_unit, speed=100.0))

    def test_trade_component_initialization(self):
        self.assertEqual(self.trade_comp.hull_cost, TRADE_BASE_HULL_COST)
        self.assertEqual(self.trade_comp.trades_completed, 0)
        self.assertEqual(self.trade_comp.total_trade_income, 0.0)
        self.assertIsNone(self.trade_comp.last_traded_sector)
        self.assertEqual(self.trade_unit.trade_component, self.trade_comp)

    def test_engine_requirement_validation(self):
        # Design with Trade Component but NO engine -> MUST fail validation
        config_no_engine = ComponentConfig(
            has_trade_component=True,
            has_engine=False
        )
        template_no_engine = CustomUnitTemplate(
            display_name="Engine-less Trader",
            hull_size=HullSize.MEDIUM,
            components=config_no_engine
        )
        errors = template_no_engine.validate()
        self.assertTrue(any("Trade component requires an Engine component" in e for e in errors))

        # Design with Trade Component AND engine -> Valid
        config_with_engine = ComponentConfig(
            has_trade_component=True,
            has_engine=True,
            engine_speed=100.0
        )
        template_with_engine = CustomUnitTemplate(
            display_name="Valid Trader",
            hull_size=HullSize.MEDIUM,
            components=config_with_engine
        )
        errors_valid = template_with_engine.validate()
        self.assertFalse(any("Trade component requires an Engine component" in e for e in errors_valid))

    def test_hull_restrictions(self):
        self.assertIn("has_trade_component", HULL_RESTRICTIONS[HullSize.STRIKECRAFT_WING])
        self.assertIn("has_trade_component", HULL_RESTRICTIONS[HullSize.TINY])
        self.assertNotIn("has_trade_component", HULL_RESTRICTIONS[HullSize.SMALL])
        self.assertNotIn("has_trade_component", HULL_RESTRICTIONS[HullSize.MEDIUM])

    def test_distance_and_income_calculation(self):
        # Intra-system distance between (0, 0) and (3, 0) is 3 hexes
        origin = ("Alpha", (0, 0))
        dest_intra = ("Alpha", (3, 0))
        dist_intra = self.trade_comp.calculate_distance_between_sectors(origin, dest_intra, self.galaxy)
        self.assertEqual(dist_intra, 3.0)

        expected_income_intra = TRADE_BASE_INCOME + 3.0 * TRADE_INCOME_PER_DISTANCE_UNIT
        self.assertEqual(self.trade_comp.calculate_trade_income(origin, dest_intra, self.galaxy), expected_income_intra)

        # Same sector distance is 0, income is 0
        self.assertEqual(self.trade_comp.calculate_trade_income(origin, origin, self.galaxy), 0.0)

        # Inter-system distance from Alpha (0, 0) to Beta (1, 1) -> 1 hop * 10 + hex_dist((0,0), (1,1)) (which is 2) = 12.0
        dest_inter = ("Beta", (1, 1))
        dist_inter = self.trade_comp.calculate_distance_between_sectors(origin, dest_inter, self.galaxy)
        self.assertEqual(dist_inter, 1.0 * TRADE_INTERSYSTEM_HOP_DISTANCE + 2.0)
        expected_income_inter = TRADE_BASE_INCOME + dist_inter * TRADE_INCOME_PER_DISTANCE_UNIT
        self.assertEqual(self.trade_comp.calculate_trade_income(origin, dest_inter, self.galaxy), expected_income_inter)

    def test_trade_execution_cycle(self):
        # 1. Initial trade establishes port without payout
        success1, income1, msg1 = self.trade_comp.execute_trade(self.habitat_unit_a, self.galaxy)
        self.assertTrue(success1)
        self.assertEqual(income1, 0.0)
        self.assertEqual(self.trade_comp.last_traded_sector, ("Alpha", (0, 0)))
        self.assertEqual(self.trade_comp.trades_completed, 0)
        self.assertEqual(self.player.credits, 500.0)

        # 2. Attempting to trade again in the same sector fails
        success_same, income_same, msg_same = self.trade_comp.execute_trade(self.habitat_unit_a, self.galaxy)
        self.assertFalse(success_same)
        self.assertEqual(income_same, 0.0)
        self.assertIn("different sector", msg_same)

        # 3. Moving to Habitat Alpha-2 in sector (3, 0) earns distance-based payout
        success2, income2, msg2 = self.trade_comp.execute_trade(self.habitat_unit_a2, self.galaxy)
        self.assertTrue(success2)
        expected_income = TRADE_BASE_INCOME + 3.0 * TRADE_INCOME_PER_DISTANCE_UNIT
        self.assertEqual(income2, expected_income)
        self.assertEqual(self.player.credits, 500.0 + expected_income)
        self.assertEqual(self.trade_comp.trades_completed, 1)
        self.assertEqual(self.trade_comp.last_traded_sector, ("Alpha", (3, 0)))
        self.assertEqual(self.trade_comp.last_trade_income, expected_income)
        self.assertEqual(self.trade_comp.total_trade_income, expected_income)

        # 4. Moving to Habitat Beta in Beta system (1, 1) earns even higher inter-system payout
        # Hex distance between (3,0) and (1,1) is 2
        dist_inter = 10.0 + 2.0
        expected_income_inter = TRADE_BASE_INCOME + dist_inter * TRADE_INCOME_PER_DISTANCE_UNIT
        success3, income3, msg3 = self.trade_comp.execute_trade(self.habitat_unit_b, self.galaxy)
        self.assertTrue(success3)
        self.assertEqual(income3, expected_income_inter)
        self.assertEqual(self.trade_comp.trades_completed, 2)
        self.assertGreater(income3, income2)

    def test_trade_fails_on_inactive_or_destroyed_habitat(self):
        # Prime at habitat A
        self.trade_comp.execute_trade(self.habitat_unit_a, self.galaxy)

        # Destroy habitat A2
        self.habitat_comp_a2.current_hit_points = 0
        self.assertTrue(self.habitat_comp_a2.is_destroyed)

        success, income, msg = self.trade_comp.execute_trade(self.habitat_unit_a2, self.galaxy)
        self.assertFalse(success)
        self.assertEqual(income, 0.0)

        # Uncolonize planet B
        self.planet_b.population = 0
        self.assertFalse(self.habitat_comp_b.is_active(self.galaxy))
        success_b, income_b, msg_b = self.trade_comp.execute_trade(self.habitat_unit_b, self.galaxy)
        self.assertFalse(success_b)
        self.assertEqual(income_b, 0.0)


class TestTradeOrders(unittest.TestCase):
    def setUp(self):
        self.player = Player(name="Test Trader", color=RED, is_human=True)
        self.player.credits = 100.0

        self.galaxy = Galaxy()
        self.system = StarSystem(name="Sol", position=None, radius=4)
        for h in self.system.hexes.values():
            h.celestial_bodies.clear()
            h.units.clear()
        self.galaxy.systems["Sol"] = self.system

        # Planet & Habitat 1 in (0, 0)
        self.planet1 = Planet(in_hex=(0, 0), in_system="Sol", planet_type=None)
        self.planet1.owner = self.player
        self.planet1.population = 100.0
        self.system.add_celestial_body(self.planet1)

        self.hab1 = Unit(
            owner=self.player,
            position=Position(100.0, 100.0),
            in_hex=(0, 0),
            in_system="Sol",
            name="Habitat 1",
            hull_size=HullSize.MEDIUM,
            game=MagicMock(galaxy=self.galaxy)
        )
        self.system.add_unit(self.hab1)
        self.hab1.add_component(CivilianHabitatComponent(self.hab1, economic_bonus=50.0))

        # Planet & Habitat 2 in (2, 0)
        self.planet2 = Planet(in_hex=(2, 0), in_system="Sol", planet_type=None)
        self.planet2.owner = self.player
        self.planet2.population = 100.0
        self.system.add_celestial_body(self.planet2)

        self.hab2 = Unit(
            owner=self.player,
            position=Position(100.0, 100.0),
            in_hex=(2, 0),
            in_system="Sol",
            name="Habitat 2",
            hull_size=HullSize.MEDIUM,
            game=MagicMock(galaxy=self.galaxy)
        )
        self.system.add_unit(self.hab2)
        self.hab2.add_component(CivilianHabitatComponent(self.hab2, economic_bonus=50.0))

        # Trade Ship in (0, 0)
        self.trader = Unit(
            owner=self.player,
            position=Position(100.0, 100.0),
            in_hex=(0, 0),
            in_system="Sol",
            name="Trader 1",
            hull_size=HullSize.MEDIUM,
            game=MagicMock(galaxy=self.galaxy)
        )
        self.system.add_unit(self.trader)
        self.trade_comp = TradeComponent(self.trader)
        self.trader.add_component(self.trade_comp)
        self.trader.add_component(Engines(self.trader, speed=100.0))

    def test_trade_order_direct_execution(self):
        # Prime at Hab 1
        self.trade_comp.execute_trade(self.hab1, self.galaxy)

        # Place trader in range of Hab 2 and give TradeOrder
        self.trader.in_hex = (2, 0)
        self.trader.position = Position(100.0, 100.0)

        order = TradeOrder(self.trader, {"target_unit_id": self.hab2.id})
        order.execute(self.galaxy)

        self.assertEqual(order.status, OrderStatus.COMPLETED)
        self.assertEqual(self.trade_comp.trades_completed, 1)
        expected_income = TRADE_BASE_INCOME + 2.0 * TRADE_INCOME_PER_DISTANCE_UNIT
        self.assertEqual(self.player.credits, 100.0 + expected_income)

    def test_continuous_trade_order_loop(self):
        # Start continuous trade order
        cont_order = ContinuousTradeOrder(self.trader)
        cont_order.execute(self.galaxy)

        # Since trader is in (0, 0) where Hab 1 is located, it primes at Hab 1
        # and automatically spawns a TradeOrder sub-order targeting Hab 2 in (2, 0)
        self.assertTrue(cont_order.has_active_sub_orders())
        sub = cont_order.sub_orders[0]
        self.assertEqual(sub.order_type, OrderType.TRADE)
        self.assertEqual(sub.parameters.get("target_unit_id"), self.hab2.id)

        # Simulate arrival at Hab 2
        self.trader.in_hex = (2, 0)
        self.trader.position = Position(100.0, 100.0)
        sub.execute(self.galaxy)
        self.assertEqual(sub.status, OrderStatus.COMPLETED)

        # Update continuous order -> picks Hab 1 next
        cont_order.update(self.galaxy)
        self.assertTrue(cont_order.has_active_sub_orders())
        next_sub = cont_order.sub_orders[0]
        self.assertEqual(next_sub.order_type, OrderType.TRADE)
        self.assertEqual(next_sub.parameters.get("target_unit_id"), self.hab1.id)


class TestTradeSerializationAndCatalog(unittest.TestCase):
    def setUp(self):
        self.player = Player(name="Test Player", color=RED, is_human=True)
        self.galaxy = Galaxy()
        self.system = StarSystem(name="Sol", position=None, radius=3)
        self.galaxy.systems["Sol"] = self.system

    def test_save_load_serialization(self):
        unit = Unit(
            owner=self.player,
            position=Position(50.0, 50.0),
            in_hex=(1, -1),
            in_system="Sol",
            name="Trade Vessel",
            hull_size=HullSize.MEDIUM,
            game=MagicMock(galaxy=self.galaxy)
        )
        trade_comp = TradeComponent(unit, hull_cost=10.0, trade_revenue_multiplier=1.5)
        trade_comp.last_traded_sector = ("Sol", (0, 0))
        trade_comp.last_trade_income = 75.0
        trade_comp.total_trade_income = 300.0
        trade_comp.trades_completed = 4
        unit.add_component(trade_comp)
        unit.add_component(Engines(unit, speed=100.0))

        # Serialize
        serialized = serialize_unit(unit)
        self.assertIn("TradeComponent", serialized["components"])
        comp_data = serialized["components"]["TradeComponent"]
        self.assertEqual(comp_data["total_trade_income"], 300.0)
        self.assertEqual(comp_data["trades_completed"], 4)
        self.assertEqual(comp_data["last_traded_sector"], ["Sol", (0, 0)])

        # Deserialize
        players_by_id = {self.player.id: self.player}
        restored_unit = deserialize_unit(serialized, players_by_id, MagicMock(galaxy=self.galaxy))
        self.assertIsNotNone(restored_unit.trade_component)
        self.assertEqual(restored_unit.trade_component.total_trade_income, 300.0)
        self.assertEqual(restored_unit.trade_component.trades_completed, 4)
        self.assertEqual(restored_unit.trade_component.last_traded_sector, ("Sol", (0, 0)))
        self.assertEqual(restored_unit.trade_component.trade_revenue_multiplier, 1.5)

    def test_catalog_and_descriptions(self):
        catalog_keys = [row["key"] for row in COMPONENT_ROWS]
        self.assertIn("has_trade_component", catalog_keys)
        self.assertIn("has_trade_component", COMPONENT_DESCRIPTIONS)
        desc = COMPONENT_DESCRIPTIONS["has_trade_component"]
        self.assertIn("Trade Module", desc)
        self.assertIn("Engine", desc)

    def test_instantiate_from_template(self):
        from unit_templates import UNIT_TEMPLATES
        template = {
            "name": "Custom Merchant",
            "hull_size": "MEDIUM",
            "has_engine": True,
            "engine_speed": 100.0,
            "has_trade_component": True,
            "trade_hull_cost": 10.0,
            "trade_revenue_multiplier": 1.2
        }
        UNIT_TEMPLATES["Custom Merchant"] = template
        try:
            mock_game = MagicMock(galaxy=self.galaxy)
            instantiate_unit_from_template(
                template_name="Custom Merchant",
                owner=self.player,
                system_name="Sol",
                hex_coord=(0, 0),
                position=Position(0, 0),
                galaxy=self.galaxy,
                game=mock_game
            )
            all_units = self.system.get_all_units()
            self.assertTrue(len(all_units) > 0)
            unit = all_units[-1][0]
            self.assertIsNotNone(unit.trade_component)
            self.assertEqual(unit.trade_component.trade_revenue_multiplier, 1.2)
            self.assertEqual(unit.trade_component.hull_cost, 10.0)
        finally:
            UNIT_TEMPLATES.pop("Custom Merchant", None)


if __name__ == '__main__':
    unittest.main()
