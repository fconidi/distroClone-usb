#!/usr/bin/python3 -I
"""Fixed polkit entry point; ignore Python environment and user site packages."""

import argparse
import json
import os
from pathlib import Path
import signal
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from distroclone_usb.writer import create_usb
from distroclone_usb.i18n import LANGUAGES, set_language, tr


def emit(event, **data):
    print(json.dumps({'event': event, **data}), flush=True)


def main():
    parser = argparse.ArgumentParser(description='distroClone USB privileged writer')
    parser.add_argument('--iso', required=True)
    parser.add_argument('--device', required=True)
    parser.add_argument('--persistence-mib', type=int, required=True)
    parser.add_argument('--expected-id', required=True)
    parser.add_argument('--confirm', required=True)
    parser.add_argument('--sha256', required=True)
    parser.add_argument('--language', choices=LANGUAGES, default='en')
    args = parser.parse_args()
    set_language(args.language)
    # Permit cleanup on terminal termination; SIGKILL/power loss cannot be handled.
    def stop(signum, frame):
        raise InterruptedError(tr('Operation interrupted. The USB may be incomplete.'))
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    try:
        uid = int(os.environ.get('PKEXEC_UID', os.environ.get('SUDO_UID', os.getuid())))
        create_usb(args.iso, args.device, args.persistence_mib, args.expected_id,
                   args.confirm, args.sha256, uid, emit)
    except Exception as error:
        emit('error', message=str(error))
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
