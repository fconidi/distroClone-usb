import io
import gzip
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from distroclone_usb.crypto import CryptoVolumes, encryption_modules, read_secret, validate_encryption
from distroclone_usb.encrypted_boot import write_supplemental_initrd
from distroclone_usb.profiles import Profile, grub_config
from distroclone_usb.writer import Runner


DEBIAN = Profile('debian', 'SysLinuxOS', '/live/vmlinuz', ('/live/initrd.img',), ('boot=live',), 'persistence')


class CryptoTest(unittest.TestCase):
    def test_supplemental_archive_contains_only_trusted_unlock_script(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'unlock.gz'
            write_supplemental_initrd(path, b"/scripts/init-premount/original-test-script \"$@\"\n")
            contents = gzip.decompress(path.read_bytes())
            result = subprocess.run(['cpio', '-it'], input=contents, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout.decode().splitlines(),
                             ['scripts', 'scripts/init-premount', 'scripts/init-premount/distroclone-usb-unlock', 'scripts/init-premount/ORDER'])
            self.assertNotIn(b'TEST-SECRET', contents)
            self.assertIn(b'/scripts/init-premount/original-test-script', contents)
            self.assertIn(b'/scripts/init-premount/distroclone-usb-unlock \"$@\"', contents)

    def test_password_rules_and_unsupported_profiles(self):
        validate_encryption(DEBIAN, 'none', None)
        validate_encryption(DEBIAN, 'persistence', 'long-test-passphrase')
        validate_encryption(DEBIAN, 'all', 'a long test passphrase 2026')
        for mode, password in [('all', 'short'), ('persistence', 'short'),
                               ('all', 'é' * 24), ('all', 'a'*20+'\n'), ('bad', 'a'*24)]:
            with self.subTest(mode=mode, password=password), self.assertRaises(ValueError):
                validate_encryption(DEBIAN, mode, password)
        with self.assertRaises(ValueError):
            validate_encryption(Profile('casper', 'Ubuntu', '', (), (), 'writable'), 'all', 'a'*24)

    def test_both_encrypted_modes_accept_twelve_and_reject_eleven_characters(self):
        for mode in ('persistence', 'all'):
            validate_encryption(DEBIAN, mode, 'Abcd1234Efgh')
            with self.assertRaises(ValueError):
                validate_encryption(DEBIAN, mode, 'Abcd1234Efg')

    def test_secret_transport_is_bounded_and_rejects_extra_fields(self):
        self.assertEqual(read_secret(io.BytesIO(b'{"password":"test only phrase"}\n')), 'test only phrase')
        for content in (b'x'*4097, b'{}', b'{"password":12}', b'{"password":"test","keyfile":"/tmp/x"}'):
            with self.assertRaises(ValueError):
                read_secret(io.BytesIO(content))

    def test_runner_never_logs_secret(self):
        events = []
        class Result:
            returncode = 0
            stdout = b''
            stderr = b''
        with patch('subprocess.run', return_value=Result()) as run:
            Runner(lambda *args, **kwargs: events.append((args, kwargs))).run(
                '/usr/bin/true', input_secret=b'TEST-SECRET-ONLY')
        self.assertNotIn('TEST-SECRET-ONLY', repr(events))
        self.assertNotIn('TEST-SECRET-ONLY', repr(run.call_args.args))
        self.assertEqual(run.call_args.kwargs['input'], b'TEST-SECRET-ONLY')

    def test_only_successfully_opened_mappings_are_closed_in_reverse_order(self):
        calls = []
        class FakeRunner:
            def run(self, command, *args, **kwargs):
                calls.append((command, args))
                if args and args[0] == 'open' and args[-1].endswith('persist'):
                    raise RuntimeError('unlock failed')
                return ''
        with self.assertRaises(RuntimeError):
            with CryptoVolumes(FakeRunner(), 'a test phrase', 'test') as volumes:
                volumes.format_open('/dev/sdz3', 'data', 'pbkdf2')
                volumes.format_open('/dev/sdz4', 'persist', 'argon2id')
        closed = [args[1] for command, args in calls if args and args[0] == 'close']
        self.assertEqual(closed, ['dcusb-test-data'])

    def test_full_boot_loads_iso_through_crypto_and_passes_only_uuids(self):
        data = '12345678-1234-1234-1234-123456789abc'
        persist = '87654321-4321-4321-4321-cba987654321'
        config = grub_config(DEBIAN, 'dcusb123', 'dc-p123', 'all', data, persist)
        self.assertIn('cryptomount -u ' + data.replace('-', ''), config)
        self.assertIn('dcusb.data-uuid=' + data, config)
        self.assertIn('live-media=/dev/mapper/dcusb_data', config)
        self.assertIn('dcusb.persist-uuid=' + persist, config)
        self.assertIn('/distroclone/unlock-initrd.gz', config)
        self.assertIn('luks2', encryption_modules('all'))
    def test_preflight_preserves_original_initpremount_order(self):
        from distroclone_usb.encrypted_boot import check_initrd_capabilities
        def command(argv, uid=None, pass_fds=()):
            if argv[0].endswith('xorriso'):
                Path(argv[-1]).write_bytes(b'initrd fixture')
            elif argv[0].endswith('lsinitramfs'):
                return ('usr/sbin/cryptsetup\nusr/lib/cryptsetup/askpass\n'
                        'scripts/live\nusr/lib/modules/test/dm-crypt.ko.xz\n')
            elif argv[0].endswith('unmkinitramfs'):
                path = Path(argv[-1]) / 'main/scripts/init-premount/ORDER'
                path.parent.mkdir(parents=True)
                path.write_bytes(b'/scripts/init-premount/original "$@"\n')
            return ''
        with tempfile.TemporaryFile() as iso, patch('distroclone_usb.encrypted_boot.limited_output', side_effect=command):
            self.assertEqual(check_initrd_capabilities(iso.fileno(), DEBIAN, os.getuid()),
                             b'/scripts/init-premount/original "$@"\n')

    def test_initrd_order_cannot_read_host_files_through_symlinks(self):
        from distroclone_usb.encrypted_boot import read_order
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            outside = root / 'private-host-file'
            outside.write_text('PRIVATE TEST DATA')
            extracted = root / 'extracted'
            path = extracted / 'scripts/init-premount'
            path.mkdir(parents=True)
            (path / 'ORDER').symlink_to(outside)
            with self.assertRaises(OSError):
                read_order(extracted, 'scripts/init-premount/ORDER')
            (path / 'ORDER').unlink()
            path.rmdir()
            (extracted / 'scripts').rmdir()
            (extracted / 'scripts').symlink_to(root)
            with self.assertRaises(OSError):
                read_order(extracted, 'scripts/init-premount/ORDER')

    def test_cancelled_open_closes_a_mapping_created_before_command_exit(self):
        from distroclone_usb.cancellation import CancellationRequested
        calls = []
        class FakeRunner:
            def run(self, command, *args, **kwargs):
                calls.append(args)
                if args[0] == 'open':
                    raise CancellationRequested('test cancellation')
        with patch('distroclone_usb.crypto.Path.exists', side_effect=[False, True]):
            with self.assertRaises(CancellationRequested):
                with CryptoVolumes(FakeRunner(), 'Abcd1234Efgh', 'test') as volumes:
                    volumes.format_open('/dev/sdz3', 'data', 'pbkdf2')
        self.assertEqual(calls[-1], ('close', 'dcusb-test-data'))
