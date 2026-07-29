import pytest
from unittest.mock import MagicMock
from entities import Unit
from game import Game
from constants import HullSize
from geometry import Position

def test_multi_unit_selection_sidebar_buttons():
    # Setup mock game and units
    mock_game = MagicMock()
    mock_game.galaxy = MagicMock()
    mock_game.sidebar_needs_update = True
    mock_game.selected_objects = []
    mock_game.gui = MagicMock()
    
    player = MagicMock()
    player.name = "Player 1"
    
    unit1 = Unit(
        owner=player,
        position=Position(0, 0),
        in_hex=(0, 0),
        in_system="Sol",
        name="Ship A",
        hull_size=HullSize.MEDIUM,
        game=mock_game
    )
    unit1.id = 101

    unit2 = Unit(
        owner=player,
        position=Position(0, 0),
        in_hex=(0, 0),
        in_system="Sol",
        name="Ship B",
        hull_size=HullSize.MEDIUM,
        game=mock_game
    )
    unit2.id = 102

    mock_game.selected_objects = [unit1, unit2]
    mock_game.players = [player]
    mock_game.current_player_index = 0
    mock_game.selected_component_name = None
    
    # Call update_side_bar_content
    Game.update_side_bar_content(mock_game)
    
    # Verify that gui.update_side_bar_content was called with select buttons for each unit
    mock_game.gui.update_side_bar_content.assert_called_once()
    data_list = mock_game.gui.update_side_bar_content.call_args[0][0]
    
    buttons = [d for d in data_list if d.get("type") == "button" and d.get("action_id") == "select_individual_unit"]
    assert len(buttons) == 2
    
    assert buttons[0]["text"] == "Ship A"
    assert buttons[0]["target_data"] == 101
    assert buttons[1]["text"] == "Ship B"
    assert buttons[1]["target_data"] == 102

def test_handle_gui_action_select_individual_unit():
    # Setup mock game, galaxy, and units
    mock_game = MagicMock()
    mock_game.galaxy = MagicMock()
    mock_game.sidebar_needs_update = False
    mock_game.selected_objects = []
    
    unit1 = MagicMock()
    unit1.id = 101
    
    # Mock get_unit_by_id
    mock_game.galaxy.get_unit_by_id.side_effect = lambda uid: unit1 if uid == 101 else None
    
    # Execute handle_gui_action with select_individual_unit action
    action = {
        'action': 'select_individual_unit',
        'unit_id': 101
    }
    
    Game.handle_gui_action(mock_game, action)
    
    # Verify selection is updated to only unit1, and sidebar is marked for update
    assert mock_game.selected_objects == [unit1]
    assert mock_game.sidebar_needs_update is True

def test_handle_gui_action_deselect_individual_unit_shift():
    # Setup mock game, galaxy, and units
    mock_game = MagicMock()
    mock_game.galaxy = MagicMock()
    mock_game.sidebar_needs_update = False
    
    unit1 = MagicMock()
    unit1.id = 101
    
    # Mock get_unit_by_id
    mock_game.galaxy.get_unit_by_id.side_effect = lambda uid: unit1 if uid == 101 else None
    
    # Execute handle_gui_action with select_individual_unit action AND shift_pressed=True
    action = {
        'action': 'select_individual_unit',
        'unit_id': 101,
        'shift_pressed': True
    }
    
    Game.handle_gui_action(mock_game, action)
    
    # Verify deselect_object was called on mock_game with unit1
    mock_game.deselect_object.assert_called_once_with(unit1)
    assert mock_game.sidebar_needs_update is True

def test_single_unit_sidebar_tabs_basic_info():
    mock_game = MagicMock()
    mock_game.galaxy = MagicMock()
    mock_game.sidebar_needs_update = True
    mock_game.selected_unit_tab = 'basic_info'
    mock_game.selected_component_name = None
    mock_game.gui = MagicMock()
    
    player = MagicMock()
    player.name = "Player 1"
    
    unit = Unit(
        owner=player,
        position=Position(0, 0),
        in_hex=(0, 0),
        in_system="Sol",
        name="Battleship Alpha",
        hull_size=HullSize.LARGE,
        game=mock_game
    )
    unit.id = 201

    mock_game.selected_objects = [unit]
    mock_game.players = [player]
    mock_game.current_player_index = 0

    # Call update_side_bar_content
    Game.update_side_bar_content(mock_game)
    mock_game.gui.update_side_bar_content.assert_called_once()
    data_list = mock_game.gui.update_side_bar_content.call_args[0][0]

    # Verify tab buttons exist and are marked side_by_side
    tab_buttons = [d for d in data_list if d.get("type") == "button" and d.get("action_id") == "switch_unit_sidebar_tab"]
    assert len(tab_buttons) == 2
    assert tab_buttons[0]["target_data"] == "basic_info"
    assert tab_buttons[0].get("side_by_side") is True
    assert tab_buttons[1]["target_data"] == "components"
    assert tab_buttons[1].get("side_by_side") is True

    # Verify Component Overview header is present in Basic Info tab
    headers = [d for d in data_list if d.get("type") == "label" and d.get("text") == "Component Overview:"]
    assert len(headers) == 1

def test_single_unit_sidebar_tabs_switch_to_components():
    mock_game = MagicMock()
    mock_game.galaxy = MagicMock()
    mock_game.sidebar_needs_update = True
    mock_game.selected_unit_tab = 'basic_info'
    mock_game.selected_component_name = None
    mock_game.gui = MagicMock()
    
    player = MagicMock()
    player.name = "Player 1"
    
    unit = Unit(
        owner=player,
        position=Position(0, 0),
        in_hex=(0, 0),
        in_system="Sol",
        name="Cruiser Beta",
        hull_size=HullSize.MEDIUM,
        game=mock_game
    )
    unit.id = 202

    mock_game.selected_objects = [unit]
    mock_game.players = [player]
    mock_game.current_player_index = 0

    # Switch tab to components via handle_gui_action
    action = {
        'action': 'switch_unit_sidebar_tab',
        'tab_name': 'components'
    }
    Game.handle_gui_action(mock_game, action)
    assert mock_game.selected_unit_tab == 'components'
    assert mock_game.sidebar_needs_update is True

    # Call update_side_bar_content in components tab
    Game.update_side_bar_content(mock_game)
    data_list = mock_game.gui.update_side_bar_content.call_args[0][0]

    # Verify component selection dropdown menu is present
    comp_dropdowns = [d for d in data_list if d.get("type") == "drop_down_menu" and d.get("action_id") is None]
    assert len(comp_dropdowns) == 1
    assert "Commander" in comp_dropdowns[0]["options_list"]


def test_component_overview_colored_labels():
    """Verify that component overview items return appropriate colored label object IDs based on state."""
    mock_game = MagicMock()
    mock_game.galaxy = MagicMock()
    player = MagicMock()

    unit = Unit(
        owner=player,
        position=Position(0, 0),
        in_hex=(0, 0),
        in_system="Sol",
        name="Test Cruiser",
        hull_size=HullSize.MEDIUM,
        game=mock_game
    )

    # Check Engine (Speed readout)
    engine = unit.components.get("Engine")
    if engine:
        basic_data = engine.get_basic_sidebar_data(mock_game)
        assert len(basic_data) == 1
        assert basic_data[0]['object_id'] == '#sidebar_value_label'

    # Check Hyperdrive (Ready vs Charging)
    hyperdrive = unit.components.get("Hyperdrive")
    if hyperdrive:
        from unit_components.movement import JumpStatus
        hyperdrive.jump_status = JumpStatus.READY
        data_ready = hyperdrive.get_basic_sidebar_data(mock_game)
        assert data_ready[0]['object_id'] == '#sidebar_status_active_label'

        hyperdrive.jump_status = JumpStatus.CHARGING
        hyperdrive.recharge_time_remaining = 2
        data_charging = hyperdrive.get_basic_sidebar_data(mock_game)
        assert data_charging[0]['object_id'] == '#sidebar_status_charging_label'

    # Check Constructor (Idle vs Constructing)
    from unit_components.constructor import Constructor
    constructor = Constructor(unit)
    idle_data = constructor.get_basic_sidebar_data(mock_game)
    assert idle_data[0]['object_id'] == '#sidebar_status_idle_label'

    constructor.current_construction_target = ("Scout", "Scout Ship", 10.0, 2)
    active_data = constructor.get_basic_sidebar_data(mock_game)
    assert active_data[0]['object_id'] == '#sidebar_status_active_label'



