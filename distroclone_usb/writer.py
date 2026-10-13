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

from .i18n import tr
from .devices import device_token, inventory, mounts, source_device, validate_target, walk
from .crypto import CryptoVolumes, clear_logical_sectors, encryption_modules, unlock_search, validate_encryption
from .encrypted_boot import check_initrd_capabilities, write_supplemental_initrd
from .iso import digest_fd, inspect_fd, open_iso
from .layout import make_layout
from .profiles import grub_config
from .shared import prepare_shared

SYSTEM_PATH = '/usr/sbin:/usr/bin:/sbin:/bin'
TOOLS = ('lsblk', 'sfdisk', 'blkid', 'blockdev', 'udevadm', 'mkfs.vfat', 'mkfs.ext4',
         'mount', 'umount', 'grub-install', 'grub-mkstandalone', 'xorriso')


class Runner:
    def __init__(self, emit):
        self.emit = emit

    def run(self, command, *args, input=None, input_secret=None):
        binary = shutil.which(command, path=SYSTEM_PATH)
        if not binary:
            raise RuntimeError(tr('Command not found: {command}').format(command=command))
        self.emit('log', message=' '.join([command, *map(str, args)]))
        if input is not None and input_secret is not None:
            raise ValueError('Conflicting command input')
        result = subprocess.run([binary, *map(str, args)],
                                input=bytes(input_secret) if input_secret is not None else input,
                                text=input_secret is None, capture_output=True,
                                env={'PATH': SYSTEM_PATH, 'LC_ALL': 'C', 'HOME': '/root'},
                                timeout=600, check=False)
        stdout = result.stdout.decode(errors='replace') if isinstance(result.stdout, bytes) else result.stdout
        stderr = result.stderr.decode(errors='replace') if isinstance(result.stderr, bytes) else result.stderr
        if result.returncode:
            raise RuntimeError(f'{command}: {stderr[-2000:] or stdout[-2000:]}')
        return stdout.strip()


def check_dependencies(mode='none'):
    required = TOOLS + (('cryptsetup', 'lsinitramfs') if mode != 'none' else ())
    missing = [cmd for cmd in required if not shutil.which(cmd, path=SYSTEM_PATH)]
    for target in ('i386-pc', 'x86_64-efi'):
        if not Path(f'/usr/lib/grub/{target}/modinfo.sh').is_file():
            missing.append('grub-' + target)
    if missing:
        raise RuntimeError(tr('Missing dependencies: {items}').format(items=', '.join(missing)))


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
        raise ValueError(tr('The source ISO changed during copying. USB incomplete.'))
    emit('progress', phase='verify', fraction=0)
    verify_fd = os.open(destination, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        if digest_fd(verify_fd, lambda done, size: emit(
                'progress', phase='verify', fraction=done / size)) != expected:
            raise ValueError(tr('USB copy SHA-256 verification failed.'))
    finally:
        os.close(verify_fd)


@contextmanager
def mount_volumes(device, folder, runner, mapped=None):
    mounted, cleanup_errors = [], []
    try:
        for number, name in ((2, 'efi'), (3, 'data'), (4, 'persist')):
            path = folder / name
            path.mkdir(mode=0o700)
            target = mapped[number] if mapped else partition_path(device, number)
            runner.run('mount', '-o', 'nosuid,nodev,noexec', target, str(path))
            mounted.append(path)
        yield {name: folder / name for name in ('efi', 'data', 'persist')}
    finally:
        for path in reversed(mounted):
            try:
                runner.run('umount', str(path))
            except (RuntimeError, subprocess.SubprocessError) as error:
                cleanup_errors.append(str(error))
        if cleanup_errors:
            raise RuntimeError(tr('Unable to unmount all volumes: {details}').format(details='; '.join(cleanup_errors)))


def assert_same_device(device, expected):
    disk = next((d for d in inventory() if d['name'] == device), None)
    if disk is None or device_token(disk) != expected:
        raise ValueError(tr('The USB device was disconnected or replaced.'))
    info = os.stat(device, follow_symlinks=False)
    if not stat.S_ISBLK(info.st_mode):
        raise ValueError(tr('The device must be a real block node, without symbolic links.'))
    if f'{os.major(info.st_rdev)}:{os.minor(info.st_rdev)}' != disk['maj:min']:
        raise ValueError(tr('Block device node identity changed.'))
    return disk


def fresh_target(device, expected, confirmation, fd):
    disk = assert_same_device(device, expected)
    validate_target([disk], device, expected, confirmation, source_device(fd))
    for node in walk(disk):
        holders = Path('/sys/class/block') / Path(node['name']).name / 'holders'
        if holders.exists() and any(holders.iterdir()):
            raise ValueError(tr('The disk still contains volumes in use.'))
    return disk


def install_boot(profile, paths, data_label, persistence_label, runner,
                 mode='none', data_uuid=None, persist_uuid=None):
    boot = paths['data'] / 'boot/grub'
    boot.mkdir(parents=True)
    config = grub_config(profile, data_label, persistence_label, mode, data_uuid, persist_uuid)
    (boot / 'grub.cfg').write_text(config)
    if mode == 'all':
        plain_boot = paths['efi'] / 'boot/grub'
        plain_boot.mkdir(parents=True)
        (plain_boot / 'grub.cfg').write_text(config)
    if profile.family == 'debian':
        (paths['persist'] / 'persistence.conf').write_text('/ union\n')
    early = paths['data'] / 'distroclone/early.cfg'
    early.write_text('\n'.join(unlock_search(data_label, data_uuid if mode == 'all' else None))
                     + '\nconfigfile ($root)/boot/grub/grub.cfg\n')
    efi = paths['efi'] / 'EFI/BOOT'
    efi.mkdir(parents=True)
    runner.run('grub-mkstandalone', '--format=x86_64-efi', '--locales=', '--fonts=',
               '--modules=part_gpt fat ext2 iso9660 loopback normal linux search search_label configfile '
               + encryption_modules(mode),
               '--output=' + str(efi / 'BOOTX64.EFI'), 'boot/grub/grub.cfg=' + str(early))


def create_usb(iso, device, persistence_mib, expected, confirmation, sha256, uid, emit,
               mode='none', password=None):
    if os.geteuid() != 0:
        raise PermissionError(tr('Creating a USB requires administrative authorization.'))
    if not re.fullmatch(r'[a-f0-9]{64}', sha256):
        raise ValueError(tr('Invalid ISO digest.'))
    check_dependencies(mode)
    runner = Runner(emit)
    fd = open_iso(iso, uid)
    lock_fd, folder = None, None
    try:
        disk = fresh_target(device, expected, confirmation, fd)
        lock_path = '/run/lock/distroclone-usb-' + disk['maj:min'].replace(':', '-')
        lock_fd = os.open(lock_path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
        lock_info = os.fstat(lock_fd)
        if lock_info.st_uid != 0 or not stat.S_ISREG(lock_info.st_mode) or lock_info.st_nlink != 1:
            raise ValueError(tr('Invalid lock file.'))
        fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        emit('progress', phase='inspect', fraction=0)
        image = inspect_fd(fd, iso, uid, lambda done, size: emit(
            'progress', phase='inspect', fraction=done / size))
        if image.sha256 != sha256:
            raise ValueError(tr('The ISO changed after selection. No data was written.'))
        validate_encryption(image.profile, mode, password)
        if mode != 'none':
            check_initrd_capabilities(fd, image.profile, uid)
        sector_size = int(runner.run('blockdev', '--getss', device))
        layout = make_layout(disk['size'], image.size, persistence_mib, sector_size)
        folder = Path(tempfile.mkdtemp(prefix='distroclone-usb-'))
        token = uuid.uuid4().hex[:8]
        data_label = 'dcusb-' + token
        persistence_label = ('dc-p-' + token if image.profile.family == 'debian'
                             else image.profile.persistence_label)
        fresh_target(device, expected, confirmation, fd)
        if mode != 'none':
            wipe_fd = os.open(device, os.O_WRONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
            try:
                actual = os.fstat(wipe_fd)
                if not stat.S_ISBLK(actual.st_mode) or f'{os.major(actual.st_rdev)}:{os.minor(actual.st_rdev)}' != disk['maj:min']:
                    raise ValueError(tr('Block device node identity changed.'))
                assert_same_device(device, expected)
                clear_logical_sectors(wipe_fd, disk['size'], emit)
            finally:
                os.close(wipe_fd)
        fresh_target(device, expected, confirmation, fd)
        emit('progress', phase='partition', fraction=0)
        runner.run('sfdisk', '--wipe', 'always', '--wipe-partitions', 'always',
                   device, input=layout.sfdisk())
        runner.run('udevadm', 'settle', '--timeout=10')
        deadline = time.monotonic() + 10
        while not all(Path(partition_path(device, n)).exists() for n in (1, 2, 3, 4)):
            if time.monotonic() > deadline:
                raise RuntimeError(tr('The new USB partitions are unavailable.'))
            time.sleep(.2)
        with CryptoVolumes(runner, password, token) as crypto:
            mapped, luks_ids = {}, {}
            for number, label, filesystem in ((2, 'DCUSB-EFI', 'vfat'),
                                               (3, data_label, 'ext4'), (4, persistence_label, 'ext4')):
                current = assert_same_device(device, expected)
                if mounts(current):
                    raise ValueError(tr('The disk has mounted volumes or active swap. Unmount them first.'))
                target = partition_path(device, number)
                if (number == 3 and mode == 'all') or (number == 4 and mode != 'none'):
                    target = crypto.format_open(target, 'data' if number == 3 else 'persist',
                                                'pbkdf2' if number == 3 else 'argon2id')
                    luks_ids[number] = runner.run('cryptsetup', 'luksUUID', partition_path(device, number))
                mapped[number] = target
                if filesystem == 'vfat':
                    runner.run('mkfs.vfat', '-F', '32', '-n', label, target)
                else:
                    runner.run('mkfs.ext4', '-F', '-m', '0', '-O', '^orphan_file', '-L', label, target)
            current = assert_same_device(device, expected)
            if mounts(current):
                raise ValueError(tr('The disk has mounted volumes or active swap. Unmount them first.'))
            with mount_volumes(device, folder, runner, mapped) as paths:
                persist_fs_uuid = runner.run('blkid', '-s', 'UUID', '-o', 'value', mapped[4])
                prepare_shared(paths['persist'], image.profile, persist_fs_uuid)
                (paths['data'] / 'distroclone').mkdir()
                copy_verified(fd, paths['data'] / 'distroclone/live.iso', sha256, emit)
                if mode != 'none':
                    write_supplemental_initrd(paths['data'] / 'distroclone/unlock-initrd.gz')
                emit('progress', phase='boot', fraction=0)
                install_boot(image.profile, paths, data_label, persistence_label, runner,
                             mode, luks_ids.get(3), luks_ids.get(4))
                assert_same_device(device, expected)
                boot_root = paths['efi'] if mode == 'all' else paths['data']
                runner.run('grub-install', '--target=i386-pc', '--no-floppy', '--recheck',
                           '--boot-directory=' + str(boot_root / 'boot'), device)
        emit('done', message=tr('USB created and verified. Volumes unmounted.'), sha256=sha256)
    finally:
        os.close(fd)
        if lock_fd is not None:
            os.close(lock_fd)
        if folder and not any(os.path.ismount(folder / name) for name in ('efi', 'data', 'persist')):
            shutil.rmtree(folder)
