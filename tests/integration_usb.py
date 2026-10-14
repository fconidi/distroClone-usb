#!/usr/bin/python3
"""Root-only integration test on a newly created disposable loop image.

Never shipped in the package. The production writer rejects loop devices. This
test supplies a device inventory restricted to the exact loop device it creates,
and checks its backing file before EVERY writer validation.
"""

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from distroclone_usb import writer
from distroclone_usb.devices import device_token
from distroclone_usb.iso import inspect_iso


def command(*args):
    return subprocess.check_output(args, text=True).strip()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--iso', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--debug-boot', action='store_true')
    args = parser.parse_args()
    if os.geteuid() != 0:
        parser.error('Run via sudo: this test uses only its own disposable loop device.')
    output = Path(args.output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    # O_EXCL is essential: never truncate an existing test or user image.
    image_fd = os.open(output, os.O_CREAT | os.O_EXCL | os.O_RDWR, 0o600)
    os.ftruncate(image_fd, 9 * 1024**3)
    os.close(image_fd)
    loop = command('/usr/sbin/losetup', '--find', '--show', '--partscan', str(output))
    if not loop.startswith('/dev/loop'):
        raise AssertionError('Unexpected loop device')
    info_path = Path('/sys/class/block') / Path(loop).name / 'loop/backing_file'
    mounted = False
    log = output.with_suffix('.writer.jsonl')

    def loop_inventory():
        actual = info_path.read_text().strip()
        if Path('/' + actual.lstrip('/')).resolve() != output:
            raise AssertionError('Loop backing file changed')
        data = json.loads(command('/usr/bin/lsblk', '--json', '--bytes', '--paths',
                                 '--output', 'NAME,TYPE,SIZE,MODEL,SERIAL,TRAN,RM,RO,MAJ:MIN,MOUNTPOINTS', loop))
        disk = data['blockdevices'][0]
        assert disk['name'] == loop and disk['type'] == 'loop'
        # Model only removable eligibility; every actual write uses the real loop node.
        disk.update(type='disk', tran='usb', rm=True)
        disk['diskseq'] = (Path('/sys/class/block') / Path(loop).name / 'diskseq').read_text().strip()
        return [disk]

    try:
        uid = int(os.environ.get('SUDO_UID', '0'))
        iso = inspect_iso(args.iso)
        token = device_token(loop_inventory()[0])
        with log.open('w') as stream:
            def emit(event, **data):
                record = {'event': event, **data}
                stream.write(json.dumps(record) + '\n')
                stream.flush()
                if event != 'progress' or data.get('fraction') in (0, 1):
                    print(json.dumps(record), flush=True)
            with patch.object(writer, 'inventory', loop_inventory):
                writer.create_usb(args.iso, loop, 2048, token, Path(loop).name, iso.sha256, uid, emit)
        mount = output.parent / (output.stem + '-check')
        mount.mkdir()
        command('/usr/bin/mount', '-o', 'nosuid,nodev,noexec', writer.partition_path(loop, 3), str(mount))
        mounted = True
        copied = mount / 'distroclone/live.iso'
        assert copied.stat().st_size == iso.size
        config = mount / 'boot/grub/grub.cfg'
        command('/usr/bin/grub-script-check', str(config))
        assert 'persistence-label=dc-p-' in config.read_text()
        if args.debug_boot:
            # Disposable TEST IMAGE ONLY: serial root shell for persistence probes.
            text = config.read_text().replace('set timeout=10', 'set timeout=1')
            text = text.replace('quiet', '')
            text = '\n'.join(line + ' console=ttyS0,115200 init=/bin/sh'
                             if line.strip().startswith('linux ') else line for line in text.splitlines())
            config.write_text(text + '\n')
        command('/usr/bin/umount', str(mount))
        mounted = False
        mount.rmdir()
        command('/usr/sbin/losetup', '--detach', loop)
        loop = None
        os.chown(output, uid, int(os.environ.get('SUDO_GID', '0')))
        os.chown(log, uid, int(os.environ.get('SUDO_GID', '0')))
        print('PASS: real partition/format/mount/copy/checksum/BIOS/UEFI/cleanup on disposable image')
    finally:
        if mounted:
            subprocess.run(['/usr/bin/umount', str(mount)], check=False)
        if loop:
            subprocess.run(['/usr/sbin/losetup', '--detach', loop], check=False)


if __name__ == '__main__':
    main()
