"""Single-threaded cancellation of our own helper through its private stdin pipe."""

from contextlib import contextmanager
import os
import select
import signal

from .i18n import tr


_active = None


@contextmanager
def defer_cancellation():
    controller = _active
    if controller is not None:
        controller.deferred += 1
    try:
        yield
    finally:
        if controller is not None:
            controller.deferred -= 1


class CancellationRequested(Exception):
    """Distinct from InterruptedError, which selectors treats as retryable EINTR."""


class Cancellation:
    def __init__(self, fd):
        self.fd = fd
        self.requested = False
        self.buffer = bytearray()
        self.active = False
        self.deferred = 0

    def __enter__(self):
        global _active
        _active = self
        self.handlers = {sig: signal.getsignal(sig) for sig in
                         (signal.SIGALRM, signal.SIGTERM, signal.SIGINT)}
        self.previous_timer = signal.getitimer(signal.ITIMER_REAL)
        signal.signal(signal.SIGALRM, self.poll)
        signal.signal(signal.SIGTERM, self.cancel)
        signal.signal(signal.SIGINT, self.cancel)
        self.active = True
        signal.setitimer(signal.ITIMER_REAL, .2, .2)
        return self

    def disable_timer(self):
        if self.active:
            signal.setitimer(signal.ITIMER_REAL, 0)
            self.active = False

    def cancel(self, *args):
        if self.requested:
            return
        self.requested = True
        self.disable_timer()
        if not self.deferred:
            self.raise_cancelled()

    def raise_cancelled(self):
        raise CancellationRequested(tr('Operation interrupted. The USB may be incomplete.'))

    def poll(self, *args):
        if not select.select([self.fd], [], [], 0)[0]:
            return
        data = os.read(self.fd, 64)
        if not data:
            self.cancel()
        self.buffer.extend(data)
        if b'\n' in self.buffer or len(self.buffer) >= 64:
            # This channel can only stop this process, never address another PID.
            self.cancel()

    def __exit__(self, *args):
        global _active
        _active = None
        self.disable_timer()
        for sig, handler in self.handlers.items():
            signal.signal(sig, handler)
        signal.setitimer(signal.ITIMER_REAL, *self.previous_timer)
