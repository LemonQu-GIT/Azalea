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

        # qfluentwidgets LineEdit does not accept initial text as argument.
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
        quit_action.triggered.connect(QApplication.quit)

        menu.addAction(show_action)
        menu.addAction(settings_action)
        menu.addSeparator()
        menu.addAction(quit_action)

        self.setContextMenu(menu)
        self.activated.connect(self.on_tray_activated)
        self.settings_win = None

    def toggle_pet(self):
        if self.pet_window.isVisible():
            self.pet_window.hide()
        else:
            self.pet_window.show()

    def show_settings(self):
        if not self.settings_win:
            self.settings_win = SettingsWindow()
        self.settings_win.show()
        self.settings_win.raise_()
        self.settings_win.activateWindow()

    def on_tray_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self.toggle_pet()
