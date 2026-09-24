"""Combine field feedback with complete design validation before publication."""
from custom_unit_templates import CustomUnitTemplate
from gui.equipment_input import mark_entry
from .component_state import refresh_hull_controls


def update_feedback(editor):
    """Return current errors, update actions, and keep invalid settings reachable.

    Readers own draft parsing. This validates their last valid numeric values as
    a complete design without replacing any widget text or publishing a template.
    """
    name = editor._display_entry.get_text().strip() if editor._display_entry else ''
    errors = list(getattr(editor, '_field_errors', {}).values())
    errors.extend(CustomUnitTemplate(name, editor._hull_size, editor._comp).validate())
    editor._validation_errors = errors
    mark_entry(editor._display_entry, None if name else 'Display name: enter a nonempty name.')
    for button in (editor._save_button, editor._save_as_button):
        if button:
            button.disable() if errors else button.enable()
    if editor._add_turret_button:
        invalid_turret = any(field.startswith('turret.') for field in getattr(editor, '_field_errors', {}))
        editor._add_turret_button.disable() if invalid_turret else editor._add_turret_button.enable()
    refresh_hull_controls(editor)
    return errors
