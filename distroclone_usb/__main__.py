import argparse
import json
import os
from pathlib import Path
import sys

from . import __version__
from .devices import device_token, eligible_disks, inventory, mounts, validate_target
from .iso import inspect_iso
from .layout import make_layout
from .writer import check_dependencies


def main():
    parser = argparse.ArgumentParser(description='distroClone USB — persistent live USB creator')
    parser.add_argument('--version', action='version', version=__version__)
    actions = parser.add_mutually_exclusive_group()
    actions.add_argument('--inspect', metavar='ISO', help='Inspect ISO and print JSON; read-only')
    actions.add_argument('--list-devices', action='store_true', help='List USB/removable disks; read-only')
    actions.add_argument('--plan', metavar='ISO', help='Validate and print a creation plan; read-only')
    actions.add_argument('--check-dependencies', action='store_true')
    parser.add_argument('--device', help='Whole USB device, for --plan')
    parser.add_argument('--persistence-mib', type=int, default=4096)
    args = parser.parse_args()
    try:
        if args.inspect:
            print(json.dumps(inspect_iso(args.inspect).to_dict(), indent=2))
        elif args.list_devices:
            print(json.dumps([dict(d, identity=device_token(d), mounted=mounts(d))
                              for d in eligible_disks(inventory())], indent=2))
        elif args.plan:
            if not args.device:
                parser.error('--plan requires --device')
            image = inspect_iso(args.plan)
            disk = next((d for d in inventory() if d['name'] == args.device), None)
            if not disk:
                raise ValueError('Dispositivo non trovato.')
            source = os.stat(args.plan).st_dev
            validate_target([disk], args.device, device_token(disk), Path(args.device).name,
                            f'{os.major(source)}:{os.minor(source)}')
            layout = make_layout(disk['size'], image.size, args.persistence_mib, disk['sector_size'])
            print(json.dumps({'iso': image.to_dict(), 'device': disk,
                              'expected_id': device_token(disk), 'layout': layout.to_dict()}, indent=2))
        elif args.check_dependencies:
            check_dependencies()
            print('Dependencies OK')
        else:
            from .gui import run
            return run()
    except Exception as error:
        print(str(error), file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
