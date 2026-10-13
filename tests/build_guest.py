#!/usr/bin/python3
"""Build an isolated root test environment without requiring host root access."""

import argparse
import gzip
import os
from pathlib import Path
import re
import shutil
import subprocess


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', required=True)
    parser.add_argument('--kernel-version', default='6.12.111+deb13-rt-amd64')
    parser.add_argument('--mode', choices=('none', 'persistence', 'all'), default='none')
    parser.add_argument('--task', choices=('create', 'probe_setup'), default='create')
    args = parser.parse_args()
    output = Path(args.output).resolve()
    root = output / 'root'
    root.mkdir(parents=True, exist_ok=False)
    for directory in ('usr/bin', 'usr/sbin', 'usr/lib', 'usr/lib64', 'proc', 'sys', 'dev',
                      'tmp', 'run/lock', 'etc', 'root', 'app', 'iso', 'mnt'):
        (root / directory).mkdir(parents=True, exist_ok=True)
    for name, target in [('bin', 'usr/bin'), ('sbin', 'usr/sbin'), ('lib', 'usr/lib'),
                         ('lib64', 'usr/lib64')]:
        (root / name).symlink_to(target)
    copied = set()
    def copy_binary(source):
        source = str(source)
        if source in copied:
            return
        copied.add(source)
        dest = root / source.lstrip('/')
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, dest)
        result = subprocess.run(['/usr/bin/ldd', source], capture_output=True, text=True)
        for dependency in re.findall(r'(/[^\s()]+)', result.stdout):
            if Path(dependency).is_file():
                copy_binary(dependency)
    tools = ['busybox', 'python3', 'lsblk', 'sfdisk', 'blockdev', 'udevadm', 'mkfs.vfat',
             'mkfs.ext4', 'mount', 'umount', 'grub-install', 'grub-mkstandalone',
             'grub-probe', 'grub-mkimage', 'grub-mkrelpath',
             'xorriso', 'modprobe', 'blkid', 'cryptsetup', 'dmsetup', 'lsinitramfs',
             'unmkinitramfs', 'getopt', 'cpio', 'gzip', 'zstd', 'xz']
    for tool in tools:
        binary = shutil.which(tool, path='/usr/sbin:/usr/bin:/sbin:/bin')
        if not binary:
            raise RuntimeError('Missing tool: ' + tool)
        copy_binary(binary)
    shutil.copytree('/usr/lib/python3.13', root / 'usr/lib/python3.13',
                    ignore=shutil.ignore_patterns('__pycache__', 'test', 'tests'))
    for binary in (root / 'usr/lib/python3.13/lib-dynload').glob('*.so'):
        copy_binary('/usr/lib/python3.13/lib-dynload/' + binary.name)
    shutil.copytree('/usr/lib/grub', root / 'usr/lib/grub')
    for applet in ('sh', 'mkdir', 'sleep', 'cp', 'sync', 'poweroff', 'cat', 'echo', 'ln'):
        dest = root / 'usr/bin' / applet
        if not dest.exists():
            dest.symlink_to('busybox')
    kernel = args.kernel_version
    modules = ['9p', '9pnet_virtio', 'virtio_blk', 'xhci_pci', 'usb_storage',
               'sd_mod', 'ext4', 'vfat', 'nls_cp437', 'nls_ascii', 'loop',
               'dm_crypt', 'aesni_intel', 'xts']
    for module in modules:
        result = subprocess.check_output(['/usr/sbin/modprobe', '--show-depends', '-S', kernel, module], text=True)
        for source in re.findall(r'^insmod (\S+)', result, re.M):
            dest = root / source.lstrip('/')
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, dest)
    target_modules = root / 'lib/modules' / kernel
    for source in (Path('/lib/modules') / kernel).glob('modules.*'):
        shutil.copy2(source, target_modules / source.name)
    (root / 'etc/passwd').write_text('root:x:0:0:root:/root:/bin/sh\ntester:x:1000:1000:tester:/tmp:/bin/sh\n')
    (root / 'etc/group').write_text('root:x:0:\ntester:x:1000:\n')
    (root / 'etc/nsswitch.conf').write_text('passwd: files\ngroup: files\n')
    (root / 'etc/fstab').write_text('')
    (root / 'etc/mtab').symlink_to('/proc/self/mounts')
    init = '''#!/bin/sh
set -eu
export PATH=/usr/sbin:/usr/bin:/sbin:/bin
mount -t devtmpfs devtmpfs /dev
exec </dev/console >/dev/console 2>&1
mount -t proc proc /proc
mount -t sysfs sysfs /sys
modprobe 9pnet_virtio
modprobe 9p
modprobe xhci_pci
modprobe usb_storage
modprobe sd_mod
modprobe virtio_blk
modprobe ext4
modprobe vfat
modprobe nls_cp437
modprobe nls_ascii
modprobe dm_crypt
modprobe aesni_intel
modprobe xts
mount -t 9p -o trans=virtio,version=9p2000.L,msize=1048576,cache=loose,ro app /app
mount -t ext4 -o ro /dev/vda /iso
sleep 3
mkdir -p /usr/lib/distroclone-usb
cp -r /app/distroclone_usb /usr/lib/distroclone-usb/
cp /app/helper.py /usr/lib/distroclone-usb/
echo DCUSB_GUEST_READY
export DCUSB_TEST_MODE=@MODE@
python3 /app/tests/guest_@TASK@.py
sync
poweroff -f
'''
    (root / 'init').write_text(init.replace('@MODE@', args.mode).replace('@TASK@', args.task))
    (root / 'init').chmod(0o755)
    paths = [b'.'] + [os.fsencode(str(p.relative_to(root))) for p in root.rglob('*')]
    result = subprocess.run(['/usr/bin/cpio', '--null', '-o', '--format=newc', '--owner=0:0'],
                            input=b'\0'.join(paths) + b'\0', cwd=root, capture_output=True, check=True)
    with gzip.open(output / 'guest-initrd.gz', 'wb', compresslevel=1) as stream:
        stream.write(result.stdout)
    print('Built', output / 'guest-initrd.gz')


if __name__ == '__main__':
    main()
