"""Start the fixed polkit writer without exposing the phrase in argv or env."""

import json
import subprocess

HELPER = '/usr/lib/distroclone-usb/helper.py'


def start_writer(arguments, password=None):
    process = subprocess.Popen(
        ['/usr/bin/pkexec', '--disable-internal-agent', HELPER, *arguments],
        stdin=subprocess.PIPE if password is not None else subprocess.DEVNULL,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding='utf-8')
    try:
        if password is not None:
            process.stdin.write(json.dumps({'password': password}, ensure_ascii=False) + '\n')
            process.stdin.close()
    except BaseException:
        if process.stdin and not process.stdin.closed:
            try:
                process.stdin.close()
            except BrokenPipeError:
                pass
        process.wait()
        raise
    return process
