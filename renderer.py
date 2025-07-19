import pygame
from pygame import Color

from constants import (
    GALAXY_BG_COLOR, SYSTEM_BG_COLOR, SECTOR_BG_COLOR, BLACK
)
from rendering.galaxy_renderer import GalaxyViewRenderer
from rendering.system_renderer import SystemViewRenderer
from rendering.sector_renderer import SectorViewRenderer

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

    def draw(self):
        """Renders the current game state to the screen."""
        if self.game.view_mode == 'galaxy':
            background_color = GALAXY_BG_COLOR
        elif self.game.view_mode == 'system':
            background_color = SYSTEM_BG_COLOR
        elif self.game.view_mode == 'sector':
            background_color = SECTOR_BG_COLOR
        elif self.game.view_mode == 'main_menu' or self.game.view_mode == 'about':
            background_color = GALAXY_BG_COLOR
        else:
            background_color = BLACK

        self.screen.fill(background_color)

        # Always clear the overlay surface at the start of a draw call
        self.overlay_surface.fill((0, 0, 0, 0))

        if self.game.view_mode == 'galaxy' and self.game.game_started:
            self.galaxy_renderer.draw_galaxy_view()
        elif self.game.view_mode == 'system' and self.game.game_started:
            self.system_renderer.draw_system_view()
        elif self.game.view_mode == 'sector' and self.game.game_started:
            self.sector_renderer.draw_sector_view()
        
        if self.game.view_mode not in ['main_menu', 'about']:
            self.screen.blit(self.overlay_surface, (0, 0))

        self.gui.draw(self.screen)

        pygame.display.flip()
