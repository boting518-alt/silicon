"""Run checked-in migrations from a clean temporary copy, preserving source metadata."""
import argparse
from pathlib import Path
import shutil
import tempfile

from alembic import command
from alembic.config import Config


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('command', choices=['upgrade', 'downgrade', 'current', 'heads', 'history'])
    parser.add_argument('revision', nargs='?')
    args = parser.parse_args()
    if args.command in {'upgrade', 'downgrade'} and not args.revision:
        parser.error('upgrade/downgrade require a revision')
    root = Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory(prefix='silicon-migrations-') as temporary:
        scripts = Path(temporary) / 'migrations'
        shutil.copytree(root / 'apps/api/migrations', scripts,
                        ignore=shutil.ignore_patterns('._*', '__pycache__'))
        config = Config(str(root / 'alembic.ini'))
        config.set_main_option('script_location', str(scripts))
        operation = getattr(command, args.command)
        if args.command in {'upgrade', 'downgrade'}:
            operation(config, args.revision)
        else:
            operation(config)


if __name__ == '__main__':
    main()
