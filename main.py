import os
import sys
import threading
import time
import signal
import ctypes
import asyncio as _asyncio
import traceback

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt, QTimer, QUrl
from PyQt6.QtMultimedia import QSoundEffect

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
if sys.platform == "win32":
    os.environ["QT_QPA_PLATFORM"] = "windows:dpiawareness=3"
    # ctypes.windll.user32.SetProcessDPIAware()
elif sys.platform.startswith("linux") and not os.environ.get("QT_QPA_PLATFORM"):
    # 桌宠依赖绝对窗口定位（物理、拖拽、贴边），Wayland 原生协议不允许客户端
    # 自行定位窗口，因此在 Linux 上默认走 X11/XWayland
    os.environ["QT_QPA_PLATFORM"] = "xcb"


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

    _tts_sound_entries: list[tuple[QSoundEffect, str]] = []

    def _play_tts_sound(wav_path: str):
        import os
        import shutil
        import time
        import uuid

        abs_path = os.path.abspath(wav_path)
        if not os.path.isfile(abs_path):
            _pet_utils.log(f"TTS 音频文件不存在: {abs_path}", "ERROR")
            return

        data_dir = os.path.join(os.path.dirname(abs_path), "tts_cache")
        os.makedirs(data_dir, exist_ok=True)
        stamp = time.strftime("%Y%m%d_%H%M%S")
        unique = uuid.uuid4().hex[:8]
        temp_wav = os.path.join(data_dir, f"tts_{stamp}_{unique}.wav")
        try:
            shutil.copy2(abs_path, temp_wav)
        except Exception as exc:
            _pet_utils.log(f"TTS 临时音频复制失败: {exc}", "ERROR")
            return

        effect = QSoundEffect()
        effect.setSource(QUrl.fromLocalFile(temp_wav))
        effect.setVolume(1.0)
        _tts_sound_entries.append((effect, temp_wav))

        def _on_playing_changed():
            if not effect.isPlaying():
                try:
                    _tts_sound_entries.remove((effect, temp_wav))
                except ValueError:
                    pass
                try:
                    if os.path.isfile(temp_wav):
                        os.remove(temp_wav)
                except Exception:
                    pass

        effect.playingChanged.connect(_on_playing_changed)
        effect.play()

    try:
        _signals_emitter.play_tts_requested.disconnect(_play_tts_sound)
    except Exception:
        pass
    _signals_emitter.play_tts_requested.connect(_play_tts_sound)

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
