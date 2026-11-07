import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from distroclone_usb import writer
from distroclone_usb.writer import Runner, assert_same_device, copy_verified, mount_volumes, partition_path


class WriterTest(unittest.TestCase):
    def test_hotplug_replacement_aborts_before_boot_sector_write(self):
        with patch('distroclone_usb.writer.inventory', return_value=[]):
            with self.assertRaisesRegex(ValueError, 'disconnected'):
                assert_same_device('/dev/sdz', 'a' * 64)

    def test_nonzero_command_stops_operation(self):
        with self.assertRaises(RuntimeError):
            Runner(lambda *a, **k: None).run('/usr/bin/false')

    def test_partition_names(self):
        self.assertEqual(partition_path('/dev/sdb', 3), '/dev/sdb3')
        self.assertEqual(partition_path('/dev/mmcblk0', 3), '/dev/mmcblk0p3')

    def test_changed_source_fails_verification(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / 'source'
            source.write_bytes(b'contents')
            fd = os.open(source, os.O_RDONLY)
            try:
                with self.assertRaises(ValueError):
                    copy_verified(fd, Path(folder) / 'target', '0' * 64, lambda *a, **k: None)
            finally:
                os.close(fd)

    def test_copy_never_follows_destination_symlink(self):
        with tempfile.TemporaryDirectory() as folder:
            source, dest = Path(folder) / 'source', Path(folder) / 'target'
            source.write_bytes(b'original')
            dest.symlink_to(source)
            fd = os.open(source, os.O_RDONLY)
            try:
                with self.assertRaises(FileExistsError):
                    copy_verified(fd, dest, '0' * 64, lambda *a, **k: None)
            finally:
                os.close(fd)
            self.assertEqual(source.read_bytes(), b'original')

    def test_mount_failure_unmounts_only_successful_mounts(self):
        calls = []

        class FakeRunner:
            def run(self, command, *args, **kwargs):
                calls.append((command, args))
                if command == 'mount' and args[-1].endswith('/persist'):
                    raise RuntimeError('mount failure')

        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(RuntimeError):
                with mount_volumes('/dev/sdb', Path(folder), FakeRunner()):
                    self.fail('Must not enter after failed mount')
        unmounts = [args[0] for cmd, args in calls if cmd == 'umount']
        self.assertEqual(unmounts, [folder + '/data', folder + '/efi'])

    def test_unmount_failure_is_reported_and_directory_retained(self):
        class FakeRunner:
            def run(self, command, *args, **kwargs):
                if command == 'umount':
                    raise RuntimeError('busy')

        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaisesRegex(RuntimeError, 'unmount'):
                with mount_volumes('/dev/sdb', Path(folder), FakeRunner()):
                    pass
            self.assertTrue((Path(folder) / 'data').exists())

    def test_cancelled_mount_is_unmounted_if_syscall_already_succeeded(self):
        from distroclone_usb.cancellation import CancellationRequested
        calls = []
        class FakeRunner:
            def run(self, command, *args, **kwargs):
                calls.append((command,args))
                if command == 'mount':
                    raise CancellationRequested('test cancellation')
        with tempfile.TemporaryDirectory() as folder, patch('os.path.ismount', return_value=True):
            with self.assertRaises(CancellationRequested):
                with mount_volumes('/dev/sdz',Path(folder),FakeRunner()):
                    self.fail('Must not enter after cancelled mount')
        self.assertEqual(calls[-1], ('umount',(folder+'/efi',)))

    def test_ext4_orphan_option_depends_on_e2fsprogs_version(self):
        class Result:
            def __init__(self, text):
                self.stdout, self.stderr = '', text
        for text, expected in (('mke2fs 1.47.0 (5-Feb-2023)', ['-O', '^orphan_file']),
                               ('mke2fs 1.46.6 (1-Feb-2023)', []), ('garbage', [])):
            with self.subTest(text=text), patch('subprocess.run', return_value=Result(text)):
                self.assertEqual(writer.ext4_options(), expected)

    def test_automount_rule_is_written_and_removed(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(writer, 'UDEV_RULES', folder):
            calls = []
            class FakeRunner:
                def run(self, *args, **kwargs):
                    calls.append(args)
            with writer.automount_blocked('/dev/sdz', FakeRunner()):
                rule = Path(folder) / '90-distroclone-usb-sdz.rules'
                self.assertIn('UDISKS_IGNORE', rule.read_text())
                self.assertIn('sdz[0-9]*', rule.read_text())
            self.assertFalse(rule.exists())
            self.assertEqual(len([c for c in calls if c[0] == 'udevadm']), 2)

    def test_automount_rule_ignores_odd_device_names(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(writer, 'UDEV_RULES', folder):
            with writer.automount_blocked('/dev/../etc/x"y', None):
                pass
            self.assertEqual(list(Path(folder).iterdir()), [])

    def test_lock_directory_must_be_private_to_root(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / 'locks'
            with patch.object(writer, 'RUN_DIR', str(target)):
                if os.geteuid() == 0:
                    self.assertEqual(writer.lock_directory(), str(target))
                    target.chmod(0o777)
                    with self.assertRaises(ValueError):
                        writer.lock_directory()
                else:
                    with self.assertRaises(ValueError):
                        writer.lock_directory()

    def test_copy_verification_drops_cached_pages(self):
        with tempfile.TemporaryDirectory() as folder, patch('os.posix_fadvise') as advise:
            source = Path(folder) / 'a.iso'
            source.write_bytes(b'x' * 1000)
            import hashlib
            fd = os.open(source, os.O_RDONLY)
            try:
                copy_verified(fd, Path(folder) / 'b.iso', hashlib.sha256(b'x' * 1000).hexdigest(), lambda *a, **k: None)
            finally:
                os.close(fd)
            self.assertGreaterEqual(advise.call_count, 2)


if __name__ == '__main__':
    unittest.main()
