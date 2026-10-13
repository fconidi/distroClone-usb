"""LUKS lifecycle and secret validation; never put passwords in process arguments."""

import json
from pathlib import Path
import uuid

from .i18n import tr
from .cancellation import defer_cancellation

MODES = ('none', 'persistence', 'all')


def read_secret(stream):
    raw = stream.readline(4097)
    try:
        payload = json.loads(raw)
    except (ValueError, UnicodeError):
        raise ValueError(tr('Invalid password input.')) from None
    if len(raw) > 4096 or not isinstance(payload, dict) or set(payload) != {'password'}:
        raise ValueError(tr('Invalid password input.'))
    if not isinstance(payload['password'], str):
        raise ValueError(tr('Invalid password input.'))
    return payload['password']


def validate_encryption(profile, mode, password):
    if mode not in MODES:
        raise ValueError(tr('Invalid encryption mode.'))
    if mode == 'none':
        return
    if profile.family != 'debian':
        raise ValueError(tr('Encryption currently requires a compatible Debian Live / SysLinuxOS ISO.'))
    minimum = 12
    if (not isinstance(password, str) or not minimum <= len(password) <= 512
            or any(ord(c) < 32 or ord(c) == 127 for c in password)):
        raise ValueError(tr('Use a passphrase of at least {minimum} characters.').format(minimum=minimum))
    if mode == 'all' and not password.isascii():
        raise ValueError(tr('Full encryption requires an ASCII passphrase; the boot keyboard uses US layout.'))


def encryption_modules(mode):
    return ('cryptodisk luks2 pbkdf2 gcry_rijndael gcry_sha256 gcry_sha512 '
            'gcry_serpent gcry_twofish' if mode == 'all' else '')


def validate_uuid(value):
    if not value or str(uuid.UUID(value)) != value:
        raise ValueError(tr('Invalid encrypted volume UUID.'))
    return value


def unlock_search(data_label, data_uuid=None):
    search = f'search --no-floppy --label --set=root {data_label}'
    if data_uuid:
        validate_uuid(data_uuid)
        return [f'if ! {search}; then', f'    cryptomount -u {data_uuid.replace("-", "")}',
                '    ' + search, 'fi']
    return [search]


class CryptoVolumes:
    def __init__(self, runner, password, token):
        self.runner = runner
        self.secret = bytearray((password or '').encode())
        self.token, self.opened = token, []

    def __enter__(self):
        return self

    def format_open(self, device, role, pbkdf):
        name = f'dcusb-{self.token}-{role}'
        if Path('/dev/mapper/' + name).exists():
            raise RuntimeError(tr('The disk still contains volumes in use.'))
        args = ['luksFormat', '--batch-mode', '--type', 'luks2', '--cipher', 'aes-xts-plain64',
                '--key-size', '512', '--hash', 'sha256', '--pbkdf', pbkdf, '--iter-time', '2000']
        if pbkdf == 'argon2id':
            args += ['--pbkdf-memory', '262144', '--pbkdf-parallel', '2']
        self.runner.run('cryptsetup', *args, '--key-file', '-', device, input_secret=self.secret)
        try:
            self.runner.run('cryptsetup', 'open', '--type', 'luks', '--key-file', '-',
                            device, name, input_secret=self.secret)
            self.opened.append(name)
        except BaseException:
            # A cancelled cryptsetup may have created its mapping before exit.
            if name not in self.opened and Path('/dev/mapper/' + name).exists():
                self.opened.append(name)
            raise
        return '/dev/mapper/' + name

    def __exit__(self, exc_type, exc_value, traceback):
        with defer_cancellation():
            failures = []
            for name in reversed(self.opened):
                try:
                    self.runner.run('cryptsetup', 'close', name)
                except Exception as error:
                    failures.append(str(error))
            self.secret[:] = b'\0' * len(self.secret)
            if failures:
                raise RuntimeError(tr('Unable to close encrypted volumes: {details}').format(details='; '.join(failures)))
