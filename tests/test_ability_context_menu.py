import pytest
from unittest.mock import MagicMock, patch
from geometry import Position
from entities import Unit
from unit_components import AbilityComponent, AbilityType
from input_processor import InputProcessor
from events import UseAbilityEvent
from constants import HullSize

class MockPlayer:
    def __init__(self, name="Test Player"):
        self.id = 1
        self.name = name

def test_get_ability_context_options_empty():
    game = MagicMock()
    game.pending_ability = None
    player = MockPlayer()
    game.players = [player]
    game.current_player_index = 0
    
    ip = InputProcessor(game)
    
    # 1. No actors
    options = ip.get_ability_context_options([], target_is_unit=False)
    assert options == []

    # 2. Actors don't belong to current player
    enemy = MockPlayer("Enemy")
    enemy.id = 2
    unit = Unit(owner=enemy, position=Position(0,0), in_hex=(0,0), in_system="Sol", name="Enemy Unit", hull_size=HullSize.MEDIUM, game=game)
    options = ip.get_ability_context_options([unit], target_is_unit=False)
    assert options == []

def test_get_ability_context_options_single_unit():
    game = MagicMock()
    game.pending_ability = None
    player = MockPlayer()
    game.players = [player]
    game.current_player_index = 0
    
    ip = InputProcessor(game)
    
    unit = Unit(owner=player, position=Position(0,0), in_hex=(0,0), in_system="Sol", name="My Unit", hull_size=HullSize.MEDIUM, game=game)
    ability_comp = AbilityComponent(unit, [AbilityType.CLUSTER_WARHEAD, AbilityType.ION_BOLT])
    unit.add_component(ability_comp)
    
    # Ready status
    options = ip.get_ability_context_options([unit], target_is_unit=False)
    assert len(options) == 1
    assert options[0] == ("Cluster Warhead (Ready)", "use_ability_cluster_warhead")

    # Cooldown status
    ability_comp.abilities[AbilityType.CLUSTER_WARHEAD].cooldown_remaining = 3
    options = ip.get_ability_context_options([unit], target_is_unit=False)
    assert options[0] == ("Cluster Warhead (Cooldown: 3t)", "use_ability_cluster_warhead")
    ability_comp.abilities[AbilityType.CLUSTER_WARHEAD].cooldown_remaining = 0

    # Low AM status
    unit.antimatter_component.current_amount = 5.0  # Cluster Warhead cost is 30
    options = ip.get_ability_context_options([unit], target_is_unit=False)
    assert options[0] == ("Cluster Warhead (Low AM (5/30))", "use_ability_cluster_warhead")
    unit.antimatter_component.current_amount = 50.0

    # Active status
    ability_comp.abilities[AbilityType.CLUSTER_WARHEAD].is_active = True
    ability_comp.abilities[AbilityType.CLUSTER_WARHEAD].duration_remaining = 2
    options = ip.get_ability_context_options([unit], target_is_unit=False)
    assert options[0] == ("Cluster Warhead (Active (2t))", "use_ability_cluster_warhead")

def test_get_ability_context_options_multiple_units():
    game = MagicMock()
    game.pending_ability = None
    player = MockPlayer()
    game.players = [player]
    game.current_player_index = 0
    
    ip = InputProcessor(game)
    
    unit1 = Unit(owner=player, position=Position(0,0), in_hex=(0,0), in_system="Sol", name="Unit 1", hull_size=HullSize.MEDIUM, game=game)
    ability_comp1 = AbilityComponent(unit1, [AbilityType.CLUSTER_WARHEAD])
    unit1.add_component(ability_comp1)
    
    unit2 = Unit(owner=player, position=Position(0,0), in_hex=(0,0), in_system="Sol", name="Unit 2", hull_size=HullSize.MEDIUM, game=game)
    ability_comp2 = AbilityComponent(unit2, [AbilityType.CLUSTER_WARHEAD])
    unit2.add_component(ability_comp2)
    
    # 2/2 ready
    options = ip.get_ability_context_options([unit1, unit2], target_is_unit=False)
    assert len(options) == 1
    assert options[0] == ("Cluster Warhead (2/2 Ready)", "use_ability_cluster_warhead")
    
    # 1/2 ready (one on cooldown)
    ability_comp1.abilities[AbilityType.CLUSTER_WARHEAD].cooldown_remaining = 3
    options = ip.get_ability_context_options([unit1, unit2], target_is_unit=False)
    assert options[0] == ("Cluster Warhead (1/2 Ready)", "use_ability_cluster_warhead")

def test_handle_context_menu_action_use_ability():
    game = MagicMock()
    game.pending_ability = None
    player = MockPlayer()
    game.players = [player]
    game.current_player_index = 0
    game.current_system_name = "Sol"
    game.current_sector_coord = (0, 0)
    
    ip = InputProcessor(game)
    
    unit = Unit(owner=player, position=Position(0,0), in_hex=(0,0), in_system="Sol", name="Unit", hull_size=HullSize.MEDIUM, game=game)
    game.selected_objects = [unit]
    target_pos = Position(100, 200)
    
    with patch('pygame.key.get_mods', return_value=0):
        with patch.object(game.event_bus, 'publish') as mock_publish:
            ip.handle_context_menu_action("use_ability_cluster_warhead", target_pos)
            mock_publish.assert_called_once()
            event = mock_publish.call_args[0][0]
            assert isinstance(event, UseAbilityEvent)
            assert event.ability_type_str == "cluster_warhead"
            assert event.target_position == target_pos
            assert event.target_unit is None

def test_enemy_unit_context_menu_has_use_ability():
    game = MagicMock()
    game.pending_ability = None
    player = MockPlayer()
    enemy = MockPlayer("Enemy")
    enemy.id = 2
    game.players = [player, enemy]
    game.current_player_index = 0
    game.current_system_name = "Sol"
    game.current_sector_coord = (0, 0)
    
    ip = InputProcessor(game)
    
    selected_unit = Unit(owner=player, position=Position(0,0), in_hex=(0,0), in_system="Sol", name="Caster", hull_size=HullSize.MEDIUM, game=game)
    ability_comp = AbilityComponent(selected_unit, [AbilityType.ION_BOLT])
    selected_unit.add_component(ability_comp)
    game.selected_objects = [selected_unit]
    
    options = ip.get_ability_context_options(game.selected_objects, target_is_unit=True)
    assert len(options) == 1
    assert options[0] == ("Ion Bolt (Ready)", "use_ability_ion_bolt")

def test_enemy_unit_right_click_opens_menu_with_use_ability():
    game = MagicMock()
    game.pending_ability = None
    player = MockPlayer()
    enemy = MockPlayer("Enemy")
    enemy.id = 2
    game.players = [player, enemy]
    game.current_player_index = 0
    game.current_system_name = "Sol"
    game.current_sector_coord = (0, 0)
    game.view_mode = 'sector'
    
    selected_unit = Unit(owner=player, position=Position(0,0), in_hex=(0,0), in_system="Sol", name="Caster", hull_size=HullSize.MEDIUM, game=game)
    ability_comp = AbilityComponent(selected_unit, [AbilityType.ION_BOLT])
    selected_unit.add_component(ability_comp)
    game.selected_objects = [selected_unit]
    
    enemy_unit = Unit(owner=enemy, position=Position(100,0), in_hex=(0,0), in_system="Sol", name="Enemy Unit", hull_size=HullSize.MEDIUM, game=game)
    game.sector_view_mouse_hover_object = enemy_unit
    
    ip = InputProcessor(game)
    
    with patch('pygame.key.get_mods', return_value=0):
        with patch.object(game.gui, 'open_context_menu') as mock_open:
            with patch('input_processor.distance_sq', return_value=0):
                with patch('input_processor.pixels_to_sector_coords', return_value=Position(100,0)):
                    ip.handle_mouse_click(3, Position(0,0))
                    
                    mock_open.assert_called_once()
                    args = mock_open.call_args[0]
                    options = args[1]
                    
                    use_ability_option = next((opt for opt in options if opt[0] == "Use Ability"), None)
                    assert use_ability_option is not None
                    sub_options = use_ability_option[1]
                    assert len(sub_options) == 1
                    assert sub_options[0] == ("Ion Bolt (Ready)", "use_ability_ion_bolt")
