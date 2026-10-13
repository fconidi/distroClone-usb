"""Runs only inside the disposable QEMU guest, on its one USB disk."""

import os
import json
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, '/usr/lib/distroclone-usb')
from distroclone_usb.devices import device_token, eligible_disks, inventory
from distroclone_usb.crypto import encryption_modules

TEST_PASSPHRASE = 'distroClone TEST USB 2026 only'
mode = os.environ.get('DCUSB_TEST_MODE', 'none')

disks = eligible_disks(inventory())
assert len(disks) == 1, disks
disk = disks[0]
assert disk['tran'] == 'usb' and disk['size'] == 9 * 1024**3, disk
iso = next(Path('/iso').glob('*.iso'))
expected = json.loads(Path('/app/.test-artifacts/iso-input.json').read_text())
print('DCUSB_START_WRITER', flush=True)
subprocess.run(['/usr/lib/distroclone-usb/helper.py', '--iso', str(iso), '--device', disk['name'],
                '--persistence-mib', '2048', '--expected-id', device_token(disk),
                '--confirm', Path(disk['name']).name, '--sha256', expected['sha256'], '--encrypt-mode', mode],
               input=(json.dumps({'password': TEST_PASSPHRASE}).encode()+b'\n') if mode != 'none' else None,
               env={**os.environ, 'PKEXEC_UID': '1000'}, check=True)
mapped = {}
for number, role in ((3, 'data'), (4, 'persist')):
    raw = disk['name'] + str(number)
    if (number == 3 and mode == 'all') or (number == 4 and mode != 'none'):
        wrong = subprocess.run(['cryptsetup', 'open', '--key-file=-', raw, 'test-wrong'],
                               input=b'WRONG TEST PASSWORD', capture_output=True)
        assert wrong.returncode != 0
        name = 'dcusb-test-' + role
        subprocess.run(['cryptsetup', 'open', '--key-file=-', raw, name],
                       input=TEST_PASSPHRASE.encode(), check=True)
        mapped[number] = '/dev/mapper/' + name
        print('DCUSB_LUKS_REJECTION_PASS', number, flush=True)
    else:
        mapped[number] = raw
# Boot actual systemd, with a test-only root console after the shared service.
subprocess.run(['mount', mapped[3], '/mnt'], check=True)
config = Path('/mnt/boot/grub/grub.cfg')
text = config.read_text().replace('set timeout=10', 'set timeout=1').replace('quiet', '')
serial = 'serial --unit=0 --speed=115200\nterminal_input serial\nterminal_output serial\n'
text = serial + '\n'.join(line + ' console=ttyS0,115200 systemd.unit=multi-user.target'
                 if line.strip().startswith('linux ') else line for line in text.splitlines())
config.write_text(text + '\n')
if mode == 'all':
    Path('/efi').mkdir(exist_ok=True)
    subprocess.run(['mount', disk['name']+'2', '/efi'], check=True)
    Path('/efi/boot/grub/grub.cfg').write_text(text+'\n')
    early = Path('/mnt/distroclone/early.cfg')
    early.write_text(serial + early.read_text())
    subprocess.run(['grub-mkstandalone', '--format=x86_64-efi', '--locales=', '--fonts=',
                    '--modules=serial terminal part_gpt fat ext2 iso9660 loopback normal linux search search_label configfile '+encryption_modules(mode),
                    '--output=/efi/EFI/BOOT/BOOTX64.EFI', 'boot/grub/grub.cfg='+str(early)], check=True)
    subprocess.run(['umount', '/efi'], check=True)
subprocess.run(['umount', '/mnt'], check=True)
subprocess.run(['mount', mapped[4], '/mnt'], check=True)
Path('/mnt/Shared/from-host.deb').write_text('DCUSB_HOST_SHARED_MARKER')
os.chown('/mnt/Shared/from-host.deb',1000,1000)
from guest_probe_setup import configure_probe
configure_probe('/mnt')
subprocess.run(['umount','/mnt'],check=True)
for number in (4,3):
    if mapped[number].startswith('/dev/mapper/'):
        subprocess.run(['cryptsetup','close',mapped[number]],check=True)
print('DCUSB_GUEST_CREATE_PASS', flush=True)
