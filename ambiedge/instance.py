"""Keeps two copies of the app from fighting over the same lights."""

import os
import sys


class InstanceLock:
    def __init__(self, path):
        self.path = path
        self._file = None

    def acquire(self):
        os.makedirs(os.path.dirname(os.path.abspath(self.path)), exist_ok=True)
        f = open(self.path, "a+")
        try:
            if sys.platform == "win32":
                import msvcrt
                f.seek(0)
                msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            f.close()
            return False
        self._file = f
        return True

    def release(self):
        if self._file is not None:
            self._file.close()  # closing the file releases the lock
            self._file = None
