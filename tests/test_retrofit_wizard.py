"""
test_retrofit_wizard.py

Comprehensive test suite for the Retrofit Customization Options Wizard GUI.
"""

import pytest
import pygame
import pygame_gui
from geometry import Position
from utils import HexCoord
from constants import HullSize
from entities import Unit, Player
from galaxy import Galaxy, StarSystem
from events import EventBus, RefitUnitEvent
from order_system import OrderSystem
from unit_components import (
    Constructor, Engines, Weapons, Defenses, Sensors,
    CloakingDevice, AbilityComponent, AbilityType
)
from gui.retrofit_gui import RetrofitWizardWindow
from gui.retrofit_gui.catalog import RETROFIT_COMPONENTS
from game_actions import handle_gui_action
from input_processor import InputProcessor


@pytest.fixture(scope="module", autouse=True)
def pygame_init():
    pygame.init()
    pygame.display.set_mode((1280, 720))
    yield
    pygame.quit()


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
    player = Player(name="Player 1", color=(0, 0, 255), is_human=True)
    player.credits = 5000

    galaxy = Galaxy()
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


def test_retrofit_wizard_initialization(wizard_setup):
    game, galaxy, player, constructor_unit, target_unit, manager, screen_res = wizard_setup
    wizard = RetrofitWizardWindow(
        manager=manager,
        screen_res=screen_res,
        target_unit=target_unit,
        constructor_units=[constructor_unit],
        initial_comp_key="Defenses"
    )

    assert wizard.is_visible is True
    assert wizard.window.alive() is True
    assert wizard._current_comp_key == "Defenses"
    assert wizard.calculated_hull_cost > 0
    assert wizard.cost_credits > 0
    assert wizard.is_valid is True
    wizard.kill()


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
    assert "Insufficient Credits" in wizard._status_box.html_text
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
    assert "Insufficient Hull Capacity" in wizard._status_box.html_text
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

    # Advance 2 turns to finish refit
    constructor_unit.constructor_component.update(galaxy)
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
