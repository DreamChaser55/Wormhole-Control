import pygame
import pygame_gui
import os

pygame.init()
pygame.display.set_mode((800, 600))
manager = pygame_gui.UIManager((800, 600), "d:/Programming/Github_repos/Wormhole-Control/theme.json")

label_rect = pygame.Rect(0, 0, 200, -1)
label = pygame_gui.elements.UILabel(
    relative_rect=label_rect,
    text="Hit Points: 400/400",
    manager=manager,
    object_id='#sidebar_hit_points_ok_label'
)

print(f"Calculated height: {label.get_relative_rect().height}")
