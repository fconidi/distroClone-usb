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
        self.assertEqual(json.loads(process.stdin.getvalue()), {'password': phrase})
        self.assertLessEqual(len(process.stdin.getvalue().encode()), 4096)
        self.assertFalse(process.stdin.closed)

    def test_unciphered_mode_keeps_a_control_pipe_without_a_phrase(self):
        process = Mock(stdin=io.StringIO())
        with patch('subprocess.Popen', return_value=process) as popen:
            start_writer(['--encrypt-mode', 'none'])
        self.assertEqual(popen.call_args.kwargs['stdin'], subprocess.PIPE)
        self.assertEqual(process.stdin.getvalue(), '')
        self.assertIn('--control-stdin', popen.call_args.args[0])

    def test_cancel_uses_the_existing_pipe_and_never_an_external_kill_command(self):
        from distroclone_usb.writer_client import request_cancel
        process = Mock(stdin=io.StringIO())
        process.poll.return_value = None
        process.send_signal.side_effect = PermissionError('privileged child')
        self.assertTrue(request_cancel(process))
        self.assertEqual(process.stdin.getvalue(), 'cancel\n')
