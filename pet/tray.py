import os
import socket
import subprocess
import sys
import time

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QAction, QIcon
from PyQt6.QtWidgets import (
    QApplication,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QMenu,
    QMessageBox,
    QSystemTrayIcon,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import LineEdit, SpinBox, PrimaryPushButton
from qfluentwidgets import (
    FluentIcon as FIF,
    SplitFluentWindow,
    SubtitleLabel,
    setFont,
)

from pet.utils import loadConfig, saveConfig


def _find_free_tcp_port() -> int:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return int(port)


def _send_tcp_cmd(port: int, cmd: str, timeout: float = 1.5) -> str | None:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=timeout) as s:
            s.sendall((cmd.strip() + "\n").encode("utf-8"))
            s.shutdown(socket.SHUT_WR)
            data = b""
            try:
                s.settimeout(timeout)
                while True:
                    chunk = s.recv(512)
                    if not chunk:
                        break
                    data += chunk
            except socket.timeout:
                pass
            if not data:
                return ""
            return data.decode("utf-8", errors="ignore").strip()
    except OSError:
        return None


class SettingsWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self.setObjectName("settingsInterface")
        self.vBoxLayout = QVBoxLayout(self)
        self.vBoxLayout.setContentsMargins(20, 48, 20, 20)
        self.vBoxLayout.setSpacing(16)

        label = SubtitleLabel("AI 桌宠设置")
        setFont(label, 24)
        self.vBoxLayout.addWidget(label)

        self.config = loadConfig()

        self.llmGroup = QGroupBox("LLM 配置")
        llmLayout = QFormLayout(self.llmGroup)
        llmLayout.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self.endpointEdit = LineEdit()
        self.endpointEdit.setText(self.config["llm"]["endpoint"])
        self.apiKeyEdit = LineEdit()
        self.apiKeyEdit.setText(self.config["llm"]["api_key"])
        self.modelEdit = LineEdit()
        self.modelEdit.setText(self.config["llm"]["model"])
        self.embeddingModelEdit = LineEdit()
        self.embeddingModelEdit.setText(self.config["llm"]["embedding_model"])

        llmLayout.addRow("endpoint", self.endpointEdit)
        llmLayout.addRow("api_key", self.apiKeyEdit)
        llmLayout.addRow("model", self.modelEdit)
        llmLayout.addRow("embedding_model", self.embeddingModelEdit)

        self.serverGroup = QGroupBox("PetServer 配置")
        serverLayout = QFormLayout(self.serverGroup)
        serverLayout.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self.hostEdit = LineEdit()
        self.hostEdit.setText(self.config["petServer"]["host"])
        self.portEdit = SpinBox()
        self.portEdit.setRange(1, 65535)
        self.portEdit.setValue(int(self.config["petServer"]["port"]))

        serverLayout.addRow("host", self.hostEdit)
        serverLayout.addRow("port", self.portEdit)

        self.saveButton = PrimaryPushButton("保存配置")
        self.saveButton.clicked.connect(self.save_config)

        self.vBoxLayout.addWidget(self.llmGroup)
        self.vBoxLayout.addWidget(self.serverGroup)
        self.vBoxLayout.addStretch(1)

        buttonRow = QHBoxLayout()
        buttonRow.addStretch(1)
        buttonRow.addWidget(self.saveButton)
        self.vBoxLayout.addLayout(buttonRow)

    def save_config(self):
        endpoint = self.endpointEdit.text().strip()
        api_key = self.apiKeyEdit.text().strip()
        model = self.modelEdit.text().strip()
        embedding_model = self.embeddingModelEdit.text().strip()
        host = self.hostEdit.text().strip()
        port = self.portEdit.value()

        if not all([endpoint, api_key, model, embedding_model, host]):
            QMessageBox.warning(self, "保存失败", "请先填写完整的 LLM 和 petServer 配置。")
            return

        self.config["llm"].update(
            {
                "endpoint": endpoint,
                "api_key": api_key,
                "model": model,
                "embedding_model": embedding_model,
            }
        )
        self.config["petServer"].update({"host": host, "port": port})

        saveConfig(self.config)
        QMessageBox.information(self, "保存成功", "配置已保存，请重启程序后生效。")


class SettingsWindow(SplitFluentWindow):
    def __init__(self):
        super().__init__()
        self.settingsInterface = SettingsWidget(self)
        self.initNavigation()
        self.initWindow()

    def initNavigation(self):
        self.addSubInterface(self.settingsInterface, FIF.SETTING, "设置")

    def initWindow(self):
        self.resize(800, 600)
        self.setWindowTitle("桌宠设置")
        self.setWindowIcon(QIcon('./front/icon.png'))
        desktop = QApplication.screens()[0].availableGeometry()
        w, h = desktop.width(), desktop.height()
        self.move(w // 2 - self.width() // 2, h // 2 - self.height() // 2)


class SystemTray(QSystemTrayIcon):
    def __init__(self, pet_window, parent=None):
        super().__init__(parent)
        self.pet_window = pet_window

        self.setIcon(QIcon("./front/icon.png"))
        self.setToolTip("AI 桌宠")

        menu = QMenu()
        show_action = QAction("显示/隐藏桌宠", self)
        show_action.triggered.connect(self.toggle_pet)

        settings_action = QAction("打开设置", self)
        settings_action.triggered.connect(self.show_settings)

        quit_action = QAction("退出", self)
        quit_action.triggered.connect(self._quit_all)

        menu.addAction(show_action)
        menu.addAction(settings_action)
        menu.addSeparator()
        menu.addAction(quit_action)

        self.setContextMenu(menu)
        self.activated.connect(self.on_tray_activated)

        self._settings_process: subprocess.Popen | None = None
        self._settings_cmd_port: int | None = None
        self._prelaunch_settings_process()

    def _prelaunch_settings_process(self):
        self._settings_cmd_port = _find_free_tcp_port()
        project_root = os.path.dirname(
            os.path.dirname(os.path.abspath(__file__)))

        self._settings_process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "pet.settings_app",
                f"--port={self._settings_cmd_port}",
            ],
            cwd=project_root,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline:
            if self._settings_process.poll() is not None:
                self._settings_process = None
                break
            if _send_tcp_cmd(self._settings_cmd_port, "PING", timeout=0.3) == "PONG":
                break
            time.sleep(0.05)

    def _ensure_settings_alive(self) -> bool:
        alive = (
            self._settings_process is not None
            and self._settings_process.poll() is None
        )
        port_ready = (
            self._settings_cmd_port is not None
            and _send_tcp_cmd(self._settings_cmd_port, "PING", timeout=0.5) == "PONG"
        )
        if alive and port_ready:
            return True

        if self._settings_process is not None:
            try:
                self._settings_process.kill()
            except OSError:
                pass
            self._settings_process = None

        self._prelaunch_settings_process()

        if self._settings_process is None or self._settings_cmd_port is None:
            return False
        return (
            _send_tcp_cmd(self._settings_cmd_port,
                          "PING", timeout=1.0) == "PONG"
        )

    def toggle_pet(self):
        if self.pet_window.isVisible():
            self.pet_window.hide()
        else:
            self.pet_window.show()

    def show_settings(self):
        if not self._ensure_settings_alive():
            project_root = os.path.dirname(
                os.path.dirname(os.path.abspath(__file__)))
            self._settings_cmd_port = _find_free_tcp_port()
            self._settings_process = subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "pet.settings_app",
                    f"--port={self._settings_cmd_port}",
                ],
                cwd=project_root,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            return

        assert self._settings_cmd_port is not None
        _send_tcp_cmd(self._settings_cmd_port, "SHOW", timeout=1.0)

    def _quit_settings(self):
        if self._settings_cmd_port is not None:
            _send_tcp_cmd(self._settings_cmd_port, "QUIT", timeout=0.4)

        proc = self._settings_process
        if proc is None:
            return

        deadline = time.monotonic() + 1.0
        while time.monotonic() < deadline and proc.poll() is None:
            time.sleep(0.05)

        if proc.poll() is None:
            try:
                proc.kill()
            except OSError:
                pass
        self._settings_process = None

    def _quit_all(self):
        self._quit_settings()
        QApplication.quit()

    def on_tray_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self.toggle_pet()

    def cleanup(self):
        self._quit_settings()
