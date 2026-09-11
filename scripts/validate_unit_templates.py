"""Validate a custom design library without launching the game or modifying it."""
import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from unit_template_validation import parse_library, validate_library
from utils import user_data_path


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('path', nargs='?', type=Path,
                        help='JSON library (default: configured user-data library)')
    args = parser.parse_args(argv)
    try:
        path = (args.path if args.path is not None else
                user_data_path() / 'custom_unit_templates.json').resolve()
        print(f'Validating: {path}')
        raw = parse_library(path.read_bytes())
    except (OSError, ValueError) as exc:
        print(f'Error: {exc}', file=sys.stderr)
        return 2
    issues = validate_library(raw)
    for name, errors in issues.items():
        print(f'{name!r}:')
        for error in errors:
            print(f'  - {error}')
    count = len(raw) if isinstance(raw, dict) else 0
    invalid = len(issues) if isinstance(raw, dict) else 0
    print(f'{count} template(s) checked; {invalid} invalid; '
          f'{sum(map(len, issues.values()))} error(s).')
    return 1 if issues else 0


if __name__ == '__main__':
    raise SystemExit(main())
