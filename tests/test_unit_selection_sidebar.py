import pytest
from display_config import DisplayConfig
from unittest.mock import MagicMock
from domain.units import Unit
from game import Game
from constants import HullSize
from geometry import Position

def test_multi_unit_selection_sidebar_buttons():
    # Setup mock game and units
    mock_game = MagicMock()
    mock_game.display_config = DisplayConfig()
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
    mock_game.display_config = DisplayConfig()
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
    mock_game.display_config = DisplayConfig()
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
    mock_game.display_config = DisplayConfig()
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
    mock_game.display_config = DisplayConfig()
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
    mock_game.display_config = DisplayConfig()
    mock_game.galaxy = MagicMock()
    player = MagicMock()
    mock_game.players = [player]
    mock_game.current_player_index = 0

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

    constructor.current_construction_target = dict(template_name="Scout", system_name="Sol", hex_coord=(0, 0), position=Position(100, 0))
    active_data = constructor.get_basic_sidebar_data(mock_game)
    assert active_data[0]['object_id'] == '#sidebar_status_active_label'


def test_stop_unit_button_visibility():
    mock_game = MagicMock()
    mock_game.display_config = DisplayConfig()
    mock_game.galaxy = MagicMock()
    mock_game.sidebar_needs_update = True
    mock_game.selected_objects = []
    mock_game.gui = MagicMock()

    player = MagicMock()
    player.name = "Player 1"
    mock_game.players = [player]
    mock_game.current_player_index = 0
    mock_game.selected_unit_tab = 'basic_info'

    unit = Unit(
        owner=player,
        position=Position(0, 0),
        in_hex=(0, 0),
        in_system="Sol",
        name="Test Ship",
        hull_size=HullSize.MEDIUM,
        game=mock_game
    )
    unit.id = 301
    mock_game.selected_objects = [unit]

    # Case 1: 0 active orders -> Stop Unit button should NOT be present
    assert unit.commander_component.get_active_orders_count() == 0
    Game.update_side_bar_content(mock_game)
    data_list = mock_game.gui.update_side_bar_content.call_args[0][0]
    stop_buttons = [d for d in data_list if d.get("type") == "button" and d.get("action_id") == "stop_unit"]
    assert len(stop_buttons) == 0

    # Case 2: Add order -> Stop Unit button SHOULD be present
    from unit_orders.movement import MoveOrder
    order = MoveOrder(unit, {"destination_system_name": "Sol", "destination_hex_coord": (0, 0), "destination_position": Position(10, 10)})
    unit.commander_component.add_order(order)
    assert unit.commander_component.get_active_orders_count() > 0

    mock_game.sidebar_needs_update = True
    Game.update_side_bar_content(mock_game)
    data_list = mock_game.gui.update_side_bar_content.call_args[0][0]
    stop_buttons = [d for d in data_list if d.get("type") == "button" and d.get("action_id") == "stop_unit"]
    assert len(stop_buttons) == 1
    assert stop_buttons[0]["target_data"] == 301


def test_handle_gui_action_stop_unit():
    mock_game = MagicMock()
    mock_game.display_config = DisplayConfig()
    mock_game.galaxy = MagicMock()
    mock_game.sidebar_needs_update = False

    player = MagicMock()
    player.name = "Player 1"
    mock_game.players = [player]
    mock_game.current_player_index = 0

    unit = Unit(
        owner=player,
        position=Position(0, 0),
        in_hex=(0, 0),
        in_system="Sol",
        name="Test Ship",
        hull_size=HullSize.MEDIUM,
        game=mock_game
    )
    unit.id = 302
    mock_game.galaxy.get_unit_by_id.side_effect = lambda uid: unit if uid == 302 else None

    from unit_orders.movement import MoveOrder
    order = MoveOrder(unit, {"destination_system_name": "Sol", "destination_hex_coord": (0, 0), "destination_position": Position(10, 10)})
    unit.commander_component.add_order(order)
    assert unit.commander_component.current_order is not None

    action = {
        'action': 'stop_unit',
        'unit_id': 302
    }
    Game.handle_gui_action(mock_game, action)

    # Verify event_bus published CancelOrdersEvent
    mock_game.event_bus.publish.assert_called_once()
    published_event = mock_game.event_bus.publish.call_args[0][0]
    from events import CancelOrdersEvent
    assert isinstance(published_event, CancelOrdersEvent)
    assert published_event.units == [unit]
    assert mock_game.sidebar_needs_update is True


def test_stop_selected_units_multi_selection():
    mock_game = MagicMock()
    mock_game.display_config = DisplayConfig()
    mock_game.galaxy = MagicMock()
    mock_game.sidebar_needs_update = True
    mock_game.gui = MagicMock()

    player = MagicMock()
    player.name = "Player 1"
    mock_game.players = [player]
    mock_game.current_player_index = 0

    unit1 = Unit(
        owner=player,
        position=Position(0, 0),
        in_hex=(0, 0),
        in_system="Sol",
        name="Ship A",
        hull_size=HullSize.MEDIUM,
        game=mock_game
    )
    unit1.id = 401

    unit2 = Unit(
        owner=player,
        position=Position(0, 0),
        in_hex=(0, 0),
        in_system="Sol",
        name="Ship B",
        hull_size=HullSize.MEDIUM,
        game=mock_game
    )
    unit2.id = 402

    mock_game.selected_objects = [unit1, unit2]

    # Initially 0 orders -> No Stop Selected Units button
    Game.update_side_bar_content(mock_game)
    data_list = mock_game.gui.update_side_bar_content.call_args[0][0]
    stop_multi = [d for d in data_list if d.get("type") == "button" and d.get("action_id") == "stop_selected_units"]
    assert len(stop_multi) == 0

    # Add order to unit1 -> Stop Selected Units button appears
    from unit_orders.movement import MoveOrder
    order = MoveOrder(unit1, {"destination_system_name": "Sol", "destination_hex_coord": (0, 0), "destination_position": Position(10, 10)})
    unit1.commander_component.add_order(order)

    mock_game.sidebar_needs_update = True
    Game.update_side_bar_content(mock_game)
    data_list = mock_game.gui.update_side_bar_content.call_args[0][0]
    stop_multi = [d for d in data_list if d.get("type") == "button" and d.get("action_id") == "stop_selected_units"]
    assert len(stop_multi) == 1

    # Trigger stop_selected_units
    action = {'action': 'stop_selected_units'}
    Game.handle_gui_action(mock_game, action)

    mock_game.event_bus.publish.assert_called_once()
    published_event = mock_game.event_bus.publish.call_args[0][0]
    from events import CancelOrdersEvent
    assert isinstance(published_event, CancelOrdersEvent)
    assert published_event.units == [unit1]


def test_unit_sidebar_identity():
    """Verify that build_unit_panel assigns distinct identities for units, tabs, and components."""
    from gui.sidebar.panels_unit import build_unit_panel
    mock_game = MagicMock()
    mock_game.display_config = DisplayConfig()
    mock_game.galaxy = MagicMock()
    mock_game.selected_unit_tab = 'basic_info'
    mock_game.selected_component_name = None

    player = MagicMock()
    player.name = "Player 1"
    mock_game.players = [player]
    mock_game.current_player_index = 0

    unit1 = Unit(owner=player, position=Position(0, 0), in_hex=(0, 0), in_system="Sol",
                 name="Unit 1", hull_size=HullSize.MEDIUM, game=mock_game)
    unit1.id = 501
    unit2 = Unit(owner=player, position=Position(0, 0), in_hex=(0, 0), in_system="Sol",
                 name="Unit 2", hull_size=HullSize.SMALL, game=mock_game)
    unit2.id = 502

    # Owned unit in basic_info tab
    p1 = build_unit_panel(mock_game, unit1)
    assert p1[0]['sidebar_identity'] == 'unit:501:basic_info'

    p2 = build_unit_panel(mock_game, unit2)
    assert p2[0]['sidebar_identity'] == 'unit:502:basic_info'
    assert p1[0]['sidebar_identity'] != p2[0]['sidebar_identity']

    # Non-owned unit
    other_player = MagicMock()
    other_player.name = "Player 2"
    enemy_unit = Unit(owner=other_player, position=Position(0, 0), in_hex=(0, 0), in_system="Sol",
                      name="Enemy 1", hull_size=HullSize.MEDIUM, game=mock_game)
    enemy_unit.id = 503
    p3 = build_unit_panel(mock_game, enemy_unit)
    assert p3[0]['sidebar_identity'] == 'unit:503:basic_info'

    # Components tab
    mock_game.selected_unit_tab = 'components'
    mock_game.selected_component_name = 'Commander'
    p1_comp = build_unit_panel(mock_game, unit1)
    assert p1_comp[0]['sidebar_identity'] == 'unit:501:components:Commander'


def test_sidebar_scroll_resets_on_new_unit_selection():
    """Verify that scrolling down a tall unit sidebar and selecting a shorter unit resets scroll to top."""
    import os
    os.environ['SDL_VIDEODRIVER'] = 'dummy'
    import pygame
    pygame.init()
    game = Game(display_config=DisplayConfig(1280, 720, fullscreen=False))
    game.start_new_game()
    gui = game.gui
    scroll = gui.side_bar_scroll_container

    tall_data = [{'type': 'text_entry_line', 'initial_text': 'Ship 1', 'object_id': '#unit_name_entry',
                  'height': 30, 'sidebar_identity': 'unit:101:basic_info'}]
    for i in range(80):
        tall_data.append({'type': 'label', 'text': f'Row {i} detailed description text', 'object_id': '#sidebar_info_label', 'height': 25})

    gui.update_side_bar_content(tall_data)
    gui.manager.update(0.1)
    assert scroll.vert_scroll_bar_active

    # Scroll down halfway
    scroll.vert_scroll_bar.set_scroll_from_start_percentage(0.5)
    gui.manager.update(0.1)
    assert scroll.vert_scroll_bar.start_percentage == 0.5
    assert scroll.get_container().get_relative_rect().y < 0

    # Select short unit
    short_data = [{'type': 'text_entry_line', 'initial_text': 'Ship 2', 'object_id': '#unit_name_entry',
                   'height': 30, 'sidebar_identity': 'unit:102:basic_info'}]
    for i in range(5):
        short_data.append({'type': 'label', 'text': f'Short Row {i}', 'object_id': '#sidebar_info_label', 'height': 25})

    gui.update_side_bar_content(short_data)
    gui.manager.update(0.1)

    # Content should start at the top (0, 0), scroll percentage 0.0
    assert scroll.vert_scroll_bar.start_percentage == 0.0
    assert scroll.get_container().get_relative_rect().y == 0
    assert not scroll.vert_scroll_bar_active


def test_sidebar_scroll_preserved_on_same_unit_refresh():
    """Verify that refreshing content for the same unit preserves the vertical scroll position."""
    import os
    os.environ['SDL_VIDEODRIVER'] = 'dummy'
    import pygame
    pygame.init()
    game = Game(display_config=DisplayConfig(1280, 720, fullscreen=False))
    game.start_new_game()
    gui = game.gui
    scroll = gui.side_bar_scroll_container

    tall_data = [{'type': 'text_entry_line', 'initial_text': 'Ship 1', 'object_id': '#unit_name_entry',
                  'height': 30, 'sidebar_identity': 'unit:101:basic_info'}]
    for i in range(80):
        tall_data.append({'type': 'label', 'text': f'Row {i} detailed description text', 'object_id': '#sidebar_info_label', 'height': 25})

    gui.update_side_bar_content(tall_data)
    gui.manager.update(0.1)

    scroll.vert_scroll_bar.set_scroll_from_start_percentage(0.5)
    gui.manager.update(0.1)
    initial_scroll = scroll.vert_scroll_bar.start_percentage
    initial_y = scroll.get_container().get_relative_rect().y
    assert initial_scroll == 0.5
    assert initial_y < 0

    # Refresh the same unit with identical identity and height
    gui.update_side_bar_content(tall_data)
    gui.manager.update(0.1)

    assert scroll.vert_scroll_bar.start_percentage == pytest.approx(initial_scroll, abs=0.01)
    assert scroll.get_container().get_relative_rect().y == pytest.approx(initial_y, abs=2)


def test_sidebar_scroll_resets_on_tall_to_tall_unit_switch():
    """Verify that switching between two tall units resets the scroll position to 0.0."""
    import os
    os.environ['SDL_VIDEODRIVER'] = 'dummy'
    import pygame
    pygame.init()
    game = Game(display_config=DisplayConfig(1280, 720, fullscreen=False))
    game.start_new_game()
    gui = game.gui
    scroll = gui.side_bar_scroll_container

    tall_data_1 = [{'type': 'text_entry_line', 'initial_text': 'Ship 1', 'object_id': '#unit_name_entry',
                    'height': 30, 'sidebar_identity': 'unit:101:basic_info'}]
    for i in range(80):
        tall_data_1.append({'type': 'label', 'text': f'Ship 1 Row {i}', 'object_id': '#sidebar_info_label', 'height': 25})

    gui.update_side_bar_content(tall_data_1)
    gui.manager.update(0.1)

    scroll.vert_scroll_bar.set_scroll_from_start_percentage(0.6)
    gui.manager.update(0.1)
    assert scroll.vert_scroll_bar.start_percentage > 0.4

    tall_data_2 = [{'type': 'text_entry_line', 'initial_text': 'Ship 2', 'object_id': '#unit_name_entry',
                    'height': 30, 'sidebar_identity': 'unit:102:basic_info'}]
    for i in range(80):
        tall_data_2.append({'type': 'label', 'text': f'Ship 2 Row {i}', 'object_id': '#sidebar_info_label', 'height': 25})

    gui.update_side_bar_content(tall_data_2)
    gui.manager.update(0.1)

    assert scroll.vert_scroll_bar.start_percentage == 0.0
    assert scroll.get_container().get_relative_rect().y == 0
    assert scroll.vert_scroll_bar_active
