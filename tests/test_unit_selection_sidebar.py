import pytest
from display_config import DisplayConfig
from unittest.mock import MagicMock
from constants import FieldDensity, HullSize, MAX_UNIT_XP
from domain.celestials import IceField
from domain.units import Unit
from game import Game
from geometry import Position
from gui.sidebar.builder import build_sidebar_data
from tests.support.campaigns import campaign, ship
from unit_components.antimatter import AntimatterHarvester, AntimatterStorage
from unit_components.constructor import Constructor
from unit_components.defenses import Defenses
from unit_components.enums import HyperdriveType, JumpStatus, TurretType, TurretVariant
from unit_components.movement import Engines, Hyperdrive
from unit_components.weapons import Turret, Weapons


def _overview_sections(data):
    overview_index = next(i for i, row in enumerate(data) if row.get('text') == 'Component Overview:')
    sections = {}
    for row in data[overview_index + 1:]:
        if row.get('object_id') == '#sidebar_component_header_label':
            title = row['text']
            assert title not in sections
            assert row.get('indent_level', 0) == 0
            sections[title] = []
        else:
            assert row['indent_level'] >= 1
            sections[title].append(row)
    assert all(sections.values())
    return sections


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
    unit.add_component(AntimatterHarvester(unit))
    weapons = Weapons(unit)
    weapons.add_turret(Turret(TurretType.BEAM, 16, 300, 2, unit))
    unit.add_component(weapons)
    unit.add_component(Hyperdrive(unit))
    unit.add_component(Defenses(unit))
    unit.add_component(Engines(unit, speed=175))

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

    sections = _overview_sections(data_list)
    assert list(sections) == [
        'Commander', 'Antimatter Storage', 'Engines', 'Hyperdrive', 'Weapons',
        'Antimatter Harvester', 'Defenses', 'Sensors',
    ]
    assert sections['Engines'][0]['text'] == '175.0 units/turn'
    assert sections['Weapons'][0]['text'].startswith('Standard Beam')


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
    unit.add_component(Engines(unit, speed=100))
    unit.add_component(Weapons(unit))

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
    assert comp_dropdowns[0]['starting_option'] == 'Commander'
    assert comp_dropdowns[0]['options_list'] == ['Commander', 'Antimatter Storage', 'Weapons', 'Engines', 'Sensors']
    assert all(row.get('text') != 'Component Overview:' for row in data_list)


@pytest.mark.parametrize(('status', 'text', 'style'), [
    (JumpStatus.READY, 'Ready', '#sidebar_status_active_label'),
    (JumpStatus.CHARGING, 'Charging (2 turns)', '#sidebar_status_charging_label'),
    (JumpStatus.JUMPING, 'Jumping', '#sidebar_status_active_label'),
    (JumpStatus.ERROR, 'Error', '#sidebar_hit_points_critical_damage_label'),
])
def test_hyperdrive_overview_status(status, text, style):
    game = campaign()
    unit = ship(game)
    game.selected_objects = [unit]
    unit.experience_points = MAX_UNIT_XP
    hyperdrive = Hyperdrive(unit, drive_type=HyperdriveType.ADVANCED, jump_range=10)
    hyperdrive.jump_status = status
    hyperdrive.recharge_time_remaining = 2 if status == JumpStatus.CHARGING else 0
    unit.add_component(hyperdrive)

    row, = _overview_sections(build_sidebar_data(game))['Hyperdrive']
    assert row['text'] == f'Advanced · Range 12 hexes · {text}'
    assert row['object_id'] == style


def test_overview_uses_current_fuel_and_terrain_adjusted_speed():
    game = campaign()
    unit = ship(game, hull=HullSize.MEDIUM)
    game.selected_objects = [unit]
    unit.experience_points = MAX_UNIT_XP
    unit.add_component(Engines(unit, speed=200))
    storage = AntimatterStorage(unit, max_capacity=120)
    unit.add_component(storage)
    field = IceField(unit.in_hex, unit.in_system, FieldDensity.LOW)
    field.position = unit.position
    game.galaxy.systems[unit.in_system].add_celestial_body(field)

    storage.current_amount = 84.5
    sections = _overview_sections(build_sidebar_data(game))
    assert sections['Antimatter Storage'][0]['text'] == '84.5 / 120.0 AM'
    speed, = sections['Engines']
    assert speed['text'] == '207.0 units/turn'
    assert speed['object_id'] == '#sidebar_value_label'

    storage.current_amount = 0
    sections = _overview_sections(build_sidebar_data(game))
    assert sections['Antimatter Storage'][0]['text'] == '0.0 / 120.0 AM'


def test_overview_distinguishes_missing_empty_and_destroyed_equipment():
    game = campaign()
    station = ship(game, 'Defense platform')
    game.selected_objects = [station]
    sections = _overview_sections(build_sidebar_data(game))
    assert list(sections) == ['Commander', 'Antimatter Storage', 'Sensors']

    weapons = Weapons(station)
    station.add_component(weapons)
    sections = _overview_sections(build_sidebar_data(game))
    assert [row['text'] for row in sections['Weapons']] == ['No turrets']

    weapons.current_hit_points = 0
    destroyed, = _overview_sections(build_sidebar_data(game))['Weapons']
    assert destroyed['text'] == 'Destroyed'
    assert destroyed['object_id'] == '#sidebar_hit_points_critical_damage_label'


def test_constructor_overview_status_colors():
    game = campaign()
    unit = ship(game)
    constructor = Constructor(unit)
    unit.add_component(constructor)
    game.selected_objects = [unit]
    idle, = _overview_sections(build_sidebar_data(game))['Constructor']
    assert idle['text'] == 'Idle'
    assert idle['object_id'] == '#sidebar_status_idle_label'

    constructor.current_construction_target = {
        'template_name': 'Scout', 'system_name': 'Sol',
        'hex_coord': (0, 0), 'position': Position(100, 0),
    }
    active, = _overview_sections(build_sidebar_data(game))['Constructor']
    assert active['text'].startswith('Constructing Scout')
    assert active['object_id'] == '#sidebar_status_active_label'


def test_equipment_health_and_allowed_details_are_inside_each_section():
    from unit_components.planetary import SiegeBatteryComponent, TroopTransportComponent
    from unit_components.wormhole_stabilizer import WormholeStabilizerComponent

    game = campaign()
    unit = ship(game)
    troops = TroopTransportComponent(unit, capacity=40)
    troops.troops = 7
    components = (troops, SiegeBatteryComponent(unit), WormholeStabilizerComponent(unit))
    for component in components:
        unit.add_component(component)
        component.current_hit_points = 7
    game.selected_objects = [unit]

    from hp_format import format_hp
    sections = _overview_sections(build_sidebar_data(game))
    for component in components:
        health, *details = sections[component.DISPLAY_NAME]
        assert health['text'] == f'HP: 7/{format_hp(component.max_hit_points)}'
        assert all(component.DISPLAY_NAME not in row['text'] for row in details)
    assert sections['Troop Transport'][1]['text'] == 'Troops: 7/40'
    assert any(row['text'] == 'Idle' for row in sections['Wormhole Stabilizer'])

    game.current_player_index = 1
    enemy_sections = _overview_sections(build_sidebar_data(game))
    assert enemy_sections['Troop Transport'][1]['text'] == 'Troop capacity: 40'
    assert all(row['text'] != 'Idle' for row in enemy_sections['Wormhole Stabilizer'])
    assert 'Commander' not in enemy_sections

    game.players[1].team_id = unit.owner.team_id
    ally_sections = _overview_sections(build_sidebar_data(game))
    assert ally_sections['Troop Transport'] == sections['Troop Transport']
    assert ally_sections['Wormhole Stabilizer'] == sections['Wormhole Stabilizer']


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
    assert stop_buttons[0] in _overview_sections(data_list)['Commander']


@pytest.mark.usefixtures('pygame_context')
def test_cancel_dismantling_from_commander_overview():
    from dismantling import offline
    from game_actions import handle_gui_action
    from gui.dynamic_actions import build_button_payload
    from tactical_ui import issue
    from unit_orders.base import OrderStatus

    game = campaign()
    game.galaxy.game = game
    constructor = ship(game, 'Constructor')
    constructor.add_component(Constructor(constructor))
    target = ship(game, 'Target', hull=HullSize.SMALL)
    assert issue(game, {'type': 'dismantle_unit', 'unit_ids': [constructor.id], 'target_id': target.id})
    order = constructor.commander_component.current_order
    assert offline(target)

    game.selected_objects = [target]
    commander_rows = _overview_sections(build_sidebar_data(game))['Commander']
    button, = [row for row in commander_rows if row.get('action_id') == 'cancel_dismantling']
    assert button['text'] == 'Cancel dismantling'
    assert any(row['type'] == 'progress_bar' for row in commander_rows)
    action = build_button_payload(None, button['action_id'], button['target_data'])
    handle_gui_action(game, action)
    assert order.status == OrderStatus.CANCELLED
    assert not offline(target)


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


@pytest.mark.filterwarnings('error:Label Rect is too small:UserWarning')
@pytest.mark.parametrize('size', [(1280, 720), (2560, 1440)])
def test_component_overview_wraps_and_scrolls_in_hud(pygame_context, tmp_path, size):
    from pygame_gui.elements import UILabel
    from gui.handler import GUI_Handler

    screen = pygame_context.display.set_mode(size)
    game = campaign()
    game.display_config = DisplayConfig(*size, fullscreen=False)
    first, second = ship(game, 'First cruiser'), ship(game, 'Second cruiser')
    for unit in (first, second):
        unit.add_component(Engines(unit, speed=175))
        unit.add_component(Hyperdrive(unit, drive_type=HyperdriveType.ADVANCED, jump_range=5))
        weapons = Weapons(unit)
        for _ in range(20):
            weapons.add_turret(Turret(
                TurretType.MASS_DRIVER, 23.5, 345.75, 12, unit,
                variant=TurretVariant.ANTI_STRIKECRAFT, current_cooldown=12,
            ))
        unit.add_component(weapons)

    game.gui = gui = GUI_Handler(game.display_config, game)

    def refresh(unit):
        game.selected_objects = [unit]
        game.sidebar_needs_update = True
        Game.update_side_bar_content(game)
        gui.manager.update(0.1)

    try:
        gui.show_game_ui()
        refresh(first)
        scroll = gui.side_bar_scroll_container
        labels = [element for element in gui.side_bar_dynamic_elements if isinstance(element, UILabel)]
        headings = [label for label in labels if '#sidebar_component_header_label' in label.object_ids]
        assert [label.text for label in headings] == [
            'Commander', 'Antimatter Storage', 'Engines', 'Hyperdrive', 'Weapons', 'Sensors',
        ]
        for label in labels:
            assert label.font.get_rect(label.text).width <= label.get_relative_rect().width

        weapons_heading, sensors_heading = headings[-2:]
        weapon_labels = labels[labels.index(weapons_heading) + 1:labels.index(sensors_heading)]
        weapon_rows = _overview_sections(build_sidebar_data(game))['Weapons']
        assert len(weapon_labels) > len(weapon_rows)
        assert ' '.join(label.text for label in weapon_labels) == ' '.join(row['text'] for row in weapon_rows)
        assert weapon_labels[0].get_relative_rect().x > weapons_heading.get_relative_rect().x

        screen.fill((5, 10, 20))
        gui.manager.draw_ui(screen)
        sidebar_image = screen.subsurface(gui.side_bar_info_panel.get_abs_rect())
        pygame_context.image.save(sidebar_image, str(tmp_path / 'component-overview.png'))

        assert scroll.vert_scroll_bar_active
        scroll.vert_scroll_bar.set_scroll_from_start_percentage(0.25)
        gui.manager.update(0.1)
        original_y = scroll.get_container().get_relative_rect().y
        assert original_y < 0
        first.weapons_component.turrets[0].current_cooldown = 11
        refresh(first)
        assert scroll.get_container().get_relative_rect().y == pytest.approx(original_y, abs=2)

        refresh(second)
        assert scroll.vert_scroll_bar_active
        assert scroll.get_container().get_relative_rect().y == 0
    finally:
        gui.clear_and_reset()


@pytest.mark.parametrize('scroll_percentage', [0.25, 1.0], ids=['interior', 'bottom'])
def test_sidebar_scroll_resets_on_new_unit_selection(game_factory, scroll_percentage):
    """Verify that scrolling down a tall unit sidebar and selecting a shorter unit resets scroll to top."""
    game = game_factory(display_config=DisplayConfig(1280, 720, fullscreen=False))
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

    # pygame_gui clamps the requested percentage to the rendered content's range.
    scroll.vert_scroll_bar.set_scroll_from_start_percentage(scroll_percentage)
    gui.manager.update(0.1)
    assert scroll.vert_scroll_bar.start_percentage > 0
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


@pytest.mark.parametrize('scroll_percentage', [0.25, 1.0], ids=['interior', 'bottom'])
def test_sidebar_scroll_preserved_on_same_unit_refresh(game_factory, scroll_percentage):
    """Verify that refreshing content for the same unit preserves the vertical scroll position."""
    game = game_factory(display_config=DisplayConfig(1280, 720, fullscreen=False))
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

    scroll.vert_scroll_bar.set_scroll_from_start_percentage(scroll_percentage)
    gui.manager.update(0.1)
    # Preserve the actual offset, which depends on font metrics and clamping.
    initial_scroll = scroll.vert_scroll_bar.start_percentage
    initial_y = scroll.get_container().get_relative_rect().y
    assert initial_scroll > 0
    assert initial_y < 0

    # Refresh the same unit with identical identity and height
    gui.update_side_bar_content(tall_data)
    gui.manager.update(0.1)

    assert scroll.vert_scroll_bar.start_percentage == pytest.approx(initial_scroll, abs=0.01)
    assert scroll.get_container().get_relative_rect().y == pytest.approx(initial_y, abs=2)


@pytest.mark.parametrize('scroll_percentage', [0.25, 1.0], ids=['interior', 'bottom'])
def test_sidebar_scroll_resets_on_tall_to_tall_unit_switch(game_factory, scroll_percentage):
    """Verify that switching between two tall units resets the scroll position to 0.0."""
    game = game_factory(display_config=DisplayConfig(1280, 720, fullscreen=False))
    game.start_new_game()
    gui = game.gui
    scroll = gui.side_bar_scroll_container

    tall_data_1 = [{'type': 'text_entry_line', 'initial_text': 'Ship 1', 'object_id': '#unit_name_entry',
                    'height': 30, 'sidebar_identity': 'unit:101:basic_info'}]
    for i in range(80):
        tall_data_1.append({'type': 'label', 'text': f'Ship 1 Row {i}', 'object_id': '#sidebar_info_label', 'height': 25})

    gui.update_side_bar_content(tall_data_1)
    gui.manager.update(0.1)
    assert scroll.vert_scroll_bar_active

    scroll.vert_scroll_bar.set_scroll_from_start_percentage(scroll_percentage)
    gui.manager.update(0.1)
    assert scroll.vert_scroll_bar.start_percentage > 0
    assert scroll.get_container().get_relative_rect().y < 0

    tall_data_2 = [{'type': 'text_entry_line', 'initial_text': 'Ship 2', 'object_id': '#unit_name_entry',
                    'height': 30, 'sidebar_identity': 'unit:102:basic_info'}]
    for i in range(80):
        tall_data_2.append({'type': 'label', 'text': f'Ship 2 Row {i}', 'object_id': '#sidebar_info_label', 'height': 25})

    gui.update_side_bar_content(tall_data_2)
    gui.manager.update(0.1)

    assert scroll.vert_scroll_bar.start_percentage == 0.0
    assert scroll.get_container().get_relative_rect().y == 0
    assert scroll.vert_scroll_bar_active


def test_abilities_only_shown_in_abilities_component_tab():
    """Verify that ability descriptions and tactical controls appear only when Abilities is selected."""
    from domain.players import Player
    from unit_components.enums import AbilityType
    from unit_components.abilities import AbilityComponent
    from gui.sidebar.builder import build_sidebar_data

    mock_game = MagicMock()
    mock_game.display_config = DisplayConfig()
    mock_game.galaxy = MagicMock()
    mock_game.galaxy.systems = {}
    player = Player(name="Player 1", color=(0, 200, 255))
    mock_game.players = [player]
    mock_game.current_player_index = 0

    unit = Unit(owner=player, position=Position(0, 0), in_hex=(0, 0), in_system="Sol",
                name="Test Ability Ship", hull_size=HullSize.MEDIUM, game=mock_game)
    unit.id = 901
    comp = AbilityComponent(unit, [AbilityType.GHOST_FLEET, AbilityType.REPAIR_CLOUD])
    unit.add_component(comp)
    mock_game.selected_objects = [unit]

    # 1. Basic Info tab: No ability descriptions or tactical ability panels
    mock_game.selected_unit_tab = 'basic_info'
    mock_game.selected_component_name = None
    data_basic = build_sidebar_data(mock_game)
    texts_basic = [d.get('text', '') for d in data_basic]
    assert 'Abilities' not in _overview_sections(data_basic)
    assert not any('Ghost Fleet' in t for t in texts_basic)
    assert not any('Repair Cloud' in t for t in texts_basic)

    # 2. Components tab with Commander selected: No ability descriptions or tactical ability panels
    mock_game.selected_unit_tab = 'components'
    mock_game.selected_component_name = 'Commander'
    data_commander = build_sidebar_data(mock_game)
    texts_commander = [d.get('text', '') for d in data_commander]
    assert not any('Ghost Fleet' in t for t in texts_commander)
    assert not any('Repair Cloud' in t for t in texts_commander)

    # 3. Components tab with Abilities selected: Ability descriptions and tactical ability panels are shown
    mock_game.selected_unit_tab = 'components'
    mock_game.selected_component_name = 'Abilities'
    data_abilities = build_sidebar_data(mock_game)
    texts_abilities = [d.get('text', '') for d in data_abilities]
    assert any('Ghost Fleet' in t for t in texts_abilities)
    assert any('Repair Cloud' in t for t in texts_abilities)
    assert any('emitters' in t for t in texts_abilities)
