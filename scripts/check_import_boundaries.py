"""Check core dependency direction without importing or initializing the game."""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CORE_FILES = (
    'constants.py', 'geometry.py', 'utils.py', 'display_config.py',
    'turn_presentation.py', 'turn_processor.py', 'galaxy.py', 'game_settings.py',
    'visibility.py', 'economy.py', 'pathfinding.py', 'sector_utils.py',
    'hexgrid_utils.py', 'order_history.py',
)
FORBIDDEN = {
    'pygame', 'pygame_gui', 'gui', 'rendering', 'renderer', 'input_processor',
    'game', 'game_actions', 'game_camera', 'application_bootstrap',
}


def core_paths(root: Path = ROOT) -> list[Path]:
    return [root / name for name in CORE_FILES] + [
        path for folder in ('domain', 'unit_components', 'unit_orders')
        for path in sorted((root / folder).rglob('*.py'))
    ]


def violations(path: Path) -> list[str]:
    errors: list[str] = []

    class Imports(ast.NodeVisitor):
        def visit_If(self, node: ast.If) -> None:
            test = node.test
            if ((isinstance(test, ast.Name) and test.id == 'TYPE_CHECKING') or
                    (isinstance(test, ast.Attribute) and test.attr == 'TYPE_CHECKING')):
                for child in node.orelse:
                    self.visit(child)
            else:
                self.generic_visit(node)

        def check(self, module: str, line: int) -> None:
            if module.split('.')[0] in FORBIDDEN:
                errors.append(f'{path.name}:{line}: core imports {module}')

        def visit_Import(self, node: ast.Import) -> None:
            for alias in node.names:
                self.check(alias.name, node.lineno)

        def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
            if node.level == 0:
                self.check(node.module or '', node.lineno)

    Imports().visit(ast.parse(path.read_text(encoding='utf-8')))
    return errors


def main() -> int:
    errors = [error for path in core_paths() for error in violations(path)]
    if errors:
        print('\n'.join(errors))
        return 1
    print('Core import boundaries passed.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
