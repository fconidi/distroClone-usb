import os
import subprocess
import sys
import unittest


class CancellationTest(unittest.TestCase):
    def test_control_pipe_interrupts_worker_and_cleanup_runs(self):
        self.run_worker(b'cancel\n')

    def test_closed_control_pipe_interrupts_abandoned_worker(self):
        self.run_worker(b'')

    def test_control_pipe_interrupts_active_subprocess_and_cleanup_runs(self):
        self.run_worker(b'cancel\n', active_command=True)

    def test_cancellation_during_cleanup_is_deferred_until_resources_are_closed(self):
        self.run_worker(b'cancel\n', cleanup=True)

    def run_worker(self, command, active_command=False, cleanup=False):
        code = '''
import sys,time
from distroclone_usb.cancellation import Cancellation, CancellationRequested
try:
    with Cancellation(sys.stdin.fileno()):
        print('READY',flush=True)
        try: time.sleep(15)
        finally: print('CLEANUP',flush=True)
except CancellationRequested:
    print('CANCELLED',flush=True)
'''
        if active_command:
            code = code.replace('time.sleep(15)', "__import__('distroclone_usb.writer', fromlist=['Runner']).Runner(lambda *a, **k: None).run('/usr/bin/sleep', '15')")
        if cleanup:
            code = code.replace('Cancellation, CancellationRequested', 'Cancellation, CancellationRequested, defer_cancellation')
            code = code.replace('with Cancellation(sys.stdin.fileno()):', 'with Cancellation(sys.stdin.fileno()) as controller:')
            code = code.replace('try: time.sleep(15)', 'try:\n            with defer_cancellation(): time.sleep(.6)\n            if controller.requested: controller.raise_cancelled()')
        process = subprocess.Popen([sys.executable, '-c', code], stdin=subprocess.PIPE,
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            self.assertEqual(process.stdout.readline().strip(), b'READY')
            output, error = process.communicate(command, timeout=4)
            self.assertEqual(process.returncode, 0, error)
            self.assertIn(b'CLEANUP', output)
            self.assertIn(b'CANCELLED', output)
        finally:
            if process.poll() is None:
                process.kill()
                process.wait()
            process.stdout.close()
            process.stderr.close()

    def test_helper_reads_secret_and_queued_cancel_without_waiting_for_pipe_eof(self):
        code = '''
import sys,time
from unittest.mock import patch
import helper
from distroclone_usb.cancellation import defer_cancellation
sys.argv=['helper.py','--iso','/unused.iso','--device','/dev/unused',
          '--persistence-mib','512','--expected-id','test','--confirm','unused',
          '--sha256','0'*64,'--encrypt-mode','all','--control-stdin']
def fake_create(*args):
    assert args[-1]=='Abcd1234Efgh'
    print('READY',flush=True)
    with defer_cancellation(): time.sleep(.6)
    print('CLEANUP',flush=True)
with patch('helper.os.geteuid',return_value=0),patch('helper.create_usb',side_effect=fake_create):
    sys.exit(helper.main())
'''
        process = subprocess.Popen([sys.executable,'-c',code],stdin=subprocess.PIPE,
                                   stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        try:
            process.stdin.write(b'{"password":"Abcd1234Efgh"}\ncancel\n')
            process.stdin.flush()
            self.assertEqual(process.stdout.readline().strip(),b'READY')
            self.assertEqual(process.stdout.readline().strip(),b'CLEANUP')
            self.assertIn(b'"event": "cancelled"',process.stdout.readline())
            self.assertEqual(process.wait(timeout=3),2)
        finally:
            if process.poll() is None:
                process.kill()
                process.wait()
            process.stdin.close()
            process.stdout.close()
            process.stderr.close()
