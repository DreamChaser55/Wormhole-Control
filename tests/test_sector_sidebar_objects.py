import pytest
from unittest.mock import MagicMock
from entities import Unit, Planet, Star, Minefield, Player
from game import Game
from constants import HullSize, PlanetType, StarType
from geometry import Position
from utils import HexCoord

def test_hex_sidebar_objects_as_buttons_and_colored():
    mock_game = MagicMock()
    mock_game.galaxy = MagicMock()
    mock_game.sidebar_needs_update = True
    mock_game.gui = MagicMock()
    mock_game.is_unit_visible = MagicMock(return_value=True)
    mock_game.hex_has_presence = MagicMock(return_value=False)

    p1 = Player(name="Player 1", color=(0, 0, 255))
    p1.id = 1
    mock_game.players = [p1]
    mock_game.current_player_index = 0

    # Create hex mock with system
    system_mock = MagicMock()
    system_mock.name = "Sol"
    mock_game.galaxy.systems = {"Sol": system_mock}

    from galaxy import Hex
    hex_mock = Hex(q=0, r=0, in_system="Sol")

    # Celestial Body (Planet) with owner
    planet = Planet(in_hex=(0, 0), in_system="Sol", planet_type=PlanetType.TERRAN)
    planet.id = 501
    planet.name = "Earth"
    planet.owner = p1

    # Celestial Body (Star) unowned
    star = Star(in_system="Sol", star_type=StarType.G_TYPE)
    star.id = 502
    star.name = "Sol Star"
    star.owner = None

    hex_mock.celestial_bodies = [planet, star]

    # Unit
    unit = Unit(
        owner=p1,
        position=Position(0, 0),
        in_hex=(0, 0),
        in_system="Sol",
        name="Cruiser Alpha",
        hull_size=HullSize.MEDIUM,
        game=mock_game
    )
    unit.id = 601
    hex_mock.units = [unit]

    # Minefield
    minefield = Minefield(
        owner=p1,
        position=Position(0, 0),
        in_hex=(0, 0),
        in_system="Sol",
        mines_remaining=50
    )
    minefield.id = 701
    hex_mock.minefields = [minefield]

    mock_game.selected_objects = [hex_mock]

    # Run update_side_bar_content
    Game.update_side_bar_content(mock_game)

    # Verify gui.update_side_bar_content was called
    mock_game.gui.update_side_bar_content.assert_called_once()
    data_list = mock_game.gui.update_side_bar_content.call_args[0][0]

    # Check celestial body buttons
    body_buttons = [d for d in data_list if d.get("type") == "button" and d.get("action_id") == "select_celestial_body"]
    assert len(body_buttons) == 2
    assert body_buttons[0]["target_data"] == 501
    assert body_buttons[0]["text"] == "Earth"
    assert body_buttons[0]["object_id"] == "#player_player_1_button"
    assert body_buttons[1]["target_data"] == 502
    assert body_buttons[1]["text"] == "Sol Star"
    assert body_buttons[1]["object_id"] == "#sidebar_neutral_button"

    # Check unit buttons
    unit_buttons = [d for d in data_list if d.get("type") == "button" and d.get("action_id") == "select_individual_unit"]
    assert len(unit_buttons) == 1
    assert unit_buttons[0]["target_data"] == 601
    assert unit_buttons[0]["text"] == "Cruiser Alpha"
    assert unit_buttons[0]["object_id"] == "#player_player_1_button"

    # Check minefield buttons
    mf_buttons = [d for d in data_list if d.get("type") == "button" and d.get("action_id") == "select_minefield"]
    assert len(mf_buttons) == 1
    assert mf_buttons[0]["target_data"] == 701
    assert "50 mines" in mf_buttons[0]["text"]
    assert mf_buttons[0]["object_id"] == "#player_player_1_button"

def test_handle_gui_action_select_celestial_body():
    mock_game = MagicMock()
    mock_game.galaxy = MagicMock()
    mock_game.selected_objects = []
    mock_game.sidebar_needs_update = False

    planet = MagicMock()
    planet.id = 501
    mock_game.galaxy.get_celestial_body_by_id.return_value = planet

    action = {'action': 'select_celestial_body', 'body_id': 501}
    Game.handle_gui_action(mock_game, action)

    assert mock_game.selected_objects == [planet]
    assert mock_game.sidebar_needs_update is True
