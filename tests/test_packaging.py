from pathlib import Path
import os
import re
import stat
import unittest

from distroclone_usb import __version__
from distroclone_usb.iso import private_workdir

ROOT = Path(__file__).resolve().parent.parent


class PackagingTest(unittest.TestCase):
    def test_versions_agree(self):
        self.assertTrue((ROOT / 'CHANGELOG.md').read_text().startswith(f'# Changelog\n\n## {__version__} '))
        self.assertTrue((ROOT / 'packaging/changelog').read_text().startswith(f'distroclone-usb ({__version__})'))
        self.assertIn(f'distroClone USB {__version__}"', (ROOT / 'packaging/distroclone-usb.1').read_text())
        self.assertIn(f'version {__version__}', (ROOT / 'docs/COMPATIBILITY.md').read_text())

    def test_all_files_installed_by_deb_script_exist(self):
        for name in re.findall(r'\$ROOT_DIR/(docs/[\w.-]+|packaging/[\w.-]+)', (ROOT / 'build-deb.sh').read_text()):
            self.assertTrue((ROOT / name).exists(), name)

    def test_work_folder_cannot_be_swapped_by_the_user(self):
        with private_workdir('dcusb-test-') as work:
            parent = os.path.dirname(work)
            self.assertEqual(stat.S_IMODE(os.stat(parent).st_mode), 0o711)
            self.assertEqual(stat.S_IMODE(os.stat(work).st_mode), 0o700)
        self.assertFalse(os.path.exists(parent))


if __name__ == '__main__':
    unittest.main()
