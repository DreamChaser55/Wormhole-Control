import pytest
from constants import StarType, STAR_COLORS
from entities import Star

def test_all_star_types_have_colors():
    """Verify that every defined StarType has an entry in STAR_COLORS."""
    for star_type in StarType:
        assert star_type in STAR_COLORS, f"Missing color for StarType: {star_type}"

def test_star_colors_are_valid_rgb_tuples():
    """Verify that all color entries in STAR_COLORS are valid 3-element RGB tuples."""
    for star_type, color in STAR_COLORS.items():
        assert isinstance(color, tuple), f"Color for {star_type} must be a tuple"
        assert len(color) == 3, f"Color for {star_type} must be an RGB 3-tuple"
        for channel in color:
            assert isinstance(channel, int), f"RGB channel for {star_type} must be an int"
            assert 0 <= channel <= 255, f"RGB channel for {star_type} must be between 0 and 255"

def test_all_star_types_have_distinct_colors():
    """Verify that all 11 star types have unique RGB colors."""
    unique_colors = set(STAR_COLORS.values())
    assert len(unique_colors) == len(StarType), (
        f"Expected {len(StarType)} unique star colors, but found {len(unique_colors)}"
    )

def test_star_entity_color_resolution():
    """Verify that Star entity instances resolve their colors via STAR_COLORS."""
    for star_type in StarType:
        star = Star(in_system="Sol", star_type=star_type)
        resolved_color = STAR_COLORS[star.star_type]
        assert resolved_color == STAR_COLORS[star_type]
