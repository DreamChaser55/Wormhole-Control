from player_controller import PlayerController
import pytest
import pygame
import pygame_gui
from geometry import Position
from domain.coordinates import HexCoord
from constants import HullSize
from domain.units import Unit
from domain.players import Player
from galaxy import Galaxy, StarSystem
from events import EventBus
from order_system import OrderSystem
from unit_components.constructor import Constructor
from unit_components.movement import Engines
from unit_components.defenses import Defenses
from unit_components.abilities import AbilityComponent
from unit_components.enums import AbilityType
from gui.retrofit_gui import RetrofitWizardWindow
from game_actions import handle_gui_action
from input_processor import InputProcessor
"""
test_retrofit_wizard.py

Comprehensive test suite for the Retrofit Customization Options Wizard GUI.
"""


class MockGame:
    def __init__(self, galaxy, players):
        self.galaxy = galaxy
        self.players = players
        self.current_player_index = 0
        self.event_bus = EventBus()
        self.sidebar_needs_update = False
        self.gui = None


@pytest.fixture
def wizard_setup():
    player = Player(name="Player 1", color=(0, 0, 255), controller=PlayerController.HUMAN)
    player.credits = 5000

    galaxy = Galaxy(num_systems=0)
    system = StarSystem(name="Sol", position=Position(0, 0))
    galaxy.systems["Sol"] = system

    game = MockGame(galaxy, [player])
    galaxy.game = game
    order_sys = OrderSystem(game, game.event_bus)

    # Constructor unit
    constructor_unit = Unit(
        owner=player,
        position=Position(100, 100),
        in_hex=HexCoord(0, 0),
        in_system="Sol",
        name="Constructor-1",
        hull_size=HullSize.LARGE,
        game=game,
        template_name="Construction Ship"
    )
    constructor_unit.add_component(Constructor(constructor_unit, hull_cost=15.0))
    system.add_unit(constructor_unit)

    # Friendly target unit (Cruiser / Medium hull)
    target_unit = Unit(
        owner=player,
        position=Position(150, 150),
        in_hex=HexCoord(0, 0),
        in_system="Sol",
        name="Cruiser-1",
        hull_size=HullSize.MEDIUM,
        game=game,
        template_name="Cruiser"
    )
    system.add_unit(target_unit)

    screen_res = pygame.Vector2(1280, 720)
    manager = pygame_gui.UIManager((1280, 720))

    return game, galaxy, player, constructor_unit, target_unit, manager, screen_res


def test_retrofit_wizard_component_switching(wizard_setup):
    game, galaxy, player, constructor_unit, target_unit, manager, screen_res = wizard_setup
    wizard = RetrofitWizardWindow(
        manager=manager,
        screen_res=screen_res,
        target_unit=target_unit,
        constructor_units=[constructor_unit],
        initial_comp_key="Engines"
    )

    assert wizard._current_comp_key == "Engines"
    # Switch to Weapons
    wizard.select_component("Weapons")
    assert wizard._current_comp_key == "Weapons"
    assert len(wizard._turrets) > 0

    # Switch to Defenses
    wizard.select_component("Defenses")
    assert wizard._current_comp_key == "Defenses"
    wizard.kill()


def test_retrofit_wizard_engines_customization(wizard_setup):
    game, galaxy, player, constructor_unit, target_unit, manager, screen_res = wizard_setup
    wizard = RetrofitWizardWindow(
        manager=manager,
        screen_res=screen_res,
        target_unit=target_unit,
        constructor_units=[constructor_unit],
        initial_comp_key="Engines"
    )

    # Change engine speed
    wizard._engine_speed_entry.set_text("200")
    wizard._sync_cost_and_summary()

    assert wizard._comp_config["speed"] == 200.0
    assert wizard.calculated_hull_cost == Engines.calc_hull_cost(200.0, target_unit.hull_size)
    assert wizard.cost_credits == int(round(wizard.calculated_hull_cost * 30.0))
    wizard.kill()


def test_retrofit_wizard_weapons_turrets_customization(wizard_setup):
    game, galaxy, player, constructor_unit, target_unit, manager, screen_res = wizard_setup
    wizard = RetrofitWizardWindow(
        manager=manager,
        screen_res=screen_res,
        target_unit=target_unit,
        constructor_units=[constructor_unit],
        initial_comp_key="Weapons"
    )

    # Initial default turret
    assert len(wizard._turrets) == 1

    # Add a second turret
    wizard._turret_type_dd.selected_option = "BEAM"
    wizard._turret_variant_dd.selected_option = "LONG_RANGE"
    wizard._turret_dmg_entry.set_text("25")
    wizard._turret_range_entry.set_text("400")
    wizard._turret_cd_entry.set_text("3")
    wizard._add_turret()

    assert len(wizard._turrets) == 2
    assert wizard._turrets[1]["type"] == "BEAM"
    assert wizard._turrets[1]["variant"] == "LONG_RANGE"
    assert wizard._turrets[1]["damage"] == 25.0

    # Remove the first turret
    wizard._remove_turret(0)
    assert len(wizard._turrets) == 1
    assert wizard._turrets[0]["type"] == "BEAM"
    wizard.kill()


def test_retrofit_wizard_defenses_customization(wizard_setup):
    game, galaxy, player, constructor_unit, target_unit, manager, screen_res = wizard_setup
    wizard = RetrofitWizardWindow(
        manager=manager,
        screen_res=screen_res,
        target_unit=target_unit,
        constructor_units=[constructor_unit],
        initial_comp_key="Defenses"
    )

    wizard._armor_entry.set_text("100")
    wizard._shields_entry.set_text("120")
    wizard._pd_entry.set_text("15")
    wizard._sync_cost_and_summary()

    assert wizard._comp_config["armor"] == 100
    assert wizard._comp_config["shields"] == 120
    assert wizard._comp_config["point_defense"] == 15
    assert wizard.calculated_hull_cost == Defenses.calc_hull_cost(100, 120, 15)
    wizard.kill()


def test_retrofit_wizard_abilities_customization(wizard_setup):
    game, galaxy, player, constructor_unit, target_unit, manager, screen_res = wizard_setup
    wizard = RetrofitWizardWindow(
        manager=manager,
        screen_res=screen_res,
        target_unit=target_unit,
        constructor_units=[constructor_unit],
        initial_comp_key="AbilityComponent"
    )

    wizard._toggle_ability(AbilityType.ADAPTIVE_FORCEFIELD.value)
    wizard._toggle_ability(AbilityType.MICROJUMP.value)

    assert AbilityType.ADAPTIVE_FORCEFIELD.value in wizard._selected_abilities
    assert AbilityType.MICROJUMP.value in wizard._selected_abilities
    assert wizard.calculated_hull_cost == AbilityComponent.calc_hull_cost([
        AbilityType.ADAPTIVE_FORCEFIELD,
        AbilityType.MICROJUMP
    ])
    wizard.kill()


def test_retrofit_catalyst_selection_without_harvester(wizard_setup):
    from unit_components.sensors import Sensors
    game, galaxy, player, constructor_unit, target_unit, manager, screen_res = wizard_setup
    target_unit.add_component(Sensors(target_unit))
    assert target_unit.antimatter_component is not None
    assert target_unit.harvester_component is None
    wizard = RetrofitWizardWindow(manager, screen_res, target_unit, [constructor_unit],
        initial_comp_key="AbilityComponent")
    try:
        wizard._toggle_ability(AbilityType.NEBULA_CATALYST.value)
        assert wizard.is_valid
        event = pygame.event.Event(pygame_gui.UI_BUTTON_PRESSED, ui_element=wizard._confirm_button)
        action = wizard.process_event(event)
        assert action["component_type"] == "AbilityComponent"
        assert action["component_config"]["ability_types"] == ['nebula_catalyst']
    finally:
        wizard.kill()


def test_retrofit_wizard_validation_insufficient_credits(wizard_setup):
    game, galaxy, player, constructor_unit, target_unit, manager, screen_res = wizard_setup
    player.credits = 10  # Very low credits

    wizard = RetrofitWizardWindow(
        manager=manager,
        screen_res=screen_res,
        target_unit=target_unit,
        constructor_units=[constructor_unit],
        initial_comp_key="Defenses"
    )

    wizard._sync_cost_and_summary()
    assert wizard.is_valid is False
    assert "Insufficient credits" in wizard._status_box.html_text
    wizard.kill()


def test_retrofit_wizard_validation_exceeds_hull_capacity(wizard_setup):
    game, galaxy, player, constructor_unit, target_unit, manager, screen_res = wizard_setup
    player.credits = 50000

    wizard = RetrofitWizardWindow(
        manager=manager,
        screen_res=screen_res,
        target_unit=target_unit,
        constructor_units=[constructor_unit],
        initial_comp_key="Engines"
    )

    # Set absurdly high speed to exceed hull capacity
    wizard._engine_speed_entry.set_text("5000")
    wizard._sync_cost_and_summary()

    assert wizard.is_valid is False
    assert "Hull over capacity" in wizard._status_box.html_text
    wizard.kill()


def test_retrofit_wizard_confirm_action(wizard_setup):
    game, galaxy, player, constructor_unit, target_unit, manager, screen_res = wizard_setup
    wizard = RetrofitWizardWindow(
        manager=manager,
        screen_res=screen_res,
        target_unit=target_unit,
        constructor_units=[constructor_unit],
        initial_comp_key="Defenses"
    )

    wizard._armor_entry.set_text("30")
    wizard._shields_entry.set_text("30")
    wizard._pd_entry.set_text("0")
    wizard._sync_cost_and_summary()

    assert wizard.is_valid is True

    # Simulate pressing Confirm button
    event = pygame.event.Event(pygame_gui.UI_BUTTON_PRESSED, ui_element=wizard._confirm_button)
    action_res = wizard.process_event(event)

    assert action_res is not None
    assert action_res["action"] == "confirm_retrofit"
    assert action_res["target_unit"] == target_unit
    assert action_res["component_type"] == "Defenses"
    assert action_res["component_config"]["armor"] == 30
    assert action_res["component_config"]["shields"] == 30
    assert action_res["cost_credits"] > 0
    wizard.kill()


def test_retrofit_wizard_cancel_action(wizard_setup):
    game, galaxy, player, constructor_unit, target_unit, manager, screen_res = wizard_setup
    wizard = RetrofitWizardWindow(
        manager=manager,
        screen_res=screen_res,
        target_unit=target_unit,
        constructor_units=[constructor_unit],
        initial_comp_key="Defenses"
    )

    event = pygame.event.Event(pygame_gui.UI_BUTTON_PRESSED, ui_element=wizard._cancel_button)
    action_res = wizard.process_event(event)

    assert action_res == {"action": "cancel_retrofit"}
    wizard.kill()


def test_game_action_confirm_retrofit_execution(wizard_setup):
    game, galaxy, player, constructor_unit, target_unit, manager, screen_res = wizard_setup
    target_unit.position = Position(110, 110)
    initial_credits = player.credits

    action = {
        "action": "confirm_retrofit",
        "target_unit": target_unit,
        "constructor_units": [constructor_unit],
        "component_type": "Defenses",
        "component_config": {"armor": 45, "shields": 45, "point_defense": 0},
        "cost_credits": 900,
        "time_to_build": 2,
        "shift_pressed": False,
    }

    # Handle the action
    handle_gui_action(game, action)

    # Constructor should have refit order in commander and started refit
    refit_order = constructor_unit.commander_component.current_order
    assert refit_order is not None
    assert constructor_unit.constructor_component.current_refit_target is not None
    assert player.credits == initial_credits - 900

    # Thirty hull points take six turns; supplied timing is not authoritative.
    for _ in range(6):
        constructor_unit.constructor_component.update(galaxy)
    refit_order.check_completion_conditions()

    # Target unit should have Defenses installed with customized stats
    defenses = target_unit.get_component(Defenses)
    assert defenses is not None
    assert defenses.armor == 45
    assert defenses.shields == 45
    assert defenses.point_defense == 0


def test_input_processor_refit_context_menu_options(wizard_setup):
    game, galaxy, player, constructor_unit, target_unit, manager, screen_res = wizard_setup
    ip = InputProcessor(game)

    options = ip.get_refit_context_options([constructor_unit], target_unit)
    option_labels = [opt[0] for opt in options]

    assert "Add Component" in option_labels
    
    assert "Remove Component" in option_labels

pytestmark = pytest.mark.usefixtures("pygame_context")


def test_wing_retrofit_equipment_controls(wizard_setup):
    from unit_components.sensors import Sensors
    game, galaxy, player, constructor, wing, manager, screen_res = wizard_setup
    wing.hull_size = HullSize.STRIKECRAFT_WING
    wing.remove_component(Sensors)
    wizard = RetrofitWizardWindow(manager=manager, screen_res=screen_res,
        target_unit=wing, constructor_units=[constructor], initial_comp_key='Sensors')
    try:
        assert 'MiningComponent' not in {c['comp_key'] for c in wizard._get_eligible_components()}
        assert not wizard._sensor_long_range_entry.is_enabled
        assert wizard._comp_config['long_range_hexes'] == 0
        wizard._sensor_long_range_entry.set_text('2')
        wizard._sync_cost_and_summary()
        assert wizard._comp_config['long_range_hexes'] == 0
    finally:
        wizard.kill()


@pytest.mark.parametrize('value', ['nan', 'inf', 'abc', ''])
def test_invalid_numeric_input_blocks_preview_and_confirmation(wizard_setup, value):
    _, _, _, constructor, target, manager, resolution = wizard_setup
    wizard = RetrofitWizardWindow(manager, resolution, target, [constructor], initial_comp_key='Engines')
    try:
        wizard._engine_speed_entry.set_text(value)
        wizard._sync_cost_and_summary()
        assert not wizard.is_valid and not wizard._confirm_button.is_enabled
        action = wizard.process_event(pygame.event.Event(pygame_gui.UI_BUTTON_PRESSED, ui_element=wizard._confirm_button))
        assert action['action'] != 'confirm_retrofit'
        wizard._engine_speed_entry.set_text('10')
        wizard._sync_cost_and_summary()
        assert wizard.is_valid
    finally:
        wizard.kill()


def test_ally_target_preview_uses_constructor_credits(wizard_setup):
    game, _, player, constructor, target, manager, resolution = wizard_setup
    ally = Player('Ally', (1, 2, 3), team_id=player.team_id)
    ally.credits = 0
    game.players.append(ally)
    target.owner = ally
    wizard = RetrofitWizardWindow(manager, resolution, target, [constructor], initial_comp_key='Engines')
    try:
        assert wizard.is_valid
        assert str(player.credits) in wizard._player_credits_label.text
    finally:
        wizard.kill()


def test_ability_prerequisites_are_visible_and_block_installation(wizard_setup):
    _, _, _, constructor, target, manager, resolution = wizard_setup
    wizard = RetrofitWizardWindow(manager, resolution, target, [constructor], initial_comp_key='AbilityComponent')
    try:
        assert not wizard._ability_buttons['microjump'].is_enabled
        wizard._selected_abilities.add('microjump')
        wizard._sync_cost_and_summary()
        assert not wizard.is_valid
        assert 'requires component' in wizard._status_box.html_text
    finally:
        wizard.kill()


def test_invalid_turret_draft_is_not_silently_replaced_with_defaults(wizard_setup):
    _, _, _, constructor, target, manager, resolution = wizard_setup
    wizard = RetrofitWizardWindow(manager, resolution, target, [constructor], initial_comp_key='Weapons')
    try:
        count = len(wizard._turrets)
        wizard._turret_dmg_entry.set_text('nan')
        wizard._add_turret()
        assert len(wizard._turrets) == count
        assert not wizard.is_valid
    finally:
        wizard.kill()


@pytest.mark.parametrize('hull', [HullSize.TINY, HullSize.STRIKECRAFT_WING])
def test_retrofit_type_choices_respect_hull_and_wing_role(wizard_setup, hull):
    _, _, _, constructor, target, manager, resolution = wizard_setup
    target.hull_size = hull
    wizard = RetrofitWizardWindow(manager, resolution, target, [constructor], initial_comp_key='Weapons')
    def choices(dropdown):
        return [value[0] if isinstance(value, tuple) else value for value in dropdown.options_list]
    try:
        assert choices(wizard._hd_type_dropdown) == ['BASIC']
        assert choices(wizard._cloaking_type_dropdown) == ['BASIC']
        if hull == HullSize.STRIKECRAFT_WING:
            assert choices(wizard._turret_variant_dd) == ['ANTI_STRIKECRAFT']
    finally:
        wizard.kill()
