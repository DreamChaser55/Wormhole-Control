"""Release test-owned SDL event payloads and GUI resource cycles."""
import gc


def drain_events():
    """Discard events through Python so their payload references are released."""
    import pygame

    if pygame.display.get_init():
        # pygame-ce 2.5.7 event.clear() flushes SDL events without releasing
        # Python payloads, which can retain entire UI managers through widgets.
        pygame.event.get()


def release_gui_resources():
    """Run after widgets/services shut down, while SDL is still available."""
    from pygame_gui.core.utility import set_default_manager

    try:
        drain_events()
    finally:
        set_default_manager(None)
        gc.collect()
