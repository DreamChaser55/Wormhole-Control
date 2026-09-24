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


def literal_constant(path, qualified_name):
    """Read a module/class constant without importing its module or dependencies."""
    nodes = ast.parse(path.read_text(encoding='utf-8')).body
    *classes, name = qualified_name.split('.')
    for class_name in classes:
        matches = [node for node in nodes if isinstance(node, ast.ClassDef) and node.name == class_name]
        if len(matches) != 1:
            raise ValueError(f'{path}: expected one class {class_name}')
        nodes = matches[0].body
    values = []
    for node in nodes:
        targets = node.targets if isinstance(node, ast.Assign) else [node.target] if isinstance(node, ast.AnnAssign) else []
        if any(isinstance(target, ast.Name) and target.id == name for target in targets):
            values.append(ast.literal_eval(node.value))
    if len(values) != 1:
        raise ValueError(f'{path}: expected one literal constant {qualified_name}')
    return values[0]


def version_table(root=ROOT):
    """Keep independent format identifiers tied to their runtime owners."""
    sources = (
        ('Campaign save', 'save_manager.py', 'CURRENT_SAVE_VERSION'),
        ('Observation', 'game_ai/observation.py', 'OBSERVATION_SCHEMA_VERSION'),
        ('Command contract', 'game_ai/command_spec.py', 'CONTRACT_VERSION'),
        ('Response schema', 'game_ai/schema.py', 'TURN_PLAN_SCHEMA_NAME'),
        ('Prompt cache', 'game_ai/adapters/openai_responses.py', 'PROMPT_CACHE_KEY'),
        ('Local socket protocol', 'game_control_protocol.py', 'PROTOCOL_VERSION'),
        ('Strikecraft Bay component', 'unit_components/strikecraft.py', 'StrikecraftBayComponent.SCHEMA_VERSION'),
        ('Strikecraft Wing component', 'unit_components/strikecraft.py', 'StrikecraftWingComponent.SCHEMA_VERSION'),
    )
    return table(['Contract', 'Current version / identifier', 'Source'], [
        (label, literal_constant(root / relative, name), f'[{name}](../{relative})')
        for label, relative, name in sources
    ])


def generated_blocks():
    from constants import PLANET_TRAITS
    from unit_components.abilities.registry import ABILITY_DEFINITIONS
    from unit_orders.base import OrderType
    rows = component_rows()
    labels = {row['key']: row['label'] for row in rows}
    abilities = list(ABILITY_DEFINITIONS.values())
    blocks = {
        'components': f'The Unit Designer provides **{len(rows)} selectable component rows**. Commander is always present.\n\n' + table(
            ['#', 'Component Key', 'Label', 'Cost Type', 'Default Cost'],
            [(i, f"`{r['key']}`", r['label'], 'Dynamic' if r['is_dynamic'] else 'Fixed', round(r['default_cost'], 2))
             for i, r in enumerate(rows, 1)]),
        'abilities': f'There are **{len(abilities)} special abilities** registered in the game.\n\n' + table(
            ['Ability', 'Mode', 'Cooldown (Turns)', 'Duration (Turns)', 'Range (logical units)', 'AM Cost', 'Ongoing AM / owner turn', 'Required Component', 'Target Type'],
            [(f'**{a.name}**', a.activation_mode.title(), a.cooldown,
              'Until disabled' if a.activation_mode == 'toggle' else a.duration, a.range, a.antimatter_cost, a.ongoing_antimatter,
              ', '.join(labels[k] for k in a.required_components),
              'Nebula + Position' if a.ability_type.value == 'nebula_catalyst' else 'Unit' if a.requires_target_unit else 'Position' if a.requires_target_position else 'Self') for a in abilities]),
        'order-count': f'The `OrderType` enum defines **{len(OrderType)} order types**, including the persistent `STANCE` root.',
        'planets': table(['Planet Type', 'Colonizable', 'Max Population', 'Growth Rate', 'Passive Metal', 'Passive Crystal', 'Antimatter Multiplier'],
            [(f"**{kind.name.replace('_', ' ').title()}**", 'Yes' if t['is_colonizable'] else 'No',
              t['max_population'], f"{t['growth_rate'] * 100:g}% / turn", t['passive_metal'],
              t['passive_crystal'], f"{t['am_harvest_multiplier']}x") for kind, t in PLANET_TRAITS.items()]),

    }
    from unit_templates import _load_templates
    from unit_catalog import describe_template
    entries = [describe_template(key, raw) for key, raw in _load_templates().items()]
    entries.sort(key=lambda e: (e['category'], e['credit_cost'], e['name']))
    blocks['unit-catalog'] = table(
        ['Design', 'Category', 'Hull / kind', 'Hull used', 'Credits', 'Turns', 'Upkeep', 'Role and operation'],
        [(e['name'], e['category'], e['hull_size'] + ' ' + e['kind'], f"{e['hull_used']:.2f}/{e['hull_capacity']:g}",
         e['credit_cost'], e['turns'], f"{e['upkeep']:.2f}", e['description']) for e in entries])
    blocks['environment'] = environmental_tables()
    blocks['versions'] = version_table()
    return blocks


def environmental_tables():
    """Use the same public terrain values as gameplay, sidebar and observations."""
    from constants import FieldDensity, NebulaType, StarType, StormType
    from domain.celestials import AsteroidField, DebrisField, IceField, Nebula, Star, Storm
    from environmental_effects import describe_body
    rows = []
    for cls in (AsteroidField, IceField, DebrisField):
        for density in FieldDensity:
            body = cls((0, 0), 'Reference', density)
            description = describe_body(body)
            effects = dict(description.effects)
            rows.append((cls.__name__.replace('Field', ' Field'), density.name.title(), body.max_hull_size.name.title(),
                f'{description.effect_radius:g}', f'{effects["speed_multiplier"]:.0%}',
                f'{effects.get("beam_cover", 0):.0%}', f'{effects.get("kinetic_missile_cover", 0):.0%}',
                effects.get('cooldown_reduction', 0), f'{description.hazards[0].amount:g}' if description.hazards else 0))
    fields = table(['Field', 'Density', 'Largest hull', 'Effect radius', 'Speed', 'Beam cover',
                    'Kinetic/missile cover', 'Turret cooling (turns)', 'Abrasion (base HP)'], rows)
    rows = []
    for kind in NebulaType:
        effects = dict(describe_body(Nebula((0, 0), 'Reference', kind)).effects)
        rows.append((kind.name.title(), f'{effects.get("harvest_multiplier", 0):g}x',
            f'{effects.get("fuel_multiplier", 1):.0%}', f'{effects.get("sensor_multiplier", 1):.0%}',
            effects.get('cooldown_reduction', 0), f'{effects.get("splash_damage_multiplier", 1):g}x'))
    nebulae = table(['Nebula', 'AM harvest', 'Propulsion AM', 'Short-range radius',
                     'Turret cooling (turns)', 'Cluster Warhead splash taken'], rows)
    bodies = [Storm((0, 0), 'Reference', kind) for kind in StormType]
    bodies.extend(Star('Reference', kind) for kind in (StarType.BLACK_HOLE, StarType.PULSAR))
    rows = []
    for body in bodies:
        for hazard in describe_body(body).hazards:
            amount = f'{hazard.amount:.0%} of current AM' if hazard.amount_basis == 'fraction_of_current_antimatter' else f'{hazard.amount:g}'
            if hazard.kind == 'magnetic':
                amount = f'Up to {amount}'
            area = 'Whole star sector' if hazard.scope == 'sector' else f'Radius {hazard.radius:g}'
            rows.append((hazard.kind.replace('_', ' ').title(), amount, hazard.target.replace('_', ' '), area))
    hazards = table(['Hazard', 'Base amount per owner turn', 'Target', 'Area (inclusive)'], rows)
    return fields + '\n\n' + nebulae + '\n\n' + hazards


def replace_block(text, key, generated):
    start, end = f'<!-- BEGIN GENERATED: {key} -->', f'<!-- END GENERATED: {key} -->'
    if text.count(start) != 1 or text.count(end) != 1:
        raise ValueError(f'Expected exactly one marker pair for {key}')
    pattern = re.escape(start) + r'.*?' + re.escape(end)
    return re.sub(pattern, lambda _: f'{start}\n{generated}\n{end}', text, count=1, flags=re.S)


def update_documents(blocks, *, check=False, root=ROOT):
    """Return stale relative paths. Check mode never writes any document."""
    stale = []
    for relative, keys in {
        'docs/REFERENCE.md': ('components', 'abilities', 'order-count', 'planets', 'environment', 'unit-catalog'),
        'docs/DEVELOPMENT.md': ('versions',),
    }.items():
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
