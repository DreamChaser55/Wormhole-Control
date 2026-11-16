import pygame

from constants import BLACK
from player_controller import PlayerController, automated_turn_active

from rendering.galaxy_renderer import GalaxyViewRenderer
from rendering.system_renderer import SystemViewRenderer
from rendering.sector_renderer import SectorViewRenderer
from rendering.main_menu_renderer import MainMenuRenderer

class Renderer:
    def __init__(self, game_instance):
        self.game = game_instance
        self.screen = game_instance.screen
        self.overlay_surface = game_instance.overlay_surface
        self.gui = game_instance.gui

        # Instantiate the view-specific renderers
        self.galaxy_renderer = GalaxyViewRenderer(game_instance)
        self.system_renderer = SystemViewRenderer(game_instance)
        self.sector_renderer = SectorViewRenderer(game_instance)
        self.main_menu_renderer = MainMenuRenderer(game_instance)

    def _draw_status(self, title, detail):
        center_x, center_y = self.screen.get_rect().center
        for text, size, offset in ((title, 42, -18), (detail, 25, 25)):
            font = pygame.font.Font(None, size)
            image = font.render(text, True, (205, 219, 234))
            self.screen.blit(image, image.get_rect(center=(center_x, center_y + offset)))
        pygame.display.flip()

    def draw(self):
        """Renders the current game state to the screen."""

        self.screen.fill(BLACK)

        # Always clear the overlay surface at the start of a draw call
        self.overlay_surface.fill((0, 0, 0, 0))

        if automated_turn_active(self.game):
            if self.game.current_player.controller == PlayerController.CODEX:
                status = 'Waiting for Codex'
                detail = 'The map returns on the next human turn.'
            elif getattr(self.game.ai_coordinator, 'state', None) == 'error':
                status = 'AI turn needs attention'
                detail = 'Press E to skip this turn.'
            else:
                status = 'AI turn in progress'
                detail = 'The map returns on the next human turn.'
            self._draw_status(status, detail)
            return

        if self.game.view_mode == 'galaxy' and self.game.game_started:
            self.galaxy_renderer.draw_galaxy_view()
        elif self.game.view_mode == 'system' and self.game.game_started:
            self.system_renderer.draw_system_view()
        elif self.game.view_mode == 'sector' and self.game.game_started:
            self.sector_renderer.draw_sector_view()
        elif self.game.view_mode in ('main_menu', 'about'):
            self.main_menu_renderer.draw()

        if self.game.view_mode not in ['main_menu', 'about']:
            self.screen.blit(self.overlay_surface, (0, 0))

        self.gui.draw(self.screen)

        pygame.display.flip()
