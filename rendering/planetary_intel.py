"""Ownership decoration from the same disclosure view used by observations."""
import math
import pygame

from planetary_intel import displayed_owner, presentation_view


def draw_ownership_ring(surface, game, body, center, radius):
    view = presentation_view(game, body)
    owner = displayed_owner(game, body)
    if owner is None:
        return
    if view.status == 'current':
        pygame.draw.circle(surface, owner.color, center, radius, 1)
    else:
        color = tuple(round(channel * 0.55) for channel in owner.color)
        rect = pygame.Rect(center[0] - radius, center[1] - radius, 2 * radius, 2 * radius)
        for segment in range(12):
            start = segment * math.tau / 12
            pygame.draw.arc(surface, color, rect, start, start + math.tau / 24, 1)
