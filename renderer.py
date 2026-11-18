import pygame

from constants import BLACK
from game_actions.turn_presentation import defeat_notice, ai_summary_snapshot
from player_controller import automated_turn_active

from rendering.galaxy_renderer import GalaxyViewRenderer
from rendering.system_renderer import SystemViewRenderer
from rendering.sector_renderer import SectorViewRenderer
from rendering.main_menu_renderer import MainMenuRenderer
from rendering.ai_turn_renderer import AITurnRenderer

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
        self.ai_turn_renderer = AITurnRenderer(game_instance)

    def _draw_status(self, title, detail):
        center_x, center_y = self.screen.get_rect().center
        for text, size, offset in ((title, 42, -18), (detail, 25, 25)):
            font = pygame.font.Font(None, size)
            text_width = font.size(text)[0]
            if text_width > self.screen.get_width() - 32:
                font = pygame.font.Font(None, max(12, int(size * (self.screen.get_width() - 32) / text_width)))
            image = font.render(text, True, (205, 219, 234))
            self.screen.blit(image, image.get_rect(center=(center_x, center_y + offset)))
        pygame.display.flip()

    def draw(self):
        """Renders the current game state to the screen."""

        self.screen.fill(BLACK)

        # Always clear the overlay surface at the start of a draw call
        self.overlay_surface.fill((0, 0, 0, 0))

        defeated = defeat_notice(self.game)
        if defeated:
            title = f"{defeated[0]} has been defeated." if len(defeated) == 1 else "Players have been defeated."
            detail = "Press Enter to continue" if len(defeated) == 1 else ", ".join(defeated)
            self._draw_status(title, detail)
            return
        players = getattr(self.game, 'players', ())
        if self.game.game_started and players and all(player.defeated for player in players):
            self._draw_status("Campaign ended", "All players have been defeated.")
            return

        summary = ai_summary_snapshot(self.game)
        if summary is not None:
            self.game.turn_presentation.mark_ai_summary_visible()
            self.ai_turn_renderer.draw(summary)
            pygame.display.flip()
            return

        if automated_turn_active(self.game):
            self.ai_turn_renderer.draw(self.game.ai_coordinator.progress_snapshot())
            pygame.display.flip()
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
