"""Runs only inside the disposable QEMU guest, on its one USB disk."""

import os
import json
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, '/usr/lib/distroclone-usb')
from distroclone_usb.devices import device_token, eligible_disks, inventory
from distroclone_usb.crypto import encryption_modules

quick_probe = os.environ.get('DCUSB_TEST_QUICK_CANCEL_PROBE') == '1'
TEST_PASSPHRASE = 'Abcd1234Efgh' if quick_probe else 'distroClone TEST USB 2026 only'
mode = os.environ.get('DCUSB_TEST_MODE', 'none')

disks = eligible_disks(inventory())
assert len(disks) == 1, disks
disk = disks[0]
assert disk['tran'] == 'usb' and disk['size'] == 9 * 1024**3, disk
iso = next(Path('/iso').glob('*.iso'))
expected = json.loads(Path('/app/.test-artifacts/iso-input.json').read_text())
print('DCUSB_START_WRITER', flush=True)
command = ['/usr/lib/distroclone-usb/helper.py', '--iso', str(iso), '--device', disk['name'],
           '--persistence-mib', '2048', '--expected-id', device_token(disk),
           '--confirm', Path(disk['name']).name, '--sha256', expected['sha256'], '--encrypt-mode', mode]
secret_input = (json.dumps({'password': TEST_PASSPHRASE}).encode()+b'\n') if mode != 'none' else b''
if quick_probe:
    marker = b'DCUSB_QUICK_REUSE_SENTINEL'
    raw_fd = os.open(disk['name'], os.O_RDWR | os.O_NOFOLLOW)
    os.pwrite(raw_fd, marker, 512 * 1024)
    os.fsync(raw_fd)
    os.close(raw_fd)
    for cancel in (True, False):
        process = subprocess.Popen(command+['--control-stdin'], stdin=subprocess.PIPE,
                                   stdout=subprocess.PIPE, env={**os.environ, 'PKEXEC_UID':'1000'})
        process.stdin.write(secret_input)
        process.stdin.flush()
        requested, cancelled, completed = False, False, False
        for line in process.stdout:
            sys.stdout.buffer.write(line)
            sys.stdout.flush()
            event = json.loads(line)
            assert event.get('phase') != 'erase', 'Unexpected whole-device wipe'
            if cancel and not requested and event.get('phase') == 'copy':
                process.stdin.write(b'cancel\n')
                process.stdin.flush()
                requested = True
            cancelled = cancelled or event.get('event') == 'cancelled'
            completed = completed or event.get('event') == 'done'
        code = process.wait(timeout=10)
        process.stdin.close()
        process.stdout.close()
        if cancel:
            assert requested and cancelled and code == 2, (requested,cancelled,code)
            assert not any('distroclone-usb-' in line for line in Path('/proc/mounts').read_text().splitlines())
            assert 'No devices found' in subprocess.check_output(['dmsetup','ls'],text=True)
            print('DCUSB_CANCEL_CLEANUP_PASS', flush=True)
        else:
            assert completed and code == 0, code
    raw_fd = os.open(disk['name'], os.O_RDONLY)
    assert os.pread(raw_fd,len(marker),512*1024)==marker, 'Whole-device clearing was performed'
    os.close(raw_fd)
    print('DCUSB_QUICK_FORMAT_12_CHAR_PASS',flush=True)
else:
    subprocess.run(command, input=secret_input if mode != 'none' else None,
                   env={**os.environ, 'PKEXEC_UID':'1000'}, check=True)
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
