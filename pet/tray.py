import os
import socket
import subprocess
import sys
import time

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QAction, QIcon
from PyQt6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QMenu,
    QSizePolicy,
    QSystemTrayIcon,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import (
    BoolValidator,
    ColorConfigItem,
    ConfigItem,
    CustomColorSettingCard,
    Dialog,
    EnumSerializer,
    ExpandLayout,
    LineEdit,
    OptionsConfigItem,
    OptionsSettingCard,
    OptionsValidator,
    PasswordLineEdit,
    PrimaryPushButton,
    QConfig,
    ScrollArea,
    SettingCard,
    SettingCardGroup,
    SpinBox,
    SwitchButton,
    Theme,
    PushButton,
    qconfig,
    setTheme,
    setThemeColor,
)
from qfluentwidgets import (
    FluentIcon as FIF,
    SplitFluentWindow,
    SubtitleLabel,
    setFont,
)
import darkdetect

from pet.utils import loadConfig, saveConfig
from pet.windows_utils import get_windows_theme_color


class ThemeConfig(QConfig):
    themeMode = OptionsConfigItem(
        "ui", "theme", Theme.AUTO,
        OptionsValidator(Theme), EnumSerializer(Theme),
        restart=False,
    )
    themeColor = ColorConfigItem(
        "QFluentWidgets", "ThemeColor", get_windows_theme_color(hex=True)[0:7])


_theme_cfg_path = os.path.abspath(
    os.path.join(os.path.dirname(__file__), os.pardir, "./configs/theme.json")
)
themeCfg = ThemeConfig()
themeCfg.themeMode.value = Theme.AUTO
try:
    qconfig.load(_theme_cfg_path, themeCfg)
except Exception:
    pass


class LineEditSettingCard(SettingCard):
    """ Setting card with a LineEdit on the right """

    def __init__(self, icon, title, content=None, value="", parent=None):
        super().__init__(icon, title, content, parent)
        self.lineEdit = LineEdit(self)
        self.lineEdit.setText(str(value))
        self.lineEdit.setFixedWidth(320)
        self.hBoxLayout.addWidget(
            self.lineEdit, 0, Qt.AlignmentFlag.AlignRight)
        self.hBoxLayout.addSpacing(16)

    def value(self) -> str:
        return self.lineEdit.text().strip()

    def setValue(self, value: str):
        self.lineEdit.setText(str(value))


class PasswordLineEditSettingCard(SettingCard):

    def __init__(self, icon, title, content=None, value="", parent=None):
        super().__init__(icon, title, content, parent)
        self.lineEdit = PasswordLineEdit(self)
        self.lineEdit.setText(str(value))
        self.lineEdit.setFixedWidth(320)
        self.lineEdit.setEchoMode(LineEdit.EchoMode.Password)
        self.hBoxLayout.addWidget(
            self.lineEdit, 0, Qt.AlignmentFlag.AlignRight)
        self.hBoxLayout.addSpacing(16)

    def value(self) -> str:
        return self.lineEdit.text().strip()

    def setValue(self, value: str):
        self.lineEdit.setText(str(value))


class SpinBoxSettingCard(SettingCard):

    def __init__(self, icon, title, content=None, value=0,
                 range=(1, 65535), parent=None):
        super().__init__(icon, title, content, parent)
        self.spinBox = SpinBox(self)
        self.spinBox.setRange(*range)
        self.spinBox.setValue(int(value))
        self.spinBox.setFixedWidth(160)
        self.hBoxLayout.addWidget(self.spinBox, 0, Qt.AlignmentFlag.AlignRight)
        self.hBoxLayout.addSpacing(16)

    def value(self) -> int:
        return self.spinBox.value()

    def setValue(self, value: int):
        self.spinBox.setValue(int(value))


class SwitchSettingCard(SettingCard):

    def __init__(self, icon, title, content=None, value=False, parent=None):
        super().__init__(icon, title, content, parent)
        self.switchButton = SwitchButton(self)
        self.switchButton.setChecked(bool(value))
        self.switchButton.setOnText("开")
        self.switchButton.setOffText("关")
        self.hBoxLayout.addWidget(
            self.switchButton, 0, Qt.AlignmentFlag.AlignRight)
        self.hBoxLayout.addSpacing(16)

    def value(self) -> bool:
        return self.switchButton.isChecked()

    def setValue(self, value: bool):
        self.switchButton.setChecked(bool(value))


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
        self.setStyleSheet("#settingsInterface { background: transparent; }")

        self.scrollWidget = QWidget()
        self.expandLayout = ExpandLayout(self.scrollWidget)

        # 标题
        self.settingLabel = SubtitleLabel("AI 桌宠设置", self.scrollWidget)
        setFont(self.settingLabel, 24)

        self.config = loadConfig()
        llm_cfg = self.config["llm"]
        tts_cfg = self.config.setdefault("tts", {})
        server_cfg = self.config["petServer"]

        # --- UI 外观组 ---
        self.uiGroup = SettingCardGroup("UI 外观", self.scrollWidget)

        self.themeCard = OptionsSettingCard(
            themeCfg.themeMode,
            FIF.BRUSH,
            "主题",
            "改变应用的整体外观（浅色 / 深色 / 跟随系统）",
            texts=["浅色", "深色", "跟随系统"],
            parent=self.uiGroup,
        )
        self.themeCard.optionChanged.connect(
            lambda ci: setTheme(ci.value)
        )

        self.themeColorCard = CustomColorSettingCard(
            themeCfg.themeColor,
            FIF.PALETTE,
            "主题色",
            "改变应用的主题强调色",
            parent=self.uiGroup,
        )
        self.themeColorCard.colorChanged.connect(setThemeColor)

        self.uiGroup.addSettingCard(self.themeCard)
        self.uiGroup.addSettingCard(self.themeColorCard)

        # --- LLM 配置组 ---
        self.llmGroup = SettingCardGroup("LLM 配置", self.scrollWidget)

        self.llmEnabledCard = SwitchSettingCard(
            FIF.EDIT,
            "启用 LLM",
            "是否启用大模型对话与智能功能",
            value=bool(llm_cfg.get("enabled", False)),
            parent=self.llmGroup,
        )
        self.talkFrequencyCard = LineEditSettingCard(
            FIF.SPEED_HIGH,
            "对话频率",
            "桌宠的说话频率（low / normal / high）",
            value=llm_cfg.get("talk_frequency", "normal"),
            parent=self.llmGroup,
        )
        self.endpointCard = LineEditSettingCard(
            FIF.CLOUD,
            "API 请求端点",
            value=llm_cfg.get("endpoint", ""),
            parent=self.llmGroup,
        )
        self.apiKeyCard = PasswordLineEditSettingCard(
            FIF.VPN,
            "API Key",
            "用于认证的 API Key",
            value=llm_cfg.get("api_key", ""),
            parent=self.llmGroup,
        )
        self.modelCard = LineEditSettingCard(
            FIF.LIBRARY,
            "模型",
            "对话使用的模型名称",
            value=llm_cfg.get("model", ""),
            parent=self.llmGroup,
        )
        self.reasoningEffortCard = LineEditSettingCard(
            FIF.SPEED_HIGH,
            "推理程度",
            "推理程度（none / minimal / low / medium / high）",
            value=llm_cfg.get("reasoning_effort", "none"),
            parent=self.llmGroup,
        )
        self.embeddingModelCard = LineEditSettingCard(
            FIF.FOLDER,
            "向量化模型",
            "向量化模型路径或名称（用于 Embedding API 服务加载）",
            value=llm_cfg.get("embedding_model", ""),
            parent=self.llmGroup,
        )
        self.embeddingEndpointCard = LineEditSettingCard(
            FIF.CLOUD,
            "向量化模型 API 端点",
            "如 http://127.0.0.1:8002/v1/embeddings",
            value=llm_cfg.get("embedding_model_endpoint", ""),
            parent=self.llmGroup,
        )
        self.embeddingApiKeyCard = PasswordLineEditSettingCard(
            FIF.VPN,
            "Embedding API Key",
            "调用 Embedding API 时使用的认证密钥（可留空）",
            value=llm_cfg.get("embedding_model_key", ""),
            parent=self.llmGroup,
        )

        self.llmGroup.addSettingCard(self.llmEnabledCard)
        self.llmGroup.addSettingCard(self.talkFrequencyCard)
        self.llmGroup.addSettingCard(self.endpointCard)
        self.llmGroup.addSettingCard(self.apiKeyCard)
        self.llmGroup.addSettingCard(self.modelCard)
        self.llmGroup.addSettingCard(self.reasoningEffortCard)
        self.llmGroup.addSettingCard(self.embeddingModelCard)
        self.llmGroup.addSettingCard(self.embeddingEndpointCard)
        self.llmGroup.addSettingCard(self.embeddingApiKeyCard)

        self.serverGroup = SettingCardGroup("PetServer 配置", self.scrollWidget)

        self.hostCard = LineEditSettingCard(
            FIF.IOT,
            "桌宠服务地址",
            "本地 PetServer 监听地址",
            value=server_cfg.get("host", "127.0.0.1"),
            parent=self.serverGroup,
        )
        self.portCard = SpinBoxSettingCard(
            FIF.RINGER,
            "服务端口",
            "本地 PetServer 监听端口",
            value=int(server_cfg.get("port", 8001)),
            range=(1, 65535),
            parent=self.serverGroup,
        )

        self.serverGroup.addSettingCard(self.hostCard)
        self.serverGroup.addSettingCard(self.portCard)

        # --- TTS 配置组 ---
        self.ttsGroup = SettingCardGroup("TTS 语音配置", self.scrollWidget)

        self.ttsEnabledCard = SwitchSettingCard(
            FIF.VOLUME,
            "启用 TTS",
            "是否启用文本转语音播报功能",
            value=bool(tts_cfg.get("enabled", True)),
            parent=self.ttsGroup,
        )
        self.ttsEndpointCard = LineEditSettingCard(
            FIF.CLOUD,
            "TTS 服务端点",
            "TTS HTTP 服务地址，如 http://127.0.0.1:8003",
            value=tts_cfg.get("endpoint", "http://127.0.0.1:8003"),
            parent=self.ttsGroup,
        )
        self.ttsHostCard = LineEditSettingCard(
            FIF.IOT,
            "TTS 监听地址",
            "本地 TTS 服务绑定地址",
            value=tts_cfg.get("host", "127.0.0.1"),
            parent=self.ttsGroup,
        )
        self.ttsPortCard = SpinBoxSettingCard(
            FIF.RINGER,
            "TTS 服务端口",
            "本地 TTS 服务监听端口",
            value=int(tts_cfg.get("port", 8003)),
            range=(1, 65535),
            parent=self.ttsGroup,
        )
        self.ttsLanguageCard = LineEditSettingCard(
            FIF.LANGUAGE,
            "语言",
            "合成语言（如 zh / jp）",
            value=tts_cfg.get("language", "zh"),
            parent=self.ttsGroup,
        )
        self.ttsGenieDirCard = LineEditSettingCard(
            FIF.FOLDER,
            "Genie 数据目录",
            "GenieData 资源目录路径",
            value=tts_cfg.get("genie_data_dir", "./data/GenieData"),
            parent=self.ttsGroup,
        )
        self.ttsOnnxDirCard = LineEditSettingCard(
            FIF.FOLDER,
            "ONNX 模型目录",
            "ONNX 模型资源目录路径",
            value=tts_cfg.get("onnx_model_dir", "./data/onnx_mika"),
            parent=self.ttsGroup,
        )

        self.ttsGroup.addSettingCard(self.ttsEnabledCard)
        self.ttsGroup.addSettingCard(self.ttsEndpointCard)
        self.ttsGroup.addSettingCard(self.ttsHostCard)
        self.ttsGroup.addSettingCard(self.ttsPortCard)
        self.ttsGroup.addSettingCard(self.ttsLanguageCard)
        self.ttsGroup.addSettingCard(self.ttsGenieDirCard)
        self.ttsGroup.addSettingCard(self.ttsOnnxDirCard)

        innerScroll = ScrollArea(self)
        innerScroll.setWidget(self.scrollWidget)
        innerScroll.setWidgetResizable(True)
        innerScroll.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        self.scrollWidget.setObjectName("scrollWidget")
        innerScroll.setStyleSheet("""
            QScrollArea, #scrollWidget {
                background-color: transparent;
                border: none;
            }
        """)

        self.topMask = QWidget(self)
        self.topMask.setObjectName("topMask")
        self.topMask.setAttribute(
            Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.topMask.setStyleSheet("""
            #topMask {
                background-color: transparent;
            }
        """)
        self.topMask.raise_()

        def _update_mask_color():
            if themeCfg.themeMode.value == Theme.DARK:
                self.topMask.setStyleSheet(
                    "#topMask { background-color: #202020; }")
            elif themeCfg.themeMode.value == Theme.LIGHT:
                self.topMask.setStyleSheet(
                    "#topMask { background-color: #fafafa; }")
            else:
                self.topMask.setStyleSheet(
                    "#topMask { background-color: palette(window); }")
        _update_mask_color()
        themeCfg.themeMode.valueChanged.connect(
            lambda ci: _update_mask_color())

        self.saveButton = PrimaryPushButton("保存配置", self)
        self.saveButton.setFixedHeight(40)
        self.saveButton.setFixedWidth(180)
        self.saveButton.clicked.connect(self.save_config)

        footer = QWidget(self)
        footer.setMinimumHeight(72)
        footer.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        footerLayout = QHBoxLayout(footer)
        footerLayout.setContentsMargins(36, 16, 36, 20)
        footerLayout.addStretch(1)
        footerLayout.addWidget(self.saveButton)
        footer.setStyleSheet("background: transparent;")

        outerLayout = QVBoxLayout(self)
        outerLayout.setContentsMargins(0, 0, 0, 0)
        outerLayout.setSpacing(0)
        outerLayout.addWidget(innerScroll, 1)
        outerLayout.addWidget(footer, 0)

        self.expandLayout.setSpacing(28)
        self.expandLayout.setContentsMargins(36, 48, 36, 32)
        self.expandLayout.addWidget(self.settingLabel)
        self.expandLayout.addWidget(self.uiGroup)
        self.expandLayout.addWidget(self.llmGroup)
        self.expandLayout.addWidget(self.ttsGroup)
        self.expandLayout.addWidget(self.serverGroup)

    def _update_top_mask_geometry(self):
        title_bar_height = 40
        self.topMask.setGeometry(0, 0, self.width(), title_bar_height)
        self.topMask.raise_()

    def resizeEvent(self, a0):
        super().resizeEvent(a0)
        self._update_top_mask_geometry()

    def showEvent(self, a0):
        super().showEvent(a0)
        self._update_top_mask_geometry()

    def _show_dialog(self, title: str, content: str):
        w = Dialog(title, content, self)
        try:
            yes_btn = w.yesButton
            cancel_btn = w.cancelButton
            if isinstance(yes_btn, (PrimaryPushButton, PushButton)):
                yes_btn.setText("确定")
            if cancel_btn is not None:
                cancel_btn.hide()
        except Exception:
            pass
        w.exec()

    def save_config(self):
        endpoint = self.endpointCard.value()
        api_key = self.apiKeyCard.value()
        model = self.modelCard.value()
        embedding_model = self.embeddingModelCard.value()
        embedding_endpoint = self.embeddingEndpointCard.value()
        embedding_api_key = self.embeddingApiKeyCard.value()
        enabled = self.llmEnabledCard.value()
        host = self.hostCard.value()
        port = self.portCard.value()

        tts_enabled = self.ttsEnabledCard.value()
        tts_endpoint = self.ttsEndpointCard.value()
        tts_host = self.ttsHostCard.value()
        tts_port = self.ttsPortCard.value()
        tts_language = self.ttsLanguageCard.value()
        tts_genie_dir = self.ttsGenieDirCard.value()
        tts_onnx_dir = self.ttsOnnxDirCard.value()

        if enabled:
            if not all([endpoint, api_key, model, embedding_model, embedding_endpoint]):
                self._show_dialog(
                    "保存失败",
                    "启用 LLM 后，请先填写完整的 LLM 配置（包括 Embedding Endpoint）。",
                )
                return
        if not host:
            self._show_dialog(
                "保存失败",
                "PetServer 的 host 不能为空。",
            )
            return
        if tts_enabled and not tts_endpoint:
            self._show_dialog(
                "保存失败",
                "启用 TTS 后，请先填写 TTS 服务端点。",
            )
            return

        self.config["llm"].update(
            {
                "endpoint": endpoint,
                "api_key": api_key,
                "model": model,
                "embedding_model": embedding_model,
                "embedding_model_endpoint": embedding_endpoint,
                "embedding_model_key": embedding_api_key,
                "enabled": enabled,
            }
        )
        self.config["petServer"].update({"host": host, "port": port})
        self.config.setdefault("tts", {}).update(
            {
                "enabled": tts_enabled,
                "endpoint": tts_endpoint,
                "host": tts_host,
                "port": tts_port,
                "language": tts_language,
                "genie_data_dir": tts_genie_dir,
                "onnx_model_dir": tts_onnx_dir,
            }
        )

        saveConfig(self.config)

        try:
            qconfig.save()
        except Exception:
            pass

        self._show_dialog(
            "保存成功",
            "配置已保存，请重启程序后生效。",
        )


class SettingsWindow(SplitFluentWindow):
    _TARGET_W = 900
    _TARGET_H = 700

    def __init__(self):
        super().__init__()
        setTheme(themeCfg.themeMode.value)
        setThemeColor(themeCfg.themeColor.value)

        self.setMinimumSize(self._TARGET_W, self._TARGET_H)
        self.resize(self._TARGET_W, self._TARGET_H)

        self.settingsInterface = SettingsWidget(self)
        self.initNavigation()
        self.initWindow()

    def initNavigation(self):
        self.addSubInterface(self.settingsInterface, FIF.SETTING, "设置")

    def initWindow(self):
        self.setWindowTitle("桌宠设置")
        self.setWindowIcon(QIcon(
            './front/icon_light' if themeCfg.themeMode.value == Theme.LIGHT else './front/icon_dark'))
        self._center_window()

    def _center_window(self):
        screen = self.screen() or QApplication.screens()[0]
        desktop = screen.availableGeometry()
        w, h = desktop.width(), desktop.height()
        self.move(w // 2 - self.width() // 2, h // 2 - self.height() // 2)

    def showEvent(self, event):  # type: ignore
        setTheme(themeCfg.themeMode.value)
        setThemeColor(themeCfg.themeColor.value)

        super().showEvent(event)
        current = self.size()
        if current.width() != self._TARGET_W or current.height() != self._TARGET_H:
            self.resize(self._TARGET_W, self._TARGET_H)
        self._center_window()


class SystemTray(QSystemTrayIcon):
    def __init__(self, pet_window, parent=None):
        super().__init__(parent)
        self.pet_window = pet_window

        self.setIcon(QIcon('./front/icon_light' if themeCfg.themeMode.value ==
                     Theme.LIGHT else './front/icon_dark'))
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
