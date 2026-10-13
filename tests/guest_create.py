"""Runs only inside the disposable QEMU guest, on its one USB disk."""

import os
import json
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, '/usr/lib/distroclone-usb')
from distroclone_usb.devices import device_token, eligible_disks, inventory
from distroclone_usb.iso import inspect_iso

disks = eligible_disks(inventory())
assert len(disks) == 1, disks
disk = disks[0]
assert disk['tran'] == 'usb' and disk['size'] == 9 * 1024**3, disk
iso = next(Path('/iso').glob('*.iso'))
expected = json.loads(Path('/app/.test-artifacts/iso-input.json').read_text())
print('DCUSB_START_WRITER', flush=True)
subprocess.run(['/usr/lib/distroclone-usb/helper.py', '--iso', str(iso), '--device', disk['name'],
                '--persistence-mib', '2048', '--expected-id', device_token(disk),
                '--confirm', Path(disk['name']).name, '--sha256', expected['sha256']],
               env={**os.environ, 'PKEXEC_UID': '1000'}, check=True)
# Enable serial root shell in this disposable test image only.
subprocess.run(['mount', disk['name'] + '3', '/mnt'], check=True)
config = Path('/mnt/boot/grub/grub.cfg')
text = config.read_text().replace('set timeout=10', 'set timeout=1').replace('quiet', '')
text = '\n'.join(line + ' console=ttyS0,115200 init=/bin/sh'
                 if line.strip().startswith('linux ') else line for line in text.splitlines())
config.write_text(text + '\n')
subprocess.run(['umount', '/mnt'], check=True)
print('DCUSB_GUEST_CREATE_PASS', flush=True)
