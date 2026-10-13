"""Validate live initrd capabilities and build a key-free supplemental archive."""

import gzip
import os
from pathlib import Path
import selectors
import signal
import subprocess
import tempfile
import time

from .i18n import tr
from .iso import demote, open_iso


def limited_output(command, uid=None, pass_fds=()):
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                               pass_fds=pass_fds, preexec_fn=demote(uid), start_new_session=True,
                               env={'PATH': '/usr/sbin:/usr/bin:/sbin:/bin', 'LC_ALL': 'C'})
    selector = selectors.DefaultSelector()
    selector.register(process.stdout, selectors.EVENT_READ)
    output, deadline = bytearray(), time.monotonic() + 120
    try:
        while selector.get_map():
            if time.monotonic() > deadline:
                raise ValueError(tr('The ISO initramfs could not be verified for encryption.'))
            for key, _ in selector.select(timeout=1):
                chunk = os.read(key.fd, 65536)
                if not chunk:
                    selector.unregister(key.fileobj)
                else:
                    output.extend(chunk)
                    if len(output) > 8 * 1024 * 1024:
                        raise ValueError(tr('The ISO initramfs could not be verified for encryption.'))
        if process.wait(timeout=max(1, deadline - time.monotonic())):
            raise ValueError(tr('The ISO initramfs could not be verified for encryption.'))
        return output.decode(errors='replace')
    finally:
        selector.close()
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait()


def check_initrd_capabilities(iso_fd, profile, uid):
    contents = set()
    with tempfile.TemporaryDirectory(prefix='dcusb-initrd-') as folder:
        if os.geteuid() == 0 and uid is not None:
            os.chown(folder, uid, -1)
        for index, member in enumerate(profile.initrds):
            path = Path(folder) / str(index)
            limited_output(['/usr/bin/xorriso', '-abort_on', 'FAILURE', '-indev',
                            f'/proc/self/fd/{iso_fd}', '-osirrox', 'on', '-extract', member, str(path)],
                           uid, (iso_fd,))
            fd = open_iso(str(path), uid)
            try:
                if os.fstat(fd).st_size > 512 * 1024 * 1024:
                    raise ValueError(tr('The ISO initramfs could not be verified for encryption.'))
                listing = limited_output(['/usr/bin/lsinitramfs', f'/proc/self/fd/{fd}'], uid, (fd,))
                contents.update(line.removeprefix('./') for line in listing.splitlines())
            finally:
                os.close(fd)
    if (not {'usr/sbin/cryptsetup', 'sbin/cryptsetup'} & contents
            or not {'usr/lib/cryptsetup/askpass', 'lib/cryptsetup/askpass'} & contents
            or 'scripts/live' not in contents
            or not any('/dm-crypt.ko' in name for name in contents)):
        raise ValueError(tr('The ISO lacks cryptsetup, askpass or dm-crypt support. Use a compatible SysLinuxOS ISO.'))


def newc_entry(name, content, mode, inode):
    encoded = name.encode() + b'\0'
    fields = (inode, mode, 0, 0, 1, 0, len(content), 0, 0, 0, 0, len(encoded), 0)
    header = b'070701' + ''.join(f'{field:08x}' for field in fields).encode()
    record = header + encoded
    record += b'\0' * (-len(record) % 4)
    record += content
    return record + b'\0' * (-len(content) % 4)


def write_supplemental_initrd(destination):
    script = Path(__file__).with_name('boot_unlock.sh').read_bytes()
    archive = newc_entry('scripts', b'', 0o40755, 1)
    archive += newc_entry('scripts/init-premount', b'', 0o40755, 2)
    archive += newc_entry('scripts/init-premount/distroclone-usb-unlock', script, 0o100755, 3)
    archive += newc_entry('TRAILER!!!', b'', 0, 4)
    destination.write_bytes(gzip.compress(archive, mtime=0))
    destination.chmod(0o600)
