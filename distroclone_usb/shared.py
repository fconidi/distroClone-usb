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
    for relative in ('', 'etc', 'etc/systemd', 'etc/systemd/system', 'etc/skel'):
        directory = overlay / relative
        directory.mkdir(parents=True, exist_ok=True)
        # These become the live system's directories; a private helper umask
        # must not make / or /etc inaccessible to the live user.
        directory.chmod(0o755)
    system = overlay / 'etc/systemd/system'
    service = system / 'distroclone-usb-shared.service'
    service.write_text(f'''[Unit]
Description=distroClone USB shared files
After=local-fs.target live-config.service casper.service
Before=display-manager.service
ConditionKernelCommandLine=|persistence
ConditionKernelCommandLine=|persistent

[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart=/usr/bin/mkdir -p /run/distroclone-usb-persistence /Shared
ExecStart=/usr/bin/mount -t ext4 -o nosuid,nodev,noexec UUID={filesystem_uuid} /run/distroclone-usb-persistence
ExecStart=/usr/bin/mount --bind /run/distroclone-usb-persistence/Shared /Shared
ExecStart=-/usr/bin/ln -sT /Shared /home/{live_user(profile)}/Shared
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
    # Let live-config create the home normally and copy the full distro skeleton.
    (overlay / 'etc/skel/Shared').symlink_to('/Shared')
    (persistence / 'SHARED-README.txt').write_text(
        'distroClone USB: copy portable files into the Shared directory.\n'
        'In the persistent live session open Shared in your home directory.\n'
        'System changes are separate; do not edit rw/upper or work manually.\n'
        'Encrypted USBs must be unlocked before these files can be accessed.\n\n'
        'IT: copia i file in Shared; nella live apri Shared dalla Home.\n'
        'ES: copia los archivos en Shared; en la live abre Shared desde tu carpeta personal.\n'
        'FR: copiez les fichiers dans Shared ; ouvrez Shared dans votre dossier personnel live.\n'
        'DE: Dateien nach Shared kopieren; im Live-System Shared im Home-Ordner öffnen.\n')
