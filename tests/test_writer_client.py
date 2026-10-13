import io
import json
import subprocess
import unittest
from unittest.mock import Mock, patch

from distroclone_usb.writer_client import start_writer


class SecretClientTest(unittest.TestCase):
    def test_phrase_uses_stdin_and_never_argv_or_environment(self):
        class Capture(io.StringIO):
            def close(self):
                self.written = self.getvalue()
                super().close()
        process = Mock(stdin=Capture())
        phrase = 'test-only-secret-🍋' * 24
        with patch('subprocess.Popen', return_value=process) as popen:
            self.assertIs(start_writer(['--encrypt-mode', 'persistence'], phrase), process)
        command = popen.call_args.args[0]
        self.assertIn('--disable-internal-agent', command)
        self.assertNotIn(phrase, repr(popen.call_args))
        self.assertEqual(json.loads(process.stdin.written), {'password': phrase})
        self.assertLessEqual(len(process.stdin.written.encode()), 4096)
        self.assertTrue(process.stdin.closed)

    def test_no_phrase_means_no_interactive_input(self):
        with patch('subprocess.Popen') as popen:
            start_writer(['--encrypt-mode', 'none'])
        self.assertEqual(popen.call_args.kwargs['stdin'], subprocess.DEVNULL)
