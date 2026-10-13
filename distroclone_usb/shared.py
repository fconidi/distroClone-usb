"""Expose a separate shared directory without changing live-boot's overlay."""

import os
from pathlib import Path
import re
import uuid


def live_user(profile):
    for key in ('username', 'user'):
        for argument in profile.arguments:
            if argument.startswith(key + '='):
                name = argument.split('=', 1)[1]
                if re.fullmatch(r'[a-z_][a-z0-9_-]{0,31}', name):
                    return name
    return 'user' if profile.family == 'debian' else 'ubuntu'


def prepare_shared(persistence, profile, filesystem_uuid):
    if str(uuid.UUID(filesystem_uuid)) != filesystem_uuid:
        raise ValueError('Invalid persistence UUID')
    shared = persistence / 'Shared'
    shared.mkdir(mode=0o700)
    os.chown(shared, 1000, 1000)
    overlay = persistence / ('rw' if profile.family == 'debian' else 'upper')
    for relative in ('', 'etc', 'etc/systemd', 'etc/systemd/system', 'home'):
        directory = overlay / relative
        directory.mkdir(parents=True, exist_ok=True)
        # These become the live system's directories; a private helper umask
        # must not make / or /etc inaccessible to the live user.
        directory.chmod(0o755)
    system = overlay / 'etc/systemd/system'
    service = system / 'distroclone-usb-shared.service'
    service.write_text(f'''[Unit]
Description=distroClone USB shared files
After=local-fs.target
Before=display-manager.service
ConditionKernelCommandLine=|persistence
ConditionKernelCommandLine=|persistent

[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart=/usr/bin/mkdir -p /run/distroclone-usb-persistence /Shared
ExecStart=/usr/bin/mount -t ext4 -o nosuid,nodev,noexec UUID={filesystem_uuid} /run/distroclone-usb-persistence
ExecStart=/usr/bin/mount --bind /run/distroclone-usb-persistence/Shared /Shared
ExecStopPost=-/usr/bin/umount /Shared
ExecStopPost=-/usr/bin/umount /run/distroclone-usb-persistence

[Install]
WantedBy=multi-user.target
''')
    service.chmod(0o644)
    wants = system / 'multi-user.target.wants'
    wants.mkdir(mode=0o755)
    wants.chmod(0o755)
    (wants / service.name).symlink_to('/etc/systemd/system/' + service.name)
    home = overlay / 'home' / live_user(profile)
    home.mkdir(parents=True, mode=0o700)
    os.chown(home, 1000, 1000)
    (home / 'Shared').symlink_to('/Shared')
    os.lchown(home / 'Shared', 1000, 1000)
    (persistence / 'SHARED-README.txt').write_text(
        'distroClone USB: copy portable files into the Shared directory.\n'
        'In the persistent live session open Shared in your home directory.\n'
        'System changes are separate; do not edit rw/upper or work manually.\n'
        'Encrypted USBs must be unlocked before these files can be accessed.\n')
