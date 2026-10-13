"""Read boot configurations as data; never execute configuration from an ISO."""

from .i18n import tr
from dataclasses import dataclass
import re
import shlex


class UnsupportedISO(ValueError):
    pass


@dataclass(frozen=True)
class Profile:
    family: str
    name: str
    kernel: str
    initrds: tuple[str, ...]
    arguments: tuple[str, ...]
    persistence_label: str


SAFE_PATH = re.compile(r'^/[A-Za-z0-9_./+\-]+$')
SAFE_VALUE = re.compile(r'^[A-Za-z0-9_./,:@+%=\-]+$')
ARG_KEYS = {'boot', 'username', 'user', 'hostname', 'locales', 'locale',
            'keyboard-layouts', 'keyboard-variants', 'keyboard-model',
            'keyboard-options', 'live-media-path', 'union', 'module',
            'timezone', 'utc', 'access', 'layerfs-path'}
ARG_FLAGS = {'quiet', 'splash', 'components', 'config', 'noeject', 'noprompt',
             'noautologin', 'noconfig', 'nonetworking', 'noswap'}


def iso_path(value):
    value = re.sub(r'^\(loop\)', '', value)
    if not value.startswith('/'):
        value = '/' + value
    if not SAFE_PATH.fullmatch(value) or '..' in value.split('/'):
        return None
    return value


def safe_arguments(tokens):
    result = []
    for token in tokens:
        if token == '---':
            break
        if token in ARG_FLAGS or (token.split('=', 1)[0] in ARG_KEYS
                                  and '=' in token and SAFE_VALUE.fullmatch(token)):
            result.append(token)
    return tuple(result)


def boot_entries(config):
    """Recognize simple GRUB linux/initrd and syslinux kernel/append pairs."""
    kernel, args, initrds = None, (), ()
    for line in config.splitlines():
        try:
            tokens = shlex.split(line, comments=True)
        except ValueError:
            continue
        if not tokens:
            continue
        command = tokens[0].lower()
        if command in {'menuentry', 'label', '}'}:
            if kernel and initrds:
                yield kernel, initrds, args
            kernel, args, initrds = None, (), ()
        elif command in {'linux', 'linuxefi', 'kernel'} and len(tokens) >= 2:
            if kernel and initrds:
                yield kernel, initrds, args
            kernel, args, initrds = iso_path(tokens[1]), safe_arguments(tokens[2:]), ()
        elif command in {'initrd', 'initrdefi'}:
            initrds = tuple(iso_path(t) for t in tokens[1:])
        elif command == 'append':
            args = safe_arguments(tokens[1:])
            initrds = tuple(iso_path(p) for t in tokens[1:] if t.startswith('initrd=')
                            for p in t.split('=', 1)[1].split(','))
    if kernel and initrds:
        yield kernel, initrds, args


def casper_label(info):
    # Unknown derivatives must be validated rather than guessed from "casper".
    ubuntu = re.search(r'(?:[A-Za-z]*ubuntu|Ubuntu)[^\d]*(\d{2})\.(\d{2})', info, re.I)
    mint = re.search(r'Linux Mint\s+(\d+)', info, re.I)
    if ubuntu:
        return 'writable' if tuple(map(int, ubuntu.groups())) >= (20, 4) else 'casper-rw'
    if mint:
        return 'writable' if int(mint.group(1)) >= 20 else 'casper-rw'
    raise UnsupportedISO(tr('Casper version not recognized; persistence label is unverified.'))


def detect_profile(files, configurations, info=''):
    if any(p.startswith('/antiX/') for p in files):
        raise UnsupportedISO(tr('MX/antiX recognized: persistence is not supported in version 0.1.'))
    if not any(p.lower() == '/efi/boot/bootx64.efi' for p in files):
        raise UnsupportedISO(tr('An x86-64 live ISO with recognizable UEFI boot is required.'))
    if re.search(r'ubuntu[- ]server|subiquity', info, re.I):
        raise UnsupportedISO(tr('Server installer ISO: persistent live sessions are not supported.'))
    for config in configurations:
        for kernel, initrds, args in boot_entries(config):
            if kernel not in files or not initrds or any(p not in files for p in initrds):
                continue
            if ('boot=live' in args and kernel.startswith('/live/')
                    and any(p.startswith('/live/') and p.endswith('.squashfs') for p in files)):
                return Profile('debian', info.strip()[:160] or 'Debian Live', kernel,
                               initrds, args, 'persistence')
            if (kernel.startswith('/casper/') and any(p.startswith('/casper/')
                    and p.endswith('.squashfs') for p in files)):
                if 'boot=casper' not in args:
                    args = ('boot=casper',) + args
                return Profile('casper', info.strip()[:160] or 'Ubuntu Live', kernel,
                               initrds, args, casper_label(info))
    raise UnsupportedISO(tr('No compatible live profile found in the ISO boot menus.'))


def grub_config(profile, data_label, persistence_label):
    for label in (data_label, persistence_label):
        if not re.fullmatch(r'[A-Za-z0-9\-]{1,16}', label):
            raise ValueError(tr('Invalid filesystem label.'))
    text = ['set default=0', 'set timeout=10', 'insmod part_gpt', 'insmod ext2',
            'insmod iso9660', 'insmod loopback',
            f'search --no-floppy --label --set=root {data_label}']
    if profile.family == 'debian':
        base = f'findiso=/distroclone/live.iso'
        persistent = f'persistence persistence-label={persistence_label}'
        temporary = 'nopersistence'
    elif profile.family == 'casper':
        base = 'iso-scan/filename=/distroclone/live.iso'
        persistent, temporary = 'persistent', 'nopersistent'
    else:
        raise UnsupportedISO(tr('Unknown profile.'))
    args = ' '.join(profile.arguments)
    for title, extra in [('Live - persistence', persistent),
                         ('Live - temporary session', temporary),
                         ('Live - persistence (safe graphics)', persistent + ' nomodeset')]:
        text += [f'menuentry "distroClone USB: {tr(title)}" {{',
                 '    loopback loop /distroclone/live.iso',
                 f'    linux (loop){profile.kernel} {args} {base} {extra}',
                 '    initrd ' + ' '.join(f'(loop){p}' for p in profile.initrds), '}']
    return '\n'.join(text) + '\n'
