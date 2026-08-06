"""GUI action dispatch package for Wormhole Control."""
import logging
import typing
from . import app_actions, unit_actions, selection_actions

logger = logging.getLogger(__name__)

ACTION_HANDLERS: typing.Dict[str, typing.Callable[[typing.Any, dict], None]] = {
    **app_actions.HANDLERS,
    **unit_actions.HANDLERS,
    **selection_actions.HANDLERS,
}


def handle_gui_action(game, action: dict) -> None:
    """Handles action events triggered by user interactions with GUI controls.

    Args:
        game: Target game instance.
        action (dict): Dictionary containing action details including the 'action' string key.
    """
    action_type = action.get('action')
    handler = ACTION_HANDLERS.get(action_type)
    if handler is None:
        logger.debug(f"Warning: Unhandled GUI action type: {action_type}")
        return
    handler(game, action)


__all__ = [
    'ACTION_HANDLERS',
    'handle_gui_action',
]
