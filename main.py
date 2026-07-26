import os
import sys
import threading
import time
import signal
import ctypes

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt, QTimer

from pet.server import start_fastapi_server
from pet.pet_window import PetWindow, register_send_command_threadsafe, register_request_hit_test
from pet.tray import SystemTray
from pet.server import ws_manager
from pet.pet_api import request_hit_test

register_request_hit_test(request_hit_test)
register_send_command_threadsafe(ws_manager.broadcast_threadsafe)

os.environ["QT_ENABLE_HIGHDPI_SCALING"] = "0"
ctypes.windll.user32.SetProcessDPIAware()


def main():
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    app = QApplication(sys.argv)

    api_thread = threading.Thread(target=start_fastapi_server, daemon=True)
    api_thread.start()

    pet = PetWindow()
    pet.show()

    tray = SystemTray(pet)
    tray.show()

    app.aboutToQuit.connect(pet.cleanup)

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
