"""Every star type can supply a color to the renderer."""
import pygame
from constants import StarType, STAR_COLORS
from domain.celestials import Star


def test_every_star_type_resolves_a_renderable_color():
    for star_type in StarType:
        star = Star(in_system="Sol", star_type=star_type)
        color = STAR_COLORS[star.star_type]
        assert len(color) == 3
        assert all(type(channel) is int and 0 <= channel <= 255 for channel in color)
        pygame.draw.circle(pygame.Surface((8, 8)), color, (4, 4), 2)
