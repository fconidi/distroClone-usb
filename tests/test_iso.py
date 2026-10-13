import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from distroclone_usb.iso import inspect_iso, open_iso
from distroclone_usb.profiles import UnsupportedISO


@unittest.skipUnless(shutil.which('xorriso'), 'xorriso required')
class RealISOTest(unittest.TestCase):
    def fixture(self, folder, family='debian', info='Debian Live 13 amd64'):
        root = Path(folder) / 'tree'
        directory = 'live' if family == 'debian' else 'casper'
        for path in (directory + '/vmlinuz', directory + '/initrd.img',
                     directory + '/filesystem.squashfs', 'EFI/BOOT/BOOTX64.EFI'):
            dest = root / path
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(b'fixture')
        (root / 'boot/grub').mkdir(parents=True)
        (root / 'boot/grub/grub.cfg').write_text(
            f'linux /{directory}/vmlinuz boot={"live" if family == "debian" else "casper"} components quiet\n'
            f'initrd /{directory}/initrd.img\n')
        (root / '.disk').mkdir()
        (root / '.disk/info').write_text(info)
        image = Path(folder) / 'image.iso'
        subprocess.run(['xorriso', '-as', 'mkisofs', '-R', '-o', str(image), str(root)],
                       check=True, capture_output=True)
        return image

    def test_real_iso_extraction_and_digest_debian_and_casper(self):
        import hashlib
        for family, info in [('debian', 'Debian Live 13 amd64'), ('casper', 'Ubuntu 24.04 LTS')]:
            with self.subTest(family=family), tempfile.TemporaryDirectory() as folder:
                image = self.fixture(folder, family, info)
                result = inspect_iso(str(image))
                self.assertEqual(result.profile.family, family)
                self.assertEqual(result.sha256, hashlib.sha256(image.read_bytes()).hexdigest())
                self.assertEqual(result.size, image.stat().st_size)

    def test_fifo_and_directory_are_rejected_without_blocking(self):
        with tempfile.TemporaryDirectory() as folder:
            fifo = Path(folder) / 'pipe'
            os.mkfifo(fifo)
            for path in (fifo, Path(folder)):
                with self.subTest(path=path), self.assertRaises(ValueError):
                    open_iso(str(path))

    def test_arbitrary_data_is_not_an_iso(self):
        with tempfile.NamedTemporaryFile() as source:
            source.write(b'not an ISO')
            source.flush()
            with self.assertRaises(UnsupportedISO):
                inspect_iso(source.name)
