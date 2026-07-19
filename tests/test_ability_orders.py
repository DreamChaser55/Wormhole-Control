import pytest
from unittest.mock import MagicMock, patch
from geometry import Position, distance
from entities import Unit, Player, OrderType
from constants import HullSize, RED
from unit_components import AbilityComponent, AbilityType, Engines, AntimatterStorage, Commander
from unit_orders import UseAbilityOrder, OrderStatus, MoveOrder
from tests.test_unit_components import MockPlayer
from rendering.sector_renderer import SectorViewRenderer
from rendering.system_renderer import SystemViewRenderer

class DummyGame:
    def __init__(self):
        self.galaxy = MagicMock()
        self.selected_objects = []
        self.sector_view_mouse_hover_object = None
        self.is_dragging_selection_box = False
        self.current_system_name = "Sol"
        self.current_sector_coord = (0, 0)
        self.screen = MagicMock()
        self.overlay_surface = MagicMock()
        self.players = []
        self.current_player_index = 0
        self.system_view_mouse_hover_hex = None

def test_use_ability_order_no_target():
    player = MockPlayer()
    game = DummyGame()
    unit = Unit(owner=player, position=Position(0, 0), in_hex=(0, 0), in_system="Sol", name="Test Ship", hull_size=HullSize.MEDIUM, game=game)
    
    # Setup ability component
    ability_comp = AbilityComponent(unit, [AbilityType.ADAPTIVE_FORCEFIELD])
    unit.add_component(ability_comp)
    
    # Verify antimatter is set up and sufficient (cost is 20)
    am_comp = unit.antimatter_component
    am_comp.current_amount = 50.0
    
    order = UseAbilityOrder(unit, {
        "ability_type": "adaptive_forcefield"
    })
    
    order.execute(game.galaxy)
    assert order.status == OrderStatus.COMPLETED
    assert unit.damage_reduction == 0.75

def test_use_ability_order_unit_target_in_range():
    player = MockPlayer()
    game = DummyGame()
    unit = Unit(owner=player, position=Position(0, 0), in_hex=(0, 0), in_system="Sol", name="Caster", hull_size=HullSize.MEDIUM, game=game)
    target = Unit(owner=player, position=Position(100, 0), in_hex=(0, 0), in_system="Sol", name="Target", hull_size=HullSize.MEDIUM, game=game)
    target.id = 999
    
    game.galaxy.get_unit_by_id.return_value = target
    
    ability_comp = AbilityComponent(unit, [AbilityType.ION_BOLT])
    unit.add_component(ability_comp)
    unit.antimatter_component.current_amount = 50.0
    
    # Range of ION_BOLT is 400.0, target is at 100.0 distance
    order = UseAbilityOrder(unit, {
        "ability_type": "ion_bolt",
        "target_unit_id": target.id
    })
    
    order.execute(game.galaxy)
    assert order.status == OrderStatus.COMPLETED
    assert target.is_disabled is True

def test_use_ability_order_unit_target_out_of_range():
    player = MockPlayer()
    game = DummyGame()
    unit = Unit(owner=player, position=Position(0, 0), in_hex=(0, 0), in_system="Sol", name="Caster", hull_size=HullSize.MEDIUM, game=game)
    target = Unit(owner=player, position=Position(500, 0), in_hex=(0, 0), in_system="Sol", name="Target", hull_size=HullSize.MEDIUM, game=game)
    target.id = 999
    
    engines = Engines(unit, speed=50.0)
    unit.add_component(engines)
    
    game.galaxy.get_unit_by_id.return_value = target
    
    ability_comp = AbilityComponent(unit, [AbilityType.ION_BOLT])
    unit.add_component(ability_comp)
    unit.antimatter_component.current_amount = 50.0
    
    # Range of ION_BOLT is 400.0, target is at 500.0 distance
    order = UseAbilityOrder(unit, {
        "ability_type": "ion_bolt",
        "target_unit_id": target.id
    })
    
    order.execute(game.galaxy)
    assert order.status == OrderStatus.IN_PROGRESS
    assert len(order.sub_orders) == 2
    assert order.sub_orders[0].order_type == OrderType.MOVE
    assert order.sub_orders[1].order_type == OrderType.USE_ABILITY

def test_use_ability_order_position_target_in_range():
    player = MockPlayer()
    game = DummyGame()
    unit = Unit(owner=player, position=Position(0, 0), in_hex=(0, 0), in_system="Sol", name="Caster", hull_size=HullSize.MEDIUM, game=game)
    
    ability_comp = AbilityComponent(unit, [AbilityType.CLUSTER_WARHEAD])
    unit.add_component(ability_comp)
    unit.antimatter_component.current_amount = 50.0
    
    # CLUSTER_WARHEAD range is 500.0, target is at 100.0 distance
    order = UseAbilityOrder(unit, {
        "ability_type": "cluster_warhead",
        "target_position": Position(100, 0),
        "target_system_name": "Sol",
        "target_hex_coord": (0, 0)
    })
    
    # Mock galaxy and systems
    system = MagicMock()
    hex_obj = MagicMock()
    hex_obj.units = []
    system.hexes = {(0, 0): hex_obj}
    game.galaxy.systems = {"Sol": system}
    
    order.execute(game.galaxy)
    assert order.status == OrderStatus.COMPLETED

def test_use_ability_order_position_target_out_of_range():
    player = MockPlayer()
    game = DummyGame()
    unit = Unit(owner=player, position=Position(0, 0), in_hex=(0, 0), in_system="Sol", name="Caster", hull_size=HullSize.MEDIUM, game=game)
    
    engines = Engines(unit, speed=50.0)
    unit.add_component(engines)
    
    ability_comp = AbilityComponent(unit, [AbilityType.CLUSTER_WARHEAD])
    unit.add_component(ability_comp)
    unit.antimatter_component.current_amount = 50.0
    
    # CLUSTER_WARHEAD range is 500.0, target position is at 600.0 distance
    order = UseAbilityOrder(unit, {
        "ability_type": "cluster_warhead",
        "target_position": Position(600, 0),
        "target_system_name": "Sol",
        "target_hex_coord": (0, 0)
    })
    
    order.execute(game.galaxy)
    assert order.status == OrderStatus.IN_PROGRESS
    assert len(order.sub_orders) == 2
    assert order.sub_orders[0].order_type == OrderType.MOVE
    assert order.sub_orders[1].order_type == OrderType.USE_ABILITY

def test_apply_cluster_warhead_accurate_routing():
    player = MockPlayer()
    game = DummyGame()
    caster = Unit(owner=player, position=Position(0, 0), in_hex=(0, 0), in_system="Sol", name="Caster", hull_size=HullSize.MEDIUM, game=game)
    enemy = Unit(owner=player, position=Position(10, 10), in_hex=(0, 1), in_system="Sol", name="Enemy", hull_size=HullSize.MEDIUM, game=game)
    
    ability_comp = AbilityComponent(caster, [AbilityType.CLUSTER_WARHEAD])
    caster.add_component(ability_comp)
    
    # Mock system and hexes
    system = MagicMock()
    hex00 = MagicMock()
    hex01 = MagicMock()
    hex00.units = [caster]
    hex01.units = [enemy]
    system.hexes = {(0, 0): hex00, (0, 1): hex01}
    game.galaxy.systems = {"Sol": system}
    
    # Target position is (10, 10) in Hex (0, 1)
    # Target is out of caster's hex but we fire it at hex (0, 1) directly
    success = ability_comp.activate(
        AbilityType.CLUSTER_WARHEAD,
        game.galaxy,
        target_position=Position(10, 10),
        target_system_name="Sol",
        target_hex_coord=(0, 1)
    )
    
    assert success is True
    # Enemy should take splash damage (base damage is 80, falloff is 0 because distance is 0)
    assert enemy.current_hit_points < enemy.max_hit_points

def test_sector_view_renderer_collect_waypoints_for_ability():
    game = DummyGame()
    renderer = SectorViewRenderer(game)
    
    caster = Unit(owner=MockPlayer(), position=Position(0, 0), in_hex=(0, 0), in_system="Sol", name="Caster", hull_size=HullSize.MEDIUM, game=game)
    order = UseAbilityOrder(caster, {
        "ability_type": "cluster_warhead",
        "target_position": Position(100, 200),
        "target_system_name": "Sol",
        "target_hex_coord": (0, 0)
    })
    caster.commander_component.add_order(order)
    
    waypoints = renderer._collect_all_waypoints(caster)
    assert len(waypoints) == 1
    assert waypoints[0]['position'] == Position(100, 200)
    assert waypoints[0]['order_type'] == OrderType.USE_ABILITY
    
    # Verify styling
    color, width = renderer._get_waypoint_style(waypoints[0])
    assert color == (255, 105, 180) # Hot Pink

def test_system_view_renderer_collect_waypoints_for_ability():
    game = DummyGame()
    renderer = SystemViewRenderer(game)
    
    caster = Unit(owner=MockPlayer(), position=Position(0, 0), in_hex=(0, 0), in_system="Sol", name="Caster", hull_size=HullSize.MEDIUM, game=game)
    game.players = [caster.owner]
    game.selected_objects = [caster]
    order = UseAbilityOrder(caster, {
        "ability_type": "cluster_warhead",
        "target_position": Position(100, 200),
        "target_system_name": "Sol",
        "target_hex_coord": (0, 1)
    })
    caster.commander_component.add_order(order)
    
    # Test drawing method collection using mocks
    with patch.object(renderer, 'screen', MagicMock()), \
         patch.object(renderer, 'overlay_surface', MagicMock()), \
         patch('rendering.system_renderer.hex_to_pixel', return_value=Position(0, 0)):
        
        # We check that collect_all_hex_waypoints handles USE_ABILITY
        system = MagicMock()
        system.name = "Sol"
        system.hexes = {(0, 0): MagicMock(), (0, 1): MagicMock()}
        game.galaxy.systems = {"Sol": system}
        
        # Manually invoke line drawing which triggers the waypoint collection
        with patch("rendering.system_renderer.pygame.draw.line") as mock_draw_line, \
             patch("rendering.system_renderer.pygame.draw.circle") as mock_draw_circle:
            renderer._draw_system_view_order_lines(system)
            # The line should be drawn to hex (0, 1)
            assert mock_draw_line.called


def test_capture_unit_success_no_engines():
    player_caster = MockPlayer()
    player_target = MockPlayer()
    player_target.id = 2
    game = DummyGame()
    caster = Unit(owner=player_caster, position=Position(0, 0), in_hex=(0, 0), in_system="Sol", name="Caster", hull_size=HullSize.MEDIUM, game=game)
    target = Unit(owner=player_target, position=Position(50, 0), in_hex=(0, 0), in_system="Sol", name="Target", hull_size=HullSize.MEDIUM, game=game)
    target.id = 999
    
    game.galaxy.get_unit_by_id.return_value = target
    
    ability_comp = AbilityComponent(caster, [AbilityType.CAPTURE_UNIT])
    caster.add_component(ability_comp)
    caster.antimatter_component.current_amount = 50.0
    
    order = UseAbilityOrder(caster, {
        "ability_type": "capture_unit",
        "target_unit_id": target.id
    })
    
    order.execute(game.galaxy)
    assert order.status == OrderStatus.COMPLETED
    assert target.owner == player_caster


def test_capture_unit_success_disabled_engines():
    player_caster = MockPlayer()
    player_target = MockPlayer()
    player_target.id = 2
    game = DummyGame()
    caster = Unit(owner=player_caster, position=Position(0, 0), in_hex=(0, 0), in_system="Sol", name="Caster", hull_size=HullSize.MEDIUM, game=game)
    target = Unit(owner=player_target, position=Position(50, 0), in_hex=(0, 0), in_system="Sol", name="Target", hull_size=HullSize.MEDIUM, game=game)
    target.id = 999
    
    engines = Engines(target, speed=50.0)
    engines.current_hit_points = 0 # Destroyed / Disabled engines
    target.add_component(engines)
    
    game.galaxy.get_unit_by_id.return_value = target
    
    ability_comp = AbilityComponent(caster, [AbilityType.CAPTURE_UNIT])
    caster.add_component(ability_comp)
    caster.antimatter_component.current_amount = 50.0
    
    order = UseAbilityOrder(caster, {
        "ability_type": "capture_unit",
        "target_unit_id": target.id
    })
    
    order.execute(game.galaxy)
    assert order.status == OrderStatus.COMPLETED
    assert target.owner == player_caster


def test_capture_unit_success_disabled_unit():
    player_caster = MockPlayer()
    player_target = MockPlayer()
    player_target.id = 2
    game = DummyGame()
    caster = Unit(owner=player_caster, position=Position(0, 0), in_hex=(0, 0), in_system="Sol", name="Caster", hull_size=HullSize.MEDIUM, game=game)
    target = Unit(owner=player_target, position=Position(50, 0), in_hex=(0, 0), in_system="Sol", name="Target", hull_size=HullSize.MEDIUM, game=game)
    target.id = 999
    
    engines = Engines(target, speed=50.0)
    target.add_component(engines)
    target.is_disabled = True # Unit disabled (e.g. by Ion Bolt)
    
    game.galaxy.get_unit_by_id.return_value = target
    
    ability_comp = AbilityComponent(caster, [AbilityType.CAPTURE_UNIT])
    caster.add_component(ability_comp)
    caster.antimatter_component.current_amount = 50.0
    
    order = UseAbilityOrder(caster, {
        "ability_type": "capture_unit",
        "target_unit_id": target.id
    })
    
    order.execute(game.galaxy)
    assert order.status == OrderStatus.COMPLETED
    assert target.owner == player_caster


def test_capture_unit_fails_engines_active():
    player_caster = MockPlayer()
    player_target = MockPlayer()
    player_target.id = 2
    game = DummyGame()
    caster = Unit(owner=player_caster, position=Position(0, 0), in_hex=(0, 0), in_system="Sol", name="Caster", hull_size=HullSize.MEDIUM, game=game)
    target = Unit(owner=player_target, position=Position(50, 0), in_hex=(0, 0), in_system="Sol", name="Target", hull_size=HullSize.MEDIUM, game=game)
    target.id = 999
    
    engines = Engines(target, speed=50.0)
    target.add_component(engines) # Active, healthy engines
    
    game.galaxy.get_unit_by_id.return_value = target
    
    ability_comp = AbilityComponent(caster, [AbilityType.CAPTURE_UNIT])
    caster.add_component(ability_comp)
    caster.antimatter_component.current_amount = 50.0
    
    order = UseAbilityOrder(caster, {
        "ability_type": "capture_unit",
        "target_unit_id": target.id
    })
    
    order.execute(game.galaxy)
    assert order.status == OrderStatus.FAILED
    assert target.owner == player_target # Still owned by original owner


def test_capture_unit_fails_already_friendly():
    player = MockPlayer()
    game = DummyGame()
    caster = Unit(owner=player, position=Position(0, 0), in_hex=(0, 0), in_system="Sol", name="Caster", hull_size=HullSize.MEDIUM, game=game)
    target = Unit(owner=player, position=Position(50, 0), in_hex=(0, 0), in_system="Sol", name="Target", hull_size=HullSize.MEDIUM, game=game)
    target.id = 999
    
    game.galaxy.get_unit_by_id.return_value = target
    
    ability_comp = AbilityComponent(caster, [AbilityType.CAPTURE_UNIT])
    caster.add_component(ability_comp)
    caster.antimatter_component.current_amount = 50.0
    
    order = UseAbilityOrder(caster, {
        "ability_type": "capture_unit",
        "target_unit_id": target.id
    })
    
    order.execute(game.galaxy)
    assert order.status == OrderStatus.FAILED


def test_capture_unit_out_of_range():
    player_caster = MockPlayer()
    player_target = MockPlayer()
    player_target.id = 2
    game = DummyGame()
    caster = Unit(owner=player_caster, position=Position(0, 0), in_hex=(0, 0), in_system="Sol", name="Caster", hull_size=HullSize.MEDIUM, game=game)
    target = Unit(owner=player_target, position=Position(200, 0), in_hex=(0, 0), in_system="Sol", name="Target", hull_size=HullSize.MEDIUM, game=game)
    target.id = 999
    
    engines = Engines(caster, speed=50.0)
    caster.add_component(engines)
    
    game.galaxy.get_unit_by_id.return_value = target
    
    ability_comp = AbilityComponent(caster, [AbilityType.CAPTURE_UNIT])
    caster.add_component(ability_comp)
    caster.antimatter_component.current_amount = 50.0
    
    # Range of CAPTURE_UNIT is 100.0, target is at 200.0 distance
    order = UseAbilityOrder(caster, {
        "ability_type": "capture_unit",
        "target_unit_id": target.id
    })
    
    order.execute(game.galaxy)
    assert order.status == OrderStatus.IN_PROGRESS
    assert len(order.sub_orders) == 2
    assert order.sub_orders[0].order_type == OrderType.MOVE
    assert order.sub_orders[1].order_type == OrderType.USE_ABILITY
