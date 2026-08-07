"""Unit tests for the toggle_inhibitor GUI action handler."""
from unittest.mock import MagicMock
from game_actions import ACTION_HANDLERS, handle_gui_action
from entities import Unit
from unit_components.inhibitor import HyperspaceInhibitionFieldEmitter
from unit_components import Commander
from unit_orders import ToggleInhibitorOrder


def test_toggle_inhibitor_action_registered():
    """Verify 'toggle_inhibitor' is registered in ACTION_HANDLERS."""
    assert 'toggle_inhibitor' in ACTION_HANDLERS


def test_toggle_inhibitor_direct():
    """Verify direct toggle calls inhibitor.toggle(galaxy_ref=game.galaxy)."""
    mock_game = MagicMock()
    mock_unit = MagicMock(spec=Unit)
    mock_unit.name = "Test Unit"
    mock_inhibitor = MagicMock(spec=HyperspaceInhibitionFieldEmitter)
    mock_unit.inhibitor_component = mock_inhibitor
    mock_game.selected_objects = [mock_unit]
    mock_game.galaxy = MagicMock()

    action = {'action': 'toggle_inhibitor', 'shift_pressed': False}
    handle_gui_action(mock_game, action)

    mock_inhibitor.toggle.assert_called_once_with(galaxy_ref=mock_game.galaxy)
    assert mock_game.sidebar_needs_update is True


def test_toggle_inhibitor_queued_with_shift():
    """Verify shift_pressed=True queues a ToggleInhibitorOrder with inverted turn_on state."""
    mock_game = MagicMock()
    mock_unit = MagicMock(spec=Unit)
    mock_unit.name = "Test Unit"
    mock_inhibitor = MagicMock(spec=HyperspaceInhibitionFieldEmitter)
    mock_inhibitor.is_active = True
    mock_commander = MagicMock(spec=Commander)
    mock_unit.inhibitor_component = mock_inhibitor
    mock_unit.commander_component = mock_commander
    mock_game.selected_objects = [mock_unit]

    action = {'action': 'toggle_inhibitor', 'shift_pressed': True}
    handle_gui_action(mock_game, action)

    mock_inhibitor.toggle.assert_not_called()
    mock_commander.add_order.assert_called_once()
    added_order = mock_commander.add_order.call_args[0][0]
    assert isinstance(added_order, ToggleInhibitorOrder)
    assert added_order.parameters == {'turn_on': False}
    assert mock_game.sidebar_needs_update is True
