"""One Speak per user: a QLockFile plus a local server, so a second launch shows the running window and exits."""
import hashlib
import sys

from PySide6.QtCore import QLockFile
from PySide6.QtNetwork import QLocalServer, QLocalSocket

from .. import config


INSTANCE_NAME = "speak-" + hashlib.sha1(str(config.APP_DIR).encode()).hexdigest()[:12]  # per user


def claim(wait_ms: int):
    """Return (lock, server) if this is the only Speak, else None after asking the running one to show itself.

    Two instances would both hear the shortcut and paste every dictation twice.
    """
    config.APP_DIR.mkdir(parents=True, exist_ok=True)
    lock = QLockFile(str(config.APP_DIR / "speak.lock"))
    lock.setStaleLockTime(0)  # never by age; a crashed owner's lock is still detected (dead PID) and taken over
    if not lock.tryLock(wait_ms):
        if "--background" not in sys.argv:
            socket = QLocalSocket()
            socket.connectToServer(INSTANCE_NAME)
            if socket.waitForConnected(1000):
                socket.write(b"show")
                socket.waitForBytesWritten(1000)
                socket.disconnectFromServer()
        return None
    QLocalServer.removeServer(INSTANCE_NAME)
    server = QLocalServer()
    server.listen(INSTANCE_NAME)
    return lock, server
