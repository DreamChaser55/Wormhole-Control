"""Text layout and measurement helper functions."""
import logging
import typing
import pygame

logger = logging.getLogger(__name__)


def wrap_text_to_lines(text_to_wrap: str, max_pixel_width: int, font: pygame.font.Font) -> typing.Tuple[typing.List[str], int]:
    """Wraps text to fit within a maximum pixel width.

    Args:
        text_to_wrap: The string to wrap.
        max_pixel_width: The maximum width in pixels for a line.
        font: The pygame.font.Font object used for measuring text.

    Returns:
        A tuple containing:
            - A list of strings, where each string is a wrapped line.
            - The height of a single line of text with the given font.
    """
    if not text_to_wrap:
        return [""], font.get_rect("A").height if font else 10

    line_height = font.get_rect("A").height
    if max_pixel_width <= 0:
        return [text_to_wrap], line_height

    lines = []
    words = text_to_wrap.split(' ')
    current_line = ""

    if not words:
        return [""], line_height

    for word_idx, word in enumerate(words):
        try:
            word_width = font.get_rect(word).width
        except pygame.error as e:
            logger.debug(f"Warning: Pygame font error sizing word '{word}': {e}. Treating as zero width for layout.")
            word_width = 0

        if word_width > max_pixel_width and len(word) > 1:
            if current_line:
                lines.append(current_line)
                current_line = ""

            temp_char_line = ""
            for char_idx, char in enumerate(word):
                try:
                    char_render_width = font.get_rect(temp_char_line + char).width
                except pygame.error:
                    char_render_width = max_pixel_width + 1

                if char_render_width <= max_pixel_width:
                    temp_char_line += char
                else:
                    if temp_char_line:
                        lines.append(temp_char_line)
                    temp_char_line = char
                    if font.get_rect(char).width > max_pixel_width and len(temp_char_line) > 1:
                        lines.append(char)
                        temp_char_line = ""

            if temp_char_line:
                lines.append(temp_char_line)
            current_line = ""
        else:
            if not current_line:
                current_line = word
            else:
                test_line = current_line + " " + word
                try:
                    test_line_width = font.get_rect(test_line).width
                except pygame.error:
                    test_line_width = max_pixel_width + 1

                if test_line_width <= max_pixel_width:
                    current_line = test_line
                else:
                    lines.append(current_line)
                    current_line = word

    if current_line:
        lines.append(current_line)

    if not lines:
        lines.append("")

    return lines, line_height
