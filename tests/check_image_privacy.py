#!/usr/bin/python3
"""Read-only at-rest checks on disposable test images; uses no user secrets."""

import argparse
import json
from pathlib import Path
import subprocess


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--image', required=True)
    parser.add_argument('--mode', choices=('persistence', 'all'), required=True)
    args = parser.parse_args()
    path = Path(args.image).resolve()
    if '.test-artifacts' not in path.parts or not path.is_file():
        parser.error('Only an existing disposable .test-artifacts image may be used')
    table = json.loads(subprocess.check_output(['/usr/sbin/sfdisk', '--json', str(path)], text=True))['partitiontable']
    sectors = table.get('sectorsize', 512)
    with path.open('rb') as stream:
        for number in ((3, 4) if args.mode == 'all' else (4,)):
            stream.seek(table['partitions'][number - 1]['start'] * sectors)
            assert stream.read(6) == b'LUKS\xba\xbe', ('missing LUKS header', number)
        stream.seek(0)
        needles = (b'distroClone TEST USB 2026 only', b'DCUSB_HOST_SHARED_MARKER', b'persisted-20261013')
        previous = b''
        while chunk := stream.read(8 * 1024 * 1024):
            data = previous + chunk
            assert not any(value in data for value in needles), 'Plaintext test data found'
            previous = data[-128:]
    print('PASS:', args.mode, 'LUKS headers; test phrase and private markers absent from entire raw image')


if __name__ == '__main__':
    main()
