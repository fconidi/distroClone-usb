"""Privileged operations. No physical target is accepted without fresh validation."""

from contextlib import contextmanager
import fcntl
import hashlib
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import tempfile
import time
import uuid

from .devices import device_token, inventory, source_device, validate_target, walk
from .iso import digest_fd, inspect_fd, open_iso
from .layout import make_layout
from .profiles import grub_config

SYSTEM_PATH = '/usr/sbin:/usr/bin:/sbin:/bin'
TOOLS = ('lsblk', 'sfdisk', 'blockdev', 'udevadm', 'mkfs.vfat', 'mkfs.ext4',
         'mount', 'umount', 'grub-install', 'grub-mkstandalone', 'xorriso')


class Runner:
    def __init__(self, emit):
        self.emit = emit

    def run(self, command, *args, input=None):
        binary = shutil.which(command, path=SYSTEM_PATH)
        if not binary:
            raise RuntimeError(f'Comando mancante: {command}')
        self.emit('log', message=' '.join([command, *map(str, args)]))
        result = subprocess.run([binary, *map(str, args)], input=input,
                                text=True, capture_output=True,
                                env={'PATH': SYSTEM_PATH, 'LC_ALL': 'C', 'HOME': '/root'},
                                timeout=600, check=False)
        if result.returncode:
            raise RuntimeError(f'{command}: {result.stderr[-2000:] or result.stdout[-2000:]}')
        return result.stdout.strip()


def check_dependencies():
    missing = [cmd for cmd in TOOLS if not shutil.which(cmd, path=SYSTEM_PATH)]
    for target in ('i386-pc', 'x86_64-efi'):
        if not Path(f'/usr/lib/grub/{target}/modinfo.sh').is_file():
            missing.append('grub-' + target)
    if missing:
        raise RuntimeError('Dipendenze mancanti: ' + ', '.join(missing))


def partition_path(device, number):
    return f'{device}{"p" if device[-1].isdigit() else ""}{number}'


def copy_verified(fd, destination, expected, emit):
    os.lseek(fd, 0, os.SEEK_SET)
    total, done, last_percent = os.fstat(fd).st_size, 0, -1
    output = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o644)
    digest = hashlib.sha256()
    with os.fdopen(output, 'wb') as stream:
        while chunk := os.read(fd, 4 * 1024 * 1024):
            stream.write(chunk)
            digest.update(chunk)
            done += len(chunk)
            percent = int(done * 100 / total)
            if percent != last_percent:
                emit('progress', phase='copy', fraction=done / total)
                last_percent = percent
        stream.flush()
        os.fsync(stream.fileno())
    if digest.hexdigest() != expected or done != total:
        raise ValueError('La ISO sorgente è cambiata durante la copia. USB incompleta.')
    emit('progress', phase='verify', fraction=0)
    verify_fd = os.open(destination, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        if digest_fd(verify_fd, lambda done, size: emit(
                'progress', phase='verify', fraction=done / size)) != expected:
            raise ValueError('Verifica SHA-256 della copia USB fallita.')
    finally:
        os.close(verify_fd)


@contextmanager
def mount_volumes(device, folder, runner):
    mounted, cleanup_errors = [], []
    try:
        for number, name in ((2, 'efi'), (3, 'data'), (4, 'persist')):
            path = folder / name
            path.mkdir(mode=0o700)
            runner.run('mount', '-o', 'nosuid,nodev,noexec', partition_path(device, number), str(path))
            mounted.append(path)
        yield {name: folder / name for name in ('efi', 'data', 'persist')}
    finally:
        for path in reversed(mounted):
            try:
                runner.run('umount', str(path))
            except (RuntimeError, subprocess.SubprocessError) as error:
                cleanup_errors.append(str(error))
        if cleanup_errors:
            raise RuntimeError('Impossibile smontare tutti i volumi: ' + '; '.join(cleanup_errors))


def assert_same_device(device, expected):
    disk = next((d for d in inventory() if d['name'] == device), None)
    if disk is None or device_token(disk) != expected:
        raise ValueError('Il dispositivo USB è stato scollegato o sostituito.')
    info = os.stat(device, follow_symlinks=False)
    if not stat.S_ISBLK(info.st_mode):
        raise ValueError('Il dispositivo deve essere un nodo a blocchi reale, senza collegamenti.')
    if f'{os.major(info.st_rdev)}:{os.minor(info.st_rdev)}' != disk['maj:min']:
        raise ValueError('Identità del nodo a blocchi cambiata.')
    return disk


def fresh_target(device, expected, confirmation, fd):
    disk = assert_same_device(device, expected)
    validate_target([disk], device, expected, confirmation, source_device(fd))
    for node in walk(disk):
        holders = Path('/sys/class/block') / Path(node['name']).name / 'holders'
        if holders.exists() and any(holders.iterdir()):
            raise ValueError('Il disco contiene volumi ancora in uso.')
    return disk


def install_boot(profile, paths, data_label, persistence_label, runner):
    boot = paths['data'] / 'boot/grub'
    boot.mkdir(parents=True)
    (boot / 'grub.cfg').write_text(grub_config(profile, data_label, persistence_label))
    if profile.family == 'debian':
        (paths['persist'] / 'persistence.conf').write_text('/ union\n')
    early = paths['data'] / 'distroclone/early.cfg'
    early.write_text(f'search --no-floppy --label --set=root {data_label}\n'
                     'set prefix=($root)/boot/grub\nconfigfile $prefix/grub.cfg\n')
    efi = paths['efi'] / 'EFI/BOOT'
    efi.mkdir(parents=True)
    runner.run('grub-mkstandalone', '--format=x86_64-efi', '--locales=', '--fonts=',
               '--modules=part_gpt fat ext2 iso9660 loopback normal linux search search_label configfile',
               '--output=' + str(efi / 'BOOTX64.EFI'), 'boot/grub/grub.cfg=' + str(early))


def create_usb(iso, device, persistence_mib, expected, confirmation, sha256, uid, emit):
    if os.geteuid() != 0:
        raise PermissionError('La creazione USB richiede autorizzazione amministrativa.')
    if not re.fullmatch(r'[a-f0-9]{64}', sha256):
        raise ValueError('Digest ISO non valido.')
    check_dependencies()
    runner = Runner(emit)
    fd = open_iso(iso, uid)
    lock_fd, folder = None, None
    try:
        disk = fresh_target(device, expected, confirmation, fd)
        lock_path = '/run/lock/distroclone-usb-' + disk['maj:min'].replace(':', '-')
        lock_fd = os.open(lock_path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
        lock_info = os.fstat(lock_fd)
        if lock_info.st_uid != 0 or not stat.S_ISREG(lock_info.st_mode) or lock_info.st_nlink != 1:
            raise ValueError('File di blocco non valido.')
        fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        emit('progress', phase='inspect', fraction=0)
        image = inspect_fd(fd, iso, uid, lambda done, size: emit(
            'progress', phase='inspect', fraction=done / size))
        if image.sha256 != sha256:
            raise ValueError('La ISO è cambiata dopo la selezione. Nessuna scrittura eseguita.')
        sector_size = int(runner.run('blockdev', '--getss', device))
        layout = make_layout(disk['size'], image.size, persistence_mib, sector_size)
        folder = Path(tempfile.mkdtemp(prefix='distroclone-usb-'))
        token = uuid.uuid4().hex[:8]
        data_label = 'dcusb-' + token
        persistence_label = ('dc-p-' + token if image.profile.family == 'debian'
                             else image.profile.persistence_label)
        fresh_target(device, expected, confirmation, fd)
        emit('progress', phase='partition', fraction=0)
        runner.run('sfdisk', '--wipe', 'always', '--wipe-partitions', 'always',
                   device, input=layout.sfdisk())
        runner.run('udevadm', 'settle', '--timeout=10')
        deadline = time.monotonic() + 10
        while not all(Path(partition_path(device, n)).exists() for n in (1, 2, 3, 4)):
            if time.monotonic() > deadline:
                raise RuntimeError('Le nuove partizioni USB non sono disponibili.')
            time.sleep(.2)
        for number, label, filesystem in ((2, 'DCUSB-EFI', 'vfat'),
                                           (3, data_label, 'ext4'), (4, persistence_label, 'ext4')):
            fresh_target(device, expected, confirmation, fd)
            target = partition_path(device, number)
            if filesystem == 'vfat':
                runner.run('mkfs.vfat', '-F', '32', '-n', label, target)
            else:
                # Disable orphan_file for live kernels predating ext4 feature support.
                runner.run('mkfs.ext4', '-F', '-m', '0', '-O', '^orphan_file', '-L', label, target)
        fresh_target(device, expected, confirmation, fd)
        with mount_volumes(device, folder, runner) as paths:
            (paths['data'] / 'distroclone').mkdir()
            copy_verified(fd, paths['data'] / 'distroclone/live.iso', sha256, emit)
            emit('progress', phase='boot', fraction=0)
            install_boot(image.profile, paths, data_label, persistence_label, runner)
            assert_same_device(device, expected)
            runner.run('grub-install', '--target=i386-pc', '--no-floppy', '--recheck',
                       '--boot-directory=' + str(paths['data'] / 'boot'), device)
        emit('done', message='USB creata e verificata. Volumi smontati.', sha256=sha256)
    finally:
        os.close(fd)
        if lock_fd is not None:
            os.close(lock_fd)
        if folder and not any(os.path.ismount(folder / name) for name in ('efi', 'data', 'persist')):
            shutil.rmtree(folder)
