"""Display helper for hit-point values (HP is a float; show at most one decimal)."""


def format_hp(value: float) -> str:
    """Format HP compactly: whole numbers without a decimal, otherwise one decimal place."""
    text = f"{float(value):.1f}"
    return text[:-2] if text.endswith(".0") else text
