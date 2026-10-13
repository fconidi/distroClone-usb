"""Inspect ISO metadata through an unprivileged xorriso process."""

from dataclasses import asdict, dataclass
import hashlib
import os
from pathlib import Path
import shlex
import stat
import subprocess
import tempfile

from .i18n import tr
from .profiles import Profile, UnsupportedISO, detect_profile


@dataclass(frozen=True)
class ISOImage:
    path: str
    size: int
    sha256: str
    profile: Profile

    def to_dict(self):
        return asdict(self)


def demote(uid):
    if uid is None or os.geteuid() != 0:
        return None
    import pwd
    user = pwd.getpwuid(uid)

    def drop():
        os.setgroups(os.getgrouplist(user.pw_name, user.pw_gid))
        os.setgid(user.pw_gid)
        os.setuid(uid)
    return drop


def open_iso(path, uid=None):
    """The caller must have access; root must not disclose arbitrary root files."""
    old_uid, old_gid, groups = os.geteuid(), os.getegid(), os.getgroups()
    try:
        if old_uid == 0 and uid is not None:
            import pwd
            user = pwd.getpwuid(uid)
            os.setgroups(os.getgrouplist(user.pw_name, user.pw_gid))
            os.setegid(user.pw_gid)
            os.seteuid(uid)
        fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK | os.O_CLOEXEC)
    finally:
        if os.geteuid() != old_uid:
            os.seteuid(old_uid)
        if old_uid == 0:
            os.setegid(old_gid)
            os.setgroups(groups)
    if not stat.S_ISREG(os.fstat(fd).st_mode):
        os.close(fd)
        raise ValueError(tr('The ISO must be a regular file.'))
    return fd


def digest_fd(fd, progress=None):
    digest = hashlib.sha256()
    os.lseek(fd, 0, os.SEEK_SET)
    size, done = os.fstat(fd).st_size, 0
    while chunk := os.read(fd, 4 * 1024 * 1024):
        digest.update(chunk)
        done += len(chunk)
        if progress:
            progress(done, size)
    os.lseek(fd, 0, os.SEEK_SET)
    return digest.hexdigest()


def inspect_fd(fd, path, uid=None, progress=None):
    def run(*args):
        result = subprocess.run(['/usr/bin/xorriso', '-abort_on', 'FAILURE',
                                 '-indev', f'/proc/self/fd/{fd}', *args],
                                pass_fds=(fd,), preexec_fn=demote(uid),
                                env={'PATH': '/usr/bin:/bin', 'LC_ALL': 'C'},
                                capture_output=True, text=True, timeout=120)
        if result.returncode:
            raise UnsupportedISO(tr('Unable to read ISO: {details}').format(details=result.stderr[-1200:]))
        if len(result.stdout) > 8 * 1024 * 1024:
            raise UnsupportedISO(tr('ISO index is too large.'))
        return result.stdout

    listing = run('-find', '/', '-maxdepth', '6', '-exec', 'echo', '--')
    files = set()
    for line in listing.splitlines():
        try:
            parsed = shlex.split(line)
        except ValueError:
            continue
        if len(parsed) == 1 and parsed[0].startswith('/'):
            files.add(parsed[0])
    if len(files) > 50000:
        raise UnsupportedISO(tr('Too many files in the ISO.'))
    configs = sorted(p for p in files if p.endswith('.cfg') and
                     p.startswith(('/boot/grub/', '/isolinux/', '/syslinux/')))
    configs.sort(key=lambda p: (p != '/boot/grub/grub.cfg', p))
    paths = configs[:64] + (['/.disk/info'] if '/.disk/info' in files else [])
    contents = {}
    # Extraction destination is controlled, with no ISO-provided filenames.
    with tempfile.TemporaryDirectory(prefix='dcusb-inspect-') as folder:
        if uid is not None and os.geteuid() == 0:
            os.chown(folder, uid, -1)
        for index, source in enumerate(paths):
            dest = Path(folder) / str(index)
            run('-osirrox', 'on', '-extract', source, str(dest))
            config_fd = open_iso(str(dest), uid)
            try:
                if os.fstat(config_fd).st_size > 1024 * 1024:
                    raise UnsupportedISO(tr('ISO configuration is too large.'))
                contents[source] = os.read(config_fd, 1024 * 1024).decode(errors='replace')
            finally:
                os.close(config_fd)
    profile = detect_profile(files, [contents[p] for p in configs[:64]],
                             contents.get('/.disk/info', ''))
    return ISOImage(str(Path(path).absolute()), os.fstat(fd).st_size,
                    digest_fd(fd, progress), profile)


def inspect_iso(path, progress=None):
    fd = open_iso(path)
    try:
        return inspect_fd(fd, path, progress=progress)
    finally:
        os.close(fd)
