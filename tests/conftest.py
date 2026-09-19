"""Keep tests and their child processes away from the real custom-design library."""
import atexit
from contextlib import ExitStack
from itertools import count
import os
from pathlib import Path
import tempfile

import pytest

from tests.support.pygame_runtime import drain_events, release_gui_resources
from tests.support.ci_diagnostics import configure_diagnostics


def pytest_configure(config):
    configure_diagnostics(config)



# Configure SDL before any test module imports application constants or GUI code.
os.environ["SDL_VIDEODRIVER"] = "dummy"
os.environ["SDL_AUDIODRIVER"] = "dummy"


_user_data = tempfile.TemporaryDirectory(prefix="wormhole-test-user-data-")
atexit.register(_user_data.cleanup)
os.environ["WORMHOLE_USER_DATA_DIR"] = _user_data.name
Path(_user_data.name, "custom_unit_templates.json").write_text("{}", encoding="utf-8")
_case_ids = count()


@pytest.fixture(autouse=True)
def isolated_process_state(monkeypatch):
    """Restore global allocators and registries; never share mutable user storage."""
    import random
    from domain.identity import GameObject
    from domain.players import Player
    from unit_components.intelligence import Agent
    from unit_orders.base import Order
    from unit_templates import UNIT_TEMPLATES, PRIVATE_TEMPLATES
    import save_manager

    owners = ((GameObject, "object_counter"), (Player, "player_counter"),
              (Agent, "agent_counter"), (Order, "order_counter"))
    counters = [(owner, field, getattr(owner, field)) for owner, field in owners]
    registry = dict(UNIT_TEMPLATES)
    private_registry = dict(PRIVATE_TEMPLATES)
    rng = random.getstate()
    random.seed(12)
    # Keep fixture-owned files outside each test's tmp_path, so filesystem tests
    # can assert that their own working directory remains untouched.
    library = Path(_user_data.name, str(next(_case_ids)))
    library.mkdir()
    (library / "custom_unit_templates.json").write_text("{}", encoding="utf-8")
    monkeypatch.setenv("WORMHOLE_USER_DATA_DIR", str(library))
    monkeypatch.setattr(save_manager, "SAVES_DIR", str(library / "saves"))
    yield
    for owner, field, value in counters:
        setattr(owner, field, value)
    UNIT_TEMPLATES.clear()
    UNIT_TEMPLATES.update(registry)
    PRIVATE_TEMPLATES.clear()
    PRIVATE_TEMPLATES.update(private_registry)
    random.setstate(rng)



@pytest.fixture(scope="session")
def _pygame_runtime():
    import pygame
    pygame.init()
    try:
        yield pygame
    finally:
        try:
            release_gui_resources()
        finally:
            pygame.quit()


@pytest.fixture
def pygame_context(_pygame_runtime):
    """Fresh display contents/events without repeatedly restarting SDL."""
    pygame = _pygame_runtime
    screen = pygame.display.set_mode((1280, 720))
    screen.fill((0, 0, 0))
    drain_events()
    try:
        yield pygame
    finally:
        release_gui_resources()


@pytest.fixture
def game_factory(pygame_context, tmp_path, monkeypatch, request):
    """Own full application instances and their threads, GUI, and runtime files."""
    from game import Game
    monkeypatch.chdir(tmp_path)
    games = []

    def create(*, display_config=None):
        game = Game(control_port=0, display_config=display_config)
        games.append(game)
        return game

    if request.instance is not None:
        request.instance.make_game = create
    try:
        yield create
    finally:
        try:
            # ExitStack attempts every shutdown even if another one raises.
            with ExitStack() as cleanup:
                for game in games:
                    cleanup.callback(game.gui.clear_and_reset)
                    cleanup.callback(game.ai_coordinator.shutdown)
                    cleanup.callback(game.control_service.shutdown)
        finally:
            games.clear()
            if request.instance is not None:
                del request.instance.make_game


# Shared fixtures are registered explicitly, independent of test module imports.
from tests.support.scenarios import atmosphere as atmosphere
