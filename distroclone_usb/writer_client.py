"""Start the fixed polkit writer without exposing the phrase in argv or env."""

import json
import signal
import subprocess

HELPER = '/usr/lib/distroclone-usb/helper.py'


def start_writer(arguments, password=None):
    process = subprocess.Popen(
        ['/usr/bin/pkexec', '--disable-internal-agent', HELPER, '--control-stdin', *arguments],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding='utf-8')
    try:
        if password is not None:
            process.stdin.write(json.dumps({'password': password}, ensure_ascii=False) + '\n')
            process.stdin.flush()
    except BaseException:
        if process.stdin and not process.stdin.closed:
            try:
                process.stdin.close()
            except BrokenPipeError:
                pass
        process.wait()
        raise
    return process


def request_cancel(process):
    if process.poll() is not None:
        return False
    try:
        process.stdin.write('cancel\n')
        process.stdin.flush()
    except (BrokenPipeError, ValueError):
        return False
    try:
        # Before authentication pkexec is still owned by the desktop user.
        # After authentication the privileged helper reads the control pipe.
        process.send_signal(signal.SIGTERM)
    except (PermissionError, ProcessLookupError):
        pass
    return True
