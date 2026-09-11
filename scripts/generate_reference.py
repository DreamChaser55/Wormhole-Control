"""Generate registry-derived reference blocks, or check them without writing.

Run from any directory. Registry imports occur only inside an isolated headless
environment; the game and custom-design manager are never instantiated.
"""
from contextlib import contextmanager
from pathlib import Path
import argparse
import ast
import os
import re
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]


@contextmanager
def isolated_environment():
    keys = ('SDL_VIDEODRIVER', 'SDL_AUDIODRIVER', 'WORMHOLE_FULLSCREEN',
            'WORMHOLE_USER_DATA_DIR', 'PYGAME_HIDE_SUPPORT_PROMPT')
    previous = {key: os.environ.get(key) for key in keys}
    with tempfile.TemporaryDirectory(prefix='wormhole-reference-') as directory:
        os.environ.update(SDL_VIDEODRIVER='dummy', SDL_AUDIODRIVER='dummy',
                          WORMHOLE_FULLSCREEN='false', WORMHOLE_USER_DATA_DIR=directory,
                          PYGAME_HIDE_SUPPORT_PROMPT='1')
        Path(directory, 'custom_unit_templates.json').write_text('{}', encoding='utf-8')
        sys.path.insert(0, str(ROOT))
        try:
            yield
        finally:
            sys.path.pop(0)
            for key, value in previous.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value


def table(headers, rows):
    def line(cells):
        return '| ' + ' | '.join(str(cell).replace('|', '\\|') for cell in cells) + ' |'
    return '\n'.join([line(headers), line(['---'] * len(headers)), *(line(row) for row in rows)])


def component_rows():
    """Read the literal designer catalogue without importing GUI widget modules."""
    tree = ast.parse((ROOT / 'gui/unit_editor_gui/catalog.py').read_text(encoding='utf-8'))
    for node in tree.body:
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.target.id == 'COMPONENT_ROWS':
            return ast.literal_eval(node.value)
    raise ValueError('COMPONENT_ROWS catalogue was not found')


def generated_blocks():
    from constants import (PLANET_TRAITS, FieldDensity, ICE_FIELD_DENSITY_BEAM_DEFENSE_BONUS,
        DEBRIS_FIELD_DENSITY_DEFENSE_BONUS, ICE_FIELD_COOLDOWN_REDUCTION,
        NITROGEN_NEBULA_COOLDOWN_REDUCTION, OXYGEN_NEBULA_SPLASH_DAMAGE_MOD)
    from unit_components.abilities.registry import ABILITY_DEFINITIONS
    from unit_orders.base import OrderType
    rows = component_rows()
    labels = {row['key']: row['label'] for row in rows}
    abilities = list(ABILITY_DEFINITIONS.values())
    blocks = {
        'components': f'The Unit Designer provides **{len(rows)} selectable component rows**. Commander is always present.\n\n' + table(
            ['#', 'Component Key', 'Label', 'Cost Type', 'Default Cost'],
            [(i, f"`{r['key']}`", r['label'], 'Dynamic' if r['is_dynamic'] else 'Fixed', r['default_cost'])
             for i, r in enumerate(rows, 1)]),
        'abilities': f'There are **{len(abilities)} special abilities** registered in the game.\n\n' + table(
            ['Ability', 'Cooldown (Turns)', 'Duration (Turns)', 'Range (logical units)', 'AM Cost', 'Required Component', 'Target Type'],
            [(f'**{a.name}**', a.cooldown, a.duration, a.range, a.antimatter_cost,
              ', '.join(labels[k] for k in a.required_components),
              'Nebula + Position' if a.ability_type.value == 'nebula_catalyst' else 'Unit' if a.requires_target_unit else 'Position' if a.requires_target_position else 'Self') for a in abilities]),
        'order-count': f'The `OrderType` enum defines **{len(OrderType)} order types**, including the persistent `STANCE` root.',
        'planets': table(['Planet Type', 'Colonizable', 'Max Population', 'Growth Rate', 'Passive Metal', 'Passive Crystal', 'Antimatter Multiplier'],
            [(f"**{kind.name.replace('_', ' ').title()}**", 'Yes' if t['is_colonizable'] else 'No',
              t['max_population'], f"{t['growth_rate'] * 100:g}% / turn", t['passive_metal'],
              t['passive_crystal'], f"{t['am_harvest_multiplier']}x") for kind, t in PLANET_TRAITS.items()]),
        'environment': table(['Density', 'Ice beam cover', 'Debris kinetic/missile cover'],
            [(d.name.title(), f'{ICE_FIELD_DENSITY_BEAM_DEFENSE_BONUS[d]:.0%}',
              f'{DEBRIS_FIELD_DENSITY_DEFENSE_BONUS[d]:.0%}') for d in FieldDensity]) + '\n\n' + table(
            ['Environment', 'Combat modifier'],
            [('Ice field', f'-{ICE_FIELD_COOLDOWN_REDUCTION} turn to cooldown reset when firing'),
             ('Nitrogen nebula', f'-{NITROGEN_NEBULA_COOLDOWN_REDUCTION} turn to cooldown reset when firing'),
             ('Oxygen nebula', f'{OXYGEN_NEBULA_SPLASH_DAMAGE_MOD:g}x splash damage taken')]),
    }
    from unit_templates import _load_templates
    from unit_catalog import describe_template
    entries = [describe_template(key, raw) for key, raw in _load_templates().items()]
    entries.sort(key=lambda e: (e['category'], e['credit_cost'], e['name']))
    blocks['unit-catalog'] = table(
        ['Design', 'Category', 'Hull / kind', 'Hull used', 'Credits', 'Turns', 'Upkeep', 'Role and operation'],
        [(e['name'], e['category'], e['hull_size'] + ' ' + e['kind'], f"{e['hull_used']:.2f}/{e['hull_capacity']:g}",
          e['credit_cost'], e['turns'], f"{e['upkeep']:.2f}", e['description']) for e in entries])
    return blocks


def replace_block(text, key, generated):
    start, end = f'<!-- BEGIN GENERATED: {key} -->', f'<!-- END GENERATED: {key} -->'
    if text.count(start) != 1 or text.count(end) != 1:
        raise ValueError(f'Expected exactly one marker pair for {key}')
    pattern = re.escape(start) + r'.*?' + re.escape(end)
    return re.sub(pattern, lambda _: f'{start}\n{generated}\n{end}', text, count=1, flags=re.S)


def update_documents(blocks, *, check=False, root=ROOT):
    """Return stale relative paths. Check mode never writes any document."""
    stale = []
    for relative, keys in {'docs/REFERENCE.md': ('components', 'abilities', 'order-count', 'planets', 'environment', 'unit-catalog')}.items():
        path = root / relative
        original = path.read_text(encoding='utf-8')
        result = original
        for key in keys:
            result = replace_block(result, key, blocks[key])
        if result != original:
            stale.append(relative)
            if not check:
                path.write_text(result, encoding='utf-8')
    return stale


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true', help='Fail if generated blocks are stale; do not write.')
    args = parser.parse_args(argv)
    with isolated_environment():
        stale = update_documents(generated_blocks(), check=args.check)
    for path in stale:
        print(f'{"Stale" if args.check else "Updated"}: {path}')
    if args.check and stale:
        print('Run python scripts/generate_reference.py to refresh these blocks.')
        return 1
    print('Generated reference is current.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
