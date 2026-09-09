from types import SimpleNamespace

from turn_processor import TurnProcessor
from turn_presentation import NullTurnPresentation


def test_domain_turn_processor_has_no_implicit_ui_or_timer_effects():
    game = SimpleNamespace(pending_ai_turn_end_time=123)
    processor = TurnProcessor(game)
    assert isinstance(processor.presentation, NullTurnPresentation)
    processor.check_and_schedule_ai_turn()
    assert game.pending_ai_turn_end_time == 123

