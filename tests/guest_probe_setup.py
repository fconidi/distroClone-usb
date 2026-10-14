"""Install an automatic probe only on disposable QEMU USBs, never host devices."""

import os
from pathlib import Path
import subprocess
import sys


def configure_probe(persistence):
    overlay = Path(persistence) / 'rw'
    scripts = overlay / 'usr/local/sbin'
    scripts.mkdir(parents=True, exist_ok=True)
    script = scripts / 'dcusb-test-probe'
    script.write_text('''#!/bin/sh
set -eu
systemctl is-active distroclone-usb-shared.service
findmnt /Shared
test "$(cat /Shared/from-host.deb)" = DCUSB_HOST_SHARED_MARKER
test -L /home/admin/Shared
if [ -f /var/lib/distroclone-usb-probe ]; then
    test "$(cat /var/lib/distroclone-usb-probe)" = persisted-20261013
    test -f /Shared/live-write
    result=PERSIST_OK
else
    printf persisted-20261013 > /var/lib/distroclone-usb-probe
    result=WRITE_OK
fi
runuser -u admin -- sh -c 'test -r /Shared/from-host.deb && touch /Shared/live-write'
printf 'DCUSB_%s\\n' SHARED_OK
printf 'DCUSB_%s\\n' "$result"
cat /proc/mounts
sync
echo b > /proc/sysrq-trigger
''')
    script.chmod(0o755)
    service = overlay / 'etc/systemd/system/distroclone-usb-test-console.service'
    service.write_text('''[Unit]
Description=Disposable automatic USB probe
After=distroclone-usb-shared.service
Wants=distroclone-usb-shared.service
[Service]
Type=oneshot
ExecStart=/bin/sh /usr/local/sbin/dcusb-test-probe
StandardInput=null
StandardOutput=tty
StandardError=tty
TTYPath=/dev/ttyS0
[Install]
WantedBy=multi-user.target
''')
    link = service.parent / 'multi-user.target.wants' / service.name
    if not link.is_symlink():
        link.symlink_to('/etc/systemd/system/' + service.name)


def main():
    sys.path.insert(0, '/usr/lib/distroclone-usb')
    from distroclone_usb.devices import eligible_disks, inventory
    disks = eligible_disks(inventory())
    assert len(disks) == 1 and disks[0]['tran'] == 'usb' and disks[0]['size'] == 9 * 1024**3
    raw = disks[0]['name'] + '4'
    encrypted = subprocess.check_output(['blkid', '-s', 'TYPE', '-o', 'value', raw], text=True).strip() == 'crypto_LUKS'
    target = raw
    if encrypted:
        subprocess.run(['cryptsetup', 'open', '--key-file=-', raw, 'dcusb-test-setup'],
                       input=b'distroClone TEST USB 2026 only', check=True)
        target = '/dev/mapper/dcusb-test-setup'
    subprocess.run(['mount', target, '/mnt'], check=True)
    configure_probe('/mnt')
    subprocess.run(['umount', '/mnt'], check=True)
    if encrypted:
        subprocess.run(['cryptsetup', 'close', 'dcusb-test-setup'], check=True)
    print('DCUSB_GUEST_PROBE_SETUP_PASS', flush=True)


if __name__ == '__main__':
    main()
