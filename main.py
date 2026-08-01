import os
import sys
import threading
import time
import signal
import ctypes
import asyncio as _asyncio
import traceback

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt, QTimer

from pet.server import start_fastapi_server
from pet.pet_window import PetWindow, register_send_command_threadsafe, register_request_hit_test
from pet.tray import SystemTray
from pet.server import ws_manager
from pet.pet_api import request_hit_test
from pet.signals import emitter as _signals_emitter
import pet.server as _pet_server_module
import pet.utils as _pet_utils

register_request_hit_test(request_hit_test)
register_send_command_threadsafe(ws_manager.broadcast_threadsafe)

os.environ["QT_ENABLE_HIGHDPI_SCALING"] = "0"
os.environ["QT_QPA_PLATFORM"] = "windows:dpiawareness=3"
# ctypes.windll.user32.SetProcessDPIAware()


def _ensure_queue_bridge_ready(timeout_s: float = 8.0, _started_at: list[float] | None = None):
    from PyQt6.QtCore import QTimer as _QTimer

    if _started_at is None:
        _started_at = [time.monotonic()]
    started_at = _started_at[0]

    q = getattr(_pet_server_module, "head_pat_queue", None)
    if q is not None and isinstance(q, _asyncio.Queue):
        def _on_pet_head_patted():
            try:
                _pet_server_module.head_pat_queue.put_nowait(True)
            except Exception:
                pass

        try:
            _signals_emitter.pet_head_patted.disconnect(_on_pet_head_patted)
        except Exception:
            pass
        _signals_emitter.pet_head_patted.connect(_on_pet_head_patted)
        return

    if time.monotonic() - started_at > timeout_s:
        return
    _QTimer.singleShot(25, lambda: _ensure_queue_bridge_ready(
        timeout_s=timeout_s, _started_at=_started_at
    ))


def main():
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    api_thread = threading.Thread(target=start_fastapi_server, daemon=True)
    api_thread.start()

    pet = PetWindow()
    pet.show()

    tray = SystemTray(pet)
    tray.show()

    app.aboutToQuit.connect(tray.cleanup)
    app.aboutToQuit.connect(pet.cleanup)

    QTimer.singleShot(0, lambda: _ensure_queue_bridge_ready())

    def request_quit(signum, frame):
        QTimer.singleShot(0, app.quit)

    signal.signal(signal.SIGINT, request_quit)

    if sys.platform == "win32" and hasattr(signal, "SIGBREAK"):
        signal.signal(signal.SIGBREAK, request_quit)

    heartbeat = QTimer()
    heartbeat.timeout.connect(lambda: None)
    heartbeat.start(100)

    try:
        code = app.exec()
    except KeyboardInterrupt:
        code = 0
    finally:
        pet.cleanup()

    sys.exit(code)


if __name__ == "__main__":
    main()
